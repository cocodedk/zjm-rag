"""file_put_many: many texts written and files removed in one locker session, with one index run (spec 21),
and the name rules and removal it shares with file_put and file_remove."""
import hashlib
import os
import time
from collections import Counter

from . import config as config_module
from . import engine, lockers, sealed
from .copying import _floor_excluded
from .errors import ZjmError

MAX_PUT_BYTES = 1 << 20


def _check_put_name(name, cfg):
    if not name or os.path.isabs(name) or "\\" in name:
        raise ZjmError(f"bad file name: {name!r}")
    segs = name.split("/")
    for i, seg in enumerate(segs):
        if seg in ("", ".", "..") or _floor_excluded(seg, i < len(segs) - 1, cfg["exclude"]):
            raise ZjmError(f"bad file name: {name!r}")


def _parents(name):
    segs = name.split("/")
    return ["/".join(segs[:i]) for i in range(1, len(segs))]


def _matching(manifest, name):
    return [k for k in manifest["files"] if k == name or k.startswith(name + "/")]


def _delete(ldir, manifest, keys):
    """Delete these locker paths and their manifest entries, then any folder they leave empty."""
    corpus = ldir / "corpus"
    for k in sorted(keys):
        path = corpus / k
        if path.exists():
            path.unlink()
        del manifest["files"][k]
        for parent in path.parents:
            if parent == corpus or not parent.is_dir() or any(parent.iterdir()):
                break
            parent.rmdir()


def _check_batch(files, remove, cfg):
    """The refusals that need no locker, in spec 21's order."""
    if not files and not remove:
        raise ZjmError("nothing to put or remove")
    for f in files:
        if not isinstance(f, dict) or set(f) != {"name", "text"} or not all(isinstance(v, str) for v in f.values()):
            raise ZjmError("each file must be an object with exactly a string name and a string text")
    names = [f["name"] for f in files]
    twice = [n for n, count in Counter(names).items() if count > 1]
    if twice:
        raise ZjmError(f"{twice[0]!r} is given twice in this call")
    for f in files:
        if len(f["text"].encode("utf-8")) > MAX_PUT_BYTES:
            raise ZjmError(f"text for {f['name']!r} exceeds 1 MiB")
    for name in names:
        _check_put_name(name, cfg)
    given = set(names)
    for name in names:
        if any(p in given for p in _parents(name)):
            raise ZjmError(f"{name!r} clashes with another file in this call")


def _clashes(corpus, name, gone):
    """Whether `name` would be a folder, or lie under a file, on disk once `gone` is deleted as _delete
    deletes it: a folder survives unless every entry in it is a deleted file (an empty subfolder stays)."""
    if any((corpus / p).exists() and not (corpus / p).is_dir() and p not in gone for p in _parents(name)):
        return True
    dest = corpus / name
    if not dest.is_dir():
        return False
    entries = list(dest.rglob("*"))
    files = [p for p in entries if not p.is_dir()]
    return not files or any(p.relative_to(corpus).as_posix() not in gone for p in files) or \
        any(p.is_dir() and not any(p.iterdir()) for p in entries)


def file_put_many(locker, files=(), key=None, *, remove=(), config=None, runner=engine.run, jev=None):
    """Remove, then write many texts, in one session with one index run (spec 21)."""
    cfg = config_module.resolve(config)
    _check_batch(files, remove, cfg)
    with sealed.open_locker(cfg, locker, key, write=True, runner=runner) as ldir:
        manifest = lockers.read_manifest(ldir)
        matches = {name: hit for name in remove if (hit := _matching(manifest, name))}
        gone = {k for ks in matches.values() for k in ks}
        for name in (f["name"] for f in files):
            if _clashes(ldir / "corpus", name, gone):
                raise ZjmError(f"{name!r} clashes with a file or folder already in locker {locker}")
        kept = set(manifest["files"]) - gone
        _delete(ldir, manifest, gone)
        added, replaced = [], []
        for f in files:
            data = f["text"].encode("utf-8")
            dest = ldir / "corpus" / f["name"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            manifest["files"][f["name"]] = {"source": None, "size": len(data),
                                            "sha256": hashlib.sha256(data).hexdigest(), "added": time.time()}
            (replaced if f["name"] in kept else added).append(f["name"])
        if files or gone:
            lockers.run_index(ldir, manifest, runner)
    return {"added": added, "replaced": replaced, "removed": list(matches)}
