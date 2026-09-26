import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import FakeRunner, fake_jev, make_config, make_locker
from zjm_rag import evidence, find


def hit(path, start, end, rank):
    return {"path": path, "start": start, "end": end, "rank": rank}


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.corpus = Path(tmp.name)

    def write(self, name, text):
        p = self.corpus / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return p

    def test_passage_is_the_full_chunk(self):
        # WIDEN is patched explicitly (even though 0 is today's default) so retuning it later
        # cannot break this test.
        with mock.patch.object(evidence, "WIDEN", 0):
            lines = [f"line{i}" for i in range(1, 21)]
            self.write("a.md", "\n".join(lines))
            built = evidence.read_candidates([hit("a.md", 5, 9, 1)], {"a.md": {}}, self.corpus, 8, want_text=False)
            passages = built["a.md"]["passages"]
            self.assertEqual(len(passages), 1)
            self.assertEqual((passages[0]["start"], passages[0]["end"]), (5, 9))
            self.assertEqual(passages[0]["text"], "\n".join(lines[4:9]))

            # \x0c, U+2028 (line separator) and a bare \r must never shift the line numbering.
            # chr(0x2028) avoids embedding the raw character in this source file.
            odd = "a\x0cb\n" + f"c{chr(0x2028)}d\n" + "e\rf\n" + "g\n"
            self.write("odd.md", odd)
            built2 = evidence.read_candidates([hit("odd.md", 1, 1, 1)], {"odd.md": {}}, self.corpus, 8,
                                              want_text=False)
            self.assertEqual(built2["odd.md"]["passages"][0]["text"], "a\x0cb")
            built3 = evidence.read_candidates([hit("odd.md", 3, 3, 1)], {"odd.md": {}}, self.corpus, 8,
                                              want_text=False)
            self.assertEqual(built3["odd.md"]["passages"][0]["text"], "e\rf")

    def test_overlaps_merge_and_order_by_rank(self):
        with mock.patch.object(evidence, "WIDEN", 0):
            self.write("a.md", "\n".join(f"l{i}" for i in range(1, 21)))
            hits = [hit("a.md", 1, 5, 3), hit("a.md", 6, 8, 2), hit("a.md", 15, 18, 1)]
            built = evidence.read_candidates(hits, {"a.md": {}}, self.corpus, 8, want_text=False)
            passages = built["a.md"]["passages"]
            self.assertEqual([(p["start"], p["end"]) for p in passages], [(15, 18), (1, 8)])

    def test_unknown_path_never_read(self):
        self.write("a.md", "kept")
        # "ghost.md" is not a manifest key and does not exist on disk either: if evidence.py tried
        # to open it, this would raise FileNotFoundError instead of silently skipping it.
        built = evidence.read_candidates([hit("ghost.md", 1, 1, 1), hit("a.md", 1, 1, 2)],
                                         {"a.md": {}}, self.corpus, 8, want_text=False)
        self.assertEqual(list(built), ["a.md"])

    def test_candidates_keep_every_hit(self):
        for n in ("a.md", "b.md", "c.md"):
            self.write(n, "x\ny\nz")
        hits = [hit("a.md", 1, 1, 1), hit("b.md", 1, 1, 2), hit("c.md", 1, 1, 3), hit("a.md", 2, 2, 4)]
        order, by_path = evidence.select_candidates(hits, {"a.md": {}, "b.md": {}, "c.md": {}}, 2)
        self.assertEqual(order, ["a.md", "b.md"])
        self.assertEqual([h["rank"] for h in by_path["a.md"]], [1, 4])
        self.assertEqual([h["rank"] for h in by_path["b.md"]], [2])

    def test_jev_evidence_capped_shape_pinned(self):
        passages = [{"start": 1, "end": 1, "text": "x" * 100}, {"start": 2, "end": 2, "text": "y" * 100}]
        snippets = evidence.jev_snippets(passages, jev_chars=50)
        self.assertTrue(snippets[0].startswith("lines 1-1:"))
        self.assertEqual(len(snippets[0]), 50)
        self.assertEqual(len(snippets), 1)
        snippets2 = evidence.jev_snippets(passages, jev_chars=1000)
        self.assertEqual(len(snippets2), 2)
        self.assertTrue(snippets2[1].startswith("lines 2-2:"))

        # End to end through find(): the pinned noul question shape is unchanged (fake_jev
        # asserts it internally), and JEV_CHARS patched small reaches the actual payload sent.
        cfg = make_config(self)
        make_locker(self, cfg, "lib")
        captured = []

        def spy(payload):
            captured.append(payload)
            return fake_jev([0.9, 0.2, 0.5])(payload)

        with mock.patch("zjm_rag.evidence.JEV_CHARS", 20):
            find("q", ["lib"], runner=FakeRunner(), jev=spy, config=cfg)
        sent = [s for e in captured[0]["state"]["evidence"] for s in e["snippets"]]
        self.assertTrue(sent)
        self.assertTrue(all(s.startswith("lines ") for s in sent))
        self.assertTrue(all(len(s) <= 20 for s in sent))

    def test_ask_budget_whole_then_passages(self):
        small_whole = "hi"
        big_whole = "B" * 500
        big_passage_text = "a" * 20
        per_locker = {"lib": {
            "small.md": {"whole": small_whole, "passages": [{"start": 1, "end": 1, "text": small_whole}]},
            "big.md": {"whole": big_whole, "passages": [{"start": 1, "end": 1, "text": big_passage_text}]},
            "extra.md": {"whole": "should not appear", "passages": [{"start": 1, "end": 1, "text": "nope"}]},
        }}
        small_block = f"=== lib/small.md ===\n{small_whole}"
        big_passage_block = f"=== lib/big.md:1-1 ===\n{big_passage_text}"
        budget = len(small_block) + len(big_passage_block)
        hits = [{"locker": "lib", "path": p} for p in ("small.md", "big.md", "extra.md")]
        context, files = evidence.build_ask_context(hits, per_locker, top_k=2, ask_chars=budget)
        self.assertEqual(context, small_block + "\n\n" + big_passage_block)
        self.assertEqual(files, ["lib/small.md", "lib/big.md"])
        self.assertNotIn("extra.md", context)

    def test_ask_deep_answer_reaches_prompt(self):
        # ASK_CHARS is patched explicitly: the ~60 000-character file must fit comfortably under
        # it regardless of any future retuning.
        with mock.patch.object(evidence, "ASK_CHARS", 100000):
            filler = "filler line\n" * 5000
            text = filler + "THE ANSWER IS HERE\n"
            self.write("deep.md", text)
            n_lines = text.count("\n")
            built = evidence.read_candidates([hit("deep.md", n_lines, n_lines, 1)], {"deep.md": {}}, self.corpus, 8,
                                             want_text=True)
            rec = built["deep.md"]
            self.assertIsNotNone(rec["whole"])
            context, files = evidence.build_ask_context([{"locker": "lib", "path": "deep.md"}],
                                                         {"lib": {"deep.md": rec}}, top_k=1)
        self.assertIn("THE ANSWER IS HERE", context)
        self.assertEqual(files, ["lib/deep.md"])


if __name__ == "__main__":
    unittest.main()
