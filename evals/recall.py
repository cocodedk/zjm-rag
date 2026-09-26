"""Recall eval: does zjm put the text that answers a question in front of Jev and the answer model?

It runs the real zg (and, with --jev, the real Jev) over evals/corpus plus a generated long
runbook. The answer model is never called: its prompt is captured instead. This is not part of
the unit suite, because it needs zg and, with --jev, the network.

    python3 evals/recall.py [--limit N] [--min-score S] [--jev] [--multilingual | --embedding M] [--verbose]

Per question it reports whether the expected file was a candidate, whether the text that answers
the question ("must") was in that file's evidence, whether the file was accepted, and whether the
answer text reached the answer model's prompt.
"""
import argparse
import inspect
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import zjm_rag  # noqa: E402
from zjm_rag import llm as llm_client  # noqa: E402
from zjm_rag import zg  # noqa: E402

TOOLS = {"zg", "git", "age", "age-keygen"}
BIRDS = ["wren", "finch", "robin", "swift", "crane", "egret", "ibis", "lark", "heron", "kestrel"]
NOUNS = ["gate", "relay", "store", "queue", "index", "sync", "cache", "feed", "vault", "watch"]
TEAMS = ["Atlas", "Beacon", "Comet", "Delta", "Ember", "Falcon", "Granite", "Harbor"]


def norm(text):
    return " ".join(text.split())


def runbook():
    """100 near-identical service sections; two planted facts sit past the first 20 000 characters."""
    out = ["# Service runbook\n"]
    for i in range(100):
        name = f"{BIRDS[i // 10]}-{NOUNS[i % 10]}"
        port = 7419 if name == "kestrel-cache" else 7000 + (i * 37) % 1000
        team = "Osprey" if name == "heron-sync" else TEAMS[(i * 3) % len(TEAMS)]
        out.append(f"## {name}\n\n{name} listens on port {port}. {name} is owned by team {team}. "
                   f"It restarts after {2 + i % 5} failures and writes its logs to /var/log/{name}.log. "
                   f"Its backups run every {6 + i % 30} hours and are kept for {3 + i % 11} days. "
                   f"On-call rotates weekly between {team} and {TEAMS[(i * 5 + 1) % len(TEAMS)]}.\n")
    return "\n".join(out)


def evidence_text(hit):
    if "passages" in hit:
        return " ".join(p["text"] for p in hit["passages"])
    return " ".join(hit.get("snippets", []))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--min-score", type=float, default=0.5)
    ap.add_argument("--jev", action="store_true", help="rank with the real Jev (network, costs)")
    ap.add_argument("--translate", action="store_true", help="turn on egress.translate (network, costs)")
    ap.add_argument("--multilingual", action="store_true")
    ap.add_argument("--embedding", help="any zg local model, e.g. local/multilingual-e5-small")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    golden = json.loads((ROOT / "golden.json").read_text())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "src"
        shutil.copytree(ROOT / "corpus", src)
        (src / "runbook.md").write_text(runbook())
        for g in golden:
            if norm(g["must"]) not in norm((src / g["file"]).read_text()):
                sys.exit(f"golden error: {g['id']}: must text not in {g['file']}")
        cfg = tmp / "config.json"
        cfg.write_text(json.dumps({"allow": [str(src)], "home": str(tmp / "home"),
                                   "egress": {"rank": args.jev, "answer": True, "translate": args.translate}}))
        zjm_rag.locker_create("eval", plain=True, multilingual=args.multilingual, embedding=args.embedding,
                              config=str(cfg))
        zjm_rag.file_add("eval", [str(src)], config=str(cfg))

        prompts = []

        def runner(argv, *, cwd, env, input=None):
            if argv[0] in TOOLS:
                return zg.run(argv, cwd=cwd, env=env, input=input)
            prompts.append(input or "")
            return 0, "", ""

        def llm(model, messages, reasoning=True):
            if not reasoning:
                return llm_client.post(model, messages, reasoning=False)  # a real translation call
            prompts.append("\n".join(m["content"] for m in messages))
            return ""

        kwargs = {"runner": runner}
        if "llm" in inspect.signature(zjm_rag.ask).parameters:
            kwargs["llm"] = llm
        totals = {}
        print(f"{'id':16} {'kind':12} cand  evid  acc   ctx")
        for g in golden:
            prompts.clear()
            r = zjm_rag.ask(g["q"], ["eval"], limit=args.limit, min_score=args.min_score, config=str(cfg), **kwargs)
            found, want = r["find"], "src/" + g["file"]
            hit = next((h for h in found["accepted"] + found["rejected"] if h["path"] == want), None)
            row = {"cand": hit is not None,
                   "evid": bool(hit) and norm(g["must"]) in norm(evidence_text(hit)),
                   "acc": bool(hit) and hit in found["accepted"],
                   "ctx": bool(prompts) and norm(g["must"]) in norm(prompts[-1])}
            for k, v in row.items():
                t = totals.setdefault(g["kind"], {}).setdefault(k, [0, 0])
                t[0] += v
                t[1] += 1
            mark = "  ".join(("yes " if v else "NO  ") for v in row.values())
            rank = f"#{hit['zg_rank']}" if hit else ""
            print(f"{g['id']:16} {g['kind']:12} {mark} {rank}")
            if args.verbose and hit and not row["evid"]:
                spans = [(p["start"], p["end"]) for p in hit.get("passages", [])]
                print(f"{'':30}evidence spans: {spans or len(hit.get('snippets', []))}")
            if args.verbose and (found.get("translations") or found.get("translate_error")):
                print(f"{'':30}translations: {found.get('translations')} {found.get('translate_error') or ''}")
        print()
        for kind, t in totals.items():
            print(f"{kind:12} " + "  ".join(f"{k} {v[0]}/{v[1]}" for k, v in t.items()))
        allk = {k: [sum(t[k][i] for t in totals.values()) for i in (0, 1)] for k in ("cand", "evid", "acc", "ctx")}
        print(f"{'ALL':12} " + "  ".join(f"{k} {v[0]}/{v[1]}" for k, v in allk.items()))


if __name__ == "__main__":
    main()
