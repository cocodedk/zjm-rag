"""`help` (spec 11): a zero-cost operation, library, CLI and HTTP."""
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from fakes import TEST_KEY, make_config, make_encrypted_locker, make_locker
from zjm_rag import guide
from zjm_rag.cli import main
from zjm_rag.http import make_server
from zjm_rag.ops import OPS


def _boom(*_a, **_k):
    raise AssertionError("help must not call runner or jev")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class HelpTest(unittest.TestCase):
    def test_guide_and_instance(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = str(Path(tmp.name) / "home")
        secret = str(Path(tmp.name) / "secret")
        kept = str(Path(tmp.name) / "src")
        under_home = str(Path(home) / "under-home")
        cfg = make_config(self, home=home, allow=[kept, str(Path(secret) / "inner"), under_home],
                          deny=[secret], egress={"rank": False, "answer": False, "translate": True})
        make_locker(self, cfg, "plain1")
        make_encrypted_locker(self, cfg, "enc1")

        r = guide.help(config=cfg, runner=_boom, jev=_boom)

        self.assertLessEqual(len(r["guide"]), 3000)
        for name in OPS:
            self.assertIn(name, r["guide"])

        inst = r["instance"]
        self.assertEqual(inst["allow"], [kept])
        self.assertEqual(inst["egress"], cfg["egress"])
        self.assertEqual(inst["languages"], cfg["languages"])
        self.assertEqual(sorted(inst["lockers"], key=lambda l: l["name"]),
                         [{"name": "enc1", "encrypted": True}, {"name": "plain1", "encrypted": False}])

        blob = json.dumps(r)
        self.assertNotIn(secret, blob)
        self.assertNotIn(home, blob)
        self.assertNotIn(TEST_KEY, blob)

        fresh_cfg = make_config(self)
        r2 = guide.help(config=fresh_cfg, runner=_boom, jev=_boom)
        self.assertEqual(r2["instance"]["lockers"], [])
        self.assertFalse(os.path.exists(fresh_cfg["home"]))

    def test_help_cli_and_http(self):
        cfg = make_config(self, allow=["/sources/agent-linters"])

        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}):
            code, out, _err = _run(["help", "--config", cfg["path"]])
            self.assertEqual(code, 0)
            self.assertIn(guide.GUIDE, out)
            self.assertIn("allow: /sources/agent-linters", out)

            code, out, _err = _run(["help", "--config", cfg["path"], "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), guide.help(config=cfg))

        server = make_server(port=0, config=cfg)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        req = urllib.request.Request(base + "/help", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            code = resp.status
            body = json.loads(resp.read())
        self.assertEqual(code, 200)
        self.assertEqual(body, guide.help(config=cfg))


if __name__ == "__main__":
    unittest.main()
