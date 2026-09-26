"""OPS: the single table the CLI, HTTP and MCP surfaces are generated from (spec 06)."""
from . import core
from . import files
from . import jev as jev_client
from . import llm as llm_client
from . import lockers
from . import search
from . import zg

_STR = {"type": "string"}
_STR_ARR = {"type": "array", "items": {"type": "string"}}
_KEYS = {"type": "object", "additionalProperties": {"type": "string"}}


def _wrap(func, *, needs_runner=False, needs_jev=False, needs_llm=False):
    def call(args, *, config, runner=None, jev=None, llm=None):
        kwargs = dict(args, config=config)
        if needs_runner:
            kwargs["runner"] = runner or zg.run
        if needs_jev:
            kwargs["jev"] = jev or jev_client.post
        if needs_llm:
            kwargs["llm"] = llm or llm_client.post
        return func(**kwargs)
    return call


_FIND_PROPS = {"query": _STR, "lockers": {**_STR_ARR, "minItems": 1}, "keys": _KEYS,
              "limit": {"type": "integer", "minimum": 1},
              "file_types": _STR_ARR, "min_score": {"type": "number", "minimum": 0, "maximum": 1},
              "sort": {"type": "string", "enum": list(search.SORTS)}, "rank": {"type": "boolean"},
              "translate": {"type": "boolean"}}
_ASK_PROPS = {**_FIND_PROPS, "top_k": {"type": "integer", "minimum": 1}, "answer_language": _STR}

OPS = {
    "locker_create": (_wrap(lockers.locker_create, needs_runner=True),
                      {"type": "object", "properties": {"name": _STR, "key": _STR,
                                                        "multilingual": {"type": "boolean"}, "embedding": _STR,
                                                        "plain": {"type": "boolean"}},
                       "required": ["name"], "additionalProperties": False},
                      "Create a named locker, encrypted with a key (or plain only with plain=true), with a fixed embedding model."),
    "locker_list": (_wrap(lockers.locker_list),
                    {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                    "List lockers, each with whether it is encrypted, and its size."),
    "locker_drop": (_wrap(lockers.locker_drop, needs_runner=True),
                    {"type": "object", "properties": {"name": _STR, "key": _STR}, "required": ["name"],
                     "additionalProperties": False},
                    "Delete a locker and everything in it."),
    "locker_encrypt": (_wrap(lockers.locker_encrypt, needs_runner=True),
                       {"type": "object", "properties": {"name": _STR, "key": _STR},
                        "required": ["name", "key"], "additionalProperties": False},
                       "Seal a plain locker into an encrypted one; this cannot be undone."),
    "file_add": (_wrap(files.file_add, needs_runner=True),
                {"type": "object", "properties": {"locker": _STR, "key": _STR, "paths": _STR_ARR},
                 "required": ["locker", "paths"], "additionalProperties": False},
                "Copy files or directories into a locker and index them."),
    "file_put": (_wrap(files.file_put, needs_runner=True),
                {"type": "object", "properties": {"locker": _STR, "key": _STR, "name": _STR, "text": _STR},
                 "required": ["locker", "name", "text"], "additionalProperties": False},
                "Write text as a file in a locker and index it."),
    "file_remove": (_wrap(files.file_remove, needs_runner=True),
                   {"type": "object", "properties": {"locker": _STR, "key": _STR, "names": _STR_ARR},
                    "required": ["locker", "names"], "additionalProperties": False},
                   "Remove files or directory prefixes from a locker."),
    "file_list": (_wrap(files.file_list, needs_runner=True),
                 {"type": "object", "properties": {"locker": _STR, "key": _STR}, "required": ["locker"],
                  "additionalProperties": False},
                 "List the files in a locker."),
    "find": (_wrap(search.find, needs_runner=True, needs_jev=True, needs_llm=True),
            {"type": "object", "properties": _FIND_PROPS, "required": ["query", "lockers"],
             "additionalProperties": False},
            "Find the files across lockers that may hold the answer to a question."),
    "ask": (_wrap(search.ask, needs_runner=True, needs_jev=True, needs_llm=True),
           {"type": "object", "properties": _ASK_PROPS, "required": ["query", "lockers"],
            "additionalProperties": False},
           "Answer a question with an LLM from the top accepted files across lockers."),
    "doctor": (_wrap(core.doctor),
              {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
              "Report whether zg, age, OPENROUTER_API_KEY and lockers are present."),
}


def _type_ok(value, spec):
    t = spec.get("type")
    if t == "string":
        ok = isinstance(value, str)
    elif t == "boolean":
        ok = isinstance(value, bool)
    elif t == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif t == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif t == "array":
        ok = isinstance(value, list) and all(_type_ok(x, spec["items"]) for x in value)
        if ok and "minItems" in spec:
            ok = len(value) >= spec["minItems"]
    elif t == "object":
        ok = isinstance(value, dict) and all(isinstance(k, str) for k in value) and \
            all(_type_ok(v, spec["additionalProperties"]) for v in value.values())
    else:
        ok = True
    if ok and t in ("integer", "number") and "minimum" in spec:
        ok = value >= spec["minimum"]
    if ok and t in ("integer", "number") and "maximum" in spec:
        ok = value <= spec["maximum"]
    if ok and "enum" in spec:
        ok = value in spec["enum"]
    return ok


def check(op, body):
    """The error message for a bad body against OPS[op]'s schema, or None."""
    _, schema, _ = OPS[op]
    if not isinstance(body, dict):
        return "body must be a JSON object"
    for reserved in ("home", "store", "config"):
        if reserved in body:
            return f"{reserved} is set by the server"
    props, required = schema["properties"], set(schema["required"])
    unknown = sorted(set(body) - set(props))
    if unknown:
        return f"unknown keys: {', '.join(unknown)}"
    missing = sorted(required - set(body))
    if missing:
        return f"missing key: {', '.join(missing)}"
    for key, value in body.items():
        if not _type_ok(value, props[key]):
            return f"{key} must match schema"
    return None
