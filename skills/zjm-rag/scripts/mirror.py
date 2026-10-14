"""Copy folders into a mirror with full paths redacted, so no host path reaches zjm's index or OpenRouter.

    python3 mirror.py SOURCE_ROOT MIRROR_DIR [RELATIVE_PATH ...]   (default: the whole SOURCE_ROOT)

In a git checkout only the files git shows are copied (tracked, or new and not ignored), as zjm itself would.
Text files have /home/<user>/, /Users/<user>/ and /root/ replaced by ~/ and any /tmp/ path by <temp>; other files are copied as they are.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOME = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+/|/root/")
TEMP = re.compile(r"/tmp/[^\s\"'`)\]>]*")


def redact(text: str) -> str:
    return TEMP.sub("<temp>", HOME.sub("~/", text))


def in_git(root: Path) -> bool:
    return any((d / ".git").exists() for d in (root, *root.parents))


def candidates(root: Path, rels: list[str]) -> list[Path]:
    if in_git(root):  # a git failure stops the run; it never falls back to copying ignored files
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                              "--", *rels], capture_output=True, check=True).stdout
        return [root / n for n in out.decode().split("\0") if n and (root / n).is_file()]
    found = []
    for rel in rels:
        src = root / rel
        found += [src] if src.is_file() else [p for p in src.rglob("*") if p.is_file() and ".git" not in p.parts]
    return found


def copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        dst.write_text(redact(src.read_text(encoding="utf-8")), encoding="utf-8")
    except UnicodeDecodeError:
        shutil.copy2(src, dst)


def main() -> None:
    root, mirror, rels = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), sys.argv[3:] or ["."]
    mirror.mkdir(parents=True, exist_ok=True)  # an empty folder still mounts
    for p in candidates(root, rels):
        if not p.is_symlink():
            copy(p, mirror / p.relative_to(root))


if __name__ == "__main__":
    assert redact("/home/someone/projects/x and /tmp/claude-1000/abc/def ok") == "~/projects/x and <temp> ok"
    assert redact("see /tmp/deliverables-registry-repair/report.txt and /tmp/graph-run/a.") == "see <temp> and <temp>"
    assert redact("/Users/bb/x /root/y") == "~/x ~/y"
    main()
