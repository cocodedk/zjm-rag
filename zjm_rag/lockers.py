"""Named lockers: layout, manifest, locking, create/list/drop (spec 06)."""
import fcntl
import json
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path

from . import config as config_module
from . import zg
from .errors import ZjmError

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MULTILINGUAL_MODEL = "local/potion-multilingual-128m"


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


def locker_dir(cfg, name):
    check_name(name)
    _, lockers_dir = home_dirs(cfg)
    return lockers_dir / name


def manifest_path(ldir):
    return ldir / "locker.json"


def read_manifest(ldir):
    return json.loads(manifest_path(ldir).read_text())


def write_manifest(ldir, manifest):
    tmp = ldir / f".locker.json.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(manifest))
    os.replace(tmp, manifest_path(ldir))


def require_locker(cfg, name):
    """The locker's directory, or raise ZjmError if it does not exist."""
    ldir = locker_dir(cfg, name)
    if not manifest_path(ldir).exists():
        raise ZjmError(f"no locker {name}")
    return ldir


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


def locker_create(name, multilingual=False, embedding=None, *, config=None, runner=None, jev=None):
    check_name(name)
    cfg = config_module.resolve(config)
    model = embedding or (MULTILINGUAL_MODEL if multilingual else cfg["embedding"])
    if not model.startswith("local/"):
        raise ZjmError(f"embedding {model!r} is not local; a remote model would send file contents out")
    with lock(cfg, exclusive=True) as lockers_dir:
        ldir = lockers_dir / name
        if manifest_path(ldir).exists():
            raise ZjmError(f"locker {name} already exists")
        _check_dir_safe(ldir)
        ldir.mkdir(mode=0o700, exist_ok=True)
        (ldir / "corpus").mkdir(mode=0o700, exist_ok=True)
        (ldir / "zghome").mkdir(mode=0o700, exist_ok=True)
        write_manifest(ldir, {"name": name, "embedding": model, "indexed": True, "files": {}})
    return {"name": name, "embedding": model}


def locker_list(*, config=None, runner=None, jev=None):
    cfg = config_module.resolve(config)
    with lock(cfg, exclusive=False) as lockers_dir:
        names = sorted(p.name for p in lockers_dir.iterdir()) if lockers_dir.is_dir() else []
        out = []
        for name in names:
            ldir = lockers_dir / name
            if not manifest_path(ldir).exists():
                continue
            manifest = read_manifest(ldir)
            out.append({"name": name, "embedding": manifest["embedding"], "files": len(manifest["files"]),
                       "bytes": sum(v["size"] for v in manifest["files"].values())})
    return {"lockers": out}


def locker_drop(name, *, config=None, runner=None, jev=None):
    cfg = config_module.resolve(config)
    with lock(cfg, exclusive=True):
        ldir = require_locker(cfg, name)
        manifest = read_manifest(ldir)
        count = len(manifest["files"])
        shutil.rmtree(ldir)
    return {"name": name, "files": count}
