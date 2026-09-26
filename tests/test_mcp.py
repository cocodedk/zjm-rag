import io
import json
import unittest

from fakes import FakeRunner, fake_jev, fake_llm, make_config, make_locker
from zjm_rag import find
from zjm_rag.mcp import serve


def rpc(*msgs, **kwargs):
    lines = [m if isinstance(m, str) else json.dumps(m) for m in msgs]
    out = io.StringIO()
    serve(io.StringIO("\n".join(lines) + "\n"), out, **kwargs)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def call(i, name, arguments):
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


class McpTest(unittest.TestCase):
    def test_initialize_and_list(self):
        init, tools = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-03-26"}},
                          {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(init["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(init["result"]["capabilities"], {"tools": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "zjm-rag")
        listed = {t["name"]: t for t in tools["result"]["tools"]}
        self.assertEqual(set(listed), {"zjm_locker_create", "zjm_locker_list", "zjm_locker_drop", "zjm_file_add",
                                       "zjm_file_put", "zjm_file_remove", "zjm_file_list", "zjm_find", "zjm_ask",
                                       "zjm_doctor", "zjm_locker_encrypt"})
        for t in listed.values():
            self.assertTrue(t["description"])
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertIs(t["inputSchema"]["additionalProperties"], False)
        self.assertEqual(listed["zjm_doctor"]["inputSchema"]["properties"], {})
        self.assertEqual(listed["zjm_find"]["inputSchema"]["required"], ["query", "lockers"])

    def test_call_find(self):
        cfg = make_config(self)
        make_locker(self, cfg, "lib")
        args = {"query": "q", "lockers": ["lib"], "min_score": 0.7, "sort": "path"}
        (r,) = rpc(call(1, "zjm_find", args), config=cfg, runner=FakeRunner(), jev=fake_jev([0.9, 0.8, 0.1]))
        want = find(**args, config=cfg, runner=FakeRunner(), jev=fake_jev([0.9, 0.8, 0.1]))
        self.assertEqual(r["result"]["structuredContent"], want)
        self.assertEqual(json.loads(r["result"]["content"][0]["text"]), want)
        self.assertNotIn("isError", r["result"])

        runner, llm = FakeRunner(), fake_llm("the answer")
        create, ask, doc, doc_args = rpc(call(2, "zjm_locker_create", {"name": "lib2", "multilingual": True, "plain": True}),
                                         call(3, "zjm_ask", {"query": "q", "lockers": ["lib"], "top_k": 1,
                                                             "answer_language": "da"}),
                                         call(4, "zjm_doctor", {}), call(5, "zjm_doctor", {"x": 1}),
                                         config=cfg, runner=runner, jev=fake_jev([0.9, 0.2, 0.1]), llm=llm)
        self.assertEqual(create["result"]["structuredContent"]["name"], "lib2")
        self.assertEqual(ask["result"]["structuredContent"]["answer"], "the answer")
        self.assertIn("Answer in da.", llm.calls[-1][1][-1]["content"])
        self.assertEqual(set(doc["result"]["structuredContent"]["checks"]), {"zg", "age", "openrouter_key"})
        self.assertIs(doc_args["result"]["isError"], True)

    def test_errors(self):
        runner = FakeRunner()
        unknown, bad, lib, typed, name = rpc({"jsonrpc": "2.0", "id": 1, "method": "nope"}, "{not json",
                                             call(3, "zjm_find", {"query": "q", "lockers": ["nope"]}),
                                             call(4, "zjm_find", {"query": "q", "lockers": ["nope"],
                                                                  "store": "/tmp/x"}),
                                             call(5, ["zjm_find"], {}),
                                             config=make_config(self), runner=runner, jev=fake_jev([]))
        self.assertEqual(name["error"]["code"], -32602)
        self.assertEqual(unknown["error"]["code"], -32601)
        self.assertEqual((bad["id"], bad["error"]["code"]), (None, -32700))
        self.assertIs(lib["result"]["isError"], True)
        self.assertIn("no locker", lib["result"]["structuredContent"]["error"])
        self.assertIs(typed["result"]["isError"], True)
        self.assertEqual(runner.calls, [])

    def test_notification_gets_no_reply(self):
        replies = rpc({"jsonrpc": "2.0", "method": "notifications/initialized"},
                      {"jsonrpc": "2.0", "method": "tools/list"},
                      {"jsonrpc": "2.0", "id": 7, "method": "ping"})
        self.assertEqual(replies, [{"jsonrpc": "2.0", "id": 7, "result": {}}])


if __name__ == "__main__":
    unittest.main()
