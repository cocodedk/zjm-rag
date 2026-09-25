import http.client
import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from fakes import PATHS, FakeRunner, fake_jev, make_store
from zjm_rag import ZjmError, find, jev


class FindTest(unittest.TestCase):
    def setUp(self):
        self.store = make_store(self)

    def test_threshold_splits_accepted_rejected(self):
        runner, payloads = FakeRunner(), []

        def jev(payload):
            payloads.append(payload)
            return fake_jev([0.9, 0.2, 0.5])(payload)

        r = find("q", store=self.store, file_types=["py", "md"], runner=runner, jev=jev)
        self.assertEqual(runner.calls[0][0], ["zg", "query", "q", "--preview", "short", "--limit", "40",
                                              "--mode", "direct", "-t", "py", "-t", "md"])
        self.assertEqual(runner.calls[0][2]["ZVEC_GREP_HOME"], str(self.store / "zghome"))
        self.assertEqual(list(payloads[0]["questions"]), ["f1", "f2", "f3"])
        self.assertEqual([h["path"] for h in r["accepted"]], ["proj/b.md", "proj/c.txt"])
        self.assertEqual([h["path"] for h in r["rejected"]], ["proj/a.py"])
        self.assertEqual(r["accepted"][0]["source_path"], "/src/proj/b.md")
        self.assertEqual(r["accepted"][0]["score"], 0.9)
        self.assertEqual((r["sort"], r["min_score"]), ("score", 0.5))

    def test_sort_keys(self):
        jev = fake_jev([0.7, 0.9, 0.8])
        orders = {"score": ["proj/a.py", "proj/c.txt", "proj/b.md"], "zg": PATHS,
                  "mtime": ["proj/b.md", "proj/c.txt", "proj/a.py"], "path": sorted(PATHS)}
        for key, expected in orders.items():
            r = find("q", store=self.store, sort=key, runner=FakeRunner(), jev=jev)
            self.assertEqual([h["path"] for h in r["accepted"]], expected, key)
        with self.assertRaises(ValueError):
            find("q", store=self.store, sort="size", runner=FakeRunner(), jev=jev)
        with self.assertRaises(ValueError):
            find("q", store=self.store, sort="score", rank=False, runner=FakeRunner(), jev=jev)

    def test_no_rank_skips_jev(self):
        def jev(payload):
            self.fail("jev called")

        r = find("q", store=self.store, rank=False, runner=FakeRunner(), jev=jev)
        self.assertEqual(r["sort"], "zg")
        self.assertEqual([h["path"] for h in r["accepted"]], PATHS)
        self.assertEqual([h["score"] for h in r["accepted"]], [None] * 3)
        self.assertEqual([h["zg_rank"] for h in r["accepted"]], [1, 2, 3])
        self.assertEqual(r["rejected"], [])

    def test_bad_jev_answer_raises(self):
        with self.assertRaises(ZjmError):
            find("q", store=self.store, runner=FakeRunner(), jev=fake_jev([0.9, 0.2]))
        with self.assertRaises(ZjmError):
            find("q", store=self.store, runner=FakeRunner(), jev=fake_jev([0.9, 1.5, 0.3]))
        self.check_jev_post()

    def check_jev_post(self):
        """jev.post: key required, auth headers and model sent, redirects refused, failures -> ZjmError."""
        sent = []

        class Opener:
            def __init__(self, result):
                self.result = result

            def open(self, req, timeout):
                sent.append((req, timeout))
                if isinstance(self.result, Exception):
                    raise self.result
                return io.BytesIO(self.result)

        def opener(result):
            return mock.patch.object(jev.urllib.request, "build_opener", return_value=Opener(result))

        with mock.patch.dict(os.environ, {}, clear=True), opener(b"{}"):
            with self.assertRaisesRegex(ZjmError, "OPENROUTER_API_KEY is not set"):
                jev.post({})
        self.assertEqual(sent, [])
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-secret"}, clear=True):
            with opener(b'{"answers": {}}') as build:
                self.assertEqual(jev.post({"questions": {}}), {"answers": {}})
            build.assert_called_once_with(jev._NoRedirect)
            req, timeout = sent[-1]
            self.assertEqual((req.full_url, req.get_method(), timeout), (jev.URL, "POST", 30))
            self.assertEqual(req.get_header("Authorization"), "Bearer sk-secret")
            self.assertEqual(req.get_header("Content-type"), "application/json")
            self.assertEqual(json.loads(req.data), {"questions": {}, "model": "typesafe/jev-1.13"})
            body = io.BytesIO(b"secret body")
            for failure in (urllib.error.HTTPError(jev.URL, 500, "err", {}, body),
                            urllib.error.URLError("no route"), http.client.IncompleteRead(b"")):
                with opener(failure), self.assertRaises(ZjmError) as ctx:
                    jev.post({})
                self.assertNotIn("secret", str(ctx.exception))
        with self.assertRaisesRegex(ZjmError, "redirect"):
            jev._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example")


if __name__ == "__main__":
    unittest.main()
