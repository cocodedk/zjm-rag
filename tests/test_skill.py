"""The skill's zjm-project wrapper and mirror, against a stub zjm that records each config it is given."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills/zjm-rag/scripts"
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # a git hook's GIT_DIR must not leak in


class SkillTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        stub = self.tmp / "bin/zjm"  # one locker, "other", exists; every config zjm receives is appended to configs
        stub.parent.mkdir()
        stub.write_text('#!/bin/sh\ncat "$ZJM_HOST_CONFIG" >> "$HOME/configs"; echo >> "$HOME/configs"\n'
                        '[ "$1" = locker-list ] && echo "other  1 files  1 bytes"\nexit 0\n')
        stub.chmod(0o755)
        self.project = self.tmp / "project"
        (self.project / "docs").mkdir(parents=True)

    def run_script(self, *args, settings=None, **env):
        (self.project / "zjm-project.json").write_text(json.dumps(settings or {"locker": "mine", "folders": ["docs"]}))
        env = {**CLEAN, "PATH": f"{self.tmp / 'bin'}{os.pathsep}{os.defpath}", "HOME": str(self.tmp),
               "XDG_CACHE_HOME": str(self.tmp / "cache"), **env}
        return subprocess.run([shutil.which("python3"), str(SKILL / "zjm-project"), *args], cwd=self.project, env=env,
                              capture_output=True, text=True, check=False, timeout=30)

    def configs(self):
        return [json.loads(c) for c in (self.tmp / "configs").read_text().split("\n") if c]

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

    def test_refuses_a_config_override_on_the_command_line(self):
        self.assertEqual(self.run_script("reindex").returncode, 0)
        for args in (["--config", "/x.json"], ["--config=/x.json"]):
            r = self.run_script("find", "who approves?", *args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("--config", r.stderr)

    def mirror(self, src):
        out = self.tmp / "mirror"
        subprocess.run([shutil.which("python3"), str(SKILL / "mirror.py"), str(src), str(out)], env=CLEAN, check=True,
                       timeout=30)
        return sorted(p.name for p in out.rglob("*") if p.is_file())

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
