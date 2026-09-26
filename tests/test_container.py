"""zjm runs only in its container (spec 07): the CLI guard, the bind guard, embedding and locking."""
import contextlib
import io
import os
import threading
import time
import unittest
from unittest import mock

from fakes import FakeRunner, fake_jev, make_config, make_locker
from zjm_rag import ZjmError, find, locker_create
from zjm_rag import lockers as lockers_mod
from zjm_rag.cli import main
from zjm_rag.http import make_server


def _run(argv, **fakes):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, **fakes)
    return code, out.getvalue(), err.getvalue()


class ContainerTest(unittest.TestCase):
    def test_cli_refuses_outside_container(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            code, out, err = _run(["locker-list"])
        self.assertEqual(code, 1)
        self.assertIn("runs only in its container", err)
        self.assertEqual(out, "")

    def test_bind_all_only_in_container(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                make_server(host="0.0.0.0")
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}):
            server = make_server(host="0.0.0.0", port=0)
            self.addCleanup(server.server_close)
            self.assertEqual(server.server_address[0], "0.0.0.0")

    def test_unbaked_embedding_refused_in_container(self):
        cfg = make_config(self)
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}):
            locker_create("lib", plain=True, config=cfg)
            with self.assertRaisesRegex(ZjmError, "not baked into the container"):
                locker_create("other", embedding="local/some-other-model", plain=True, config=cfg)

        bad_cfg = make_config(self, embedding="local/some-other-model")
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}):
            from zjm_rag import config as config_module
            with self.assertRaisesRegex(ZjmError, "not baked into the container"):
                config_module.load(bad_cfg["path"])

    def test_find_takes_shared_lock(self):
        cfg = make_config(self)
        make_locker(self, cfg, "lib")
        order = []
        release = threading.Event()

        def hold_exclusive():
            with lockers_mod.lock(cfg, exclusive=True):
                order.append("exclusive-acquired")
                release.wait(2)
            order.append("exclusive-released")

        t = threading.Thread(target=hold_exclusive)
        t.start()
        while "exclusive-acquired" not in order:
            time.sleep(0.01)
        time.sleep(0.05)

        def do_find():
            find("q", ["lib"], runner=FakeRunner(), jev=fake_jev([0.9, 0.8, 0.1]), config=cfg)
            order.append("find-done")

        finder = threading.Thread(target=do_find)
        finder.start()
        time.sleep(0.1)
        self.assertNotIn("find-done", order)
        release.set()
        t.join(2)
        finder.join(2)
        self.assertEqual(order, ["exclusive-acquired", "exclusive-released", "find-done"])


if __name__ == "__main__":
    unittest.main()
