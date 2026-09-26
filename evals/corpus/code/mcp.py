"""zjm mcp: the library as MCP tools, JSON-RPC 2.0 over stdio, generated from OPS (spec 06)."""
import json
import sys
from importlib import metadata

from . import config as config_module
from .errors import ZjmError
from .ops import OPS, check


def _version():
    try:
        return metadata.version("zjm-rag")
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def _tool_result(obj, error=False):
    result = {"content": [{"type": "text", "text": json.dumps(obj)}], "structuredContent": obj}
    return {**result, "isError": True} if error else result


class _BadParams(Exception):
    pass


def serve(stdin, stdout, *, config=None, runner=None, jev=None):
    """Answer JSON-RPC lines from `stdin` on `stdout` until EOF."""
    cfg = config_module.resolve(config)
    fakes = {"runner": runner, "jev": jev}
    tools = {f"zjm_{name}": (name, desc) for name, (_, _, desc) in OPS.items()}

    def call_tool(params):
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or tool_name not in tools:
            raise _BadParams(f"unknown tool: {tool_name!r}")
        op = tools[tool_name][0]
        args = params.get("arguments", {})
        error = check(op, args)
        if error:
            return _tool_result({"error": error}, True)
        try:
            return _tool_result(OPS[op][0](args, config=cfg, **fakes))
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
            return {"tools": [{"name": n, "description": d, "inputSchema": OPS[op][1]}
                              for n, (op, d) in tools.items()]}
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
