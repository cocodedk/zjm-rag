import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from fakes import FakeRunner, fake_jev, make_config, make_store
from zjm_rag import ZjmError, ask, doctor, find, index
from zjm_rag.cli import main
from zjm_rag.http import make_server


def _req(base, path, headers=None, method=None, data=None):
    r = urllib.request.Request(base + path, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        e.close()
        return e.code


class SafetyTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_refused_outside_allow(self):
        src = self.tmp / "proj"
        src.mkdir()
        runner = FakeRunner()
        default_cfg = {"home": str(self.tmp / "home"), "allow": [], "deny": [], "exclude": [],
                       "egress": {"rank": False, "answer": False}, "embedding": "local/potion-code-16m-v2",
                       "llm": ["claude"], "path": None}
        with self.assertRaisesRegex(ZjmError, 'add it to "allow"'):
            index([src], store=self.tmp / "store", runner=runner, config=default_cfg)
        self.assertEqual(runner.calls, [])
        self.assertFalse((self.tmp / "home").exists())
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        cfg = make_config(self, allow=[str(elsewhere)])
        with self.assertRaisesRegex(ZjmError, 'add it to "allow"'):
            index([src], store=self.tmp / "store2", runner=runner, config=cfg)
        self.assertEqual(runner.calls, [])

    def test_deny_before_filesystem(self):
        denied = self.tmp / "denied"
        denied.mkdir()
        cfg = make_config(self, allow=[str(self.tmp)], deny=[str(denied)])
        with mock.patch("os.path.realpath", side_effect=AssertionError("must not resolve a denied path")):
            with self.assertRaises(ZjmError):
                index([denied], store=self.tmp / "store", runner=FakeRunner(), config=cfg)
        src = self.tmp / "proj"
        secret = src / "secret"
        secret.mkdir(parents=True)
        (secret / "f.txt").write_text("x")
        (src / "denyme.txt").write_text("y")
        (src / "keep.txt").write_text("z")
        (src / "link").symlink_to(secret)
        cfg2 = make_config(self, allow=[str(self.tmp)], deny=[str(secret), str(src / "denyme.txt")])
        real_scandir = os.scandir

        def guarded(path="."):
            if os.path.abspath(path) == str(secret):
                raise AssertionError("must not scandir a denied directory")
            return real_scandir(path)

        with mock.patch("os.scandir", guarded):
            index([src], store=self.tmp / "store2", runner=FakeRunner(), config=cfg2)
        copy = self.tmp / "store2" / "corpus" / "proj"
        self.assertTrue((copy / "keep.txt").exists())
        self.assertFalse((copy / "secret").exists())
        self.assertFalse((copy / "denyme.txt").exists())
        self.assertFalse((copy / "link").exists())

    def test_exclude_floor_and_config_exclude(self):
        src = self.tmp / "proj"
        (src / ".ssh").mkdir(parents=True)
        (src / ".ssh" / "config").write_text("x")
        for name in ("id_rsa", "x.pem", ".npmrc", ".env.local", "app.log"):
            (src / name).write_text("x")
        (src / "keep.md").write_text("keep")
        (src / "linky").symlink_to(src / "keep.md")
        cfg = make_config(self, allow=[str(self.tmp)], exclude=["*.log"])
        result = index([src], store=self.tmp / "store", runner=FakeRunner(), config=cfg)
        copy = self.tmp / "store" / "corpus" / "proj"
        self.assertEqual([p.name for p in copy.iterdir()], ["keep.md"])
        self.assertEqual(result["excluded"], 7)

    def test_gitignored_not_copied(self):
        src = self.tmp / "proj"
        src.mkdir()
        (src / "keep.md").write_text("k")
        (src / "drop.md").write_text("d")
        (src / "id_rsa").write_text("secret")
        cfg = make_config(self, allow=[str(self.tmp)], deny=[str(self.tmp / "deny-me")])
        runner = FakeRunner(ignored=["drop.md"])
        index([src], store=self.tmp / "store", runner=runner, config=cfg)
        copy = self.tmp / "store" / "corpus" / "proj"
        self.assertTrue((copy / "keep.md").exists())
        self.assertFalse((copy / "drop.md").exists())
        git_call = [c for c in runner.calls if c[0][0] == "git"][0]
        names = [n for n in git_call[3].split("\0") if n]
        self.assertEqual(set(names), {"keep.md", "drop.md"})

        src2 = self.tmp / "proj2"
        (src2 / "a.md").parent.mkdir(parents=True, exist_ok=True)
        (src2 / "a.md").write_text("a")
        index([src2], store=self.tmp / "store2", runner=FakeRunner(), config=cfg)
        self.assertTrue((self.tmp / "store2" / "corpus" / "proj2" / "a.md").exists())

        src3 = self.tmp / "proj3"
        (src3 / "a.md").parent.mkdir(parents=True, exist_ok=True)
        (src3 / "a.md").write_text("a")
        (src3 / ".git").mkdir()
        with self.assertRaises(ZjmError):
            index([src3], store=self.tmp / "store3", runner=FakeRunner(), config=cfg)

    def test_egress_ceiling(self):
        store = make_store(self)
        cfg_off = make_config(self, egress={"rank": False, "answer": False})

        def jev_fail(payload):
            self.fail("jev must not be called")

        with self.assertRaises(ZjmError):
            find("q", store=store, rank=True, runner=FakeRunner(), jev=jev_fail, config=cfg_off)
        r = find("q", store=store, rank=None, runner=FakeRunner(), jev=jev_fail, config=cfg_off)
        self.assertEqual(r["sort"], "zg")
        with self.assertRaises(ZjmError):
            ask("q", store=store, runner=FakeRunner(), jev=jev_fail, config=cfg_off)
        cfg_on = make_config(self, egress={"rank": True, "answer": True})
        find("q", store=store, rank=True, runner=FakeRunner(), jev=fake_jev([0.9, 0.8, 0.1]), config=cfg_on)
        ask("q", store=store, runner=FakeRunner(), jev=fake_jev([0.9, 0.8, 0.1]), config=cfg_on)
        code, out, err = _run_cli(["find", "q", "--store", str(store)], runner=FakeRunner(), jev=jev_fail)
        self.assertEqual(code, 0)

    def test_llm_cannot_act(self):
        store = make_store(self)
        cfg = make_config(self, egress={"rank": True, "answer": True})
        captured = {}

        class Runner(FakeRunner):
            def __call__(self, argv, *, cwd, env, input):
                if argv[0] not in ("zg", "git"):
                    captured.update(argv=argv, cwd=cwd, env=env)
                return super().__call__(argv, cwd=cwd, env=env, input=input)

        ask("q", store=store, runner=Runner(), jev=fake_jev([0.9, 0.8, 0.1]), config=cfg)
        argv = captured["argv"]
        self.assertIn("--tools", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertFalse(Path(captured["cwd"]).is_relative_to(Path(cfg["home"])))
        self.assertNotIn("OPENROUTER_API_KEY", captured["env"])

    def test_http_guard(self):
        store = make_store(self)
        cfg = make_config(self)
        server = make_server(port=0, store=store, config=cfg, runner=FakeRunner(), jev=fake_jev([]))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        self.assertEqual(_req(base, "/health", headers={"Host": "evil.example"}), 403)
        self.assertEqual(_req(base, "/health", headers={"Origin": "http://evil.example"}), 403)
        self.assertEqual(_req(base, "/find", method="POST", data=b"{}", headers={"Content-Type": "text/plain"}), 415)
        self.assertEqual(_req(base, "/health"), 200)
        with self.assertRaises(ValueError):
            make_server(host="0.0.0.0")
        code, out, err = _run_cli(["serve", "--host", "0.0.0.0"])
        self.assertEqual(code, 2)

    def test_doctor_reports_config(self):
        store = make_store(self)
        cfg = make_config(self, egress={"rank": False, "answer": True})
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("shutil.which", return_value="/usr/bin/x"):
            r = doctor(store, config=cfg)
        self.assertEqual((r["config"], r["home"], r["egress"]), (cfg["path"], cfg["home"], cfg["egress"]))
        self.assertTrue(r["ok"])


def _run_cli(argv, **fakes):
    import contextlib
    import io
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, **fakes)
    return code, out.getvalue(), err.getvalue()


if __name__ == "__main__":
    unittest.main()
