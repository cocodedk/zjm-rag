"""find and ask search only some files of a locker (spec 19, piece 192)."""
import contextlib
import io
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from fakes import FakeRunner, fake_jev, fake_llm, make_config, make_locker

from zjm_rag import ZjmError, ask, find
from zjm_rag.cli import main
from zjm_rag.http import make_server
from zjm_rag.mcp import serve

BAD = [[], [""], ["/a"], ["."], ["./a"], ["a//b"], ["a/../b"], [3]]


def sent(runner):
    """(argv, stdin JSON) of the one engine call."""
    (call,) = [c for c in runner.calls if c[0][0] == "zjm-engine"]
    return call[0], json.loads(call[3])


class FindNamesTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_config(self, egress={"rank": True, "answer": True, "translate": True}, languages=["da"])
        make_locker(self, self.cfg, "lib")

    def test_find_sends_names_on_stdin_not_argv(self):
        runner = FakeRunner()
        find("q", ["lib"], names=["a", "b/c.md/"], translate=False, runner=runner, jev=fake_jev([0.9] * 3),
             config=self.cfg)
        argv, body = sent(runner)
        self.assertEqual(body, {"question": "q", "translations": [], "names": ["a", "b/c.md"]})
        self.assertFalse({"a", "b/c.md", "b/c.md/"} & set(argv))
        runner = FakeRunner()
        find("q", ["lib"], translate=False, runner=runner, jev=fake_jev([0.9] * 3), config=self.cfg)
        argv, body = sent(runner)
        self.assertNotIn("names", body)
        self.assertNotIn("a", argv)

    def test_ask_sends_names_on_stdin_not_argv(self):
        runner = FakeRunner()
        ask("q", ["lib"], names=["docs/", "x.md"], translate=False, runner=runner, jev=fake_jev([0.9] * 3),
            llm=fake_llm("the answer"), config=self.cfg)
        argv, body = sent(runner)
        self.assertEqual(body["names"], ["docs", "x.md"])
        self.assertFalse({"docs", "docs/", "x.md"} & set(argv))

    def test_bad_names_are_refused_before_any_call(self):
        for op in (find, ask):
            for names in BAD:
                runner, llm = FakeRunner(), fake_llm("x")
                with self.assertRaises(ZjmError, msg=f"{op.__name__} {names!r}"):
                    op("q", ["lib"], names=names, runner=runner, jev=fake_jev([]), llm=llm, config=self.cfg)
                self.assertEqual((runner.calls, llm.calls), ([], []), names)
        # The cap is checked first, and a bad name before the config and the no-lockers check.
        with self.assertRaisesRegex(ZjmError, "maximum"):
            find("q", ["lib"], limit=1000, names=[], config=self.cfg)
        with self.assertRaisesRegex(ZjmError, "names must"):
            find("q", [], names=[], config={"home": 1})

    def test_http_find_and_ask_pass_names_and_schema_refuses_bad_ones(self):
        runner = FakeRunner()
        server = make_server(port=0, config=self.cfg, runner=runner, jev=fake_jev([0.9, 0.2, 0.1]),
                             llm=fake_llm("the answer"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                e.close()
                return e.code

        for path in ("/find", "/ask"):
            runner.calls.clear()
            body = {"query": "q", "lockers": ["lib"], "translate": False, "names": ["a/"]}
            self.assertEqual(post(path, body), 200, path)
            self.assertEqual(sent(runner)[1]["names"], ["a"], path)
            runner.calls.clear()
            for names in ("a", [1], [["a"]]):
                self.assertEqual(post(path, {**body, "names": names}), 400, (path, names))
            self.assertEqual(runner.calls, [])

    def test_mcp_find_and_ask_list_names(self):
        out = io.StringIO()
        serve(io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"), out)
        listed = {t["name"]: t["inputSchema"]["properties"] for t in json.loads(out.getvalue())["result"]["tools"]}
        for tool in ("zjm_find", "zjm_ask"):
            self.assertEqual(listed[tool]["names"], {"type": "array", "items": {"type": "string"}}, tool)

    def test_cli_name_is_repeatable(self):
        for cmd in ("find", "ask"):
            runner = FakeRunner()
            with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main([cmd, "q", "-l", "lib", "--config", self.cfg["path"], "--json", "--no-translate",
                             "--name", "a", "--name", "b"],
                            runner=runner, jev=fake_jev([0.9, 0.2, 0.1]), llm=fake_llm("the answer"))
            self.assertEqual(code, 0, cmd)
            argv, body = sent(runner)
            self.assertEqual(body["names"], ["a", "b"], cmd)
            self.assertNotIn("--name", argv)
