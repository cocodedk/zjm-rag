"""zjm mcp: the library as MCP tools, JSON-RPC 2.0 over stdio, one message per line."""
import json
import sys
from importlib import metadata

from . import core
from .errors import ZjmError
from .http import CHECKS, KEYS, _check

TOOLS = {"zjm_index": ("/index", "Copy source folders into the store and build its zg index."),
         "zjm_find": ("/find", "Find the indexed files that may hold the answer, ranked by Jev."),
         "zjm_ask": ("/ask", "Answer a question with an LLM from the top accepted files, citing their paths."),
         "zjm_doctor": (None, "Report whether zg, claude, OPENROUTER_API_KEY and the store are present.")}
TYPES = {"sources": {"type": "array", "items": {"type": "string"}},
         "file_types": {"type": "array", "items": {"type": "string"}},
         "limit": {"type": "integer", "minimum": 1}, "top_k": {"type": "integer", "minimum": 1},
         "min_score": {"type": "number", "minimum": 0, "maximum": 1},
         "sort": {"type": "string", "enum": list(core.SORTS)}}


def _version():
    try:
        return metadata.version("zjm-rag")
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def _schema(path):
    required, allowed = KEYS[path] if path else (set(), set())
    props = {k: TYPES.get(k, {"type": "boolean" if k in CHECKS else "string"}) for k in sorted(allowed)}
    return {"type": "object", "properties": props, "required": sorted(required), "additionalProperties": False}


def _tool_result(obj, error=False):
    result = {"content": [{"type": "text", "text": json.dumps(obj)}], "structuredContent": obj}
    return {**result, "isError": True} if error else result


class _BadParams(Exception):
    pass


def serve(stdin, stdout, *, store=core.DEFAULT_STORE, runner=None, jev=None):
    """Answer JSON-RPC lines from `stdin` on `stdout` until EOF."""
    fakes = {k: v for k, v in {"runner": runner, "jev": jev}.items() if v is not None}
    calls = {"/index": lambda a: core.index(**a, store=store, **{k: v for k, v in fakes.items() if k != "jev"}),
             "/find": lambda a: core.find(**a, store=store, **fakes),
             "/ask": lambda a: core.ask(**a, store=store, **fakes),
             None: lambda a: core.doctor(store)}

    def call_tool(params):
        if not isinstance(params.get("name"), str) or params["name"] not in TOOLS:
            raise _BadParams(f"unknown tool: {params.get('name')!r}")
        path = TOOLS[params["name"]][0]
        args = params.get("arguments", {})
        if path:
            error = _check(path, args)
        else:
            error = None if args == {} else "zjm_doctor takes no arguments"
        if error:
            return _tool_result({"error": error}, True)
        try:
            return _tool_result(calls[path](args))
        except (ZjmError, ValueError) as e:
            return _tool_result({"error": str(e)}, True)

    def handle(method, params):
        if method == "initialize":
            version = params.get("protocolVersion")
            return {"protocolVersion": version if isinstance(version, str) else "2025-06-18",
                    "capabilities": {"tools": {}}, "serverInfo": {"name": "zjm-rag", "version": _version()}}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{"name": n, "description": d, "inputSchema": _schema(p)}
                              for n, (p, d) in TOOLS.items()]}
        if method == "tools/call":
            return call_tool(params)
        return None

    def reply(msg):
        if not isinstance(msg, dict) or not isinstance(msg.get("method"), str):
            return {"code": -32600, "message": "invalid request"}, None
        params = msg.get("params", {})
        if not isinstance(params, dict):
            return {"code": -32602, "message": "params must be an object"}, None
        try:
            result = handle(msg["method"], params)
        except _BadParams as e:
            return {"code": -32602, "message": str(e)}, None
        except Exception as e:
            print(f"zjm mcp: {type(e).__name__}: {e}", file=sys.stderr)
            return {"code": -32603, "message": f"{type(e).__name__}: {e}"}, None
        if result is None:
            return {"code": -32601, "message": f"unknown method: {msg['method']}"}, None
        return None, result

    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            if isinstance(msg, dict) and "id" not in msg:
                continue
            error, result = reply(msg)
            msg_id = msg.get("id") if isinstance(msg, dict) else None
            out = {"jsonrpc": "2.0", "id": msg_id, **({"error": error} if error else {"result": result})}
        stdout.write(json.dumps(out) + "\n")
        stdout.flush()
    return 0
