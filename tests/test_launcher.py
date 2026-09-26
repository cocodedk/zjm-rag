"""bin/zjm in dry run, with a stub PATH and a temp host config; never runs docker (spec 07)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "bin" / "zjm"


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stub_path = self.root / "stubpath"
        self.stub_path.mkdir()
        real_python3 = shutil.which("python3")
        (self.stub_path / "python3").symlink_to(real_python3)
        self.conf_dir = self.root / "conf"
        self.conf_dir.mkdir()
        self.config_path = self.conf_dir / "config.json"

    def write_config(self, egress):
        self.config_path.write_text(json.dumps({"egress": egress}))

    def make_source(self, name):
        d = self.root / "src" / name
        d.mkdir(parents=True)
        return d

    def run_launcher(self, args, *, sources=(), env_extra=None):
        env = {"PATH": str(self.stub_path), "HOME": str(self.root),
               "ZJM_HOST_CONFIG": str(self.config_path), "ZJM_LAUNCH_DRY_RUN": "1"}
        if sources:
            env["ZJM_SOURCES"] = ":".join(str(s) for s in sources)
        if env_extra:
            env.update(env_extra)
        return subprocess.run([shutil.which("sh"), str(SCRIPT)] + args, env=env,
                              capture_output=True, text=True, timeout=30)

    def test_offline_argv(self):
        self.write_config({"rank": False, "answer": False})
        src = self.make_source("docs")
        r = self.run_launcher(["find", "q", "-l", "lib"], sources=[src])
        self.assertEqual(r.returncode, 0, r.stderr)
        line = r.stdout.strip()
        self.assertTrue(line.startswith("+ docker run"))
        self.assertIn("--network none", line)
        self.assertIn("--read-only", line)
        self.assertIn("--cap-drop=ALL", line)
        self.assertIn("-v zjm-data:/data", line)
        self.assertIn(f"-v {self.config_path}:/etc/zjm/config.json:ro", line)
        self.assertIn(f"-v {src}:/sources/docs:ro", line)
        self.assertNotIn(" -e ", line)
        self.assertTrue(line.endswith("zjm-rag:latest find q -l lib"))

    def test_online_serve_argv(self):
        self.write_config({"rank": True, "answer": True})
        r = self.run_launcher(["serve"])
        self.assertEqual(r.returncode, 0, r.stderr)
        line = r.stdout.strip()
        self.assertIn("-p 127.0.0.1:8765:8765", line)
        self.assertIn("-e OPENROUTER_API_KEY", line)
        self.assertIn("-e ANTHROPIC_API_KEY", line)
        self.assertNotIn("--network none", line)
        self.assertTrue(line.endswith("zjm-rag:latest serve --host 0.0.0.0 --port 8765"))

    def test_serve_offline_refused_and_bad_sources(self):
        self.write_config({"rank": False, "answer": False})
        r = self.run_launcher(["serve"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("HTTP needs egress on, or use MCP", r.stderr)

        missing = self.root / "src" / "nope"
        r = self.run_launcher(["find", "q", "-l", "lib"], sources=[missing])
        self.assertEqual(r.returncode, 1)
        self.assertIn("source directory not found", r.stderr)


if __name__ == "__main__":
    unittest.main()
