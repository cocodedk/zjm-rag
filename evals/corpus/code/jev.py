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


def post(payload, *, timeout=30):
    """POST one decision request; returns the parsed JSON response."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ZjmError("OPENROUTER_API_KEY is not set")
    body = json.dumps({**payload, "model": os.environ.get("JEV_MODEL", "typesafe/jev-1.13")}).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ZjmError(f"jev request failed: HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        raise ZjmError(f"jev request failed: {getattr(e, 'reason', e)}") from None
    except ValueError:
        raise ZjmError("jev response is not JSON") from None
