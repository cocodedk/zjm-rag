import argparse
import io
import json
import threading
import unittest
import urllib.error
import urllib.request

from fakes import FakeRunner, make_config
from zjm_rag.cli import _parser
from zjm_rag.http import make_server
from zjm_rag.mcp import serve
from zjm_rag.ops import OPS


class OpsTest(unittest.TestCase):
    def test_surfaces_match_ops(self):
        parser = _parser()
        sub_action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        cli_names = {a.replace("-", "_") for a in sub_action.choices if a not in ("serve", "mcp")}
        self.assertEqual(cli_names, set(OPS))
        cfg = make_config(self)
        server = make_server(port=0, config=cfg, runner=FakeRunner(), jev=lambda p: {"answers": {}})
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        for name in OPS:
            req = urllib.request.Request(base + f"/{name}", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req)
            except urllib.error.HTTPError as e:
                self.assertNotEqual(e.code, 404, name)
                e.close()

        out = io.StringIO()
        serve(io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"), out,
             config=make_config(self))
        tools = {t["name"][len("zjm_"):] for t in json.loads(out.getvalue())["result"]["tools"]}
        self.assertEqual(tools, set(OPS))

    def test_file_ops_over_http_and_mcp(self):
        cfg = make_config(self)
        from zjm_rag import locker_create
        locker_create("lib", plain=True, config=cfg)
        server = make_server(port=0, config=cfg, runner=FakeRunner())
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                code, r = e.code, json.loads(e.read())
                e.close()
                return code, r

        code, r = call("/file_put", {"locker": "lib", "name": "a.md", "text": "hi"})
        self.assertEqual((code, r["added"]), (200, ["a.md"]))
        code, r = call("/file_list", {"locker": "lib"})
        self.assertEqual((code, [f["name"] for f in r["files"]]), (200, ["a.md"]))
        code, r = call("/file_put", {"locker": "lib", "name": "a.md", "text": "hi", "home": "/tmp"})
        self.assertEqual(code, 400)

        def rpc(method, params):
            out = io.StringIO()
            serve(io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) + "\n"),
                 out, config=cfg, runner=FakeRunner())
            return json.loads(out.getvalue())

        put = rpc("tools/call", {"name": "zjm_file_put", "arguments": {"locker": "lib", "name": "b.md",
                                                                        "text": "yo"}})
        self.assertNotIn("isError", put["result"])
        lst = rpc("tools/call", {"name": "zjm_file_list", "arguments": {"locker": "lib"}})
        self.assertEqual({f["name"] for f in lst["result"]["structuredContent"]["files"]}, {"a.md", "b.md"})


if __name__ == "__main__":
    unittest.main()
