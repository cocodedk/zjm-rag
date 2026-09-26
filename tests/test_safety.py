import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from fakes import FakeRunner, fake_jev, fake_llm, make_config, make_locker
from zjm_rag import ZjmError, ask, doctor, find, locker_create
from zjm_rag import files as files_mod
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
        cfg = make_config(self, home=str(self.tmp / "home"))
        locker_create("lib", plain=True, config=cfg)
        with self.assertRaisesRegex(ZjmError, 'add it to "allow"'):
            files_mod.file_add("lib", [str(src)], config=cfg, runner=FakeRunner())
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        cfg2 = make_config(self, allow=[str(elsewhere)])
        locker_create("lib", plain=True, config=cfg2)
        with self.assertRaisesRegex(ZjmError, 'add it to "allow"'):
            files_mod.file_add("lib", [str(src)], config=cfg2, runner=FakeRunner())

    def test_deny_before_filesystem(self):
        denied = self.tmp / "denied"
        denied.mkdir()
        cfg = make_config(self, allow=[str(self.tmp)], deny=[str(denied)])
        locker_create("lib", plain=True, config=cfg)
        with mock.patch("os.path.realpath", side_effect=AssertionError("must not resolve a denied path")):
            with self.assertRaises(ZjmError):
                files_mod.file_add("lib", [str(denied)], config=cfg, runner=FakeRunner())
        src = self.tmp / "proj"
        secret = src / "secret"
        secret.mkdir(parents=True)
        (secret / "f.txt").write_text("x")
        (src / "denyme.txt").write_text("y")
        (src / "keep.txt").write_text("z")
        (src / "link").symlink_to(secret)
        cfg2 = make_config(self, allow=[str(self.tmp)], deny=[str(secret), str(src / "denyme.txt")])
        locker_create("lib", plain=True, config=cfg2)
        real_scandir = os.scandir

        def guarded(path="."):
            if os.path.abspath(path) == str(secret):
                raise AssertionError("must not scandir a denied directory")
            return real_scandir(path)

        with mock.patch("os.scandir", guarded):
            files_mod.file_add("lib", [str(src)], config=cfg2, runner=FakeRunner())
        from zjm_rag import lockers as lockers_mod
        copy = lockers_mod.locker_dir(cfg2, "lib") / "corpus" / "proj"
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
        locker_create("lib", plain=True, config=cfg)
        result = files_mod.file_add("lib", [str(src)], config=cfg, runner=FakeRunner())
        from zjm_rag import lockers as lockers_mod
        copy = lockers_mod.locker_dir(cfg, "lib") / "corpus" / "proj"
        self.assertEqual([p.name for p in copy.iterdir()], ["keep.md"])
        self.assertEqual(result["excluded"], 7)

    def test_gitignored_not_copied(self):
        src = self.tmp / "proj"
        src.mkdir()
        (src / "keep.md").write_text("k")
        (src / "drop.md").write_text("d")
        (src / "id_rsa").write_text("secret")
        cfg = make_config(self, allow=[str(self.tmp)], deny=[str(self.tmp / "deny-me")])
        locker_create("lib", plain=True, config=cfg)
        runner = FakeRunner(ignored=["drop.md"])
        files_mod.file_add("lib", [str(src)], config=cfg, runner=runner)
        from zjm_rag import lockers as lockers_mod
        copy = lockers_mod.locker_dir(cfg, "lib") / "corpus" / "proj"
        self.assertTrue((copy / "keep.md").exists())
        self.assertFalse((copy / "drop.md").exists())
        git_call = [c for c in runner.calls if c[0][0] == "git"][0]
        names = [n for n in git_call[3].split("\0") if n]
        self.assertEqual(set(names), {"keep.md", "drop.md"})

        src3 = self.tmp / "proj3"
        (src3 / "a.md").parent.mkdir(parents=True, exist_ok=True)
        (src3 / "a.md").write_text("a")
        (src3 / ".git").mkdir()
        with self.assertRaises(ZjmError):
            files_mod.file_add("lib", [str(src3)], config=cfg, runner=FakeRunner())

    def test_egress_ceiling(self):
        cfg_off = make_config(self, egress={"rank": False, "answer": False})
        locker_create("lib", plain=True, config=cfg_off)

        def jev_fail(payload):
            self.fail("jev must not be called")

        with self.assertRaises(ZjmError):
            find("q", ["lib"], rank=True, runner=FakeRunner(), jev=jev_fail, config=cfg_off)
        r = find("q", ["lib"], rank=None, runner=FakeRunner(), jev=jev_fail, config=cfg_off)
        self.assertEqual(r["sort"], "zg")
        with self.assertRaises(ZjmError):
            ask("q", ["lib"], runner=FakeRunner(), jev=jev_fail, config=cfg_off)
        cfg_on = make_config(self, egress={"rank": True, "answer": True})
        locker_create("lib", plain=True, config=cfg_on)
        find("q", ["lib"], rank=True, runner=FakeRunner(), jev=fake_jev([0.9, 0.8, 0.1]), config=cfg_on)
        ask("q", ["lib"], runner=FakeRunner(), jev=fake_jev([0.9, 0.8, 0.1]), llm=fake_llm(), config=cfg_on)
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}):
            code, out, err = _run_cli(["find", "q", "-l", "lib", "--config", cfg_off["path"]], runner=FakeRunner(),
                                      jev=jev_fail)
        self.assertEqual(code, 0)

    def test_llm_cannot_act(self):
        cfg = make_config(self, egress={"rank": True, "answer": True})
        make_locker(self, cfg, "lib")
        runner = FakeRunner()
        llm = fake_llm("ok")
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-should-not-leak"}):
            ask("q", ["lib"], runner=runner, jev=fake_jev([0.9, 0.8, 0.1]), llm=llm, config=cfg)
        self.assertEqual(len(llm.calls), 1)
        self.assertTrue(runner.calls)
        self.assertTrue(all(c[0][0] in ("zg", "git") for c in runner.calls))
        _model, messages = llm.calls[0]
        self.assertNotIn("sk-should-not-leak", json.dumps(messages))

    def test_http_guard(self):
        cfg = make_config(self)
        make_locker(self, cfg, "lib")
        server = make_server(port=0, config=cfg, runner=FakeRunner(), jev=fake_jev([]))
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
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}):
            code, out, err = _run_cli(["serve", "--host", "evil.example"])
        self.assertEqual(code, 2)

    def test_doctor_reports_config(self):
        cfg = make_config(self, egress={"rank": False, "answer": True})
        locker_create("lib", plain=True, config=cfg)
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "x"}, clear=True), \
                mock.patch("shutil.which", return_value="/usr/bin/x"):
            r = doctor(config=cfg)
        self.assertEqual((r["config"], r["home"], r["egress"], r["lockers"]),
                         (cfg["path"], cfg["home"], cfg["egress"], 1))
        self.assertTrue(r["ok"])


def _run_cli(argv, **fakes):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, **fakes)
    return code, out.getvalue(), err.getvalue()


if __name__ == "__main__":
    unittest.main()
