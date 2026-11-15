import unittest
from pathlib import Path
from unittest import mock

from zjm_rag import zg

FIXTURE = Path(__file__).resolve().parent / "fixtures/zg-query-0.3.0.md"


class ZgTest(unittest.TestCase):
    def test_parse_keeps_every_hit_with_lines(self):
        hits = zg.parse(FIXTURE.read_text())
        self.assertEqual(len(hits), 40)
        self.assertEqual(hits[0], {"path": "code/__init__.py", "start": 1, "end": 9, "rank": 1})
        self.assertEqual(hits[1], {"path": "code/search.py", "start": 118, "end": 126, "rank": 2})
        self.assertEqual(hits[-1], {"path": "code/http.py", "start": 25, "end": 121, "rank": 40})
        self.assertEqual([h["rank"] for h in hits], list(range(1, 41)))
        single = zg.parse("#9 one.md:7\n7\tx\n")
        self.assertEqual(single, [{"path": "one.md", "start": 7, "end": 7, "rank": 9}])

    def test_query_argv(self):
        # ZG_HITS is patched explicitly so tuning it later cannot break this test.
        with mock.patch.object(zg, "ZG_HITS", 7):
            argv = zg.query_argv("q", ["py", "md"])
            self.assertEqual(argv, ["zg", "--preview", "none", "--limit", "7", "--mode", "direct",
                                    "-t", "py", "-t", "md", "--", "q"])
            self.assertEqual(zg.query_argv("q"),
                             ["zg", "--preview", "none", "--limit", "7", "--mode", "direct", "--", "q"])
            self.assertEqual(zg.query_argv("--help"),
                             ["zg", "--preview", "none", "--limit", "7", "--mode", "direct", "--", "--help"])


if __name__ == "__main__":
    unittest.main()
