"""Minimal stdlib client for the OpenRouter chat completions API (the answer model, spec 09)."""
import http.client
import json
import os
import urllib.error
import urllib.request

from .errors import ZjmError

URL = "https://openrouter.ai/api/v1/chat/completions"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ZjmError(f"answer model request redirected (HTTP {code}); refusing")


def _open(req, timeout):
    return urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout)


def post(model, messages, *, timeout=120, reasoning=True):
    """POST one chat completion; returns the answer text, or raises ZjmError. `reasoning=False`
    (used for translating, spec 10) adds "reasoning": {"enabled": false} to the body; otherwise
    the body is unchanged."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ZjmError("OPENROUTER_API_KEY is not set")
    payload = {"model": model, "messages": messages, "provider": {"data_collection": "deny"}}
    if not reasoning:
        payload["reasoning"] = {"enabled": False}
    body = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with _open(req, timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ZjmError(f"answer model request failed: HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        raise ZjmError(f"answer model request failed: {getattr(e, 'reason', e)}") from None
    except ValueError:
        raise ZjmError("answer model response is not JSON") from None
    choices = data.get("choices") if isinstance(data, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ZjmError("answer model returned no text")
    return content
