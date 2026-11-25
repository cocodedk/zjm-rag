"""Spec 21: file_put_many writes many texts and removes files in one locker session, with one index run."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import (
    TEST_KEY,
    FakeRunner,
    make_config,
    make_encrypted_locker,
    make_locker,
    make_multi_locker,
)

from zjm_rag import ZjmError, file_list, file_put, file_put_many, lockers, sealed

BIG = "x" * ((1 << 20) + 1)
REFUSALS = [  # (files, remove, message)
    ([], [], "nothing to put or remove"),
    ([{"name": "a.md"}], [], "exactly a string name and a string text"),
    ([{"name": "a.md", "text": "1"}, {"name": "a.md", "text": "2"}], [], "'a.md' is given twice"),
    ([{"name": "../a.md", "text": "1"}], [], "bad file name: '../a.md'"),
    ([{"name": "big.md", "text": BIG}], [], "text for 'big.md' exceeds 1 MiB"),
    ([{"name": "proj", "text": "1"}], ["proj/b.md"], "'proj' clashes with a file or folder already in locker lib"),
    ([{"name": "proj/a.py/x", "text": "1"}], [], "'proj/a.py/x' clashes with a file or folder already"),
    ([{"name": "a", "text": "1"}, {"name": "a/b.md", "text": "2"}], [], "'a/b.md' clashes with another file in this call"),
]


def index_runs(runner):
    return sum(1 for argv, *_ in runner.calls if argv[:2] == ["zjm-engine", "index"])


def seals(runner):
    return sum(1 for argv, *_ in runner.calls if argv[0] == "age" and "-o" in argv)


def put(*names):
    return [{"name": n, "text": f"text of {n}"} for n in names]


class FilePutManyTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(sealed, "TMP_ROOT", Path(tmp.name) / "zjm-tmp")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = make_config(self)
        self.runner = FakeRunner()

    def test_one_session(self):
        make_encrypted_locker(self, self.cfg, "lib")
        r = file_put_many("lib", put("n/1.md", "n/2.md", "3.md"), TEST_KEY, config=self.cfg, runner=self.runner)
        self.assertEqual(r, {"added": ["n/1.md", "n/2.md", "3.md"], "replaced": [], "removed": []})
        self.assertEqual((index_runs(self.runner), seals(self.runner)), (1, 1))
        listed = {f["name"]: f for f in file_list("lib", TEST_KEY, config=self.cfg, runner=FakeRunner())["files"]}
        for f in put("n/1.md", "n/2.md", "3.md"):
            data = f["text"].encode()
            self.assertEqual((listed[f["name"]]["size"], listed[f["name"]]["sha256"]),
                             (len(data), hashlib.sha256(data).hexdigest()))
        self.assertEqual(len(listed), 6)
        make_locker(self, self.cfg, "plain")
        runner = FakeRunner()
        file_put_many("plain", put("a.md", "b.md", "c.md"), config=self.cfg, runner=runner)
        self.assertEqual(index_runs(runner), 1)

    def test_put_and_remove_together(self):
        ldir = make_multi_locker(self.cfg, "lib", {"p1/a.md": "a", "p1/b.md": "b", "p2/c.md": "c"})
        r = file_put_many("lib", [{"name": "p1/a.md", "text": "new"}, {"name": "p3/d.md", "text": "d"}],
                          remove=["p1/b.md", "p2", "gone.md"], config=self.cfg, runner=self.runner)
        self.assertEqual(r, {"added": ["p3/d.md"], "replaced": ["p1/a.md"], "removed": ["p1/b.md", "p2"]})
        names = [f["name"] for f in file_list("lib", config=self.cfg)["files"]]
        self.assertEqual(names, ["p1/a.md", "p3/d.md"])
        self.assertEqual((ldir / "corpus/p1/a.md").read_text(), "new")
        self.assertFalse((ldir / "corpus/p2").exists())
        self.assertEqual(index_runs(self.runner), 1)

    def test_removed_then_put(self):
        ldir = make_multi_locker(self.cfg, "lib", {"x.md": "old", "p/q.md": "q"})
        r = file_put_many("lib", [{"name": "x.md", "text": "new"}, {"name": "p", "text": "p"}], remove=["x.md", "p"],
                          config=self.cfg, runner=self.runner)
        self.assertEqual(r, {"added": ["x.md", "p"], "replaced": [], "removed": ["x.md", "p"]})
        self.assertEqual((ldir / "corpus/x.md").read_text(), "new")
        self.assertEqual((ldir / "corpus/p").read_text(), "p")

    def test_removals_only(self):
        ldir = make_locker(self, self.cfg, "lib")
        before = snapshot(ldir)
        r = file_put_many("lib", [], remove=["gone.md"], config=self.cfg, runner=self.runner)
        self.assertEqual(r, {"added": [], "replaced": [], "removed": []})
        self.assertEqual(snapshot(ldir), before)

    def test_refusals_change_nothing(self):
        make_encrypted_locker(self, self.cfg, "lib")
        age = lockers.home_dirs(self.cfg)[1] / "lib.age"
        self._refuse_all(TEST_KEY, lambda: age.read_bytes())
        plain_cfg = make_config(self)
        ldir = make_locker(self, plain_cfg, "lib")
        self.cfg = plain_cfg
        self._refuse_all(None, lambda: snapshot(ldir))

    def _refuse_all(self, key, state):
        for files, remove, message in REFUSALS:
            with self.subTest(files=str(files)[:80], remove=remove, key=key is not None):
                before, runner = state(), FakeRunner()
                with self.assertRaisesRegex(ZjmError, message):
                    file_put_many("lib", files, key, remove=remove, config=self.cfg, runner=runner)
                self.assertEqual(state(), before)
                self.assertEqual(index_runs(runner), 0)

    def test_folder_on_disk_not_in_manifest(self):
        ldir = make_multi_locker(self.cfg, "lib", {"d/a.md": "a"})
        (ldir / "corpus/proj/empty").mkdir(parents=True)
        (ldir / "corpus/d/e").mkdir()
        before = snapshot(ldir)
        puts = [lambda n, r: file_put_many("lib", [{"name": n, "text": "x"}], remove=r, config=self.cfg,
                                           runner=self.runner)]
        puts.append(lambda n, r: file_put("lib", n, "x", config=self.cfg, runner=self.runner))
        for call in puts:
            for name, remove in (("proj/empty", []), ("proj", []), ("d", ["d/a.md"]), ("proj/empty", ["d/a.md"])):
                with self.subTest(name=name, remove=remove):
                    with self.assertRaisesRegex(ZjmError, f"'{name}' clashes with a file or folder already in locker lib"):
                        call(name, remove)
                    self.assertEqual(snapshot(ldir), before)
        self.assertEqual(index_runs(self.runner), 0)

    def test_file_put_delegates(self):
        make_locker(self, self.cfg, "lib")
        r = file_put("lib", "a.md", "hi", config=self.cfg, runner=self.runner)
        self.assertEqual(r, {"added": ["a.md"], "replaced": []})
        self.assertEqual(index_runs(self.runner), 1)

    def test_refusal_order_before_the_locker(self):
        for call in (lambda n, t: file_put("nope", n, t, config=self.cfg, runner=self.runner),
                     lambda n, t: file_put_many("nope", [{"name": n, "text": t}], config=self.cfg, runner=self.runner)):
            with self.assertRaisesRegex(ZjmError, "bad file name"):
                call("../a.md", "x")
            with self.assertRaisesRegex(ZjmError, "exceeds 1 MiB"):
                call("a.md", BIG)
            with self.assertRaisesRegex(ZjmError, "text for '../a.md' exceeds 1 MiB"):
                call("../a.md", BIG)
        with self.assertRaisesRegex(ZjmError, "bad file name: None"):
            file_put("nope", None, "x", config=self.cfg, runner=self.runner)
        self.assertEqual(self.runner.calls, [])


def snapshot(ldir):
    """Every path under the locker, with a file's bytes (None for a folder)."""
    return {p.relative_to(ldir).as_posix(): p.read_bytes() if p.is_file() else None for p in ldir.rglob("*")}
