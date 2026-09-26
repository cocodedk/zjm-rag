import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import TEST_KEY, FakeRunner, make_config
from zjm_rag import ZjmError, find, locker_create, locker_drop, locker_list
from zjm_rag import files as files_mod
from zjm_rag import lockers as lockers_mod


class LockerTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_config(self)

    def test_create_list_drop(self):
        locker_create("a", plain=True, config=self.cfg)
        locker_create("b", plain=True, config=self.cfg)
        listed = locker_list(config=self.cfg)["lockers"]
        self.assertEqual([l["name"] for l in listed], ["a", "b"])
        self.assertEqual([l["files"] for l in listed], [0, 0])
        with self.assertRaisesRegex(ZjmError, "already exists"):
            locker_create("a", plain=True, config=self.cfg)
        r = locker_drop("a", config=self.cfg)
        self.assertEqual(r, {"name": "a", "files": 0})
        self.assertEqual([l["name"] for l in locker_list(config=self.cfg)["lockers"]], ["b"])
        with self.assertRaisesRegex(ZjmError, "no locker nope"):
            locker_drop("nope", config=self.cfg)

    def test_bad_names_refused(self):
        for bad in ("", "A", "a/b", "..", "x" * 65):
            with self.assertRaises(ZjmError):
                locker_create(bad, plain=True, config=self.cfg)
        self.assertFalse(Path(self.cfg["home"]).exists())

    def test_file_add_manifest_and_zg(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "docs"
        (src / "sub").mkdir(parents=True)
        (src / "sub" / "a.md").write_text("aaa")
        single = Path(tmp.name) / "single.txt"
        single.write_text("bbb")
        cfg = make_config(self, allow=[tmp.name])
        locker_create("lib", plain=True, config=cfg)
        runner = FakeRunner()
        r = files_mod.file_add("lib", [str(src), str(single)], config=cfg, runner=runner)
        self.assertEqual(r["added"], ["docs", "single.txt"])
        manifest = lockers_mod.read_manifest(lockers_mod.locker_dir(cfg, "lib"))
        self.assertTrue(manifest["indexed"])
        entry = manifest["files"]["docs/sub/a.md"]
        self.assertEqual((entry["size"], len(entry["sha256"])), (3, 64))
        self.assertTrue(entry["source"].endswith("sub/a.md"))
        self.assertEqual(manifest["files"]["single.txt"]["source"], str(single))
        self.assertFalse(any(".zvec-grep" in k for k in manifest["files"]))
        zg_calls = [c for c in runner.calls if c[0][0] == "zg"]
        self.assertEqual(len(zg_calls), 1)
        argv, cwd, env, _ = zg_calls[0]
        self.assertEqual(argv, ["zg", "index", ".", "--embedding", "local/potion-code-16m-v2", "--mode",
                                "direct", "--hidden"])
        self.assertEqual(cwd, str(lockers_mod.locker_dir(cfg, "lib") / "corpus"))
        self.assertEqual(env["ZVEC_GREP_HOME"], str(lockers_mod.locker_dir(cfg, "lib") / "zghome"))
        git_calls = [c for c in runner.calls if c[0][0] == "git"]
        self.assertEqual(git_calls[-1][1], str(Path(tmp.name)))
        self.assertEqual(git_calls[-1][3], "single.txt\0")

        outside = Path(tmp.name).parent / "outside-not-allowed"
        outside.mkdir(exist_ok=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        with self.assertRaisesRegex(ZjmError, "allow"):
            files_mod.file_add("lib", [str(outside)], config=cfg, runner=FakeRunner())
        manifest2 = lockers_mod.read_manifest(lockers_mod.locker_dir(cfg, "lib"))
        self.assertNotIn("outside-not-allowed", manifest2["files"])

    def test_same_name_replaces(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "docs"
        src.mkdir()
        (src / "a.md").write_text("a")
        (src / "b.md").write_text("b")
        cfg = make_config(self, allow=[tmp.name])
        locker_create("lib", TEST_KEY, config=cfg, runner=FakeRunner())
        files_mod.file_add("lib", [str(src)], key=TEST_KEY, config=cfg, runner=FakeRunner())
        (src / "a.md").unlink()
        r = files_mod.file_add("lib", [str(src)], key=TEST_KEY, config=cfg, runner=FakeRunner())
        self.assertEqual(r["replaced"], ["docs"])
        listed = files_mod.file_list("lib", key=TEST_KEY, config=cfg, runner=FakeRunner())
        names = [f["name"] for f in listed["files"]]
        self.assertNotIn("docs/a.md", names)
        self.assertIn("docs/b.md", names)

        (src / "c.md").write_text("c")
        age_path = lockers_mod.home_dirs(cfg)[1] / "lib.age"
        before = age_path.read_bytes()

        def failing(argv, *, cwd, env, input):
            if argv[0] == "zg" and argv[1] == "index":
                return 1, "", "boom"
            return FakeRunner()(argv, cwd=cwd, env=env, input=input)

        with self.assertRaises(ZjmError):
            files_mod.file_add("lib", [str(src)], key=TEST_KEY, config=cfg, runner=failing)

        # settled detail 8/9: a failed write never touches the sealed locker; find still works.
        self.assertEqual(age_path.read_bytes(), before)

        def query_runner(argv, *, cwd, env, input):
            if argv[0] == "zg" and argv[1] == "query":
                return 0, "hits: 1\n\n#1 matchedBy=fts docs/b.md:1-1\nsource:\n1\tb\n", ""
            return FakeRunner()(argv, cwd=cwd, env=env, input=input)

        found = find("q", ["lib"], keys={"lib": TEST_KEY}, config=cfg, runner=query_runner,
                     jev=lambda p: {"answers": {k: {"noul": 0.9} for k in p["questions"]}})
        self.assertEqual([h["path"] for h in found["accepted"]], ["docs/b.md"])

    def test_file_put_rules(self):
        cfg = make_config(self)
        locker_create("lib", plain=True, config=cfg)
        r = files_mod.file_put("lib", "notes/a.md", "hello", config=cfg, runner=FakeRunner())
        self.assertEqual(r, {"added": ["notes/a.md"], "replaced": []})
        manifest = lockers_mod.read_manifest(lockers_mod.locker_dir(cfg, "lib"))
        self.assertIsNone(manifest["files"]["notes/a.md"]["source"])
        for bad in ("../x", "/x", "a//b", ".env", "x/id_rsa"):
            with self.assertRaises(ZjmError):
                files_mod.file_put("lib", bad, "x", config=cfg, runner=FakeRunner())
        with self.assertRaises(ZjmError):
            files_mod.file_put("lib", "big.txt", "x" * (1 << 20 + 1), config=cfg, runner=FakeRunner())

    def test_file_remove_all_or_nothing(self):
        cfg = make_config(self)
        locker_create("lib", plain=True, config=cfg)
        files_mod.file_put("lib", "a.md", "a", config=cfg, runner=FakeRunner())
        files_mod.file_put("lib", "dir/b.md", "b", config=cfg, runner=FakeRunner())
        with self.assertRaisesRegex(ZjmError, "nope"):
            files_mod.file_remove("lib", ["a.md", "nope"], config=cfg, runner=FakeRunner())
        manifest = lockers_mod.read_manifest(lockers_mod.locker_dir(cfg, "lib"))
        self.assertIn("a.md", manifest["files"])
        r = files_mod.file_remove("lib", ["dir"], config=cfg, runner=FakeRunner())
        self.assertEqual(r["removed"], ["dir"])
        manifest2 = lockers_mod.read_manifest(lockers_mod.locker_dir(cfg, "lib"))
        self.assertNotIn("dir/b.md", manifest2["files"])

    def test_embedding_fixed_per_locker(self):
        cfg = make_config(self, embedding="local/potion-code-16m-v2")
        locker_create("lib", multilingual=True, plain=True, config=cfg)
        runner = FakeRunner()
        files_mod.file_put("lib", "a.md", "a", config=cfg, runner=runner)
        argv = [c[0] for c in runner.calls if c[0][0] == "zg"][0]
        self.assertIn("local/potion-multilingual-128m", argv)
        with self.assertRaises(ZjmError):
            locker_create("other", embedding="qwen/x", plain=True, config=cfg)

    def test_foreign_or_symlinked_locker_refused(self):
        cfg = make_config(self)
        locker_create("lib", plain=True, config=cfg)
        home = Path(cfg["home"])
        planted = home / "lockers" / "planted"
        (home / "lockers").mkdir(parents=True, exist_ok=True)
        real = home / "real-target"
        real.mkdir()
        planted.symlink_to(real)
        with self.assertRaisesRegex(ZjmError, "symlink"):
            locker_create("planted", plain=True, config=cfg)
        with mock.patch("os.getuid", return_value=home.stat().st_uid + 1):
            with self.assertRaisesRegex(ZjmError, "owned by another user"):
                locker_create("lib2", plain=True, config=cfg)


if __name__ == "__main__":
    unittest.main()
