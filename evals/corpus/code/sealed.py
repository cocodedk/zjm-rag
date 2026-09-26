"""Sealed locker sessions: decrypt an encrypted locker into /tmp for the request, reseal after a
write, and never leave the key or the plaintext on disk (spec 08). A locker without a key is a
plain spec 06 directory and is handed back unchanged.
"""
import io
import os
import shutil
import stat
import tarfile
from contextlib import contextmanager
from pathlib import Path

from . import keys as keys_mod
from .errors import ZjmError

TMP_ROOT = Path("/tmp/zjm")


def _ensure_tmp_root():
    """TMP_ROOT must be our own, private directory, never a symlink another user could plant."""
    try:
        st = os.lstat(TMP_ROOT)
    except FileNotFoundError:
        TMP_ROOT.mkdir(mode=0o700)
        return
    if stat.S_ISLNK(st.st_mode):
        raise ZjmError(f"{TMP_ROOT} is a symlink")
    if st.st_uid != os.geteuid():
        raise ZjmError(f"{TMP_ROOT} is owned by another user")
    if st.st_mode & 0o077:
        raise ZjmError(f"{TMP_ROOT} must not be group- or other-accessible")


def session_paths(name):
    return TMP_ROOT / name, TMP_ROOT / f"{name}.key"


def locker_kind(cfg, name):
    """"age", "plain" or None (no locker by that name), without locking or touching a runner."""
    from . import lockers as lockers_mod

    _, lockers_dir = lockers_mod.home_dirs(cfg)
    if (lockers_dir / f"{name}.age").exists():
        return "age"
    if (lockers_dir / name / "locker.json").exists():
        return "plain"
    return None


def reset(session_dir):
    """Remove anything left from a crashed run, then recreate the directory at mode 0700."""
    _ensure_tmp_root()
    shutil.rmtree(session_dir, ignore_errors=True)
    session_dir.mkdir(mode=0o700)


def write_key(key_file, key):
    _ensure_tmp_root()
    key_file.unlink(missing_ok=True)
    fd = os.open(key_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.encode("utf-8"))


def cleanup(session_dir, key_file, age_path=None):
    key_file.unlink(missing_ok=True)
    shutil.rmtree(session_dir, ignore_errors=True)
    if age_path is not None:
        age_path.with_name(age_path.name + ".tmp").unlink(missing_ok=True)


def _safe_members(tf):
    members = tf.getmembers()
    for m in members:
        if not (m.isfile() or m.isdir()):
            raise ZjmError("locker archive contains an unsupported member")
        parts = Path(m.name).parts
        if m.name.startswith("/") or ".." in parts:
            raise ZjmError("locker archive contains an unsafe path")
    return members


def decrypt_into(age_path, key_file, session_dir, runner, name):
    code, out, _err = runner(["age", "-d", "-i", str(key_file), str(age_path)], cwd=str(session_dir),
                             env=dict(os.environ), input=b"")
    if code != 0:
        raise ZjmError(f"wrong key or damaged locker {name}")
    with tarfile.open(fileobj=io.BytesIO(out)) as tf:
        tf.extractall(session_dir, members=_safe_members(tf))


def tar_bytes(session_dir):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for child in sorted(session_dir.iterdir()):
            tf.add(child, arcname=child.name)
    return buf.getvalue()


def encrypt_to(session_dir, tmp_path, key_file, runner, name):
    """Tar `session_dir` and encrypt it to `tmp_path`; raises without touching anything else."""
    recipient = keys_mod.get_recipient(key_file, runner)
    data = tar_bytes(session_dir)
    code, _out, _err = runner(["age", "-r", recipient, "-o", str(tmp_path)], cwd=str(session_dir),
                              env=dict(os.environ), input=data)
    if code != 0 or not tmp_path.exists():
        tmp_path.unlink(missing_ok=True)
        raise ZjmError(f"failed to seal locker {name}")


def seal(session_dir, age_path, key_file, runner, name):
    tmp_path = age_path.with_name(age_path.name + ".tmp")
    encrypt_to(session_dir, tmp_path, key_file, runner, name)
    os.replace(tmp_path, age_path)


@contextmanager
def open_locker(cfg, name, key, *, write, runner, create=False):
    """The locker's directory (plain or a decrypted /tmp copy), or raise. Handles both the
    encrypted (`key` given) and plain (`key` is None) forms, and locker creation."""
    from . import lockers as lockers_mod

    lockers_mod.check_name(name)
    norm_key = keys_mod.check_key(key) if key is not None else None
    home, lockers_dir = lockers_mod.home_dirs(cfg)
    age_path = lockers_dir / f"{name}.age"
    plain_dir = lockers_dir / name

    with lockers_mod.lock(cfg, exclusive=True):
        age_exists = age_path.exists()
        plain_exists = (plain_dir / "locker.json").exists()
        if create:
            if age_exists or plain_exists:
                raise ZjmError(f"locker {name} already exists")
        else:
            if not age_exists and not plain_exists:
                raise ZjmError(f"no locker {name}")
            if age_exists and norm_key is None:
                raise ZjmError(f"locker {name} needs its key")
            if plain_exists and norm_key is not None:
                raise ZjmError(f"locker {name} is not encrypted")

        if age_exists or (create and norm_key is not None):
            session_dir, key_file = session_paths(name)
            reset(session_dir)
            try:
                write_key(key_file, norm_key)
                if not create:
                    decrypt_into(age_path, key_file, session_dir, runner, name)
                yield session_dir
                if write:
                    seal(session_dir, age_path, key_file, runner, name)
            finally:
                cleanup(session_dir, key_file, age_path)
        else:
            lockers_mod._check_dir_safe(plain_dir)
            if create:
                plain_dir.mkdir(mode=0o700, exist_ok=True)
            yield plain_dir
