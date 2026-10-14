"""Copy folders into a mirror with full paths redacted, so no host path reaches zjm's index or OpenRouter.

    python3 mirror.py SOURCE_ROOT MIRROR_DIR [RELATIVE_PATH ...]   (default: the whole SOURCE_ROOT)

In a git checkout only the files git shows are copied (tracked, or new and not ignored), as zjm itself would.
Text files up to 1 MiB are copied with /home/<user>/, /Users/<user>/ and /root/ replaced by ~/ and any /tmp/ path
by <temp>; larger files, binary files and files that are not UTF-8 are skipped with a warning.
"""
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+/|/root/")
TEMP = re.compile(r"/tmp/[^\s\"'`)\]>]*")
# zjm's exclude floor (zjm_rag/copying.py): never read or copied, matched without case
FLOOR_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".zvec-grep", ".zjm", ".ssh", ".gnupg", ".aws", ".kube", ".docker"}
FLOOR_FILES = {".env*", "*.pem", "*.key", "*.p12", "*.pfx", "*.kdbx", "id_rsa*", "id_dsa*", "id_ecdsa*",
               "id_ed25519*", ".npmrc", ".pypirc", ".netrc", ".git-credentials", "credentials*", ".git"}  # a worktree's .git is a file
MAX_BYTES = 1 << 20


def redact(text: str) -> str:
    return TEMP.sub("<temp>", HOME.sub("~/", text))


def warn(msg: str) -> None:
    print(msg, file=sys.stderr)


def refuse(msg: str) -> None:
    warn(msg)
    sys.exit(2)


def inside(root: Path, f: str) -> Path:
    """The real path of a configured entry; refuses anything that could leave the project."""
    p = Path(f)
    if p.is_absolute() or ".." in p.parts:
        refuse(f"{f} must be a path inside the project, without ..")
    here = root
    for part in p.parts:  # a symlink anywhere on the way would index its target instead
        here = here / part
        if here.is_symlink():
            refuse(f"{here} is a symlink: index the real path")
    real = (root / p).resolve()
    if real != root and root not in real.parents:
        refuse(f"{f} is outside the project")
    return real


def floor_check(path: Path) -> None:
    if any(part.lower() in FLOOR_DIRS for part in path.parts):
        refuse(f"{path} is inside a folder zjm never indexes")


def in_git(root: Path) -> bool:
    return any((d / ".git").exists() for d in (root, *root.parents))


def candidates(root: Path, rels: list[str]) -> list[Path]:
    if in_git(root):  # a git failure stops the run; it never falls back to copying ignored files
        out = subprocess.run(["git", "--literal-pathspecs", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                              "--", *rels], capture_output=True, check=True).stdout
        return [root / n for n in out.decode().split("\0") if n and (root / n).is_file()]
    found = []
    for rel in rels:
        src = root / rel
        if src.is_file():
            found.append(src)
        for here, dirs, files in os.walk(src):  # prune floor folders, never descend into them
            dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(d.lower(), f) for f in FLOOR_DIRS)]
            found += [p for p in (Path(here) / f for f in files) if p.is_file()]
    return found


def copy(src: Path, dst: Path) -> None:
    if src.stat().st_size > MAX_BYTES:
        return warn(f"skipped {src.name}: larger than 1 MiB")
    with src.open("rb") as f:
        data = f.read(MAX_BYTES + 1)  # a file that grew since the check is still cut off
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return warn(f"skipped {src.name}: not UTF-8 text")
    if len(data) > MAX_BYTES or "\0" in text:
        return warn(f"skipped {src.name}: too large or binary")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(redact(text), encoding="utf-8")


def excluded(rel: Path, patterns: list[str]) -> bool:
    """zjm's exclude rule: a name pattern matches a file's name, a pattern ending in / a folder's; no case."""
    for pat in patterns:
        is_dir = pat.endswith("/")
        names = rel.parts[:-1] if is_dir else rel.parts[-1:]
        if any(fnmatch.fnmatch(n.lower(), (pat[:-1] if is_dir else pat).lower()) for n in names):
            return True
    return False


def allowed(root: Path, p: Path) -> bool:
    """No symlink anywhere between root and the file, and nothing on zjm's floor."""
    rel = p.relative_to(root)
    if any((root / part).is_symlink() for part in (*reversed(rel.parents[:-1]), rel)):
        return False
    if any(fnmatch.fnmatch(d.lower(), f) for d in rel.parts[:-1] for f in FLOOR_DIRS):
        return False
    return not any(fnmatch.fnmatch(rel.name.lower(), f) for f in FLOOR_FILES)


def make(root: Path, mirror: Path, rels: list[str] | None = None, exclude: list[str] = ()) -> None:
    root = root.resolve()
    mirror.mkdir(parents=True, exist_ok=True)  # an empty folder still mounts
    for p in candidates(root, rels or ["."]):
        if allowed(root, p) and not excluded(p.relative_to(root), exclude):
            copy(p, mirror / p.relative_to(root))
    for here, dirs, files in os.walk(mirror):  # readable by the container's own user, whatever the umask or source mode
        os.chmod(here, 0o755)
        for f in files:
            os.chmod(os.path.join(here, f), 0o644)


def main() -> None:
    make(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:])


if __name__ == "__main__":
    assert redact("/home/someone/projects/x and /tmp/claude-1000/abc/def ok") == "~/projects/x and <temp> ok"
    assert redact("see /tmp/deliverables-registry-repair/report.txt and /tmp/graph-run/a.") == "see <temp> and <temp>"
    assert redact("/Users/bb/x /root/y") == "~/x ~/y"
    main()
