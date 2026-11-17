"""zg argv, the default process runner, and the parser for zg's query output."""
import os
import re
import subprocess
import threading

ZG_HITS = 40
RUN_TIMEOUT_S = 600
TIMEOUT_EXIT = 124
NOT_FOUND_EXIT = 127
DRAIN_CHUNK = 65536
CHILD_ENV_VARS = ("PATH", "HOME", "LANG", "LC_ALL", "ZVEC_GREP_MODEL_CACHE")
HIT_RE = re.compile(r"^#(\d+) (.+?):(\d+)(?:-(\d+))?$")
INCOMPATIBLE = "incompatible with the current version of zg"


def child_env(**extra):
    """The only environment a child process gets: the allowlisted variables that are set, plus `extra`."""
    env = {k: os.environ[k] for k in CHILD_ENV_VARS if k in os.environ}
    return {**env, **extra}


def _timed_out():
    return TIMEOUT_EXIT, f"timed out after {RUN_TIMEOUT_S} s"


def _run_streaming(argv, cwd, env, consume):
    """Run `argv`, handing its stdout to `consume` while it runs; (code, None, stderr). Whatever
    `consume` raises stops the process and propagates, unless the deadline killed it first."""
    try:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    except OSError as e:
        return NOT_FOUND_EXIT, None, str(e).encode()
    expired = threading.Event()

    def expire():
        expired.set()
        p.kill()

    timer = threading.Timer(RUN_TIMEOUT_S, expire)
    errors = []
    drain = threading.Thread(target=lambda: errors.append(p.stderr.read()))
    timer.start()
    drain.start()
    try:
        consume(p.stdout)
        while p.stdout.read(DRAIN_CHUNK):
            pass
    except BaseException:
        p.kill()
        if not expired.is_set():
            raise
    finally:
        timer.cancel()
        p.wait()
        drain.join()
        p.stdout.close()
        p.stderr.close()
    if expired.is_set():
        return TIMEOUT_EXIT, None, _timed_out()[1].encode()
    return p.returncode, None, errors[0]


def run(argv, *, cwd, env, input=None, consume=None):
    """Default runner: (returncode, stdout, stderr); a missing binary is exit 127 and a process
    past RUN_TIMEOUT_S is killed and exits 124. `input` as bytes selects binary mode (used for age),
    text or None selects text mode (zg, git). `consume` gets stdout as a binary stream while the
    process runs, and stdout is then None."""
    if consume is not None:
        return _run_streaming(argv, cwd, env, consume)
    binary = isinstance(input, bytes)
    try:
        p = subprocess.run(argv, cwd=cwd, env=env, input=input, text=not binary, capture_output=True,
                           timeout=RUN_TIMEOUT_S)
    except OSError as e:
        return NOT_FOUND_EXIT, (b"" if binary else ""), (str(e).encode() if binary else str(e))
    except subprocess.TimeoutExpired:
        message = _timed_out()[1]
        return TIMEOUT_EXIT, (b"" if binary else ""), (message.encode() if binary else message)
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
