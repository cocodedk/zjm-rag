import json
import unittest

from fakes import make_config, make_multi_locker
from zjm_rag import find
from zjm_rag import translate as translate_module


def _llm_returning(reply, calls=None):
    def llm(model, messages, reasoning=True):
        if calls is not None:
            calls.append((model, messages, reasoning))
        return reply
    return llm


class RewordTest(unittest.TestCase):
    def test_reworded_follows_each_translation(self):
        query = "When is the coffee machine descaled?"
        values = {"English": {"translation": "  when IS the coffee   machine descaled?", "reworded": "E2"},
                  "German": {"translation": "G1", "reworded": "G2"}}
        calls = []
        llm = _llm_returning("Here:\n```json\n" + json.dumps(values) + "\n```", calls)
        result = translate_module.translate(query, ["English", "German"], "some/model", llm=llm)
        self.assertEqual(result, (["E2", "G1", "G2"], None))
        self.assertEqual(len(calls), 1)
        model, messages, reasoning = calls[0]
        self.assertEqual(model, "some/model")
        self.assertIs(reasoning, False)
        for word in ["English", "German", '"translation"', '"reworded"']:
            self.assertIn(word, messages[0]["content"])

    def test_reworded_bad_shapes(self):
        values = {"a": {"translation": "A1", "reworded": 7},
                  "b": {"reworded": "B2"},
                  "c": ["L1", "L2"],
                  "d": 42,
                  "e": {"translation": "E1", "reworded": "x" * 501},
                  "f": {"translation": "F1", "reworded": " a1 "},
                  "g": "plain"}
        reply = json.dumps(values)
        languages = ["English", "German", "Danish", "Norwegian", "Swedish", "Finnish", "Dutch"]
        got = translate_module.translate("q", languages, "m", llm=_llm_returning(reply))
        self.assertEqual(got, (["A1", "B2", "E1", "F1", "plain"], None))

        got_one = translate_module.translate("q", ["English"], "m", llm=_llm_returning(reply))
        self.assertEqual(got_one, (["A1", "B2"], None))

        unusable = json.dumps({"a": 1, "b": [], "c": {"reworded": None}, "d": {"translation": ""}})
        got_none = translate_module.translate("q", ["English"], "m", llm=_llm_returning(unusable))
        self.assertEqual(got_none, ([], "translation reply not usable"))

    def test_find_searches_rewordings(self):
        cfg = make_config(self, egress={"rank": False, "answer": False, "translate": True})
        make_multi_locker(cfg, "lib", {"a.md": "a line1\n"})
        out = json.dumps({"query": [{"path": "a.md", "start": 1, "end": 1, "rank": 1}], "translation": []})
        calls = []

        def runner(argv, *, cwd, env, input=None):
            calls.append(input)
            return 0, out, ""

        reply = json.dumps({"English": {"translation": "when?", "reworded": "at what time?"},
                            "German": {"translation": "wann?", "reworded": "zu welcher Zeit?"}})
        r = find("when?", ["lib"], runner=runner, jev=None, llm=_llm_returning(reply), config=cfg)
        kept = ["at what time?", "wann?", "zu welcher Zeit?"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(calls[0])["translations"], kept)
        self.assertEqual(r["translations"], kept)


if __name__ == "__main__":
    unittest.main()
