"""zjm serve: the library as a local HTTP JSON API, generated from OPS (spec 06)."""
import json
import os
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config as config_module
from . import core
from .errors import ZjmError
from .ops import OPS, check

MAX_BODY = 1 << 20
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _host_of(value):
    if not value:
        return None
    if "://" in value:
        value = urllib.parse.urlsplit(value).netloc
    return value.rsplit(":", 1)[0] if value.count(":") <= 1 else value.split("]")[0].lstrip("[")


def make_server(host="127.0.0.1", port=8765, *, config=None, runner=None, jev=None):
    """A ThreadingHTTPServer bound to host:port (loopback only, or 0.0.0.0 in the container)."""
    allowed = ("127.0.0.1", "localhost", "::1")
    if os.environ.get("ZJM_IN_CONTAINER") == "1":
        allowed += ("0.0.0.0",)
    if host not in allowed:
        raise ValueError(f"host must be 127.0.0.1, localhost or ::1, not {host!r}")
    cfg = config_module.resolve(config)
    fakes = {"runner": runner, "jev": jev}
    routes = {f"/{name}": func for name, (func, _, _) in OPS.items()}

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

        def _guarded(self, method):
            host_hdr = _host_of(self.headers.get("Host"))
            if host_hdr is not None and host_hdr not in ALLOWED_HOSTS:
                self._send(403, {"error": "host not allowed"})
                return True
            origin = self.headers.get("Origin")
            if origin is not None and _host_of(origin) not in ALLOWED_HOSTS:
                self._send(403, {"error": "origin not allowed"})
                return True
            if method == "POST":
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
                if ctype != "application/json":
                    self.send_error(415)
                    return True
            return False

        def _route(self, method):
            if self._guarded(method):
                return
            if self.path == "/health":
                return self._send(200, core.doctor(config=cfg)) if method == "GET" else self.send_error(405)
            if self.path not in routes:
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
            error = check(self.path[1:], body)
            if error:
                return self.send_error(400, error)
            try:
                result = routes[self.path](body, config=cfg, **fakes)
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
