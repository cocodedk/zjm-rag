"""A store with three copied files and a fake runner that plays zg (and the LLM)."""
import json
import os
import tempfile
from pathlib import Path

PATHS = ["proj/b.md", "proj/a.py", "proj/c.txt"]  # zg order
ZG_OUT = "hits: 3\n" + "".join(f"\n#{i} matchedBy=fts+vector {p}:1-2\nsource:\n1\tbody of {p}\n"
                               for i, p in enumerate(PATHS, 1))


def make_store(test):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    store = Path(tmp.name)
    for mtime, p in zip((300, 100, 200), PATHS):
        f = store / "corpus" / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"content of {p}")
        os.utime(f, (mtime, mtime))
    (store / "zjm.json").write_text(json.dumps({"sources": ["/src/proj"], "embedding": "m"}))
    return store


class FakeRunner:
    def __init__(self, llm_out="the answer\n"):
        self.calls, self.llm_out = [], llm_out

    def __call__(self, argv, *, cwd, env, input):
        self.calls.append((argv, cwd, env, input))
        return 0, ZG_OUT if argv[0] == "zg" else self.llm_out, ""


def fake_jev(scores):
    def jev(payload):
        for q in payload["questions"].values():
            assert set(q) == {"type", "instructions", "criteria"}, q
            assert q["type"] == "noul" and q["instructions"], q
            assert set(q["criteria"]) == {"true", "false"}, q
        return {"answers": {k: {"type": "noul", "noul": s} for k, s in zip(payload["questions"], scores)}}
    return jev
