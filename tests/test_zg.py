import unittest
from pathlib import Path
from unittest import mock

from zjm_rag import zg

FIXTURE = Path(__file__).resolve().parent / "fixtures/zg-query.md"


class ZgTest(unittest.TestCase):
    def test_parse_keeps_every_hit_with_lines(self):
        hits = zg.parse(FIXTURE.read_text())
        self.assertEqual(len(hits), 20)
        self.assertEqual(hits[0], {"path": "agent-linters/llms.txt", "start": 1, "end": 43, "rank": 1})
        self.assertEqual(hits[1], {"path": "agent-linters/README.md", "start": 10, "end": 32, "rank": 2})
        self.assertEqual([h["rank"] for h in hits], list(range(1, 21)))
        single = zg.parse("hits: 1\n\n#9 matchedBy=fts one.md:7\nsource:\n7\tx\n")
        self.assertEqual(single, [{"path": "one.md", "start": 7, "end": 7, "rank": 9}])

    def test_query_argv(self):
        # ZG_HITS is patched explicitly so tuning it later cannot break this test.
        with mock.patch.object(zg, "ZG_HITS", 7):
            argv = zg.query_argv("q", ["py", "md"])
            self.assertEqual(argv, ["zg", "query", "q", "--preview", "none", "--limit", "7", "--mode", "direct",
                                    "-t", "py", "-t", "md"])
            self.assertEqual(zg.query_argv("q"),
                             ["zg", "query", "q", "--preview", "none", "--limit", "7", "--mode", "direct"])


if __name__ == "__main__":
    unittest.main()
