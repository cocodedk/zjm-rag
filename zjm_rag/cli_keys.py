"""CLI --key-file handling: read a key (or a locker->key map) without ever touching argv (spec 08)."""
import json
import sys

KEY_CMDS = {"locker-create", "locker-drop", "file-add", "file-put", "file-remove", "file-list"}
KEYS_CMDS = {"find", "ask"}


def _read(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def usage_error(cmd, key_file):
    """A message to print and exit 2 on, or None."""
    if cmd == "file-put" and key_file == "-":
        return "--key-file - cannot be combined with file-put's stdin text"
    return None


def add_to_body(cmd, key_file, body):
    """Mutate `body` in place with "key" or "keys", read from `key_file` (or None: no key)."""
    if key_file is None:
        return
    text = _read(key_file)
    if cmd in KEYS_CMDS:
        body["keys"] = json.loads(text)
    else:
        body["key"] = text[:-1] if text.endswith("\n") else text
