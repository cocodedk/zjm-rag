"""Shared setup for the skill tests: a project, a stub zjm that records its config and the files it is given."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills/zjm-rag/scripts"
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # a git hook's GIT_DIR must not leak in


class SkillBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        stub = self.tmp / "bin/zjm"  # one locker, "other", exists; every config zjm receives is appended to configs
        stub.parent.mkdir()
        stub.write_text('#!/bin/sh\ncat "$ZJM_HOST_CONFIG" >> "$HOME/configs"; echo >> "$HOME/configs"\n'
                        '[ "$1" = locker-list ] && echo "other  1 files  1 bytes"\n'
                        '[ "$1" = file-add ] && mkdir -p "$HOME/seen" && cp -R $(echo "$ZJM_SOURCES" | tr : " ") "$HOME/seen"'
                        ' && stat -c %a $(echo "$ZJM_SOURCES" | tr : " ") >> "$HOME/modes"\n'
                        'exit 0\n')
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

    def mirror(self, src, *extra):
        out = self.tmp / "mirror"
        self.last = subprocess.run([shutil.which("python3"), str(SKILL / "mirror.py"), str(src), str(out), *extra],
                                   env=CLEAN, check=True, timeout=30, capture_output=True, text=True)
        return sorted(p.name for p in out.rglob("*") if p.is_file())

    def seen(self):
        """What the stub zjm was given to index: every file under seen/, relative."""
        return sorted(str(p.relative_to(self.tmp / "seen")) for p in (self.tmp / "seen").rglob("*") if p.is_file())
