"""Regressions for the review findings of the opus-improvements branch; external commands are faked."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from fakes import FakeRunner, fake_llm, make_config, make_locker

from zjm_rag import ZjmError, ask, files, locker_create, locker_list
from zjm_rag.search import _rank

ROOT = Path(__file__).resolve().parent.parent


class ReviewFixesTest(unittest.TestCase):
    def tmpdir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_malformed_jev_answers_raise_zjm_error(self):
        evidence_map = {"lib/a.md": []}
        for response in ({"answers": {"f1": 0.9}}, {"answers": ["f1"]}, {"answers": "x"}, ["f1"]):
            with self.subTest(response=response), self.assertRaises(ZjmError):
                _rank("q", evidence_map, lambda payload, r=response: r, None)

    def test_ask_without_lockers_names_no_command(self):
        cfg = make_config(self)
        make_locker(self, cfg, "lib")
        with self.assertRaisesRegex(ZjmError, "^at least one locker is required$"):
            ask("q", [], llm=fake_llm(), config=cfg)

    def test_symlinked_home_component_is_not_copied(self):
        tmp = self.tmpdir()
        data = tmp / "data"
        (data / "share").mkdir(parents=True)
        (data / "doc.txt").write_text("keep")
        (tmp / "u").mkdir()
        (tmp / "u" / "share").symlink_to(data / "share", target_is_directory=True)
        cfg = make_config(self, allow=[str(data)], home=str(tmp / "u" / "share" / "zjm"))
        locker_create("lib", plain=True, config=cfg)
        files.file_put("lib", "secret.txt", "other locker text", config=cfg, runner=FakeRunner())
        locker_create("dst", plain=True, config=cfg)
        files.file_add("dst", [str(data)], config=cfg, runner=FakeRunner())
        self.assertEqual([f["name"] for f in files.file_list("dst", config=cfg)["files"]], ["data/doc.txt"])

    def test_file_put_name_clashing_with_folder_or_file(self):
        cfg = make_config(self)
        runner = FakeRunner()
        locker_create("lib", plain=True, config=cfg)
        files.file_put("lib", "docs/a.txt", "text", config=cfg, runner=runner)
        files.file_put("lib", "a", "text", config=cfg, runner=runner)
        for name in ("docs", "a/b"):
            with self.subTest(name=name), self.assertRaisesRegex(ZjmError, "clashes"):
                files.file_put("lib", name, "x", config=cfg, runner=runner)
        files.file_remove("lib", ["docs"], config=cfg, runner=runner)
        self.assertEqual(files.file_put("lib", "docs", "x", config=cfg, runner=runner)["added"], ["docs"])

    def test_locker_name_ending_in_age_refused(self):
        cfg = make_config(self)
        with self.assertRaisesRegex(ZjmError, "bad locker name"):
            locker_create("x.age", plain=True, config=cfg)

    def test_home_with_missing_parents_is_created(self):
        cfg = make_config(self, home=str(self.tmpdir() / "no" / "such" / "h"))
        self.assertEqual(locker_list(config=cfg)["lockers"], [])

    def test_piped_install_ignores_a_checkout_in_cwd(self):
        tmp = self.tmpdir()
        for name in ("docker", "python3"):
            (tmp / name).write_text("#!/bin/sh\nexit 0\n")
            (tmp / name).chmod(0o755)
        cwd = tmp / "foreign"
        (cwd / "bin").mkdir(parents=True)
        (cwd / "zjm_rag").mkdir()
        (cwd / "Dockerfile").write_text("FROM scratch\n")
        (cwd / "bin" / "zjm").write_text("#!/bin/sh\n")
        env = {"PATH": str(tmp) + os.pathsep + os.defpath, "HOME": str(tmp), "ZJM_INSTALL_DRY_RUN": "1"}
        r = subprocess.run(["sh"], input=(ROOT / "install.sh").read_text(), cwd=cwd, env=env,
                           capture_output=True, text=True, check=False, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("+ docker build -t zjm-rag:latest https://github.com/cocodedk/zjm-rag.git", r.stdout)
        self.assertNotIn(str(cwd), r.stdout)


if __name__ == "__main__":
    unittest.main()
