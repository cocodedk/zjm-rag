"""install.sh in dry run, with a PATH of stub scripts; the only test that starts a subprocess (sh)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "install.sh"
REPO = "git+https://github.com/cocodedk/zjm-rag"


class InstallTest(unittest.TestCase):
    def run_script(self, *stubs, dry_run=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name in stubs:
            stub = Path(tmp.name) / name
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
        env = {"PATH": tmp.name, "HOME": tmp.name}
        if dry_run:
            env["ZJM_INSTALL_DRY_RUN"] = "1"
        return subprocess.run([shutil.which("sh"), str(SCRIPT)], env=env, capture_output=True, text=True,
                              timeout=30)

    def install(self, *stubs):
        r = self.run_script(*stubs)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.splitlines()

    def test_prefers_uv_and_installs_zg(self):
        out = self.install("python3", "npm", "uv")
        self.assertIn("+ npm install -g @zvec/zvec-grep", out)
        self.assertIn(f"+ uv tool install --force {REPO}", out)
        self.assertIn("+ zjm doctor", out)
        self.assertFalse(any("pip" in line for line in out))

    def test_pip_fallback(self):
        out = self.install("python3", "zg")
        self.assertIn(f"+ python3 -m pip install --user {REPO}", out)
        self.assertFalse(any("npm" in line for line in out))
        self.assertTrue(any("OPENROUTER_API_KEY" in line for line in out))
        out = self.install("python3", "zg", "pipx")
        self.assertIn(f"+ pipx install --force {REPO}", out)
        self.assertFalse(any("pip install --user" in line for line in out))

    def test_fails_when_zjm_missing(self):
        r = self.run_script("python3", "zg", "uv", dry_run=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("PATH", r.stderr)


if __name__ == "__main__":
    unittest.main()
