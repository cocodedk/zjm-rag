"""Sealed locker sessions (spec 08): one file at rest, no key leaks, safe extraction, mixed lockers."""
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import (AGE_MARKER, OTHER_KEY, TEST_KEY, FakeRunner, _fake_recipient, fake_jev, make_config,
                   make_encrypted_locker, make_locker)
from zjm_rag import ZjmError, ask, file_list, file_put, find, locker_create, locker_encrypt, locker_list
from zjm_rag import lockers as lockers_mod
from zjm_rag import sealed


class SealedTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_config(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_root = Path(tmp.name) / "zjm-tmp"
        patcher = mock.patch.object(sealed, "TMP_ROOT", self.tmp_root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_at_rest_only_one_encrypted_file(self):
        make_encrypted_locker(self, self.cfg, "lib", key=TEST_KEY)
        file_put("lib", "a.md", "hello", key=TEST_KEY, config=self.cfg, runner=FakeRunner())
        find("q", ["lib"], keys={"lib": TEST_KEY}, config=self.cfg, runner=FakeRunner(),
            jev=fake_jev([0.1, 0.1, 0.1]))
        _, lockers_dir = lockers_mod.home_dirs(self.cfg)
        entries = list(lockers_dir.iterdir())
        self.assertEqual([p.name for p in entries], ["lib.age"])
        self.assertFalse((self.tmp_root / "lib").exists())
        self.assertFalse((self.tmp_root / "lib.key").exists())

    def test_wrong_key_refused_without_leak(self):
        locker_create("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())
        with self.assertRaisesRegex(ZjmError, "wrong key or damaged locker lib") as ctx:
            file_list("lib", key=OTHER_KEY, config=self.cfg, runner=FakeRunner())
        self.assertNotIn(TEST_KEY, str(ctx.exception))
        self.assertNotIn(OTHER_KEY, str(ctx.exception))

    def test_key_never_in_argv_or_env(self):
        runner = FakeRunner()
        make_encrypted_locker(self, self.cfg, "lib", key=TEST_KEY)
        file_put("lib", "a.md", "hello", key=TEST_KEY, config=self.cfg, runner=runner)
        find("q", ["lib"], keys={"lib": TEST_KEY}, config=self.cfg, runner=runner,
            jev=fake_jev([0.9, 0.8, 0.7]))
        ask("q", ["lib"], keys={"lib": TEST_KEY}, config=self.cfg, runner=runner,
           jev=fake_jev([0.9, 0.8, 0.7]))
        for argv, _cwd, env, _input in runner.calls:
            self.assertNotIn(TEST_KEY, argv)
            self.assertTrue(all(TEST_KEY not in str(v) for v in (env or {}).values()))

    def test_plaintext_removed_on_error(self):
        locker_create("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())
        age_path = lockers_mod.home_dirs(self.cfg)[1] / "lib.age"
        before = age_path.read_bytes()

        base = FakeRunner()

        def failing(argv, *, cwd, env, input):
            if argv[0] == "zg":
                return 1, "", "boom"
            return base(argv, cwd=cwd, env=env, input=input)

        with self.assertRaises(ZjmError):
            file_put("lib", "a.md", "hello", key=TEST_KEY, config=self.cfg, runner=failing)
        self.assertFalse((self.tmp_root / "lib").exists())
        self.assertFalse((self.tmp_root / "lib.key").exists())
        self.assertEqual(age_path.read_bytes(), before)

    def test_tar_traversal_refused(self):
        locker_create("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())
        age_path = lockers_mod.home_dirs(self.cfg)[1] / "lib.age"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            data = b"evil"
            info = tarfile.TarInfo(name="../x")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        recipient = _fake_recipient(TEST_KEY)
        age_path.write_bytes(AGE_MARKER + recipient.encode() + b"\n" + buf.getvalue())
        with self.assertRaises(ZjmError):
            file_list("lib", key=TEST_KEY, config=self.cfg, runner=FakeRunner())
        self.assertFalse((self.tmp_root / "lib").exists())
        self.assertFalse((Path(self.tmp_root).parent / "x").exists())

    def test_find_needs_every_key(self):
        locker_create("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())
        locker_create("lib2", TEST_KEY, config=self.cfg, runner=FakeRunner())
        runner = FakeRunner()
        with self.assertRaisesRegex(ZjmError, "lib2 needs its key"):
            find("q", ["lib", "lib2"], keys={"lib": TEST_KEY}, config=self.cfg, runner=runner,
                jev=fake_jev([]))
        self.assertEqual(runner.calls, [])

    def test_plain_and_encrypted_mix(self):
        make_locker(self, self.cfg, "plain1")
        make_encrypted_locker(self, self.cfg, "enc1", key=TEST_KEY)
        r = find("q", ["plain1", "enc1"], keys={"enc1": TEST_KEY}, config=self.cfg, runner=FakeRunner(),
                jev=fake_jev([0.9] * 6))
        self.assertEqual({h["locker"] for h in r["accepted"]}, {"plain1", "enc1"})

        with self.assertRaisesRegex(ZjmError, "plain1 is not encrypted"):
            find("q", ["plain1", "enc1"], keys={"plain1": TEST_KEY, "enc1": TEST_KEY}, config=self.cfg,
                runner=FakeRunner(), jev=fake_jev([]))
        with self.assertRaisesRegex(ZjmError, "enc1 needs its key"):
            find("q", ["plain1", "enc1"], config=self.cfg, runner=FakeRunner(), jev=fake_jev([]))

        listed = {l["name"]: l for l in locker_list(config=self.cfg)["lockers"]}
        self.assertEqual(listed["plain1"]["encrypted"], False)
        self.assertEqual(listed["enc1"]["encrypted"], True)

    def test_encrypt_plain_locker(self):
        make_locker(self, self.cfg, "lib")
        r = locker_encrypt("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())
        self.assertEqual(r, {"name": "lib"})
        _, lockers_dir = lockers_mod.home_dirs(self.cfg)
        self.assertEqual(sorted(p.name for p in lockers_dir.iterdir()), ["lib.age"])
        found = find("q", ["lib"], keys={"lib": TEST_KEY}, config=self.cfg, runner=FakeRunner(),
                     jev=fake_jev([0.9, 0.8, 0.7]))
        self.assertEqual(len(found["accepted"]) + len(found["rejected"]), 3)

        with self.assertRaisesRegex(ZjmError, "already encrypted"):
            locker_encrypt("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())

        make_locker(self, self.cfg, "lib2")

        def failing_seal(argv, *, cwd, env, input):
            if argv[0] == "age" and "-o" in argv:
                return 1, b"", b"boom"
            return FakeRunner()(argv, cwd=cwd, env=env, input=input)

        with self.assertRaises(ZjmError):
            locker_encrypt("lib2", TEST_KEY, config=self.cfg, runner=failing_seal)
        self.assertTrue((lockers_mod.locker_dir(self.cfg, "lib2") / "locker.json").exists())
        self.assertFalse((lockers_dir / "lib2.age").exists())
        self.assertFalse((lockers_dir / "lib2.age.tmp").exists())


if __name__ == "__main__":
    unittest.main()
