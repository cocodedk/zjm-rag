"""zjm-engine argv, the default process runner, and the parser for the engine's query output."""
import json
import os
import subprocess
import threading

from .errors import ZjmError

HITS = 40
BINARY = "zjm-engine"
MODELS_DIR = "/opt/zjm/models"
LOCAL_PREFIX = "local/"
INDEX_FILE = "engine.idx"
FORMAT_EXIT = 3
BAD_OUTPUT = "engine returned bad output"
GROUPS = ("query", "translation")
HIT_KEYS = ("path", "start", "end", "rank")
RUN_TIMEOUT_S = 600
TIMEOUT_EXIT = 124
NOT_FOUND_EXIT = 127
DRAIN_CHUNK = 65536
CHILD_ENV_VARS = ("PATH", "HOME", "LANG", "LC_ALL")


def child_env(**extra):
    """The only environment a child process gets: the allowlisted variables that are set, plus `extra`."""
    env = {k: os.environ[k] for k in CHILD_ENV_VARS if k in os.environ}
    return {**env, **extra}


def raise_if_timed_out(code, what):
    """A timed-out child (exit 124) is its own error, never read as a wrong key or a failed tool."""
    if code == TIMEOUT_EXIT:
        raise ZjmError(f"{what} timed out")


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
        if p.poll() is None:  # a child that already exited was not slow
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
    text or None selects text mode (zjm-engine, git). `consume` gets stdout as a binary stream while the
    process runs, and stdout is then None."""
    if consume is not None:
        if input is not None:
            raise ValueError("input and consume cannot be combined")
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


def model_dir(embedding):
    """The baked folder of a manifest's `embedding`, e.g. local/potion-code-16m-v2."""
    return f"{MODELS_DIR}/{embedding.removeprefix(LOCAL_PREFIX)}"


def index_argv(embedding, corpus, index):
    return [BINARY, "index", "--model", model_dir(embedding), str(corpus), str(index)]


def query_argv(embedding, index, file_types=None):
    """The question never goes on argv (it is readable in /proc): see query_input."""
    argv = [BINARY, "query", "--model", model_dir(embedding), "--limit", str(HITS)]
    for t in file_types or []:
        argv += ["--type", t]
    return argv + [str(index)]


def query_input(question, translations):
    """The JSON object the engine reads on stdin."""
    return json.dumps({"question": question, "translations": list(translations or [])})


def _hits(items):
    if not isinstance(items, list):
        raise ZjmError(BAD_OUTPUT)
    for h in items:
        if (not isinstance(h, dict) or not all(isinstance(h.get(k), int) for k in HIT_KEYS[1:])
                or not isinstance(h.get("path"), str)):
            raise ZjmError(BAD_OUTPUT)
    return [{k: h[k] for k in HIT_KEYS} for h in items]


def parse(out):
    """The engine's JSON -> {"query": [hit], "translation": [hit]}, hits as {"path", "start", "end",
    "rank"}; anything else raises ZjmError."""
    try:
        data = json.loads(out)
    except ValueError:
        raise ZjmError(BAD_OUTPUT) from None
    if not isinstance(data, dict):
        raise ZjmError(BAD_OUTPUT)
    return {g: _hits(data.get(g)) for g in GROUPS}
