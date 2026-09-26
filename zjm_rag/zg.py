"""zg argv, the default process runner, and the parser for zg's query output."""
import re
import subprocess

ZG_HITS = 40
HIT_RE = re.compile(r"^#(\d+) matchedBy=\S+ (.+?):(\d+)(?:-(\d+))?$")


def run(argv, *, cwd, env, input=None):
    """Default runner: (returncode, stdout, stderr); a missing binary is exit 127. `input` as
    bytes selects binary mode (used for age), text or None selects text mode (zg, git)."""
    binary = isinstance(input, bytes)
    try:
        p = subprocess.run(argv, cwd=cwd, env=env, input=input, text=not binary, capture_output=True)
    except OSError as e:
        return 127, (b"" if binary else ""), (str(e).encode() if binary else str(e))
    return p.returncode, p.stdout, p.stderr


def index_argv(embedding, rebuild=False):
    argv = ["zg", "index", ".", "--embedding", embedding, "--mode", "direct", "--hidden"]
    return argv + ["--rebuild"] if rebuild else argv


def query_argv(query, file_types=None):
    argv = ["zg", "query", query, "--preview", "none", "--limit", str(ZG_HITS), "--mode", "direct"]
    for t in file_types or []:
        argv += ["-t", t]
    return argv


def parse(out):
    """zg query output -> every hit, in zg order, as {"path", "start", "end", "rank"}. Only header
    lines matter; everything else (heading/scope/source lines) is ignored."""
    hits = []
    for line in out.split("\n"):
        m = HIT_RE.match(line)
        if not m:
            continue
        rank, path, start, end = m.groups()
        start = int(start)
        hits.append({"path": path, "start": start, "end": int(end) if end else start, "rank": int(rank)})
    return hits
