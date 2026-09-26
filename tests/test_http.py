import contextlib
import io
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

from fakes import FakeRunner, fake_jev, fake_llm, make_config, make_locker
from zjm_rag.cli import main
from zjm_rag.http import MAX_BODY, make_server


class HttpTest(unittest.TestCase):
    def serve(self, config, **fakes):
        server = make_server(port=0, config=config, **fakes)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(self, path, body=None, method=None, headers=None):
        data = None if body is None else body if isinstance(body, bytes) else json.dumps(body).encode()
        headers = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                code, ctype, raw = r.status, r.headers["Content-Type"], r.read()
        except urllib.error.HTTPError as e:
            code, ctype, raw = e.code, e.headers["Content-Type"], e.read()
            e.close()
        self.assertEqual(ctype, "application/json")
        return code, json.loads(raw)

    def test_health(self):
        """Through `zjm serve`, stopped once it has answered."""
        servers, out = [], io.StringIO()

        def capture(*args, **kwargs):
            servers.append(make_server(*args, **kwargs))
            return servers[0]

        argv = ["serve", "--port", "0", "--config", make_config(self)["path"]]
        with mock.patch("zjm_rag.http.make_server", capture), contextlib.redirect_stdout(out), \
                mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}):
            thread = threading.Thread(target=lambda: servers.append(main(argv)))
            thread.start()
            for _ in range(500):
                if out.getvalue():
                    break
                time.sleep(0.01)
            line = out.getvalue()
            self.assertRegex(line, r"^listening on http://127\.0\.0\.1:\d+\n$")
            self.base = line.split()[-1]
            code, r = self.call("/health")
            servers[0].shutdown()
            thread.join(5)
        self.assertEqual(code, 200)
        self.assertEqual(set(r), {"ok", "checks", "config", "home", "egress", "lockers"})
        self.assertEqual(set(r["checks"]), {"zg", "age", "openrouter_key"})
        self.assertEqual(servers[1], 0)

    def test_find_roundtrip(self):
        runner = FakeRunner()
        cfg = make_config(self)
        make_locker(self, cfg, "lib")
        self.serve(cfg, runner=runner, jev=fake_jev([0.9, 0.8, 0.1]))
        code, r = self.call("/find", {"query": "q", "lockers": ["lib"], "min_score": 0.7, "sort": "path",
                                      "file_types": ["py"]})
        self.assertEqual(code, 200)
        self.assertEqual(runner.calls[0][0][-2:], ["-t", "py"])
        self.assertEqual(set(r), {"query", "min_score", "sort", "accepted", "rejected"})
        self.assertEqual((r["min_score"], r["sort"]), (0.7, "path"))
        self.assertEqual([h["path"] for h in r["accepted"]], ["proj/a.py", "proj/b.md"])
        code, r = self.call("/locker_create", {"name": "lib2", "multilingual": True, "plain": True})
        self.assertEqual(code, 200)
        self.assertEqual(r["name"], "lib2")

    def test_ask_language(self):
        runner, llm = FakeRunner(), fake_llm("the answer")
        cfg = make_config(self)
        make_locker(self, cfg, "lib")
        self.serve(cfg, runner=runner, jev=fake_jev([0.9, 0.2, 0.1]), llm=llm)
        code, r = self.call("/ask", {"query": "q", "lockers": ["lib"], "answer_language": "da", "top_k": 1})
        self.assertEqual(code, 200)
        self.assertIn("Answer in da.", llm.calls[-1][1][-1]["content"])
        self.assertEqual((r["answer"], r["files"]), ("the answer", ["lib/proj/b.md"]))

    def test_rejects_store_and_unknown_keys(self):
        runner = FakeRunner()
        cfg = make_config(self)
        make_locker(self, cfg, "lib")
        self.serve(cfg, runner=runner, jev=fake_jev([]))
        for path, body in (("/ask", {"query": "q", "lockers": ["lib"], "store": "/tmp/other"}),
                           ("/ask", {"query": "q", "lockers": ["lib"], "colour": "red"}),
                           ("/find", {"query": "q", "lockers": ["lib"], "limit": True}),
                           ("/file_add", {"locker": "lib", "paths": "x"}), ("/file_add", {})):
            code, r = self.call(path, body)
            self.assertEqual(code, 400, body)
            self.assertIsInstance(r["error"], str)
        self.assertEqual(self.call("/find", b"{not json")[0], 400)
        self.assertEqual(runner.calls, [])

    def test_library_error_is_422(self):
        self.serve(make_config(self), runner=FakeRunner(), jev=fake_jev([]))
        code, r = self.call("/find", {"query": "q", "lockers": ["nope"]})
        self.assertEqual(code, 422)
        self.assertIn("no locker", r["error"])

    def test_404_405_413(self):
        self.serve(make_config(self), runner=FakeRunner(), jev=fake_jev([]))
        self.assertEqual(self.call("/nope")[0], 404)
        self.assertEqual(self.call("/find")[0], 405)
        self.assertEqual(self.call("/health", {}, method="POST")[0], 405)
        self.assertEqual(self.call("/ask", method="OPTIONS")[0], 405)
        self.assertEqual(self.call("/find", b"", headers={"Content-Length": "-5"})[0], 400)
        code, r = self.call("/find", b"", headers={"Content-Length": str(MAX_BODY + 1)})
        self.assertEqual(code, 413)
        self.assertIn("error", r)


if __name__ == "__main__":
    unittest.main()
