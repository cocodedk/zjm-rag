"""help: a zero-cost operation that explains zjm's workflow, keys and egress, and reports this
instance's allowed paths, egress switches, languages, lockers and limits (spec 11). It changes
nothing and creates nothing, not even the home directory: no zg, age, Jev or LLM call, and no lock
is taken.
"""
from . import config as config_module
from . import evidence
from . import files
from . import lockers as lockers_mod
from .copying import _denied

# Kept in sync with search.find's `limit` default (spec 09); there is no shared constant for it.
FIND_LIMIT_DEFAULT = 8

GUIDE = """
zjm holds named lockers of files. `find` returns the candidate files and passages (with line
ranges) that may answer a question, split into accepted and rejected. `ask` has a model answer
from the accepted files and asks it to cite them. The calling app decides who may use which locker.

## Workflow

1. `help` (this call) explains the workflow, keys, egress and what this instance allows.
2. `locker_create` (with `key`, or `plain=true` for no encryption).
3. `file_add` (paths under `instance.allow`) or `file_put` (text).
4. `find` or `ask`.
5. `file_list`, `file_remove`, `locker_list`, `locker_drop` and `locker_encrypt` manage lockers.
6. `doctor` checks the instance.

## Keys

The key is an age identity, `AGE-SECRET-KEY-1...`, one per encrypted locker, sent with every call
on that locker: `key`, or `keys: {locker: key}` for `find`/`ask`. A plain locker takes no key.
`locker_encrypt` takes the new key and converts a plain locker to encrypted, one-way only. zjm
never keeps a key: it lives only in a temporary file for the length of one call, and a lost key
means a lost locker.

## Egress

- `rank` sends the question, locker names, file paths and passages to OpenRouter (Jev).
- `answer` sends the question, locker names, file paths and file text to OpenRouter (`llm`).
- `translate` sends only the question to OpenRouter (`translate_model`).

Each switch is off unless the config turns it on. Per-call `rank`/`translate` can only turn a
switch off, never on.

## Rules

- `file_add` accepts only paths under `allow`.
- Secret files (`.env*`, `*.pem`, `*.key`, `id_rsa*`, ...) and gitignored files are never copied.
- A file with the same name is replaced.
- `file_put` accepts at most 1 MiB.
- `file_remove`: if any requested name is missing, nothing is removed.

## Errors

HTTP, MCP and `--json` return an operation error as `{"error": "..."}`. A malformed key gives
`invalid key`. A well-formed key that does not match gives `wrong key or damaged locker <name>`.
""".strip()


def _visible_allow(cfg):
    """`allow`, minus any entry inside (or equal to) a `deny` entry or `home`, compared lexically:
    such an entry could never be read anyway, so it is not worth advertising."""
    return [a for a in cfg["allow"] if not _denied(a, cfg["deny"], cfg["home"])]


def _lockers_view(cfg):
    """[{"name", "encrypted"}] read the same way `doctor` counts lockers: no lock is taken and
    nothing is created. `[]` when `<home>/lockers` does not exist; `None` if reading it fails."""
    try:
        _, lockers_dir = lockers_mod.home_dirs(cfg)
        if not lockers_dir.is_dir():
            return []
        out = []
        for p in lockers_dir.iterdir():
            if p.is_file() and p.suffix == ".age":
                out.append({"name": p.stem, "encrypted": True})
            elif p.is_dir() and (p / "locker.json").exists():
                out.append({"name": p.name, "encrypted": False})
        out.sort(key=lambda e: e["name"])
        return out
    except OSError:
        return None


def help(*, config=None, runner=None, jev=None):
    """The guide plus this instance's settings. Never raises (a bad lockers read gives `None`
    instead), and never calls zg, age, Jev or an LLM. `runner`/`jev` are accepted, unused, only so
    `help` takes the same keywords as every other op."""
    cfg = config_module.resolve(config)
    instance = {
        "allow": _visible_allow(cfg),
        "egress": dict(cfg["egress"]),
        "languages": list(cfg["languages"]),
        "translate_model": cfg["translate_model"],
        "llm": cfg["llm"],
        "embedding": cfg["embedding"],
        "lockers": _lockers_view(cfg),
        "limits": {"file_put_bytes": files.MAX_PUT_BYTES, "find_limit_default": FIND_LIMIT_DEFAULT,
                  "ask_chars": evidence.ASK_CHARS},
    }
    return {"guide": GUIDE, "instance": instance}
