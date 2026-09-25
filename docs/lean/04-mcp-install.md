---
lean_status: pr_open
lean_worktree: /tmp/graph-ujv_xxnp/task-04-mcp-install
lean_pr: https://github.com/cocodedk/zjm-rag/pull/8
---
# 04 — MCP server and one-shot install

## Goal

Agents get zjm-rag as MCP tools, and a person installs everything with one command.

## Behaviour

### MCP: `zjm mcp`

- `zjm_rag/mcp.py`, stdlib only: JSON-RPC 2.0 over stdio, one JSON message per line, no SDK.
  `serve(stdin, stdout, *, store=DEFAULT_STORE, runner=None, jev=None)` so tests drive it with
  `io.StringIO`. CLI: `zjm mcp [--store PATH]`.
- Handles `initialize` (reply `protocolVersion` echoing the client's, `capabilities: {"tools": {}}`,
  `serverInfo: {"name": "zjm-rag", "version": <package version>}`, where the version is `importlib.metadata.version("zjm-rag")`, or `"0.0.0+unknown"` when the package is not installed; no version constant in the code), `notifications/initialized`
  (no reply), `tools/list`, `tools/call`, `ping`. Unknown method → error `-32601`; bad params →
  `-32602`; unparsable line → `-32700`. Notifications never get a reply.
- Tools, each with a one-sentence description and a JSON Schema `inputSchema` whose properties
  mirror the HTTP bodies from spec 03 (`additionalProperties: false`):
  `zjm_index`, `zjm_find`, `zjm_ask`, `zjm_doctor`.
  `zjm_doctor` takes no arguments (empty `properties`). Arguments are type-checked exactly like the
  HTTP bodies in spec 03; a failed check is a `tools/call` result with `isError: true`, not a
  JSON-RPC error. A `store` argument is not accepted; the server's `--store` is used.
- `initialize` replies with the client's `protocolVersion` when it is a string, else `"2025-06-18"`.
- `tools/call` result: `{"content": [{"type": "text", "text": <JSON of the library result>}], "structuredContent": <the result>}`;
  a `ZjmError`/`ValueError` gives the same shape with `"isError": true` and `{"error": msg}`.
- Nothing but JSON-RPC is written to stdout; logs go to stderr.

### One-shot install: `install.sh`

- POSIX `sh`, at the repo root, runnable as `curl -fsSL https://raw.githubusercontent.com/cocodedk/zjm-rag/main/install.sh | sh`.
- Steps, each printed as one line; stops with a clear message on the first failure:
  1. `python3` ≥ 3.10 present, else stop.
  2. `zg` on `PATH`, else `npm install -g @zvec/zvec-grep` when `npm` exists, else stop saying
     Node/npm is needed for zg.
  3. Install the package: `uv tool install --force git+https://github.com/cocodedk/zjm-rag` when
     `uv` exists, else `pipx install --force git+https://github.com/cocodedk/zjm-rag` when `pipx`
     exists, else `python3 -m pip install --user git+https://github.com/cocodedk/zjm-rag`.
  4. Check the result (settled; this is the whole rule): stop with exit `1` and a message on stderr
     when `command -v zjm` or `command -v zg` fails after the install (saying the install
     directory, e.g. `~/.local/bin`, may be missing from `PATH`). Otherwise run `zjm doctor`, print
     its output and **ignore its exit code**: a missing `OPENROUTER_API_KEY` or `claude` is only a
     warning line saying what each is for, and the script exits `0`. In dry run the two post-install
     `command -v` checks are skipped and `+ zjm doctor` is printed.
- The Python check is `python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'`; tool presence
  is `command -v <tool>`. These two probes always run, also in dry run.
- `ZJM_INSTALL_DRY_RUN=1` runs no installing command: each command from steps 2–4 is printed on its
  own line as `+ <command>` instead of being run (step 4 prints `+ zjm doctor`); the tests use this.
- Exit `0` on success, `1` on the first failing step, with the message on stderr.
- The installed `zjm` must work from the wheel alone: no file outside the `zjm_rag` package is read at runtime.

### README

`README.md`: what it does in two sentences, the one-line install, then short examples for the
library, the CLI, HTTP (`curl` against `/find`) and MCP (a Claude Code `claude mcp add zjm -- zjm mcp`
line), the threshold and sort options, `--multilingual` for non-English content, and the
requirements (`zg`, `OPENROUTER_API_KEY`, optional `claude`). Version bump to `0.4.0`.

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 32 tests** (25 earlier plus these 7), all
passing with an empty `HOME` and no network:

- `tests/test_mcp.py`:
  1. `test_initialize_and_list` — four tools, each with a description and `inputSchema`.
  2. `test_call_find` — `structuredContent` equals the fake-backed `find()` result.
  3. `test_errors` — unknown method `-32601`, bad JSON `-32700`, library error `isError: true`.
  4. `test_notification_gets_no_reply`.
- `tests/test_install.py` (runs `sh install.sh` with `ZJM_INSTALL_DRY_RUN=1` and a `PATH` of stub
  scripts in a temp dir; this is the only test allowed to start a subprocess, and only `sh` — it replaces spec 01's "no subprocess in tests" check for this one file):
  5. `test_prefers_uv_and_installs_zg` — stubs `python3`, `npm`, `uv`; output lists
     `npm install -g @zvec/zvec-grep` and `uv tool install --force git+https://github.com/cocodedk/zjm-rag`.
  6. `test_pip_fallback` — stubs only `python3` and `zg`; output lists the `pip install --user` line.
  7. `test_fails_when_zjm_missing` — not dry run, stubs `python3`, `zg` and a `uv` that installs
     nothing: exit `1`, stderr mentions `PATH`.

These seven (with the four MCP tests above) are the complete required test set for this spec.

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

Publishing to PyPI, Homebrew, Windows installer, auto-configuring MCP clients.
