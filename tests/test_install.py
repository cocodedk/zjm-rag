"""install.sh in dry run, with a PATH of stub scripts; the only test that starts a subprocess (sh)."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "install.sh"


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

    def test_builds_from_local_checkout_and_installs_launcher(self):
        out = self.install("docker", "python3")
        self.assertIn(f"+ docker build -t zjm-rag:latest {ROOT}", out)
        self.assertTrue(any(line.startswith("+ cp ") and line.endswith("/bin/zjm") for line in out))
        self.assertTrue(any(line.startswith("+ chmod +x ") for line in out))

    def test_fails_without_docker(self):
        r = self.run_script("python3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("docker", r.stderr)

    def test_fails_without_python3(self):
        r = self.run_script("docker")
        self.assertEqual(r.returncode, 1)
        self.assertIn("python3", r.stderr)


if __name__ == "__main__":
    unittest.main()
