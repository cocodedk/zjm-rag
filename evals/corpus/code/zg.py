"""zg argv, the default process runner, and the parser for zg's query output."""
import re
import subprocess

MAX_SNIPPETS, SNIPPET_CHARS = 2, 1500


def run(argv, *, cwd, env, input=None):
    """Default runner: (returncode, stdout, stderr); a missing binary is exit 127. `input` as
    bytes selects binary mode (used for age), text or None selects text mode (zg, git, the LLM)."""
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
    argv = ["zg", "query", query, "--preview", "short", "--limit", "40", "--mode", "direct"]
    for t in file_types or []:
        argv += ["-t", t]
    return argv


def parse(out, limit=8):
    """zg query output -> {path: [snippets]} in zg order, at most `limit` paths and 2 snippets each."""
    files = {}
    for hit in re.split(r"\n(?=#\d+ matchedBy=)", out)[1:]:
        path = re.match(r"#\d+ \S+ (.+):\d+-\d+$", hit.split("\n", 1)[0]).group(1)
        if path not in files and len(files) >= limit:
            continue
        snippets = files.setdefault(path, [])
        if len(snippets) < MAX_SNIPPETS:
            snippets.append(hit.split("source:\n", 1)[-1][:SNIPPET_CHARS])
    return files
