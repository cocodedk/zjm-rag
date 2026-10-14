"""The skill's "files" list, folder and file containment, missing folders, and the mirror's text-only copy."""
import os
import shutil
import sys

from skillbase import SKILL, SkillBase

sys.path.insert(0, str(SKILL))
import mirror


class FilesTest(SkillBase):
    def cfg(self, **kw):
        return {"locker": "mine", **kw}

    def test_files_are_mirrored_under_one_mount_and_count_as_the_source(self):
        (self.project / "CLAUDE.md").write_text("rules")
        (self.project / "docs/x.md").write_text("in docs")
        (self.project / "docs/y.md").write_text("not listed")
        s = self.cfg(files=["CLAUDE.md", "docs/x.md"])
        r = self.run_script("reindex", settings=s)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.seen(), ["_files/CLAUDE.md", "_files/docs/x.md"])
        self.assertEqual(self.configs()[0]["allow"], ["/sources/_files"])
        self.assertEqual(self.run_script("find", "q", settings=s).stderr, "")
        (self.project / "CLAUDE.md").write_text("changed")
        self.assertIn("STALE", self.run_script("find", "q", settings=s).stderr)

    def test_the_files_list_is_part_of_the_lockers_source_identity(self):
        (self.project / "A.md").write_text("a")
        (self.project / "B.md").write_text("b")
        s = lambda f: {"locker": "other", "folders": ["docs"], "files": [f]}  # the stub knows the locker "other"
        self.assertEqual(self.run_script("reindex", settings=s("A.md"), ZJM_FORCE="1").returncode, 0)
        r = self.run_script("reindex", settings=s("B.md"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("not built from these folders", r.stderr)
        self.assertEqual(self.run_script("reindex", settings=s("A.md")).returncode, 0)

    def test_files_and_folders_together_and_a_config_with_neither(self):
        (self.project / "docs/a.md").write_text("a")
        (self.project / "README.md").write_text("r")
        r = self.run_script("reindex", settings=self.cfg(folders=["docs"], files=["README.md"]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.seen(), ["_files/README.md", "docs/a.md"])
        for s in (self.cfg(), self.cfg(folders=[], files=[]), self.cfg(files="README.md")):
            self.assertEqual(self.run_script("reindex", settings=s).returncode, 2)

    def test_a_file_entry_is_checked_before_it_is_read(self):
        (self.project / "real.md").write_text("x")
        (self.project / "link.md").symlink_to(self.project / "real.md")
        (self.project / "dirlink").symlink_to(self.project / "docs")
        (self.project / "docs/in.md").write_text("x")
        (self.project / ".aws").mkdir()
        (self.project / ".aws/notes.md").write_text("x")
        for f in ("/etc/hostname", "../x.md", "docs/../real.md", "link.md", "dirlink/in.md", "docs", "nope.md",
                  ".aws/notes.md"):
            r = self.run_script("reindex", settings=self.cfg(folders=["docs"], files=[f]))
            self.assertEqual(r.returncode, 2, f)
        self.assertFalse((self.tmp / "configs").exists())

    def test_a_folder_entry_may_not_leave_the_project(self):
        for f in (str(self.tmp), "../project", "docs/../docs", "docs/.."):
            self.assertEqual(self.run_script("reindex", settings=self.cfg(folders=[f])).returncode, 2, f)
        r = self.run_script("reindex", settings=self.cfg(folders=["docs", "_files"]))
        self.assertEqual(r.returncode, 2)
        (self.project / "_files").mkdir()
        self.assertEqual(self.run_script("reindex", settings=self.cfg(folders=["_files"])).returncode, 2)
        self.assertFalse((self.tmp / "configs").exists())

    def test_a_missing_folder_is_indexed_as_empty_and_goes_stale_when_it_appears(self):
        s = self.cfg(folders=["docs", "later"])
        r = self.run_script("reindex", settings=s)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("later does not exist; indexed as empty", r.stderr)
        self.assertTrue((self.tmp / "seen/later").is_dir())
        self.assertEqual(self.run_script("find", "q", settings=s).stderr, "")
        (self.project / "later").mkdir()
        self.assertIn("STALE", self.run_script("find", "q", settings=s).stderr)
        self.run_script("reindex", settings=s)
        self.assertEqual(self.run_script("find", "q", settings=s).stderr, "")

    def test_the_mirror_prunes_floor_folders_and_skips_a_git_file(self):
        (self.project / "node_modules/deep").mkdir(parents=True)
        (self.project / "node_modules/deep/a.md").write_text("x")
        (self.project / "keep.md").write_text("x")
        self.assertEqual([p.name for p in mirror.candidates(self.project.resolve(), ["."])], ["keep.md"])
        (self.project / ".git").write_text("gitdir: /elsewhere")
        self.assertFalse(mirror.allowed(self.project, self.project / ".git"))

    def test_the_mirror_copies_only_small_utf8_text_and_warns(self):
        d = self.project / "docs"
        (d / "ok.md").write_text("fine")
        (d / "big.md").write_text("x" * (mirror.MAX_BYTES + 1))
        (d / "bin.dat").write_bytes(b"a\0b")
        (d / "latin.txt").write_bytes(b"caf\xe9")
        self.assertEqual(self.mirror(d), ["ok.md"])
        for n in ("big.md", "bin.dat", "latin.txt"):
            self.assertIn(n, self.last.stderr)

    def test_the_projects_exclude_patterns_apply_inside_the_mirror(self):
        d = self.project / "docs"
        (d / "drafts").mkdir()
        (d / "drafts/a.md").write_text("x")
        (d / "NOTES.PDF").write_text("x")
        (d / "keep.md").write_text("x")
        r = self.run_script("reindex", settings=self.cfg(folders=["docs"], exclude=["*.pdf", "drafts/"]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.seen(), ["docs/keep.md"])
        shutil.rmtree(self.tmp / "seen")
        (self.project / "CLAUDE.md").write_text("x")
        self.run_script("reindex", settings=self.cfg(files=["CLAUDE.md"], exclude=["claude.*"]))
        self.assertEqual(os.listdir(self.tmp / "seen/_files"), [])
