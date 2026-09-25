import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import rag  # noqa: E402


class ParseTest(unittest.TestCase):
    def test_groups_hits_by_file_in_zg_order(self):
        files = rag.parse((ROOT / "tests/fixtures/zg-query.md").read_text())
        self.assertEqual(list(files)[:3], ["agent-linters/llms.txt", "agent-linters/README.md", "agent-linters/bin/lintp"])
        self.assertEqual(len(files), rag.MAX_FILES)
        self.assertIn("| `.css .scss .json .jsonc` | biome |", "".join(files["agent-linters/README.md"]))


if __name__ == "__main__":
    unittest.main()
