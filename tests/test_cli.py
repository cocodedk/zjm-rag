import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import FakeRunner, fake_jev, fake_llm, make_config, make_locker
from zjm_rag.cli import main


def run(argv, **fakes):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, **fakes)
    return code, out.getvalue(), err.getvalue()


def config_file(cfg_dict, tmp_dir):
    path = Path(tmp_dir) / "config.json"
    path.write_text(json.dumps(cfg_dict))
    return str(path)


class CliTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = make_config(self)
        make_locker(self, self.cfg, "lib")
        self.config_path = self.cfg["path"]

    def test_file_add_json(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "docs"
        src.mkdir()
        (src / "a.md").write_text("x")
        cfg_path = config_file({"allow": [tmp.name], "home": str(Path(tmp.name) / "home")}, tmp.name)
        code, out, _ = run(["locker-create", "lib", "--plain", "--config", cfg_path], runner=FakeRunner())
        self.assertEqual(code, 0)
        code, out, _ = run(["file-add", "lib", str(src), "--config", cfg_path, "--json"], runner=FakeRunner())
        self.assertEqual(code, 0)
        r = json.loads(out)
        self.assertEqual(set(r), {"added", "replaced", "excluded"})
        self.assertEqual(r["added"], ["docs"])

    def test_find_json_passes_options(self):
        runner = FakeRunner()
        code, out, _ = run(["find", "q", "-l", "lib", "--config", self.config_path, "--json",
                            "--min-score", "0.7", "--sort", "path", "--type", "py"],
                           runner=runner, jev=fake_jev([0.9, 0.8, 0.1]))
        self.assertEqual(code, 0)
        self.assertEqual(runner.calls[0][0][-4:], ["-t", "py", "--", "q"])
        r = json.loads(out)
        self.assertEqual((r["min_score"], r["sort"]), (0.7, "path"))
        self.assertEqual([h["path"] for h in r["accepted"]], ["proj/a.py", "proj/b.md"])

    def test_find_human_output(self):
        code, out, _ = run(["find", "q", "-l", "lib", "--config", self.config_path],
                           runner=FakeRunner(), jev=fake_jev([0.9, 0.2, 0.5]))
        self.assertEqual(code, 0)
        self.assertEqual(out, "0.90  lib/proj/b.md:1-1\n0.50  lib/proj/c.txt:1-1\nrejected: 1 below 0.5\n")

    def test_ask_lang(self):
        runner, llm = FakeRunner(), fake_llm("the answer")
        code, out, _ = run(["ask", "q", "-l", "lib", "--config", self.config_path, "--lang", "da"],
                           runner=runner, jev=fake_jev([0.9, 0.2, 0.1]), llm=llm)
        self.assertEqual(code, 0)
        self.assertIn("Answer in da.", llm.calls[-1][1][-1]["content"])
        self.assertEqual(out, "the answer\n\nsources: lib/proj/b.md\n")

    def test_error_exit_and_json(self):
        argv = ["find", "q", "-l", "nope", "--config", self.config_path]
        code, out, err = run(argv + ["--json"], runner=FakeRunner(), jev=fake_jev([]))
        self.assertEqual((code, err), (1, ""))
        self.assertIn("no locker", json.loads(out)["error"])
        code, out, err = run(argv, runner=FakeRunner(), jev=fake_jev([]))
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("zjm: no locker"))
        code, out, err = run(argv + ["--json", "--sort", "size"])
        self.assertEqual((code, out), (2, ""))
        self.assertIn("usage:", err)

    def test_doctor_hides_key(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret-value"}), \
                mock.patch("shutil.which", return_value="/usr/bin/x"):
            code, out, err = run(["doctor", "--config", self.config_path, "--json"])
            self.assertEqual(code, 0)
            r = json.loads(out)
            self.assertEqual(r["ok"], True)
            self.assertEqual(r["checks"], {"zg": True, "age": True, "openrouter_key": True})
            human = run(["doctor", "--config", self.config_path])
        self.assertEqual(human[0], 0)
        self.assertTrue(human[1].startswith("ok zg\nok age\nok openrouter_key\n"))
        self.assertNotIn("secret-value", out + err + human[1] + human[2])
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}, clear=True), \
                mock.patch("shutil.which", return_value=None):
            code, out, _ = run(["doctor", "--config", self.config_path])
        self.assertEqual((code, out.splitlines()[0]), (1, "missing zg"))


if __name__ == "__main__":
    unittest.main()
