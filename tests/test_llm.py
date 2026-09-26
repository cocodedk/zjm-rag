import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from zjm_rag import ZjmError
from zjm_rag import config as config_module
from zjm_rag import llm


class LlmTest(unittest.TestCase):
    def test_request_shape_and_errors(self):
        sent = []

        def patched(result):
            def _open(req, timeout):
                sent.append((req, timeout))
                if isinstance(result, Exception):
                    raise result
                return io.BytesIO(result)
            return mock.patch.object(llm, "_open", _open)

        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ZjmError, "OPENROUTER_API_KEY is not set"):
                llm.post("m", [])
        self.assertEqual(sent, [])

        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-secret"}, clear=True):
            with patched(b'{"choices": [{"message": {"content": "hi"}}]}'):
                messages = [{"role": "user", "content": "q"}]
                self.assertEqual(llm.post("deepseek/deepseek-v4-flash", messages), "hi")
            req, timeout = sent[-1]
            self.assertEqual((req.full_url, req.get_method(), timeout), (llm.URL, "POST", 120))
            self.assertEqual(req.get_header("Authorization"), "Bearer sk-secret")
            self.assertEqual(req.get_header("Content-type"), "application/json")
            body = json.loads(req.data)
            self.assertEqual(body, {"model": "deepseek/deepseek-v4-flash",
                                    "messages": [{"role": "user", "content": "q"}],
                                    "provider": {"data_collection": "deny"}})
            self.assertNotIn("sk-secret", json.dumps(body))

            leaky_body = io.BytesIO(b"secret response body")
            for failure in (urllib.error.HTTPError(llm.URL, 500, "err", {}, leaky_body),
                            urllib.error.URLError("no route")):
                with patched(failure), self.assertRaises(ZjmError) as ctx:
                    llm.post("m", [])
                self.assertNotIn("secret", str(ctx.exception))
                self.assertNotIn("sk-secret", str(ctx.exception))

            for empty in (b'{"choices": []}', b"{}", b'{"choices": [{"message": {}}]}'):
                with patched(empty), self.assertRaisesRegex(ZjmError, "no text"):
                    llm.post("m", [])

        with self.assertRaisesRegex(ZjmError, "redirect"):
            llm._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example")

    def test_config_llm_is_model_id(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        environ = {"HOME": str(Path(tmp.name) / "home")}
        cfg = config_module.load(cwd=str(Path(tmp.name) / "nowhere"), environ=environ)
        self.assertEqual(cfg["llm"], "deepseek/deepseek-v4-flash")

        bad = Path(tmp.name) / "bad.json"
        bad.write_text(json.dumps({"llm": ["claude", "-p"]}))
        with self.assertRaisesRegex(ZjmError, 'llm is an OpenRouter model id now'):
            config_module.load(str(bad), environ=environ)


if __name__ == "__main__":
    unittest.main()
