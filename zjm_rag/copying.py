"""Safety-checked copying: allow/deny, the exclude floor, symlinks and gitignore (spec 05)."""
import fnmatch
import os
import shutil

from .errors import ZjmError

FLOOR_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".zvec-grep", ".zjm", ".ssh", ".gnupg", ".aws",
              ".kube", ".docker"}
FLOOR_FILES = {".env*", "*.pem", "*.key", "*.p12", "*.pfx", "*.kdbx", "id_rsa*", "id_dsa*", "id_ecdsa*",
               "id_ed25519*", ".npmrc", ".pypirc", ".netrc", ".git-credentials", "credentials*"}


def is_inside(path, parent):
    """Whole-path-component containment: /a/bc is not inside /a/b."""
    path, parent = os.path.normpath(path), os.path.normpath(parent)
    return path == parent or path.startswith(parent + os.sep)


def _denied(path, deny, home):
    return any(is_inside(path, d) for d in deny) or is_inside(path, home)


def check_source_allowed(source, config):
    """Raise ZjmError unless `source` may be read; else the resolved real path."""
    p = os.path.abspath(str(source))
    if _denied(p, config["deny"], config["home"]):
        raise ZjmError(f"{source} is denied by {config['path']}")
    r = os.path.realpath(p)
    if _denied(r, config["deny"], config["home"]) or is_inside(r, os.path.realpath(config["home"])):
        raise ZjmError(f"{source} is denied by {config['path']}")
    for entry in config["allow"]:
        if is_inside(r, os.path.realpath(entry)):
            return r
    raise ZjmError(f'{source} is outside the allowed paths in {config["path"]}; add it to "allow"')


def _floor_excluded(name, is_dir, extra):
    lname = name.lower()
    patterns = FLOOR_DIRS if is_dir else FLOOR_FILES
    if any(fnmatch.fnmatch(lname, pat) for pat in patterns):
        return True
    for pat in extra:
        want_dir = pat.endswith("/")
        if want_dir != is_dir:
            continue
        if fnmatch.fnmatch(lname, (pat[:-1] if want_dir else pat).lower()):
            return True
    return False


def _walk(src, dest, config, files, count_excluded):
    with os.scandir(src) as it:
        entries = sorted(it, key=lambda e: e.name)
    for entry in entries:
        p = os.path.abspath(entry.path)
        if _denied(p, config["deny"], config["home"]) or entry.is_symlink():
            count_excluded[0] += 1
            continue
        if entry.is_dir(follow_symlinks=False):
            if _floor_excluded(entry.name, True, config["exclude"]):
                count_excluded[0] += 1
                continue
            os.makedirs(os.path.join(dest, entry.name), exist_ok=True)
            _walk(entry.path, os.path.join(dest, entry.name), config, files, count_excluded)
        elif entry.is_file(follow_symlinks=False):
            if _floor_excluded(entry.name, False, config["exclude"]):
                count_excluded[0] += 1
                continue
            rel = os.path.relpath(entry.path, src)
            files.append((rel, entry.path, os.path.join(dest, entry.name)))
        else:
            count_excluded[0] += 1


def _has_git_ancestor(path):
    cur = path
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            return False
        cur = parent


def _gitignored(src, rel_paths, runner):
    if not rel_paths:
        return set()
    data = "".join(p + "\0" for p in rel_paths)
    code, out, err = runner(["git", "-C", src, "check-ignore", "-z", "--stdin"], cwd=src, env=os.environ, input=data)
    if code in (0, 1):
        return {p for p in out.split("\0") if p}
    if _has_git_ancestor(src):
        raise ZjmError(f"git check-ignore failed: {err.strip()}")
    return set()


def copy_tree(src_real, dest, config, runner):
    """Copy `src_real` into `dest`; returns (files_copied, excluded_entries)."""
    files, count_excluded = [], [0]
    _walk(src_real, dest, config, files, count_excluded)
    ignored = _gitignored(src_real, [rel for rel, _, _ in files], runner)
    copied = 0
    for rel, srcp, destp in files:
        if rel in ignored:
            continue
        shutil.copy2(srcp, destp)
        copied += 1
    return copied, count_excluded[0]
