import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import FakeRunner, fake_jev, make_store
from zjm_rag.cli import main


def run(argv, **fakes):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, **fakes)
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.store = make_store(self)

    def test_index_json(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "docs"
        src.mkdir()
        (src / "a.md").write_text("x")
        code, out, _ = run(["index", str(src), "--store", str(Path(tmp.name) / "store"), "--json"],
                           runner=FakeRunner())
        self.assertEqual(code, 0)
        r = json.loads(out)
        self.assertEqual(set(r), {"store", "sources", "embedding", "files"})
        self.assertEqual(r["files"], 1)

    def test_find_json_passes_options(self):
        runner = FakeRunner()
        code, out, _ = run(["find", "q", "--store", str(self.store), "--json", "--min-score", "0.7",
                            "--sort", "path", "--type", "py"], runner=runner, jev=fake_jev([0.9, 0.8, 0.1]))
        self.assertEqual(code, 0)
        self.assertEqual(runner.calls[0][0][-2:], ["-t", "py"])
        r = json.loads(out)
        self.assertEqual((r["min_score"], r["sort"]), (0.7, "path"))
        self.assertEqual([h["path"] for h in r["accepted"]], ["proj/a.py", "proj/b.md"])

    def test_find_human_output(self):
        code, out, _ = run(["find", "q", "--store", str(self.store)], runner=FakeRunner(),
                           jev=fake_jev([0.9, 0.2, 0.5]))
        self.assertEqual(code, 0)
        self.assertEqual(out, "0.90  proj/b.md\n0.50  proj/c.txt\nrejected: 1 below 0.5\n")

    def test_ask_lang(self):
        runner = FakeRunner()
        code, out, _ = run(["ask", "q", "--store", str(self.store), "--lang", "da"], runner=runner,
                           jev=fake_jev([0.9, 0.2, 0.1]))
        self.assertEqual(code, 0)
        self.assertIn("Answer in da.", runner.calls[-1][3])
        self.assertEqual(out, "the answer\n\nsources: proj/b.md\n")

    def test_error_exit_and_json(self):
        empty = tempfile.TemporaryDirectory()
        self.addCleanup(empty.cleanup)
        argv = ["find", "q", "--store", empty.name]
        code, out, err = run(argv + ["--json"], runner=FakeRunner(), jev=fake_jev([]))
        self.assertEqual((code, err), (1, ""))
        self.assertIn("no index", json.loads(out)["error"])
        code, out, err = run(argv, runner=FakeRunner(), jev=fake_jev([]))
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("zjm: no index"))
        code, out, err = run(argv + ["--json", "--sort", "size"])
        self.assertEqual((code, out), (2, ""))
        self.assertIn("usage:", err)

    def test_doctor_hides_key(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret-value"}), \
                mock.patch("shutil.which", return_value="/usr/bin/x"):
            code, out, err = run(["doctor", "--store", str(self.store), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), {"ok": True, "checks": {"zg": True, "claude": True,
                                                                      "openrouter_key": True, "store": True}})
            human = run(["doctor", "--store", str(self.store)])
        self.assertEqual(human[:2], (0, "ok zg\nok claude\nok openrouter_key\nok store\n"))
        self.assertNotIn("secret-value", out + err + human[1] + human[2])
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("shutil.which", return_value=None):
            code, out, _ = run(["doctor", "--store", str(self.store)])
        self.assertEqual((code, out.splitlines()[0]), (1, "missing zg"))


if __name__ == "__main__":
    unittest.main()
