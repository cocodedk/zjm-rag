"""zg argv, the default process runner, and the parser for zg's query output."""
import re
import subprocess

ZG_HITS = 40
HIT_RE = re.compile(r"^#(\d+) (.+?):(\d+)(?:-(\d+))?$")
INCOMPATIBLE = "incompatible with the current version of zg"


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
    argv = ["zg", "--index", ".", "--embedding", embedding, "--mode", "direct", "--hidden"]
    return argv + ["--rebuild"] if rebuild else argv


def query_argv(query, file_types=None):
    """Options first, `-t` per type, then `--` and the query last, so a question such as
    `--help` is searched, not obeyed (spec 10)."""
    argv = ["zg", "--preview", "none", "--limit", str(ZG_HITS), "--mode", "direct"]
    for t in file_types or []:
        argv += ["-t", t]
    return argv + ["--", query]


def query_argv_translations(translations, file_types=None):
    """One `--hybrid=<t>` argv element per translation, so it can never be read as an option;
    `--fuse` only when there is more than one (spec 10)."""
    argv = ["zg"] + [f"--hybrid={t}" for t in translations]
    if len(translations) > 1:
        argv.append("--fuse")
    argv += ["--preview", "none", "--limit", str(ZG_HITS), "--mode", "direct"]
    for t in file_types or []:
        argv += ["-t", t]
    return argv


def incompatible(stderr):
    """True when zg refused an index that an older zg built; `--index --rebuild` repairs it."""
    return INCOMPATIBLE in stderr


def parse(out):
    """zg query output -> every hit, in zg order, as {"path", "start", "end", "rank"}. Only header
    lines matter; everything else (heading/scope/symbol lines) is ignored."""
    hits = []
    for line in out.split("\n"):
        m = HIT_RE.match(line)
        if not m:
            continue
        rank, path, start, end = m.groups()
        start = int(start)
        hits.append({"path": path, "start": start, "end": int(end) if end else start, "rank": int(rank)})
    return hits
