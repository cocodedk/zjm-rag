"""file_add, file_put, file_remove, file_list: files inside a locker (specs 06 and 08)."""
import hashlib
import os
import shutil
import time
from pathlib import Path

from . import config as config_module
from . import lockers
from . import sealed
from . import zg
from .copying import _floor_excluded, _gitignored, check_source_allowed, copy_tree
from .errors import ZjmError

MAX_PUT_BYTES = 1 << 20


def _entry(source, path):
    data = path.read_bytes()
    return {"source": source, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "added": time.time()}


def _check_put_name(name, cfg):
    if not name or os.path.isabs(name) or "\\" in name:
        raise ZjmError(f"bad file name: {name!r}")
    segs = name.split("/")
    for i, seg in enumerate(segs):
        if seg in ("", ".", ".."):
            raise ZjmError(f"bad file name: {name!r}")
        if _floor_excluded(seg, i < len(segs) - 1, cfg["exclude"]):
            raise ZjmError(f"bad file name: {name!r}")


def _prune(manifest, name):
    for k in [k for k in manifest["files"] if k == name or k.startswith(name + "/")]:
        del manifest["files"][k]


def _add_files(ldir, manifest, reals, cfg, runner):
    corpus = ldir / "corpus"
    added, replaced, excluded = [], [], 0
    for real in reals:
        name = os.path.basename(real.rstrip(os.sep))
        dest = corpus / name
        existed = dest.exists()
        _prune(manifest, name)
        if os.path.isdir(real):
            if existed:
                shutil.rmtree(dest)
            dest.mkdir(parents=True)
            _, n_excl = copy_tree(real, str(dest), cfg, runner)
            excluded += n_excl
            for root, _dirs, fnames in os.walk(dest):
                for fname in fnames:
                    full = Path(root) / fname
                    rel = full.relative_to(corpus).as_posix()
                    src_rel = full.relative_to(dest).as_posix()
                    manifest["files"][rel] = _entry(str(Path(real) / src_rel), full)
        else:
            parent, base = os.path.dirname(real), os.path.basename(real)
            if _floor_excluded(base, False, cfg["exclude"]):
                excluded += 1
                continue
            if base in _gitignored(parent, [base], runner):
                continue
            if existed:
                dest.unlink()
            shutil.copy2(real, dest)
            manifest["files"][name] = _entry(real, dest)
        (replaced if existed else added).append(name)
    lockers.run_index(ldir, manifest, runner)
    return {"added": added, "replaced": replaced, "excluded": excluded}


def file_add(locker, paths, key=None, *, config=None, runner=zg.run, jev=None):
    cfg = config_module.resolve(config)
    reals = [check_source_allowed(p, cfg) for p in paths]
    with sealed.open_locker(cfg, locker, key, write=True, runner=runner) as ldir:
        manifest = lockers.read_manifest(ldir)
        return _add_files(ldir, manifest, reals, cfg, runner)


def file_put(locker, name, text, key=None, *, config=None, runner=zg.run, jev=None):
    cfg = config_module.resolve(config)
    data = text.encode("utf-8")
    if len(data) > MAX_PUT_BYTES:
        raise ZjmError(f"text for {name!r} exceeds 1 MiB")
    _check_put_name(name, cfg)
    with sealed.open_locker(cfg, locker, key, write=True, runner=runner) as ldir:
        manifest = lockers.read_manifest(ldir)
        dest = ldir / "corpus" / name
        existed = name in manifest["files"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        manifest["files"][name] = {"source": None, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                   "added": time.time()}
        lockers.run_index(ldir, manifest, runner)
    return {"added": [] if existed else [name], "replaced": [name] if existed else []}


def file_remove(locker, names, key=None, *, config=None, runner=zg.run, jev=None):
    cfg = config_module.resolve(config)
    with sealed.open_locker(cfg, locker, key, write=True, runner=runner) as ldir:
        manifest = lockers.read_manifest(ldir)
        matches, missing = {}, []
        for name in names:
            hit = [k for k in manifest["files"] if k == name or k.startswith(name + "/")]
            if hit:
                matches[name] = hit
            else:
                missing.append(name)
        if missing:
            raise ZjmError(f"no such file(s) in locker {locker}: {', '.join(missing)}")
        corpus = ldir / "corpus"
        removed = []
        for name, ks in matches.items():
            for k in ks:
                path = corpus / k
                if path.exists():
                    path.unlink()
                del manifest["files"][k]
            removed.append(name)
        lockers.run_index(ldir, manifest, runner)
    return {"removed": removed}


def file_list(locker, key=None, *, config=None, runner=None, jev=None):
    cfg = config_module.resolve(config)
    with sealed.open_locker(cfg, locker, key, write=False, runner=runner or zg.run) as ldir:
        manifest = lockers.read_manifest(ldir)
    files = [{"name": k, "source": v["source"], "size": v["size"], "sha256": v["sha256"], "added": v["added"]}
             for k, v in manifest["files"].items()]
    files.sort(key=lambda f: f["name"])
    return {"files": files}
