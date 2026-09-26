"""Named lockers: layout, manifest, locking, create/list/drop/encrypt (specs 06 and 08)."""
import fcntl
import json
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path

from . import config as config_module
from . import keys as keys_mod
from . import sealed
from . import zg
from .errors import ZjmError

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MULTILINGUAL_MODEL = config_module.MULTILINGUAL_EMBEDDING


def check_name(name):
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ZjmError(f"bad locker name: {name!r}")


def _check_dir_safe(path):
    if path.is_symlink():
        raise ZjmError(f"refusing to write through a symlink: {path}")
    if path.exists() and hasattr(os, "getuid") and path.stat().st_uid != os.getuid():
        raise ZjmError(f"{path} is owned by another user")


def home_dirs(cfg):
    home = Path(cfg["home"])
    return home, home / "lockers"


@contextmanager
def lock(cfg, *, exclusive):
    home, lockers_dir = home_dirs(cfg)
    _check_dir_safe(home)
    home.mkdir(mode=0o700, exist_ok=True)
    _check_dir_safe(lockers_dir)
    lockers_dir.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(home / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield lockers_dir
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def manifest_path(ldir):
    return ldir / "locker.json"


def read_manifest(ldir):
    return json.loads(manifest_path(ldir).read_text())


def write_manifest(ldir, manifest):
    tmp = ldir / f".locker.json.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(manifest))
    os.replace(tmp, manifest_path(ldir))


def zg_env(ldir):
    return {**os.environ, "ZVEC_GREP_HOME": str(ldir / "zghome")}


def run_index(ldir, manifest, runner):
    """Reindex a locker's corpus; keeps files copied even when zg fails (indexed stays False)."""
    manifest["indexed"] = False
    write_manifest(ldir, manifest)
    code, _, err = runner(zg.index_argv(manifest["embedding"]), cwd=str(ldir / "corpus"),
                          env=zg_env(ldir), input=None)
    if code != 0:
        raise ZjmError(f"zg index failed: {err.strip()}")
    manifest["indexed"] = True
    write_manifest(ldir, manifest)


def locker_dir(cfg, name):
    """The plain locker's directory (tests use this to inspect a plain locker directly)."""
    _, lockers_dir = home_dirs(cfg)
    return lockers_dir / name


def _locations(cfg, name):
    _, lockers_dir = home_dirs(cfg)
    return lockers_dir / f"{name}.age", locker_dir(cfg, name)


def locker_create(name, key=None, multilingual=False, embedding=None, plain=False, *, config=None, runner=zg.run,
                  jev=None):
    check_name(name)
    if key is None and not plain:
        raise ZjmError(f"locker {name} needs a key; pass plain=true for an unencrypted locker")
    if key is not None and plain:
        raise ZjmError("a plain locker takes no key")
    cfg = config_module.resolve(config)
    model = embedding or (MULTILINGUAL_MODEL if multilingual else cfg["embedding"])
    if not model.startswith("local/"):
        raise ZjmError(f"embedding {model!r} is not local; a remote model would send file contents out")
    config_module.check_embedding_baked(model)
    with sealed.open_locker(cfg, name, key, write=True, runner=runner, create=True) as ldir:
        (ldir / "corpus").mkdir(mode=0o700, exist_ok=True)
        (ldir / "zghome").mkdir(mode=0o700, exist_ok=True)
        write_manifest(ldir, {"name": name, "embedding": model, "indexed": True, "files": {}})
    return {"name": name, "embedding": model}


def locker_list(*, config=None, runner=None, jev=None):
    cfg = config_module.resolve(config)
    with lock(cfg, exclusive=False) as lockers_dir:
        out = []
        if lockers_dir.is_dir():
            for p in sorted(lockers_dir.iterdir()):
                if p.is_file() and p.suffix == ".age":
                    out.append({"name": p.stem, "encrypted": True, "bytes": p.stat().st_size})
                elif p.is_dir() and (p / "locker.json").exists():
                    manifest = read_manifest(p)
                    out.append({"name": p.name, "encrypted": False, "files": len(manifest["files"]),
                               "bytes": sum(v["size"] for v in manifest["files"].values())})
    out.sort(key=lambda e: e["name"])
    return {"lockers": out}


def locker_drop(name, key=None, *, config=None, runner=zg.run, jev=None):
    check_name(name)
    cfg = config_module.resolve(config)
    age_path, plain_dir = _locations(cfg, name)
    with lock(cfg, exclusive=True):
        age_exists = age_path.exists()
        plain_exists = (plain_dir / "locker.json").exists()
        if not age_exists and not plain_exists:
            raise ZjmError(f"no locker {name}")
        if age_exists:
            if key is None:
                raise ZjmError(f"locker {name} needs its key")
            norm_key = keys_mod.check_key(key)
            session_dir, key_file = sealed.session_paths(name)
            sealed.reset(session_dir)
            try:
                sealed.write_key(key_file, norm_key)
                sealed.decrypt_into(age_path, key_file, session_dir, runner, name)
                count = len(read_manifest(session_dir)["files"])
            finally:
                sealed.cleanup(session_dir, key_file)
            age_path.unlink()
        else:
            if key is not None:
                raise ZjmError(f"locker {name} is not encrypted")
            count = len(read_manifest(plain_dir)["files"])
            shutil.rmtree(plain_dir)
    return {"name": name, "files": count}


def locker_encrypt(name, key, *, config=None, runner=zg.run, jev=None):
    """One-way: seal a plain locker's directory into `<name>.age`; there is no operation back."""
    check_name(name)
    cfg = config_module.resolve(config)
    norm_key = keys_mod.check_key(key)
    age_path, plain_dir = _locations(cfg, name)
    with lock(cfg, exclusive=True):
        if age_path.exists():
            raise ZjmError(f"locker {name} is already encrypted")
        if not (plain_dir / "locker.json").exists():
            raise ZjmError(f"no locker {name}")
        _check_dir_safe(plain_dir)
        tmp_path = age_path.with_name(age_path.name + ".tmp")
        _, key_file = sealed.session_paths(name)
        sealed.write_key(key_file, norm_key)
        verify_dir, _ = sealed.session_paths(f"{name}.verify")
        try:
            sealed.encrypt_to(plain_dir, tmp_path, key_file, runner, name)
            sealed.reset(verify_dir)
            try:
                sealed.decrypt_into(tmp_path, key_file, verify_dir, runner, name)
            finally:
                shutil.rmtree(verify_dir, ignore_errors=True)
            os.replace(tmp_path, age_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        finally:
            key_file.unlink(missing_ok=True)
        shutil.rmtree(plain_dir)
    return {"name": name}
