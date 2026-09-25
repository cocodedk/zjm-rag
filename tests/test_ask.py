import unittest

from fakes import FakeRunner, fake_jev, make_store
from zjm_rag import ask


class AskTest(unittest.TestCase):
    def setUp(self):
        self.store = make_store(self)

    def test_no_accepted_skips_llm(self):
        runner = FakeRunner()
        r = ask("q", store=self.store, runner=runner, jev=fake_jev([0.1, 0.2, 0.3]))
        self.assertEqual([c[0][0] for c in runner.calls], ["zg"])
        self.assertEqual((r["answer"], r["reason"], r["files"]), (None, "no file passed the threshold", []))
        self.assertEqual(len(r["find"]["rejected"]), 3)

    def test_prompt_and_language(self):
        runner = FakeRunner()
        r = ask("which file?", store=self.store, top_k=2, answer_language="da", runner=runner,
                jev=fake_jev([0.9, 0.6, 0.8]))
        argv, _, _, prompt = runner.calls[-1]
        self.assertEqual(argv, ["claude", "-p", "--effort", "medium", "--model", "sonnet"])
        self.assertTrue(prompt.startswith("Answer from these files only; cite the file path."))
        self.assertIn("=== proj/b.md ===\ncontent of proj/b.md", prompt)
        self.assertIn("=== proj/c.txt ===", prompt)
        self.assertNotIn("proj/a.py", prompt)
        self.assertTrue(prompt.endswith("Question: which file?\n\nAnswer in da."))
        self.assertEqual((r["answer"], r["reason"], r["files"]), ("the answer", None, ["proj/b.md", "proj/c.txt"]))


if __name__ == "__main__":
    unittest.main()
