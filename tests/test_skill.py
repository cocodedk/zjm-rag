"""The skill's zjm-project wrapper and mirror, against a stub zjm that records each config it is given."""
import json
import os
import shutil
import subprocess
import unittest

from skillbase import CLEAN, SkillBase


class SkillTest(SkillBase):
    def test_nothing_is_sent_unless_the_project_says_so(self):
        self.assertEqual(self.run_script("reindex").returncode, 0)
        self.assertEqual({json.dumps(c["egress"]) for c in self.configs()}, {'{"rank": false, "answer": false}'})
        r = self.run_script("ask", "who approves?")
        self.assertEqual(r.returncode, 2)
        self.assertIn('"send": true', r.stderr)
        self.run_script("find", "who approves?", settings={"locker": "mine", "folders": ["docs"], "send": True,
                                                           "llm": "some/model"})
        self.assertEqual(self.configs()[-1]["egress"], {"rank": True, "answer": True})
        self.assertEqual(self.configs()[-1]["llm"], "some/model")

    def test_refuses_a_folder_inside_a_floor_folder_in_any_case(self):
        for floor in (".aws", ".AWS", "Node_Modules"):
            (self.project / floor / "docs").mkdir(parents=True)
            r = self.run_script("reindex", settings={"locker": "mine", "folders": [f"{floor}/docs"]})
            self.assertEqual(r.returncode, 2, floor)
            self.assertIn("never indexes", r.stderr)

    def test_force_other_than_1_keeps_another_projects_locker(self):
        r = self.run_script("reindex", settings={"locker": "other", "folders": ["docs"]}, ZJM_FORCE="0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not built from these folders", r.stderr)

    def test_refuses_a_configured_folder_reached_through_a_symlink(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.project / "linked").symlink_to(outside)
        r = self.run_script("reindex", settings={"locker": "mine", "folders": ["linked"]})
        self.assertEqual(r.returncode, 2)
        self.assertIn("is a symlink", r.stderr)

    def test_a_dangling_symlink_does_not_break_a_search(self):
        (self.project / "docs/gone").symlink_to(self.tmp / "missing")
        self.assertEqual(self.run_script("reindex").returncode, 0)
        r = self.run_script("find", "who approves?")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_search_takes_only_the_allowed_options(self):
        self.assertEqual(self.run_script("reindex").returncode, 0)
        for args in (["--limit", "5"], ["--limit=5", "--no-rank"], ["--min-score=0.3", "--type", "md", "--sort=path"]):
            self.assertEqual(self.run_script("find", "who approves?", *args).returncode, 0, args)
        for args in (["--lang", "da"], ["--top-k=3"]):  # ask-only options, as zjm's own parser has them
            self.assertEqual(self.run_script("find", "who approves?", *args).returncode, 2, args)
        send = {"locker": "mine", "folders": ["docs"], "send": True}
        self.assertEqual(self.run_script("ask", "who approves?", "--top-k=3", "--lang", "da", settings=send).returncode, 0)
        self.assertEqual(self.run_script("ask", "who approves?", "--sort=path", settings=send).returncode, 2)
        for args in (["--config", "/x.json"], ["--config=/x.json"], ["--c", "x"], ["--conf=x"], ["-l", "other"],
                     ["--locker", "other"], ["--key-file", "k"], ["--lim", "5"], ["--limit"], ["--limit", "-l"],
                     ["--no-rank=1"], ["stray"], ["--limit", "5", "--config", "x"]):
            r = self.run_script("find", "who approves?", *args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("not allowed", r.stderr)
        self.assertEqual(self.run_script("find", "-l").returncode, 2)

    def test_a_removed_folder_is_stale(self):
        self.assertEqual(self.run_script("reindex").returncode, 0)
        shutil.rmtree(self.project / "docs")
        self.assertIn("STALE", self.run_script("find", "who approves?").stderr)

    def test_mirror_is_readable_by_others_whatever_the_umask(self):
        docs = self.project / "docs"
        (docs / "sub").mkdir()
        (docs / "sub/b.bin").write_text("text")
        (docs / "sub/b.bin").chmod(0o600)
        old = os.umask(0o077)
        try:
            self.mirror(docs)
        finally:
            os.umask(old)
        out = self.tmp / "mirror"
        self.assertEqual({oct(p.stat().st_mode & 0o777) for p in [out, out / "sub"]}, {"0o755"})
        self.assertEqual(oct((out / "sub/b.bin").stat().st_mode & 0o777), "0o644")

    def test_mirror_skips_floor_files(self):
        docs = self.project / "docs"
        (docs / "keep.md").write_text("keep")
        (docs / ".env").write_text("TOKEN=1")
        (docs / ".SSH").mkdir()
        (docs / ".SSH/notes.md").write_text("key")
        self.assertEqual(self.mirror(docs), ["keep.md"])

    def test_mirror_skips_a_tracked_file_under_a_folder_replaced_by_a_symlink(self):
        docs = self.project / "docs"
        git = ["git", "-C", str(docs), "-c", "user.name=t", "-c", "user.email=t@t"]
        (docs / "sub").mkdir()
        (docs / "sub/a.md").write_text("tracked")
        for cmd in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
            subprocess.run(git + cmd, env=CLEAN, check=True, timeout=30)
        shutil.rmtree(docs / "sub")
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "a.md").write_text("outside")
        (docs / "sub").symlink_to(outside)
        self.assertEqual(self.mirror(docs), [])


if __name__ == "__main__":
    unittest.main()
