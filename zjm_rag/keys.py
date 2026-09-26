"""age key format and recipient lookup (spec 08). The key itself never appears in argv/env/logs."""
import os
import re

from .errors import ZjmError

KEY_RE = re.compile(r"^AGE-SECRET-KEY-1[0-9A-Z]+$")


def check_key(key):
    """The key, with any single trailing newline stripped, or raise ZjmError("invalid key")."""
    if not isinstance(key, str):
        raise ZjmError("invalid key")
    k = key[:-1] if key.endswith("\n") else key
    if "\n" in k or not KEY_RE.match(k):
        raise ZjmError("invalid key")
    return k


def get_recipient(key_file, runner):
    """`age-keygen -y <key_file>` through `runner` (bytes), or raise ZjmError("invalid key")."""
    code, out, _err = runner(["age-keygen", "-y", str(key_file)], cwd=str(key_file.parent),
                             env=dict(os.environ), input=b"")
    text = out.decode("utf-8", "replace") if isinstance(out, bytes) else out
    lines = [ln for ln in text.split("\n") if ln != ""]
    if code != 0 or len(lines) != 1:
        raise ZjmError("invalid key")
    return lines[0]
