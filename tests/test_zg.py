import unittest
from pathlib import Path

from zjm_rag import zg

FIXTURE = Path(__file__).resolve().parent / "fixtures/zg-query.md"


class ParseTest(unittest.TestCase):
    def test_groups_hits_by_file_in_zg_order(self):
        files = zg.parse(FIXTURE.read_text())
        self.assertEqual(list(files)[:3], ["agent-linters/llms.txt", "agent-linters/README.md", "agent-linters/bin/lintp"])
        self.assertEqual(len(files), 8)
        self.assertIn("| `.css .scss .json .jsonc` | biome |", "".join(files["agent-linters/README.md"]))

    def test_caps_files_and_snippets(self):
        files = zg.parse(FIXTURE.read_text(), limit=3)
        self.assertEqual(len(files), 3)
        self.assertTrue(all(len(s) <= 2 for s in files.values()))
        self.assertTrue(all(len(x) <= 1500 for s in files.values() for x in s))
        spaced = zg.parse("hits: 1\n\n#1 matchedBy=fts my proj/a b.md:3-4\nsource:\n3\tx\n")
        self.assertEqual(spaced, {"my proj/a b.md": ["3\tx\n"]})


if __name__ == "__main__":
    unittest.main()
