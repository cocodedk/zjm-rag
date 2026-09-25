---
lean_status: pr_open
lean_pr: https://github.com/cocodedk/zjm-rag/pull/7
---
# 03 — local HTTP JSON API: `zjm serve`

## Goal

Let an app written in any language call zjm-rag over HTTP on the same machine.

## Behaviour

- `zjm_rag/http.py`, stdlib `http.server.ThreadingHTTPServer` only.
  `make_server(host="127.0.0.1", port=8765, *, store=DEFAULT_STORE, runner=None, jev=None)` returns
  the server without starting it (tests bind port `0`).
- CLI: `zjm serve [--host H] [--port P] [--store PATH]`, prints `listening on http://H:P` and serves
  until interrupted. Default host `127.0.0.1`; binding elsewhere needs an explicit `--host`.
- Endpoints, JSON in and out, `Content-Type: application/json`:
  - `GET /health` → the `doctor` dict from spec 02 (built by the same function the CLI uses); always `200`, even when `ok` is false.
  - `POST /index` body `{"sources": [...], "multilingual"?, "embedding"?, "rebuild"?}` → `index()` result.
  - `POST /find` body `{"query": str, "limit"?, "file_types"?, "min_score"?, "sort"?, "rank"?}` → `find()` result.
  - `POST /ask` body `{"query": str, "top_k"?, "answer_language"?, plus any /find field}` → `ask()` result.
  - The server's `--store` is used; a `store` field in a body is rejected (`400`), so a caller
    cannot point the server at another directory.
- Body keys map one-to-one onto the library's keyword arguments. Unknown keys, missing `query`/
  `sources`, wrong JSON types or invalid JSON → `400 {"error": "<message>"}`. `ZjmError` and
  `ValueError` from the library → `422 {"error": ...}`. Unknown path → `404`, wrong method → `405`.
  Bodies over 1 MiB → `413`.
- Body values are passed to the library as given after a type check: `sources`/`file_types` lists of
  strings, `limit`/`top_k` positive ints (a JSON bool is not an int), `min_score` a number in [0, 1],
  `rank`/`multilingual`/`rebuild` bools, strings elsewhere. A failed check is `400`.
- Every response, including errors, is a JSON object with `Content-Type: application/json`.
- Version bump to `0.3.0`.

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 25 tests** (19 earlier plus these 6 in
`tests/test_http.py`), all passing with an empty `HOME`. Tests start `make_server(port=0, ...)` with
fakes in a background thread and call it with `urllib.request` on `127.0.0.1` only:

1. `test_health` — `200` and the doctor keys.
2. `test_find_roundtrip` — body options reach the library; response equals the `find()` shape.
3. `test_ask_language` — `answer_language` reaches the LLM prompt.
4. `test_rejects_store_and_unknown_keys` — both `400`.
5. `test_library_error_is_422` — find on an empty store.
6. `test_404_405_413`.

## Jev request shape (pinned)

Nothing in this spec builds a Jev request; it goes through `zjm_rag.find`. Do not change the payload
in `zjm_rag/core.py` or the client in `zjm_rag/jev.py`. The live API rejects any other shape with
HTTP 400, and the fake Jev in the tests will not catch it. For reference, each `noul` question is exactly:

```python
{"type": "noul",
 "instructions": "Does file fK (<path>) contain the information needed to answer the question? ...",
 "criteria": {"true": "The file holds the answer.", "false": "The file does not hold the answer."}}
```

Fakes used in this spec's tests must accept only that shape.

## Out of scope

Authentication, TLS, CORS, streaming. MCP and install script (spec 04).
