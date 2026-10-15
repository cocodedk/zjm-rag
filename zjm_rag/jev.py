"""Minimal stdlib client for decision models: Jev straight to TypeSafe, every other model through OpenRouter."""
import http.client
import json
import os
import urllib.error
import urllib.request

from .errors import ZjmError

URL = "https://openrouter.ai/api/alpha/decisions"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_JEV = "jev-1.14.0"  # pinned: TypeSafe's own jev-latest still lags


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ZjmError(f"jev request redirected (HTTP {code}); refusing")


DEFAULT_MODELS = (
    "perplexity/pplx-decider-v1.1-27b",
    TYPESAFE_JEV,
    "openai/gpt-6-luna-decisions",
    "microsoft/microsoft-decision-1",
)
MAX_REQUEST_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


def route(model):
    """(url, key variable, provider model name): Jev goes to TypeSafe under its own name, the rest to OpenRouter.
    An OpenRouter-style Jev name is translated: TypeSafe rejects `jev-1.14` and its own `jev-latest` lags."""
    if model.startswith("jev-"):
        return TYPESAFE_URL, "TYPESAFE_API_KEY", model
    if model.removeprefix("~").startswith("typesafe/jev-"):
        version = model.split("/jev-", 1)[1]
        return TYPESAFE_URL, "TYPESAFE_API_KEY", TYPESAFE_JEV if version == "latest" else f"jev-{version}" + ".0" * (version.count(".") == 1)
    return URL, "OPENROUTER_API_KEY", model


def post(payload, *, model=None, timeout=30):
    """Try the selected model and remaining defaults; custom models get one attempt."""
    selected = model or payload.get("model") or os.environ.get("JEV_MODEL") or DEFAULT_MODELS[0]
    if not isinstance(selected, str) or not selected.strip():
        raise ZjmError("decision model must be a nonempty string")
    models = DEFAULT_MODELS[DEFAULT_MODELS.index(selected):] if selected in DEFAULT_MODELS else (selected,)
    attempts = [(url, env, json.dumps({**payload, "model": name}, allow_nan=False).encode())
                for url, env, name in map(route, models)]
    if any(len(body) > MAX_REQUEST_BYTES for _, _, body in attempts):
        raise ZjmError("jev request exceeds 512 KiB; reduce evidence")
    for url, env, body in attempts:
        key = os.environ.get(env)
        if not key:
            failed = ZjmError(f"{env} is not set")
            continue
        try:
            return _attempt(url, body, key, timeout)
        except ZjmError as error:
            failed = error
    raise failed


def _attempt(url, body, key, timeout):
    req = urllib.request.Request(url, data=body, method="POST", headers={
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
