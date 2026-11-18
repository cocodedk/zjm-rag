import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import PATHS, FakeRunner, fake_jev, make_config, make_locker, make_multi_locker
from zjm_rag import ZjmError, doctor, find
from zjm_rag import config as config_module
from zjm_rag import engine
from zjm_rag import lockers as lockers_mod
from zjm_rag import translate as translate_module


class TranslateTest(unittest.TestCase):
    def test_translate_parses_and_filters(self):
        calls = []
        query = "When is the coffee machine descaled?"
        values = {
            "English": "find the coffee rota",
            "German": "Wann wird die Kaffeemaschine entkalkt?",
            "Danish": "wann   wird DIE kaffeemaschine entkalkt?",  # duplicate of German
            "Norwegian": "-flag-like translation",  # starts with '-', kept
            "Swedish": "",  # empty
            "Finnish": "x" * 501,  # over 500 chars
            "Icelandic": " WHEN is the   coffee machine descaled?  ",  # equals the query
            "Dutch": "one more kept value",
        }
        reply = "Sure, here you go:\n```json\n" + json.dumps(values) + "\n```"

        def llm(model, messages, reasoning=True):
            calls.append((model, messages, reasoning))
            return reply

        languages = list(values)
        translations, error = translate_module.translate(query, languages, "upstage/solar-mini4", llm=llm)
        self.assertIsNone(error)
        self.assertEqual(translations, ["find the coffee rota", "Wann wird die Kaffeemaschine entkalkt?",
                                        "-flag-like translation", "one more kept value"])

        self.assertEqual(len(calls), 1)
        model, messages, reasoning = calls[0]
        self.assertEqual(model, "upstage/solar-mini4")
        self.assertFalse(reasoning)
        self.assertEqual(messages[1], {"role": "user", "content": query})
        for lang in languages:
            self.assertIn(lang, messages[0]["content"])

        stdin = json.loads(engine.query_input(query, translations))
        self.assertEqual(stdin["translations"], translations)
        self.assertNotIn("-flag-like translation", " ".join(engine.query_argv("local/m", "i")))

    def test_translate_failure_never_raises(self):
        def raising_llm(model, messages, reasoning=True):
            raise ZjmError("boom question=When is x? key=sk-should-not-appear")

        translations, error = translate_module.translate("q", ["English", "German"], "m", llm=raising_llm)
        self.assertEqual((translations, error), ([], "translation request failed"))

        def bad_json_llm(model, messages, reasoning=True):
            return "not json"

        translations2, error2 = translate_module.translate("q", ["English"], "m", llm=bad_json_llm)
        self.assertEqual((translations2, error2), ([], "translation reply not usable"))

        cfg = make_config(self, egress={"rank": True, "answer": True, "translate": True})
        make_locker(self, cfg, "lib")
        r = find("q", ["lib"], runner=FakeRunner(), jev=fake_jev([0.9, 0.2, 0.5]), llm=raising_llm, config=cfg)
        self.assertEqual(r["translations"], [])
        self.assertEqual(r["translate_error"], "translation request failed")
        self.assertEqual({h["path"] for h in r["accepted"] + r["rejected"]}, set(PATHS))

    def test_translate_egress_ceiling(self):
        cfg_off = make_config(self, egress={"rank": True, "answer": True})
        make_locker(self, cfg_off, "lib")

        def fail_llm(model, messages, reasoning=True):
            self.fail("llm called")

        r = find("q", ["lib"], runner=FakeRunner(), jev=fake_jev([0.9, 0.2, 0.5]), llm=fail_llm, config=cfg_off)
        self.assertEqual(r["translations"], [])
        self.assertIsNone(r["translate_error"])

        def fail_runner(argv, *, cwd, env, input=None):
            self.fail("runner called")

        with self.assertRaisesRegex(ZjmError, "translating sends the question to OpenRouter"):
            find("q", ["lib"], translate=True, runner=fail_runner, jev=fake_jev([]), llm=fail_llm, config=cfg_off)

        cfg_on = make_config(self, egress={"rank": True, "answer": True, "translate": True})
        make_locker(self, cfg_on, "lib")
        r2 = find("q", ["lib"], translate=False, runner=FakeRunner(), jev=fake_jev([0.9, 0.2, 0.5]), llm=fail_llm,
                  config=cfg_on)
        self.assertEqual(r2["translations"], [])
        self.assertIsNone(r2["translate_error"])

    def test_translations_only_add_candidates(self):
        r, _calls = self._find_with_translations()
        self.assertEqual([(h["path"], h["via"]) for h in r["accepted"]],
                         [("proj/b.md", "query"), ("proj/a.py", "query"),
                          ("proj/c.txt", "translation"), ("proj/d.md", "translation")])
        self.assertEqual(r["rejected"], [])

    def test_find_makes_one_engine_call_with_translations(self):
        _r, calls = self._find_with_translations()
        self.assertEqual(len(calls), 1)
        argv, stdin = calls[0]
        self.assertNotIn("when?", " ".join(argv))
        self.assertEqual(json.loads(stdin), {"question": "when?",
                                             "translations": ["kaffeemaschine frage", "kaffe maskine spoergsmaal"]})

    def _find_with_translations(self):
        group = lambda paths: [{"path": p, "start": 1, "end": 1, "rank": i} for i, p in enumerate(paths, 1)]
        out = json.dumps({"query": group(["proj/b.md", "proj/a.py"]),
                          "translation": group(["proj/c.txt", "proj/d.md"])})
        cfg = make_config(self, egress={"rank": False, "answer": False, "translate": True})
        make_multi_locker(cfg, "lib", {"proj/b.md": "b line1\nb line2\n", "proj/a.py": "a line1\n",
                                       "proj/c.txt": "c line1\n", "proj/d.md": "d line1\n"})
        calls = []

        def runner(argv, *, cwd, env, input=None):
            calls.append((argv, input))
            return 0, out, ""

        def llm(model, messages, reasoning=True):
            return json.dumps({"German": "kaffeemaschine frage", "Danish": "kaffe maskine spoergsmaal"})

        def jev_fail(payload):
            raise AssertionError("jev should not be called")

        return find("when?", ["lib"], limit=2, runner=runner, jev=jev_fail, llm=llm, config=cfg), calls

    def test_merge_query_candidates_first(self):
        cfg = make_config(self, egress={"rank": False, "answer": False, "translate": True})
        make_multi_locker(cfg, "lib1", {"q1a.md": "qa1\n", "q1b.md": "qa2\n", "t1a.md": "ta1\n",
                                        "t1b.md": "ta2\n"})
        make_multi_locker(cfg, "lib2", {"q2a.md": "qb1\n", "t2a.md": "tb1\n"})

        def hits(paths):
            return [{"path": p, "start": 1, "end": 1, "rank": i} for i, p in enumerate(paths, 1)]

        outs = {
            str(lockers_mod.locker_dir(cfg, "lib1")): {"query": hits(["q1a.md", "q1b.md"]),
                                                       "translation": hits(["t1a.md", "t1b.md"])},
            str(lockers_mod.locker_dir(cfg, "lib2")): {"query": hits(["q2a.md"]), "translation": hits(["t2a.md"])},
        }

        def runner(argv, *, cwd, env, input=None):
            return 0, json.dumps(outs[cwd]), ""

        def llm(model, messages, reasoning=True):
            return json.dumps({"German": "frage"})

        def jev_fail(payload):
            raise AssertionError("jev should not be called")

        r = find("q", ["lib1", "lib2"], limit=2, runner=runner, jev=jev_fail, llm=llm, config=cfg)
        got = [(h["locker"], h["path"], h["via"]) for h in r["accepted"]]
        self.assertEqual(got, [("lib1", "q1a.md", "query"), ("lib2", "q2a.md", "query"),
                               ("lib1", "t1a.md", "translation"), ("lib2", "t2a.md", "translation")])
        self.assertEqual([h["zg_rank"] for h in r["accepted"]], [1, 2, 3, 4])

    def test_config_translate_keys(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        environ = {"HOME": str(Path(tmp.name) / "home")}
        cfg = config_module.load(cwd=str(Path(tmp.name) / "nowhere"), environ=environ)
        self.assertEqual(cfg["egress"]["translate"], False)
        self.assertEqual(cfg["languages"], ["English", "German", "Danish", "Norwegian", "Swedish"])
        self.assertEqual(cfg["translate_model"], "upstage/solar-mini4")

        bad_languages = Path(tmp.name) / "bad_languages.json"
        bad_languages.write_text(json.dumps({"languages": "not-a-list"}))
        with self.assertRaises(ZjmError):
            config_module.load(str(bad_languages), environ=environ)

        bad_model = Path(tmp.name) / "bad_model.json"
        bad_model.write_text(json.dumps({"translate_model": ""}))
        with self.assertRaises(ZjmError):
            config_module.load(str(bad_model), environ=environ)

        cfg2 = make_config(self, egress={"rank": False, "answer": False, "translate": False})
        with mock.patch("shutil.which", return_value="/usr/bin/x"):
            r = doctor(config=cfg2)
        self.assertIn("translate", r["egress"])


if __name__ == "__main__":
    unittest.main()
