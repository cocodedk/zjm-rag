"""zjm serve: the library as a local HTTP JSON API."""
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import core
from .errors import ZjmError

MAX_BODY = 1 << 20
FIND_KEYS = {"query", "limit", "file_types", "min_score", "sort", "rank"}
KEYS = {"/index": ({"sources"}, {"sources", "multilingual", "embedding", "rebuild"}),
        "/find": ({"query"}, FIND_KEYS),
        "/ask": ({"query"}, FIND_KEYS | {"top_k", "answer_language"})}


def _list_str(v):
    return isinstance(v, list) and all(isinstance(s, str) for s in v)


def _pos_int(v):
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _score(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1


CHECKS = {"sources": (_list_str, "a list of strings"), "file_types": (_list_str, "a list of strings"),
          "limit": (_pos_int, "a positive integer"), "top_k": (_pos_int, "a positive integer"),
          "min_score": (_score, "a number in [0, 1]"), "rank": (lambda v: isinstance(v, bool), "a boolean"),
          "multilingual": (lambda v: isinstance(v, bool), "a boolean"),
          "rebuild": (lambda v: isinstance(v, bool), "a boolean")}


def _check(path, body):
    """The error message for a bad body, or None."""
    if not isinstance(body, dict):
        return "body must be a JSON object"
    if "store" in body:
        return "store is set by the server"
    required, allowed = KEYS[path]
    if body.keys() - allowed:
        return f"unknown keys: {', '.join(sorted(body.keys() - allowed))}"
    if required - body.keys():
        return f"missing key: {', '.join(sorted(required - body.keys()))}"
    for key, value in body.items():
        ok, want = CHECKS.get(key, (lambda v: isinstance(v, str), "a string"))
        if not ok(value):
            return f"{key} must be {want}"
    return None


def make_server(host="127.0.0.1", port=8765, *, store=core.DEFAULT_STORE, runner=None, jev=None):
    """A ThreadingHTTPServer bound to host:port, not yet serving."""
    fakes = {k: v for k, v in {"runner": runner, "jev": jev}.items() if v is not None}
    calls = {"/index": lambda b: core.index(**b, store=store, **{k: v for k, v in fakes.items() if k != "jev"}),
             "/find": lambda b: core.find(**b, store=store, **fakes),
             "/ask": lambda b: core.ask(**b, store=store, **fakes)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send(self, code, obj):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def send_error(self, code, message=None, explain=None):
            self.close_connection = True
            self._send(code, {"error": message or HTTPStatus(code).phrase})

        def _route(self, method):
            if self.path == "/health":
                return self._send(200, core.doctor(store)) if method == "GET" else self.send_error(405)
            if self.path not in calls:
                return self.send_error(404)
            if method != "POST":
                return self.send_error(405)
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                return self.send_error(400, "bad Content-Length")
            if length > MAX_BODY:
                return self.send_error(413)
            try:
                body = json.loads(self.rfile.read(length))
            except ValueError:
                return self.send_error(400, "invalid JSON")
            error = _check(self.path, body)
            if error:
                return self.send_error(400, error)
            try:
                result = calls[self.path](body)
            except (ZjmError, ValueError) as e:
                return self.send_error(422, str(e))
            except Exception as e:
                return self.send_error(500, f"{type(e).__name__}: {e}")
            self._send(200, result)

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def do_PUT(self):
            self._route("PUT")

        def do_PATCH(self):
            self._route("PATCH")

        def do_DELETE(self):
            self._route("DELETE")

        def do_HEAD(self):
            self._route("HEAD")

        def do_OPTIONS(self):
            self._route("OPTIONS")

    return ThreadingHTTPServer((host, port), Handler)
