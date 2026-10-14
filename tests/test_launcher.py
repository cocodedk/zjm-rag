"""bin/zjm in dry run, with a stub PATH and a temp host config; never runs docker (spec 07)."""
import json
import shlex
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
        return subprocess.run([shutil.which("python3"), str(SCRIPT)] + args, env=env,
                              capture_output=True, text=True, check=False, timeout=30)

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
        self.assertIn("/config.json:/etc/zjm/config.json:ro", line)
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
        self.assertNotIn("ANTHROPIC_API_KEY", line)
        self.assertNotIn("--network none", line)
        self.assertTrue(line.endswith("zjm-rag:latest serve --host 0.0.0.0 --port 8765"))

        # Either egress switch alone is still enough for -e OPENROUTER_API_KEY.
        self.write_config({"rank": True, "answer": False})
        r2 = self.run_launcher(["find", "q", "-l", "lib"])
        self.assertIn("-e OPENROUTER_API_KEY", r2.stdout)
        self.write_config({"rank": False, "answer": True})
        r3 = self.run_launcher(["find", "q", "-l", "lib"])
        self.assertIn("-e OPENROUTER_API_KEY", r3.stdout)
        r4 = self.run_launcher(["find", "q", "-l", "lib"], env_extra={"JEV_MODEL": "custom"})
        self.assertIn("-e JEV_MODEL", r4.stdout)

    def test_translate_only_egress(self):
        self.write_config({"rank": False, "answer": False, "translate": True})
        r = self.run_launcher(["find", "q", "-l", "lib"])
        self.assertEqual(r.returncode, 0, r.stderr)
        line = r.stdout.strip()
        self.assertNotIn("--network none", line)
        self.assertIn("-e OPENROUTER_API_KEY", line)

    def test_serve_offline_refused_and_bad_sources(self):
        self.write_config({"rank": False, "answer": False})
        r = self.run_launcher(["serve"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("HTTP needs egress on, or use MCP", r.stderr)

        missing = self.root / "src" / "nope"
        r = self.run_launcher(["find", "q", "-l", "lib"], sources=[missing])
        self.assertEqual(r.returncode, 1)
        self.assertIn("source directory not found", r.stderr)

    def test_paths_keys_and_serve_options(self):
        self.write_config({"rank": True})
        source = self.make_source("my docs")
        key = self.root / "my key.txt"
        key.write_text("not-a-real-key")
        r = self.run_launcher(["file-put", "lib", "note", "--key-file", str(key)], sources=[source])
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = shlex.split(r.stdout[2:])
        self.assertIn(f"{source}:/sources/my docs:ro", argv)
        self.assertTrue(any(arg.endswith("/key:/run/zjm-key:ro") for arg in argv))
        self.assertEqual(argv[-2:], ["--key-file", "/run/zjm-key"])
        self.assertNotIn("not-a-real-key", r.stdout)
        r = self.run_launcher(["serve", "--config", str(self.config_path), "--port", "9000"])
        argv = shlex.split(r.stdout[2:])
        self.assertIn("127.0.0.1:9000:9000", argv)
        self.assertEqual(argv[-4:], ["--config", "/etc/zjm/config.json", "--port", "9000"])
        r = self.run_launcher(["find", "q", "-l", "lib", "--key-file=-"])
        self.assertIn("--key-file=-", r.stdout)
        self.assertNotIn("/run/zjm-key", r.stdout)

    def test_private_mounts_readable_and_cleaned(self):
        self.write_config({})
        self.config_path.chmod(0o600)
        key = self.root / "private.key"
        key.write_text("secret-test-key")
        key.chmod(0o600)
        docker = self.stub_path / "docker"
        docker.write_text("#!/usr/bin/env python3\n"
                          "import json, pathlib, sys\n"
                          "mounts = [a for a in sys.argv if a.endswith(':ro') and "
                          "('/etc/zjm/config.json' in a or '/run/zjm-key' in a)]\n"
                          "for mount in mounts:\n"
                          "    p = pathlib.Path(mount.split(':')[0])\n"
                          "    assert p.stat().st_mode & 0o777 == 0o444\n"
                          "    assert p.parent.stat().st_mode & 0o777 == 0o700\n"
                          "    assert p.read_bytes()\n"
                          "print(json.dumps(mounts))\n")
        docker.chmod(0o755)
        r = self.run_launcher(["file-list", "lib", "--key-file", str(key)],
                              env_extra={"ZJM_LAUNCH_DRY_RUN": "0"})
        self.assertEqual(r.returncode, 0, r.stderr)
        for mount in json.loads(r.stdout):
            self.assertFalse(Path(mount.split(":")[0]).exists())
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o600)
        self.write_config({"rank": True})
        r = self.run_launcher(["serve", "--host", "127.0.0.1"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("published port is loopback-only", r.stderr)


if __name__ == "__main__":
    unittest.main()
