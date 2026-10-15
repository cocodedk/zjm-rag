"""zjm: the library on the command line, with --json."""
import argparse
import json
import os
import sys

from . import cli_keys, search
from . import config as config_module
from .cli_human import human as _human
from .errors import ZjmError
from .ops import OPS, check


def _common(p):
    p.add_argument("--config", default=None)
    p.add_argument("--json", action="store_true")
    return p


def _parser():
    parser = argparse.ArgumentParser(prog="zjm", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = _common(sub.add_parser("locker-create"))
    p.add_argument("name")
    p.add_argument("--key-file", metavar="PATH")
    p.add_argument("--multilingual", action="store_true")
    p.add_argument("--embedding", metavar="MODEL")
    p.add_argument("--plain", action="store_true")

    _common(sub.add_parser("locker-list"))

    for name in ("locker-drop", "locker-encrypt"):
        p = _common(sub.add_parser(name))
        p.add_argument("name")
        p.add_argument("--key-file", metavar="PATH", required=name == "locker-encrypt")

    for name in ("file-add", "file-put", "file-remove", "file-list"):
        p = _common(sub.add_parser(name))
        p.add_argument("locker")
        p.add_argument("--key-file", metavar="PATH")
        if name == "file-add":
            p.add_argument("paths", nargs="+", metavar="PATH")
        elif name == "file-put":
            p.add_argument("name")
        elif name == "file-remove":
            p.add_argument("names", nargs="+", metavar="NAME")

    for name in ("find", "ask"):
        p = _common(sub.add_parser(name))
        p.add_argument("query")
        p.add_argument("-l", "--locker", action="append", dest="lockers", required=True, metavar="LOCKER")
        p.add_argument("--key-file", metavar="PATH")
        p.add_argument("--limit", type=int, default=8)
        p.add_argument("--type", action="append", dest="types", metavar="T")
        p.add_argument("--min-score", type=float, default=0.5)
        if name == "find":
            p.add_argument("--sort", choices=list(search.SORTS))
        p.add_argument("--no-rank", action="store_true")
        p.add_argument("--model", help="Decision model override (not the answer model)")
        p.add_argument("--no-translate", action="store_true")
        if name == "ask":
            p.add_argument("--top-k", type=int)
            p.add_argument("--lang")

    _common(sub.add_parser("doctor"))
    _common(sub.add_parser("help"))

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
        for name in ("multilingual", "embedding", "plain"):
            value = getattr(args, name)
            if value:
                body[name] = value
        return body
    if cmd in ("locker-list", "doctor", "help"):
        return {}
    if cmd in ("locker-drop", "locker-encrypt"):
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
    if args.model:
        body["model"] = args.model
    if args.types:
        body["file_types"] = args.types
    if args.no_rank:
        body["rank"] = False
    if args.no_translate:
        body["translate"] = False
    if cmd == "find" and args.sort:
        body["sort"] = args.sort
    if cmd == "ask":
        if args.top_k is not None:
            body["top_k"] = args.top_k
        if args.lang:
            body["answer_language"] = args.lang
    return body


def main(argv=None, *, runner=None, jev=None, llm=None):
    if os.environ.get("ZJM_IN_CONTAINER") != "1":
        print("zjm: runs only in its container; use the zjm launcher", file=sys.stderr)
        return 1
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code
    try:
        return _execute(args, runner=runner, jev=jev, llm=llm)
    except (ZjmError, ValueError, OSError) as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(e)}))
        else:
            print(f"zjm: {e}", file=sys.stderr)
        return 1


def _execute(args, *, runner, jev, llm):
    allowed_hosts = ("127.0.0.1", "localhost", "::1")
    if os.environ.get("ZJM_IN_CONTAINER") == "1":
        allowed_hosts += ("0.0.0.0",)
    if args.cmd == "serve" and args.host not in allowed_hosts:
        print(f"zjm: --host must be 127.0.0.1, localhost or ::1, not {args.host!r}", file=sys.stderr)
        return 2
    if args.cmd == "serve":
        from .http import make_server
        cfg = config_module.resolve(args.config)
        try:
            server = make_server(args.host, args.port, config=cfg, runner=runner, jev=jev, llm=llm)
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
        return serve(sys.stdin, sys.stdout, config=cfg, runner=runner, jev=jev, llm=llm)

    key_file = getattr(args, "key_file", None)
    usage_err = cli_keys.usage_error(args.cmd, key_file)
    if usage_err:
        print(f"zjm: {usage_err}", file=sys.stderr)
        return 2
    op = args.cmd.replace("-", "_")
    body = _args_to_body(args.cmd, args)
    cli_keys.add_to_body(args.cmd, key_file, body)
    error = check(op, body)
    if error:
        raise ZjmError(error)
    cfg = config_module.resolve(args.config)
    result = OPS[op][0](body, config=cfg, runner=runner, jev=jev, llm=llm)
    lines = [json.dumps(result)] if args.json else _human(args.cmd, result)
    if lines:
        print("\n".join(lines))
    return 1 if args.cmd == "doctor" and not result["ok"] else 0
