"""The zjm config file: lookup, validation and path resolution (spec 05)."""
import json
import os

from .errors import ZjmError

ALLOWED_KEYS = {"home", "allow", "deny", "exclude", "egress", "embedding", "llm"}
EGRESS_KEYS = {"rank", "answer"}
DEFAULT_EMBEDDING = "local/potion-code-16m-v2"
MULTILINGUAL_EMBEDDING = "local/potion-multilingual-128m"
BAKED_EMBEDDINGS = {DEFAULT_EMBEDDING, MULTILINGUAL_EMBEDDING}
DEFAULT_LLM = ["claude", "-p", "--tools", "", "--strict-mcp-config", "--model", "sonnet", "--effort", "medium"]


def check_embedding_baked(model):
    """In the container, only the two baked models may be used; anywhere else this is a no-op."""
    if os.environ.get("ZJM_IN_CONTAINER") == "1" and model not in BAKED_EMBEDDINGS:
        raise ZjmError(f"embedding {model!r} is not baked into the container; use one of {sorted(BAKED_EMBEDDINGS)}")


def _default_home(environ):
    xdg = environ.get("XDG_DATA_HOME")
    base = xdg if xdg else os.path.join(environ.get("HOME", ""), ".local/share")
    return os.path.join(base, "zjm")


def _find_file(path, *, cwd, environ):
    """The config file to use, or None for the built-in defaults."""
    if path is not None:
        if not os.path.isfile(path):
            raise ZjmError(f"config file not found: {path}")
        return path
    env_path = environ.get("ZJM_CONFIG")
    if env_path:
        if not os.path.isfile(env_path):
            raise ZjmError(f"config file not found: {env_path}")
        return env_path
    cwd_path = os.path.join(cwd, ".zjm", "config.json")
    if os.path.isfile(cwd_path):
        return cwd_path
    xdg = environ.get("XDG_CONFIG_HOME")
    xdg_path = os.path.join(xdg, "zjm", "config.json") if xdg else os.path.join(
        environ.get("HOME", ""), ".config", "zjm", "config.json")
    return xdg_path if os.path.isfile(xdg_path) else None


def _type_error(key, used_path, msg):
    raise ZjmError(f"{key} must be {msg} in {used_path}")


def _check_type(raw, key, ok, msg, used_path):
    if key in raw and not ok(raw[key]):
        _type_error(key, used_path, msg)


def _is_str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _validate(raw, used_path):
    if not isinstance(raw, dict):
        raise ZjmError(f"config file {used_path} must be a JSON object")
    unknown = sorted(set(raw) - ALLOWED_KEYS)
    if unknown:
        raise ZjmError(f"unknown key {unknown[0]!r} in {used_path}")
    _check_type(raw, "home", lambda v: isinstance(v, str), "a string", used_path)
    _check_type(raw, "allow", _is_str_list, "a list of strings", used_path)
    _check_type(raw, "deny", _is_str_list, "a list of strings", used_path)
    _check_type(raw, "exclude", _is_str_list, "a list of strings", used_path)
    _check_type(raw, "embedding", lambda v: isinstance(v, str), "a string", used_path)
    if "embedding" in raw and not raw["embedding"].startswith("local/"):
        raise ZjmError(f"embedding must start with local/ in {used_path}")
    if "embedding" in raw:
        check_embedding_baked(raw["embedding"])
    _check_type(raw, "llm", lambda v: _is_str_list(v) and len(v) > 0, "a non-empty list of strings", used_path)
    egress = raw.get("egress", {})
    if not isinstance(egress, dict):
        _type_error("egress", used_path, "an object")
    unknown_e = sorted(set(egress) - EGRESS_KEYS)
    if unknown_e:
        raise ZjmError(f"unknown key {unknown_e[0]!r} in egress in {used_path}")
    for key in EGRESS_KEYS:
        if key in egress and not isinstance(egress[key], bool):
            _type_error(f"egress.{key}", used_path, "a boolean")
    return egress


def _resolve_path(value, *, base_dir, home_env):
    if value == "~" or value.startswith("~/"):
        value = home_env + value[1:]
    if not os.path.isabs(value):
        value = os.path.join(base_dir, value)
    return os.path.abspath(value)


def resolve(config):
    """`config` as a dict (as-is), a path to load, or None (load defaults)."""
    if isinstance(config, dict):
        return config
    return load(config)


def load(path=None, *, cwd=None, environ=None):
    """The resolved config: every key above, plus "path" (the file used, or None)."""
    cwd = cwd if cwd is not None else os.getcwd()
    environ = os.environ if environ is None else environ
    used_path = _find_file(path, cwd=cwd, environ=environ)
    raw = {}
    if used_path is not None:
        try:
            with open(used_path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            raise ZjmError(f"cannot read config file {used_path}: {e}") from None
        try:
            raw = json.loads(text)
        except ValueError:
            raise ZjmError(f"invalid JSON in {used_path}") from None
    egress_raw = _validate(raw, used_path)
    base_dir = os.path.dirname(os.path.abspath(used_path)) if used_path else cwd
    home_env = environ.get("HOME", "")

    def resolve(value):
        return _resolve_path(value, base_dir=base_dir, home_env=home_env)

    home = resolve(raw["home"]) if "home" in raw else os.path.abspath(_default_home(environ))
    return {
        "home": home,
        "allow": [resolve(p) for p in raw.get("allow", [])],
        "deny": [resolve(p) for p in raw.get("deny", [])],
        "exclude": list(raw.get("exclude", [])),
        "egress": {"rank": bool(egress_raw.get("rank", False)), "answer": bool(egress_raw.get("answer", False))},
        "embedding": raw.get("embedding", DEFAULT_EMBEDDING),
        "llm": list(raw.get("llm", DEFAULT_LLM)),
        "path": used_path,
    }
