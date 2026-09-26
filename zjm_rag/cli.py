"""zjm: the library on the command line, with --json."""
import argparse
import json
import sys

from . import config as config_module
from . import search
from .errors import ZjmError
from .ops import OPS, check


def _common(p):
    p.add_argument("--config", default=None)
    p.add_argument("--json", action="store_true")


def _parser():
    parser = argparse.ArgumentParser(prog="zjm", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("locker-create")
    _common(p)
    p.add_argument("name")
    p.add_argument("--multilingual", action="store_true")
    p.add_argument("--embedding", metavar="MODEL")

    _common(sub.add_parser("locker-list"))

    p = sub.add_parser("locker-drop")
    _common(p)
    p.add_argument("name")

    p = sub.add_parser("file-add")
    _common(p)
    p.add_argument("locker")
    p.add_argument("paths", nargs="+", metavar="PATH")

    p = sub.add_parser("file-put")
    _common(p)
    p.add_argument("locker")
    p.add_argument("name")

    p = sub.add_parser("file-remove")
    _common(p)
    p.add_argument("locker")
    p.add_argument("names", nargs="+", metavar="NAME")

    p = sub.add_parser("file-list")
    _common(p)
    p.add_argument("locker")

    for name in ("find", "ask"):
        p = sub.add_parser(name)
        _common(p)
        p.add_argument("query")
        p.add_argument("-l", "--locker", action="append", dest="lockers", required=True, metavar="LOCKER")
        p.add_argument("--limit", type=int, default=8)
        p.add_argument("--type", action="append", dest="types", metavar="T")
        p.add_argument("--min-score", type=float, default=0.5)
        if name == "find":
            p.add_argument("--sort", choices=list(search.SORTS))
        p.add_argument("--no-rank", action="store_true")
        if name == "ask":
            p.add_argument("--top-k", type=int, default=3)
            p.add_argument("--lang")

    _common(sub.add_parser("doctor"))

    p = sub.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--config", default=None)

    p = sub.add_parser("mcp")
    p.add_argument("--config", default=None)
    return parser


def _args_to_body(cmd, args):
    if cmd == "locker-create":
        body = {"name": args.name}
        if args.multilingual:
            body["multilingual"] = True
        if args.embedding:
            body["embedding"] = args.embedding
        return body
    if cmd in ("locker-list", "doctor"):
        return {}
    if cmd == "locker-drop":
        return {"name": args.name}
    if cmd == "file-add":
        return {"locker": args.locker, "paths": args.paths}
    if cmd == "file-put":
        return {"locker": args.locker, "name": args.name, "text": sys.stdin.read()}
    if cmd == "file-remove":
        return {"locker": args.locker, "names": args.names}
    if cmd == "file-list":
        return {"locker": args.locker}
    body = {"query": args.query, "lockers": args.lockers, "limit": args.limit, "min_score": args.min_score}
    if args.types:
        body["file_types"] = args.types
    if args.no_rank:
        body["rank"] = False
    if cmd == "find" and args.sort:
        body["sort"] = args.sort
    if cmd == "ask":
        body["top_k"] = args.top_k
        if args.lang:
            body["answer_language"] = args.lang
    return body


def _human(cmd, r):
    if cmd == "locker-create":
        return [f"created {r['name']} ({r['embedding']})"]
    if cmd == "locker-list":
        return [f"{l['name']}  {l['files']} files  {l['bytes']} bytes  ({l['embedding']})" for l in r["lockers"]]
    if cmd == "locker-drop":
        return [f"dropped {r['name']} ({r['files']} files)"]
    if cmd == "file-add":
        lines = [f"added {n}" for n in r["added"]] + [f"replaced {n}" for n in r["replaced"]]
        if r["excluded"]:
            lines.append(f"excluded {r['excluded']} entries")
        return lines
    if cmd == "file-put":
        return [f"added {n}" for n in r["added"]] + [f"replaced {n}" for n in r["replaced"]]
    if cmd == "file-remove":
        return [f"removed {n}" for n in r["removed"]]
    if cmd == "file-list":
        return [f"{f['name']}  {f['size']} bytes" for f in r["files"]]
    if cmd == "find":
        lines = [f"{'-' if h['score'] is None else format(h['score'], '.2f')}  {h['locker']}/{h['path']}"
                 for h in r["accepted"]]
        return lines + ([f"rejected: {len(r['rejected'])} below {r['min_score']}"] if r["rejected"] else [])
    if cmd == "ask":
        return [r["answer"] or r["reason"], "", f"sources: {', '.join(r['files'])}"]
    lines = [f"{'ok' if ok else 'missing'} {name}" for name, ok in r["checks"].items()]
    lines.append(f"config {r['config'] or '(built-in defaults)'}")
    lines.append(f"home {r['home']}")
    lines.append(f"egress rank={r['egress']['rank']} answer={r['egress']['answer']}")
    lines.append(f"lockers {r['lockers']}")
    return lines


def main(argv=None, *, runner=None, jev=None):
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code
    if args.cmd == "serve" and args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"zjm: --host must be 127.0.0.1, localhost or ::1, not {args.host!r}", file=sys.stderr)
        return 2
    if args.cmd == "serve":
        from .http import make_server
        cfg = config_module.resolve(args.config)
        try:
            server = make_server(args.host, args.port, config=cfg, runner=runner, jev=jev)
        except ValueError as e:
            print(f"zjm: {e}", file=sys.stderr)
            return 2
        host, port = server.server_address[:2]
        print(f"listening on http://{host}:{port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.cmd == "mcp":
        from .mcp import serve
        cfg = config_module.resolve(args.config)
        return serve(sys.stdin, sys.stdout, config=cfg, runner=runner, jev=jev)

    op = args.cmd.replace("-", "_")
    body = _args_to_body(args.cmd, args)
    error = check(op, body)
    if error:
        print(f"zjm: {error}", file=sys.stderr)
        return 1
    cfg = config_module.resolve(args.config)
    try:
        result = OPS[op][0](body, config=cfg, runner=runner, jev=jev)
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
