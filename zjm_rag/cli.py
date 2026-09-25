"""zjm: the library on the command line, with --json."""
import argparse
import json
import sys

from . import core
from .errors import ZjmError


def _parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--store", default=str(core.DEFAULT_STORE))
    common.add_argument("--json", action="store_true")
    parser = argparse.ArgumentParser(prog="zjm", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index", parents=[common])
    p.add_argument("sources", nargs="+", metavar="SRC")
    p.add_argument("--multilingual", action="store_true")
    p.add_argument("--embedding", metavar="MODEL")
    p.add_argument("--rebuild", action="store_true")
    for name in ("find", "ask"):
        p = sub.add_parser(name, parents=[common])
        p.add_argument("query", metavar="QUERY")
        if name == "ask":
            p.add_argument("--top-k", type=int, default=3)
            p.add_argument("--lang")
        p.add_argument("--limit", type=int, default=8)
        p.add_argument("--type", action="append", dest="types", metavar="T")
        p.add_argument("--min-score", type=float, default=0.5)
        if name == "find":
            p.add_argument("--sort", choices=list(core.SORTS))
        p.add_argument("--no-rank", action="store_true")
    sub.add_parser("doctor", parents=[common])
    p = sub.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--store", default=str(core.DEFAULT_STORE))
    sub.add_parser("mcp").add_argument("--store", default=str(core.DEFAULT_STORE))
    return parser


def _serve(args, fakes):
    from .http import make_server
    server = make_server(args.host, args.port, store=args.store, **fakes)
    host, port = server.server_address[:2]
    print(f"listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _run(args, fakes):
    if args.cmd == "doctor":
        return core.doctor(args.store)
    if args.cmd == "index":
        fakes.pop("jev", None)
        return core.index(args.sources, store=args.store, multilingual=args.multilingual,
                          embedding=args.embedding, rebuild=args.rebuild, **fakes)
    opts = {"limit": args.limit, "file_types": args.types, "min_score": args.min_score, "rank": not args.no_rank}
    if args.cmd == "find":
        return core.find(args.query, store=args.store, sort=args.sort, **opts, **fakes)
    return core.ask(args.query, store=args.store, top_k=args.top_k, answer_language=args.lang, **opts, **fakes)


def _human(cmd, r):
    if cmd == "index":
        return [f"indexed {r['files']} files from {len(r['sources'])} sources into {r['store']} ({r['embedding']})"]
    if cmd == "find":
        lines = [f"{'-' if h['score'] is None else format(h['score'], '.2f')}  {h['path']}" for h in r["accepted"]]
        return lines + ([f"rejected: {len(r['rejected'])} below {r['min_score']}"] if r["rejected"] else [])
    if cmd == "ask":
        return [r["answer"] or r["reason"], "", f"sources: {', '.join(r['files'])}"]
    return [f"{'ok' if ok else 'missing'} {name}" for name, ok in r["checks"].items()]


def main(argv=None, *, runner=None, jev=None):
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code
    fakes = {k: v for k, v in {"runner": runner, "jev": jev}.items() if v is not None}
    if args.cmd == "serve":
        return _serve(args, fakes)
    if args.cmd == "mcp":
        from .mcp import serve
        return serve(sys.stdin, sys.stdout, store=args.store, **fakes)
    try:
        result = _run(args, fakes)
    except (ZjmError, ValueError) as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"zjm: {e}", file=sys.stderr)
        return 1
    lines = [json.dumps(result)] if args.json else _human(args.cmd, result)
    if lines:
        print("\n".join(lines))
    return 1 if args.cmd == "doctor" and not result["ok"] else 0
