"""find and ask take the caller's translations (spec 22)."""
import contextlib
import io
import json
import os
import unittest
from unittest import mock

from fakes import FakeRunner, fake_jev, fake_llm, make_config, make_locker

from zjm_rag import ZjmError, ask, find, ops
from zjm_rag.cli import main

REPLY = json.dumps({"German": {"translation": "wann kaffee", "reworded": "zeitpunkt kaffee"}})
OVER = "x" * 501


def stdin_of(runner):
    (call,) = [c for c in runner.calls if c[0][0] == "zjm-engine"]
    return json.loads(call[3])


def no_llm(model, messages, reasoning=True):
    raise AssertionError("llm called")


class CallerTranslationsTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_config(self, egress={"rank": True, "answer": True, "translate": True}, languages=["German"])
        make_locker(self, self.cfg, "lib")

    def _find(self, **kw):
        runner = FakeRunner()
        kw.setdefault("llm", no_llm)
        r = find("when coffee?", ["lib"], runner=runner, jev=fake_jev([0.9, 0.2, 0.6]), config=self.cfg, **kw)
        return r, stdin_of(runner)

    def test_same_search_as_zjm_translating(self):
        llm = fake_llm(REPLY)
        own, own_in = self._find(translate=True, llm=llm)
        texts = own["translations"]
        self.assertTrue(texts)
        given, given_in = self._find(translations=texts)
        self.assertEqual(given_in, own_in)
        for key in ("accepted", "rejected", "translations"):
            self.assertEqual(given[key], own[key], key)
        self.assertIsNone(given["translate_error"])
        self.assertEqual(len(llm.calls), 1)

    def test_no_egress_needed(self):
        self.cfg = make_config(self, egress={"rank": True, "answer": True, "translate": False})
        make_locker(self, self.cfg, "lib")
        r, body = self._find(translations=["a", "b"])
        self.assertEqual(body["translations"], ["a", "b"])
        self.assertEqual((r["translations"], r["translate_error"]), (["a", "b"], None))

    def test_empty_list_makes_no_call(self):
        r, body = self._find(translations=[])
        self.assertEqual((body["translations"], r["translations"]), ([], []))

    def test_ask_passes_translations(self):
        runner, llm = FakeRunner(), fake_llm("the answer")
        r = ask("q", ["lib"], translations=["t1"], runner=runner, jev=fake_jev([0.9, 0.2, 0.6]), llm=llm,
                config=self.cfg)
        self.assertEqual(stdin_of(runner)["translations"], ["t1"])
        self.assertEqual(r["find"]["translations"], ["t1"])
        self.assertEqual(len(llm.calls), 1)  # the answer only, no translation call

    def test_refusals(self):
        cases = [({"translations": ["a"], "translate": True}, "not both"), ({"translations": "a"}, "list"),
                 ({"translations": ("a",)}, "list"), ({"translations": [1]}, "list"),
                 ({"translations": ["a"] * 17}, "at most 16"), ({"translations": [""]}, "not blank"),
                 ({"translations": [" \t"]}, "not blank"), ({"translations": [OVER]}, "500")]
        for op in (find, ask):
            for kw, message in cases:
                with self.subTest(op=op.__name__, kw=kw):
                    runner, llm = FakeRunner(), fake_llm("x")
                    with self.assertRaisesRegex(ZjmError, message):
                        op("q", ["lib"], runner=runner, jev=fake_jev([]), llm=llm, config=self.cfg, **kw)
                    self.assertEqual((runner.calls, llm.calls), ([], []))
        with self.subTest("before the config is read"):
            with self.assertRaisesRegex(ZjmError, "not both"):
                find("q", [], translations=[], translate=True, config={"home": 1})

    def test_surfaces(self):
        base = {"query": "q", "lockers": ["lib"]}
        for op in ("find", "ask"):
            self.assertIsNone(ops.check(op, {**base, "translations": ["a"]}), op)
            for bad in ("a", [1], [["a"]]):
                self.assertEqual(ops.check(op, {**base, "translations": bad}), "translations must match schema")
        runner = FakeRunner()
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = main(["find", "q", "-l", "lib", "--config", self.cfg["path"], "--json",
                         "--translation", "a", "--translation", "b"], runner=runner, jev=fake_jev([0.9, 0.2, 0.1]),
                        llm=no_llm)
        self.assertEqual(code, 0)
        self.assertEqual(stdin_of(runner)["translations"], ["a", "b"])
