import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import PATHS, FakeRunner, fake_jev, make_config, make_locker
from zjm_rag import ZjmError, doctor, find
from zjm_rag import config as config_module
from zjm_rag import lockers as lockers_mod
from zjm_rag import translate as translate_module
from zjm_rag import zg


def _make_multi_locker(cfg, name, files):
    """A plain locker under cfg["home"]/lockers/<name>, indexed, with the given {relpath: text}."""
    ldir = lockers_mod.locker_dir(cfg, name)
    (ldir / "corpus").mkdir(parents=True)
    (ldir / "zghome").mkdir(parents=True)
    manifest_files = {}
    for rel, text in files.items():
        p = ldir / "corpus" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        manifest_files[rel] = {"source": f"/src/{rel}", "size": p.stat().st_size, "sha256": "x", "added": 0}
    lockers_mod.write_manifest(ldir, {"name": name, "embedding": "m", "indexed": True, "files": manifest_files})
    return ldir


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

        argv = zg.query_argv_translations(translations)
        self.assertIn("--hybrid=-flag-like translation", argv)

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
        original_out = ("hits: 2\n"
                        "\n#1 matchedBy=fts+vector proj/b.md:1-1\nsource:\n1\tb line1\n"
                        "\n#2 matchedBy=fts+vector proj/a.py:1-1\nsource:\n1\ta line1\n")
        translated_out = ("hits: 3\n"
                          "\n#1 matchedBy=fts+vector proj/c.txt:1-1\nsource:\n1\tc line1\n"
                          "\n#2 matchedBy=fts+vector proj/b.md:3-3\nsource:\n3\tb line3\n"
                          "\n#3 matchedBy=fts+vector proj/d.md:1-1\nsource:\n1\td line1\n")
        cfg = make_config(self, egress={"rank": False, "answer": False, "translate": True})
        _make_multi_locker(cfg, "lib", {"proj/b.md": "b line1\nb line2\nb line3\nb line4\n",
                                        "proj/a.py": "a line1\n", "proj/c.txt": "c line1\n",
                                        "proj/d.md": "d line1\n"})
        calls = []

        def runner(argv, *, cwd, env, input=None):
            calls.append(argv)
            if any(a.startswith("--hybrid=") for a in argv):
                return 0, translated_out, ""
            return 0, original_out, ""

        def llm(model, messages, reasoning=True):
            return json.dumps({"German": "kaffeemaschine frage", "Danish": "kaffe maskine spoergsmaal"})

        def jev_fail(payload):
            raise AssertionError("jev should not be called")

        r = find("q", ["lib"], limit=2, runner=runner, jev=jev_fail, llm=llm, config=cfg)
        self.assertEqual([(h["path"], h["via"]) for h in r["accepted"]],
                         [("proj/b.md", "query"), ("proj/a.py", "query"),
                          ("proj/c.txt", "translation"), ("proj/d.md", "translation")])
        self.assertEqual(r["rejected"], [])
        b_hit = r["accepted"][0]
        self.assertEqual({(p["start"], p["end"]) for p in b_hit["passages"]}, {(1, 1), (3, 3)})

        self.assertEqual(calls[0][-2:], ["--", "q"])
        hybrid_flags = [a for a in calls[1] if a.startswith("--hybrid=")]
        self.assertEqual(len(hybrid_flags), 2)
        self.assertIn("--fuse", calls[1])

    def test_merge_query_candidates_first(self):
        cfg = make_config(self, egress={"rank": False, "answer": False, "translate": True})
        _make_multi_locker(cfg, "lib1", {"q1a.md": "qa1\n", "q1b.md": "qa2\n", "t1a.md": "ta1\n",
                                         "t1b.md": "ta2\n"})
        _make_multi_locker(cfg, "lib2", {"q2a.md": "qb1\n", "t2a.md": "tb1\n"})
        lib1_corpus = str(lockers_mod.locker_dir(cfg, "lib1") / "corpus")
        lib2_corpus = str(lockers_mod.locker_dir(cfg, "lib2") / "corpus")
        outs = {
            (lib1_corpus, False): "hits: 2\n\n#1 matchedBy=fts q1a.md:1-1\nsource:\n1\tqa1\n"
                                 "\n#2 matchedBy=fts q1b.md:1-1\nsource:\n1\tqa2\n",
            (lib1_corpus, True): "hits: 2\n\n#1 matchedBy=fts t1a.md:1-1\nsource:\n1\tta1\n"
                                "\n#2 matchedBy=fts t1b.md:1-1\nsource:\n1\tta2\n",
            (lib2_corpus, False): "hits: 1\n\n#1 matchedBy=fts q2a.md:1-1\nsource:\n1\tqb1\n",
            (lib2_corpus, True): "hits: 1\n\n#1 matchedBy=fts t2a.md:1-1\nsource:\n1\ttb1\n",
        }

        def runner(argv, *, cwd, env, input=None):
            is_translated = any(a.startswith("--hybrid=") for a in argv)
            return 0, outs[(cwd, is_translated)], ""

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
