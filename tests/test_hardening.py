"""Spec 15: what a decrypted locker can leak, and the caps and deadlines around it."""
import io
import os
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fakes import TEST_KEY, FakeRunner, fake_jev, fake_llm, make_config, make_encrypted_locker, make_locker
from zjm_rag import ZjmError, ask, copying, file_list, file_put, find, locker_create, locker_drop, locker_list
from zjm_rag import lockers as lockers_mod
from zjm_rag import engine, sealed
from zjm_rag.cli import main
from zjm_rag.lockers import check_name

SECRET = "sk-should-not-leak"
MOUNTS_TMPFS = "overlay / overlay rw 0 0\ntmpfs /tmp tmpfs rw,nosuid 0 0\n"
MOUNTS_DISK = "overlay / overlay rw 0 0\n/dev/sda1 /tmp ext4 rw 0 0\n"
NOT_TMPFS = "refusing to decrypt: /tmp is not a tmpfs; run zjm with --tmpfs /tmp"


def tar_of(*members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class HardeningTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_config(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.tmp_root = self.tmp / "zjm-tmp"
        patcher = mock.patch.object(sealed, "TMP_ROOT", self.tmp_root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def mounts(self, text):
        path = self.tmp / "mounts"
        path.write_text(text)
        patcher = mock.patch.object(sealed, "MOUNTS_PATH", path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_names_with_session_suffixes_are_refused(self):
        for bad in ("lib.key", "lib.verify", "lib.tmp", "lib.age"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ZjmError, "bad locker name"):
                check_name(bad)
        check_name("lib.keys")

    def test_limit_and_top_k_over_the_cap_are_refused(self):
        make_locker(self, self.cfg, "lib")
        runner = FakeRunner()
        with self.assertRaisesRegex(ZjmError, "limit"):
            find("q", ["lib"], limit=101, config=self.cfg, runner=runner, jev=fake_jev([]))
        with self.assertRaisesRegex(ZjmError, "top_k"):
            ask("q", ["lib"], top_k=101, config=self.cfg, runner=runner, jev=fake_jev([]), llm=fake_llm())
        self.assertEqual(runner.calls, [])

    def test_runner_kills_a_process_past_its_timeout(self):
        argv = [sys.executable, "-c", "import time; time.sleep(30)"]
        with mock.patch.object(engine, "RUN_TIMEOUT_S", 0.3):
            code, _out, err = engine.run(argv, cwd=str(self.tmp), env=engine.child_env(), input=b"")
            self.assertEqual((code, b"timed out after" in err), (124, True))
            code, _out, err = engine.run(argv, cwd=str(self.tmp), env=engine.child_env(), input=None)
            self.assertEqual((code, "timed out after" in err), (124, True))
            code, out, err = engine.run(argv, cwd=str(self.tmp), env=engine.child_env(), input=None, consume=lambda s: s.read())
            self.assertEqual((code, out, b"timed out after" in err), (124, None, True))

    def test_children_get_only_allowlisted_env(self):
        make_locker(self, self.cfg, "plain1")
        runner = FakeRunner()
        environ = {"PATH": "/bin", "HOME": "/h", "LANG": "C", "OPENROUTER_API_KEY": SECRET, "GH_TOKEN": SECRET}
        with mock.patch.dict(os.environ, environ, clear=True):
            locker_create("enc", TEST_KEY, config=self.cfg, runner=runner)
            file_put("enc", "a.md", "hi", key=TEST_KEY, config=self.cfg, runner=runner)
            find("q", ["plain1"], config=self.cfg, runner=runner, jev=fake_jev([0.9] * 3))
            src = self.tmp / "src"
            src.mkdir()
            (src / "f.txt").write_text("x")
            copying._gitignored(str(src), ["f.txt"], runner)
        seen = {c[0][0] for c in runner.calls}
        self.assertEqual(seen, {"age", "age-keygen", "zjm-engine", "git"})
        for argv, _cwd, env, _input in runner.calls:
            self.assertLessEqual(set(env), set(engine.CHILD_ENV_VARS), argv)
            self.assertNotIn(SECRET, "".join(env.values()))

    def test_decrypt_refuses_when_tmp_is_not_tmpfs(self):
        locker_create("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())
        runner = FakeRunner()
        self.mounts(MOUNTS_DISK)
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}):
            with self.assertRaisesRegex(ZjmError, NOT_TMPFS):
                find("q", ["lib"], keys={"lib": TEST_KEY}, config=self.cfg, runner=runner, jev=fake_jev([]))
        self.assertEqual(runner.calls, [])
        self.assertEqual(list(self.tmp_root.glob("*")) if self.tmp_root.exists() else [], [])

    def test_decrypt_runs_when_tmp_is_tmpfs(self):
        self.mounts(MOUNTS_TMPFS)
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}):
            locker_create("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())
            file_put("lib", "a.md", "hi", key=TEST_KEY, config=self.cfg, runner=FakeRunner())
            r = file_list("lib", key=TEST_KEY, config=self.cfg, runner=FakeRunner())
        self.assertEqual([f["name"] for f in r["files"]], ["a.md"])

    def test_core_dumps_are_off_in_the_container(self):
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}), \
                mock.patch("zjm_rag.cli.resource.setrlimit") as setrlimit, \
                mock.patch("sys.stdout", io.StringIO()):
            main(["doctor"], runner=FakeRunner())
        import resource
        setrlimit.assert_called_once_with(resource.RLIMIT_CORE, (0, 0))

    def test_decrypt_streams_into_the_session(self):
        locker_create("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())
        base, streamed = FakeRunner(), []

        def spy(argv, *, cwd, env, input, consume=None):
            result = base(argv, cwd=cwd, env=env, input=input, consume=consume)
            if "-d" in argv:
                streamed.append((consume is not None, result[1]))
            return result

        file_put("lib", "a.md", "hello", key=TEST_KEY, config=self.cfg, runner=spy)
        self.assertEqual(streamed, [(True, None)])

    def test_unsafe_member_mid_stream_stops_the_decrypt(self):
        session = self.tmp_root / "lib"
        sealed.reset(session)
        archive = tar_of(("good.txt", b"1"), ("../evil", b"2"), ("after.txt", b"3"))
        seen = []

        def runner(argv, *, cwd, env, input, consume=None):
            seen.append(consume)
            consume(io.BytesIO(archive))
            return 0, None, b""

        with self.assertRaisesRegex(ZjmError, "unsafe path"):
            sealed.decrypt_into(self.tmp / "x.age", self.tmp / "x.key", session, runner, "lib")
        self.assertTrue((session / "good.txt").exists())
        self.assertFalse((session / "after.txt").exists())
        self.assertFalse((self.tmp_root / "evil").exists())


    def test_finished_child_keeps_the_consume_error(self):
        def consume(stream):
            stream.read()
            time.sleep(2)  # past the 1 s deadline: the timer fires after the child has exited
            raise ZjmError("from consume")

        with mock.patch.object(engine, "RUN_TIMEOUT_S", 1):
            with self.assertRaisesRegex(ZjmError, "from consume"):
                engine.run(["true"], cwd=str(self.tmp), env=engine.child_env(), input=None, consume=consume)

    def test_timeouts_have_their_own_message(self):
        locker_create("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())
        base = FakeRunner()
        timed_out = {}

        def runner(argv, *, cwd, env, input, consume=None):
            if argv[0] == timed_out.get("tool"):
                return engine.TIMEOUT_EXIT, None if consume else "", b"timed out after 600 s"
            return base(argv, cwd=cwd, env=env, input=input, consume=consume)

        for tool, message in (("age", "decrypting locker lib timed out"), ("age-keygen", "timed out"),
                              ("zjm-engine", "timed out")):
            timed_out["tool"] = tool
            with self.subTest(tool=tool), self.assertRaisesRegex(ZjmError, message) as caught:
                file_put("lib", "a.md", "hi", key=TEST_KEY, config=self.cfg, runner=runner)
            self.assertNotIn("wrong key", str(caught.exception))

    def test_legacy_reserved_names_can_be_listed_and_dropped(self):
        make_locker(self, self.cfg, "old.key")
        self.assertEqual([e["name"] for e in locker_list(config=self.cfg)["lockers"]], ["old.key"])
        with self.assertRaisesRegex(ZjmError, "bad locker name"):
            locker_create("new.tmp", plain=True, config=self.cfg)
        with self.assertRaisesRegex(ZjmError, "bad locker name"):
            file_list("old.key", config=self.cfg, runner=FakeRunner())
        self.assertEqual(locker_drop("old.key", config=self.cfg)["name"], "old.key")
        self.assertEqual(locker_list(config=self.cfg)["lockers"], [])
        make_encrypted_locker(self, self.cfg, "backup")
        lockers_dir = lockers_mod.home_dirs(self.cfg)[1]
        (lockers_dir / "backup.age").rename(lockers_dir / "backup.age.age")
        self.assertEqual([e["name"] for e in locker_list(config=self.cfg)["lockers"]], ["backup.age"])
        self.assertEqual(locker_drop("backup.age", TEST_KEY, config=self.cfg, runner=FakeRunner())["name"], "backup.age")
        self.assertEqual(locker_list(config=self.cfg)["lockers"], [])
        with self.assertRaisesRegex(ZjmError, "bad locker name"):
            locker_drop("Bad Name", config=self.cfg)

    def test_timeout_on_the_index_run_is_reported(self):
        ldir = make_locker(self, self.cfg, "lib")

        def runner(argv, *, cwd, env, input, consume=None):
            return engine.TIMEOUT_EXIT, "", ""

        with self.assertRaisesRegex(ZjmError, "engine index timed out"):
            lockers_mod.run_index(ldir, lockers_mod.read_manifest(ldir), runner)
        self.assertFalse(lockers_mod.read_manifest(ldir)["indexed"])

    def test_input_with_consume_is_refused(self):
        with self.assertRaises(ValueError):
            engine.run(["true"], cwd=str(self.tmp), env={}, input=b"x", consume=lambda s: None)


if __name__ == "__main__":
    unittest.main()
