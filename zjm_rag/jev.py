"""Minimal stdlib client for the OpenRouter Decisions API (Jev)."""
import http.client
import json
import os
import urllib.error
import urllib.request

from .errors import ZjmError

URL = "https://openrouter.ai/api/alpha/decisions"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ZjmError(f"jev request redirected (HTTP {code}); refusing")


DEFAULT_MODELS = (
    "perplexity/pplx-decider-v1.1-27b",
    "~typesafe/jev-latest",
    "openai/gpt-6-luna-decisions",
    "microsoft/microsoft-decision-1",
)
MAX_REQUEST_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


def post(payload, *, model=None, timeout=30):
    """Try the selected model and remaining defaults; custom models get one attempt."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ZjmError("OPENROUTER_API_KEY is not set")
    selected = model or payload.get("model") or os.environ.get("JEV_MODEL") or DEFAULT_MODELS[0]
    if not isinstance(selected, str) or not selected.strip():
        raise ZjmError("decision model must be a nonempty string")
    models = DEFAULT_MODELS[DEFAULT_MODELS.index(selected):] if selected in DEFAULT_MODELS else (selected,)
    bodies = [json.dumps({**payload, "model": name}, allow_nan=False).encode() for name in models]
    if any(len(body) > MAX_REQUEST_BYTES for body in bodies):
        raise ZjmError("jev request exceeds 512 KiB; reduce evidence")
    for body in bodies:
        try:
            return _attempt(body, key, timeout)
        except ZjmError as error:
            failed = error
    raise failed


def _attempt(body, key, timeout):
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ZjmError("jev response exceeds 1 MiB")
        result = json.loads(body)
    except urllib.error.HTTPError as e:
        e.close()
        raise ZjmError(f"jev request failed: HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        raise ZjmError("jev connection failed or timed out") from None
    except ValueError:
        raise ZjmError("jev response is not JSON") from None
    if not isinstance(result, dict) or "error" in result:
        raise ZjmError("jev returned an error or a non-object response")
    return result
