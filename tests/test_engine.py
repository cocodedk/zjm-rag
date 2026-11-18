import json
import unittest
from unittest import mock

from zjm_rag import ZjmError, engine

OUT = {"query": [{"path": "code/search.py", "start": 118, "end": 126, "rank": 1}], "translation": []}


class EngineTest(unittest.TestCase):
    def test_parse_returns_both_groups_with_lines(self):
        self.assertEqual(engine.parse(json.dumps(OUT)), OUT)
        both = {"query": [], "translation": [{"path": "one.md", "start": 7, "end": 7, "rank": 9}]}
        self.assertEqual(engine.parse(json.dumps(both)), both)

    def test_bad_engine_output_raises(self):
        hit = {"path": "a.md", "start": 1, "end": 2, "rank": 1}
        bad = ["", "not json", "[]", "{}", '{"query": []}', json.dumps({"query": [{"path": "a.md"}], "translation": []}),
               json.dumps({"query": [dict(hit, path=3)], "translation": []}),
               json.dumps({"query": "x", "translation": []})]
        for out in bad:
            with self.subTest(out=out), self.assertRaisesRegex(ZjmError, "engine returned bad output"):
                engine.parse(out)

    def test_argv_never_carries_the_question(self):
        # HITS is patched explicitly so tuning it later cannot break this test.
        with mock.patch.object(engine, "HITS", 7):
            base = ["zjm-engine", "query", "--model", "/opt/zjm/models/potion-code-16m-v2", "--limit", "7"]
            self.assertEqual(engine.query_argv("local/potion-code-16m-v2", "i.idx", ["py", "md"]),
                             base + ["--type", "py", "--type", "md", "i.idx"])
            self.assertEqual(engine.query_argv("local/potion-code-16m-v2", "i.idx"), base + ["i.idx"])
        self.assertEqual(json.loads(engine.query_input("--help", ["a", "b"])),
                         {"question": "--help", "translations": ["a", "b"]})
        self.assertEqual(json.loads(engine.query_input("q", None)), {"question": "q", "translations": []})


if __name__ == "__main__":
    unittest.main()
