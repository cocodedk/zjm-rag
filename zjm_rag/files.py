"""file_add, file_put, file_remove, file_list: files inside a locker (specs 06 and 08); file_put_many (spec 21,
in puts.py) is re-exported here, and file_put calls it."""
import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path

from . import config as config_module
from . import engine, lockers, sealed
from .copying import _floor_excluded, _gitignored, check_source_allowed, copy_tree
from .errors import ZjmError
from .puts import (  # noqa: F401  (MAX_PUT_BYTES: guide.py)
    MAX_PUT_BYTES,
    _delete,
    _matching,
    file_put_many,
)


def _entry(source, path):
    data = path.read_bytes()
    return {"source": source, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "added": time.time()}


def _prune(manifest, name):
    for k in _matching(manifest, name):
        del manifest["files"][k]


def _prepare_source(real, staged, cfg, runner):
    """Copy and describe one source before touching the live corpus."""
    name = os.path.basename(real.rstrip(os.sep))
    is_dir = os.path.isdir(real)
    if _floor_excluded(name, is_dir, cfg["exclude"]):
        return None, 1
    if name in _gitignored(os.path.dirname(real), [name], runner):
        return None, 0
    if is_dir:
        staged.mkdir()
        _, excluded = copy_tree(real, str(staged), cfg, runner)
        entries = {}
        for root, _dirs, fnames in os.walk(staged):
            for fname in fnames:
                full = Path(root) / fname
                rel = full.relative_to(staged).as_posix()
                entries[f"{name}/{rel}"] = _entry(str(Path(real) / rel), full)
        return entries, excluded
    shutil.copy2(real, staged)
    return {name: _entry(real, staged)}, 0


def _add_files(ldir, manifest, reals, cfg, runner):
    corpus = ldir / "corpus"
    added, replaced, excluded = [], [], 0
    with tempfile.TemporaryDirectory(prefix=".add-", dir=ldir) as tmp:
        pending, installed = [], []
        for i, real in enumerate(reals):
            staged = Path(tmp) / f"new-{i}"
            entries, skipped = _prepare_source(real, staged, cfg, runner)
            excluded += skipped
            if entries is not None:
                pending.append((os.path.basename(real.rstrip(os.sep)), staged, entries))
        try:
            for i, (name, staged, entries) in enumerate(pending):
                dest = corpus / name
                backup = Path(tmp) / f"old-{i}" if dest.exists() else None
                if backup is not None:
                    os.replace(dest, backup)
                installed.append((dest, backup))
                os.replace(staged, dest)
                _prune(manifest, name)
                manifest["files"].update(entries)
                (replaced if backup is not None else added).append(name)
        except OSError:
            for dest, backup in reversed(installed):
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink(missing_ok=True)
                if backup is not None:
                    os.replace(backup, dest)
            raise
        # As before, plain lockers keep copied files if indexing fails (indexed=False).
        lockers.run_index(ldir, manifest, runner)
    return {"added": added, "replaced": replaced, "excluded": excluded}


def file_add(locker, paths, key=None, *, config=None, runner=engine.run, jev=None):
    cfg = config_module.resolve(config)
    reals = [check_source_allowed(p, cfg) for p in paths]
    with sealed.open_locker(cfg, locker, key, write=True, runner=runner) as ldir:
        manifest = lockers.read_manifest(ldir)
        return _add_files(ldir, manifest, reals, cfg, runner)


def file_put(locker, name, text, key=None, *, config=None, runner=engine.run, jev=None):
    if not isinstance(name, str):
        raise ZjmError(f"bad file name: {name!r}")
    r = file_put_many(locker, [{"name": name, "text": text}], key, config=config, runner=runner, jev=jev)
    return {"added": r["added"], "replaced": r["replaced"]}


def file_remove(locker, names, key=None, *, config=None, runner=engine.run, jev=None):
    cfg = config_module.resolve(config)
    with sealed.open_locker(cfg, locker, key, write=True, runner=runner) as ldir:
        manifest = lockers.read_manifest(ldir)
        matches = {name: _matching(manifest, name) for name in names}
        missing = [name for name in names if not matches[name]]
        if missing:
            raise ZjmError(f"no such file(s) in locker {locker}: {', '.join(missing)}")
        _delete(ldir, manifest, {k for ks in matches.values() for k in ks})
        lockers.run_index(ldir, manifest, runner)
    return {"removed": list(matches)}


def file_list(locker, key=None, *, config=None, runner=None, jev=None):
    cfg = config_module.resolve(config)
    with sealed.open_locker(cfg, locker, key, write=False, runner=runner or engine.run) as ldir:
        manifest = lockers.read_manifest(ldir)
    files = [{"name": k, "source": v["source"], "size": v["size"], "sha256": v["sha256"], "added": v["added"]}
             for k, v in manifest["files"].items()]
    return {"files": sorted(files, key=lambda f: f["name"])}
