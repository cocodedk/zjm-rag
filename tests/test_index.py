import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import make_config
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
        self.cfg = make_config(self, allow=[str(self.tmp)], home=str(self.tmp / "unused-home"))

    def test_copies_and_skips(self):
        result = index([self.src], store=self.store, runner=FakeRunner(), config=self.cfg)
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
                index(sources, store=self.store, runner=FakeRunner(), config=self.cfg)
        self.assertFalse((copy / "only.md").exists())
        victim = self.tmp / "victim"
        write(victim / "proj/keep.txt")
        planted = self.tmp / "planted"
        planted.mkdir()
        (planted / "corpus").symlink_to(victim)
        with self.assertRaisesRegex(ZjmError, "symlink"):
            index([self.src], store=planted, runner=FakeRunner(), config=self.cfg)
        self.assertEqual([p.name for p in (victim / "proj").iterdir()], ["keep.txt"])

    def test_zg_argv_and_env(self):
        runner = FakeRunner()
        index([self.src], store=self.store, runner=runner, config=self.cfg)
        argv, cwd, env, stdin = runner.calls[-1]
        self.assertEqual(argv, ["zg", "index", ".", "--embedding", "local/potion-code-16m-v2",
                                "--mode", "direct", "--hidden"])
        self.assertEqual(cwd, str(self.store / "corpus"))
        self.assertEqual(env["ZVEC_GREP_HOME"], str(self.store / "zghome"))
        self.assertIsNone(stdin)
        self.assertEqual(json.loads((self.store / "zjm.json").read_text()),
                         {"sources": [str(self.src.resolve())], "embedding": "local/potion-code-16m-v2"})
        with self.assertRaises(ZjmError):
            index([self.src], store=self.store, runner=FakeRunner(code=1), config=self.cfg)

    def test_multilingual_picks_model(self):
        runner = FakeRunner()
        result = index([self.src], store=self.store, multilingual=True, runner=runner, config=self.cfg)
        self.assertIn("local/potion-multilingual-128m", runner.calls[-1][0])
        self.assertEqual(result["embedding"], "local/potion-multilingual-128m")

    def test_model_change_needs_rebuild(self):
        index([self.src], store=self.store, runner=FakeRunner(), config=self.cfg)
        runner = FakeRunner()
        with self.assertRaisesRegex(ZjmError, "rebuild=True"):
            index([self.src], store=self.store, multilingual=True, runner=runner, config=self.cfg)
        self.assertEqual(runner.calls, [])
        index([self.src], store=self.store, multilingual=True, rebuild=True, runner=runner, config=self.cfg)
        self.assertEqual(runner.calls[-1][0][-1], "--rebuild")

    def test_foreign_store_refused(self):
        self.store.mkdir()
        runner = FakeRunner()
        with mock.patch("os.getuid", return_value=self.store.stat().st_uid + 1):
            with self.assertRaisesRegex(ZjmError, "owned by another user"):
                index([self.src], store=self.store, runner=runner, config=self.cfg)
        self.assertEqual(list(self.store.iterdir()), [])
        self.assertEqual(runner.calls, [])
        fresh = self.tmp / "fresh"
        index([self.src], store=fresh, runner=FakeRunner(), config=self.cfg)
        self.assertEqual(fresh.stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
