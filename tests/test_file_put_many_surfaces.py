"""Spec 21: file_put_many's op schema, HTTP route, MCP tool and CLI command."""
import contextlib
import io
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from fakes import FakeRunner, make_config, make_locker
from test_file_put_many import put
from test_mcp import rpc

from zjm_rag import ops
from zjm_rag.cli import main
from zjm_rag.http import make_server


class SurfacesTest(unittest.TestCase):
    def test_check(self):
        for body in ({"locker": "l", "files": [{"name": "a"}]},
                     {"locker": "l", "files": [{"name": "a", "text": "t", "x": "y"}]},
                     {"locker": "l", "files": [{"name": 1, "text": "t"}]},
                     {"locker": "l", "remove": "a"}, {"locker": "l", "remove": [1]},
                     {"locker": "l", "remove": ["a"], "nope": 1}):
            with self.subTest(body=body):
                self.assertIsNotNone(ops.check("file_put_many", body))
        self.assertIsNone(ops.check("file_put_many", {"locker": "l", "remove": ["a"]}))

    def test_http_and_mcp(self):
        cfg = make_config(self)
        make_locker(self, cfg, "lib")
        server = make_server(port=0, config=cfg, runner=FakeRunner())
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def post(body):
            req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/file_put_many",
                                         data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                with e:
                    return e.code, json.loads(e.read())

        self.assertEqual(post({"locker": "lib", "files": put("a.md"), "remove": ["proj/b.md"]}),
                         (200, {"added": ["a.md"], "replaced": [], "removed": ["proj/b.md"]}))
        self.assertEqual(post({"locker": "lib"}), (422, {"error": "nothing to put or remove"}))
        (tools,) = rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, config=cfg)
        tool = next(t for t in tools["result"]["tools"] if t["name"] == "zjm_file_put_many")
        self.assertEqual(tool["inputSchema"], ops.OPS["file_put_many"][1])
        self.assertEqual(tool["inputSchema"]["properties"]["files"]["items"],
                         {"type": "object", "properties": {"name": {"type": "string"}, "text": {"type": "string"}},
                          "required": ["name", "text"], "additionalProperties": False})

class CliTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        result = {"added": ["a.md"], "replaced": ["b.md"], "removed": ["c"]}
        fake = (lambda body, **kw: self.calls.append(body) or result,)
        for p in (mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}),
                  mock.patch.dict(ops.OPS, {"file_put_many": fake + ops.OPS["file_put_many"][1:]})):
            p.start()
            self.addCleanup(p.stop)

    def cli(self, stdin, *extra):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(out):
            code = main(["file-put-many", "lib", "--config", make_config(self)["path"], *extra])
        return code, out.getvalue(), err.getvalue()

    def test_cli(self):
        self.assertEqual(self.cli(json.dumps(put("a.md")), "--remove", "x", "--remove", "y/z")[0], 0)
        self.assertEqual(self.calls, [{"locker": "lib", "files": put("a.md"), "remove": ["x", "y/z"]}])
        code, _out, err = self.cli('{"name": "a.md", "text": "t"}')
        self.assertEqual(code, 1)
        self.assertIn("zjm: stdin must be a JSON array", err)
        self.assertEqual(len(self.calls), 1)

    def test_cli_human_output_and_empty_stdin(self):
        code, out, _err = self.cli("", "--remove", "c")
        self.assertEqual((code, out), (0, "added a.md\nreplaced b.md\nremoved c\n"))
        self.assertEqual(self.calls, [{"locker": "lib", "files": [], "remove": ["c"]}])

    def test_cli_key_file_stdin_refused(self):
        code, _out, err = self.cli("[]", "--key-file", "-")
        self.assertEqual(code, 2)
        self.assertIn("--key-file - cannot be combined with file-put-many's stdin text", err)
        self.assertEqual(self.calls, [])
