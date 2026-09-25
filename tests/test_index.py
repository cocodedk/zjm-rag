import json
import tempfile
import unittest
from pathlib import Path

from zjm_rag import ZjmError, index


class FakeRunner:
    def __init__(self, code=0):
        self.calls, self.code = [], code

    def __call__(self, argv, *, cwd, env, input):
        self.calls.append((argv, cwd, env, input))
        return self.code, "", "boom"


def write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class IndexTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.src = self.tmp / "proj"
        self.store = self.tmp / "store"
        write(self.src / "README.md")
        write(self.src / "pkg/mod.py")
        write(self.src / ".githooks/pre-push")
        write(self.src / ".git/config")
        write(self.src / "node_modules/x/index.js")
        write(self.src / ".env")
        write(self.src / ".env.local")

    def test_copies_and_skips(self):
        result = index([self.src], store=self.store, runner=FakeRunner())
        copy = self.store / "corpus/proj"
        self.assertTrue((copy / ".githooks/pre-push").is_file())
        self.assertTrue((copy / "pkg/mod.py").is_file())
        for skipped in (".git", "node_modules", ".env", ".env.local"):
            self.assertFalse((copy / skipped).exists(), skipped)
        self.assertEqual(result["files"], 3)
        self.assertEqual(result["sources"], [str(self.src.resolve())])
        other = self.tmp / "elsewhere/proj"
        write(other / "only.md")
        for sources in ([other], [self.src, other]):
            with self.assertRaisesRegex(ZjmError, "basename clash"):
                index(sources, store=self.store, runner=FakeRunner())
        self.assertFalse((copy / "only.md").exists())
        victim = self.tmp / "victim"
        write(victim / "proj/keep.txt")
        planted = self.tmp / "planted"
        planted.mkdir()
        (planted / "corpus").symlink_to(victim)
        with self.assertRaisesRegex(ZjmError, "symlink"):
            index([self.src], store=planted, runner=FakeRunner())
        self.assertEqual([p.name for p in (victim / "proj").iterdir()], ["keep.txt"])

    def test_zg_argv_and_env(self):
        runner = FakeRunner()
        index([self.src], store=self.store, runner=runner)
        [(argv, cwd, env, stdin)] = runner.calls
        self.assertEqual(argv, ["zg", "index", ".", "--embedding", "local/potion-code-16m-v2",
                                "--mode", "direct", "--hidden"])
        self.assertEqual(cwd, str(self.store / "corpus"))
        self.assertEqual(env["ZVEC_GREP_HOME"], str(self.store / "zghome"))
        self.assertIsNone(stdin)
        self.assertEqual(json.loads((self.store / "zjm.json").read_text()),
                         {"sources": [str(self.src.resolve())], "embedding": "local/potion-code-16m-v2"})
        with self.assertRaises(ZjmError):
            index([self.src], store=self.store, runner=FakeRunner(code=1))

    def test_multilingual_picks_model(self):
        runner = FakeRunner()
        result = index([self.src], store=self.store, multilingual=True, runner=runner)
        self.assertIn("local/potion-multilingual-128m", runner.calls[0][0])
        self.assertEqual(result["embedding"], "local/potion-multilingual-128m")

    def test_model_change_needs_rebuild(self):
        index([self.src], store=self.store, runner=FakeRunner())
        runner = FakeRunner()
        with self.assertRaisesRegex(ZjmError, "rebuild=True"):
            index([self.src], store=self.store, multilingual=True, runner=runner)
        self.assertEqual(runner.calls, [])
        index([self.src], store=self.store, multilingual=True, rebuild=True, runner=runner)
        self.assertEqual(runner.calls[0][0][-1], "--rebuild")


if __name__ == "__main__":
    unittest.main()
