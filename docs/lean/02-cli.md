---
lean_status: pr_open
lean_pr: https://github.com/cocodedk/zjm-rag/pull/4
---
# 02 — `zjm` command line with `--json`

## Goal

A `zjm` command that exposes the library from spec 01, so any app or agent that can run a
process gets the same operations, with machine-readable output.

## Behaviour

- `zjm_rag/cli.py` with `main(argv=None, *, runner=None, jev=None) -> int` (argparse, stdlib only);
  `zjm_rag/__main__.py` so `python3 -m zjm_rag` works; `pyproject.toml` gains
  `[project.scripts] zjm = "zjm_rag.cli:main"`. `runner`/`jev`, when given, are passed to the
  library; tests use them. Version bump to `0.2.0`.
- Global option on every subcommand: `--store PATH` (default `zjm_rag.DEFAULT_STORE`) and `--json`.
- Subcommands, each a direct call to the library function of the same name:
  - `zjm index SRC [SRC ...] [--multilingual] [--embedding MODEL] [--rebuild]`
  - `zjm find QUERY [--limit N] [--type T]... [--min-score F] [--sort score|zg|mtime|path] [--no-rank]`
  - `zjm ask QUERY [--top-k N] [--lang LANG] [--limit N] [--type T]... [--min-score F] [--no-rank]`
  - `zjm doctor` — checks, without calling any of them: `zg` on `PATH` (`shutil.which`), `claude`
    on `PATH`, `OPENROUTER_API_KEY` set (never print its value), store exists. Result:
    `{"ok": bool, "checks": {"zg": bool, "claude": bool, "openrouter_key": bool, "store": bool}}`;
    `ok` is true when `zg` and `openrouter_key` are true (`claude` is only needed by `ask`, `store`
    only after `index`).
- `--json`: print exactly one JSON object to stdout — the library's return value unchanged (for
  `doctor`, the dict above). Errors print `{"error": "<message>"}` to stdout.
- Without `--json`, human output:
  - `index`: `indexed <files> files from <n> sources into <store> (<embedding>)`
  - `find`: one line per accepted hit, `<score:.2f>  <path>` (`-` when score is `None`), then, when
    any were rejected, a line `rejected: <n> below <min_score>`.
  - `ask`: the answer (or the reason), a blank line, then `sources: <path>, <path>`.
  - `doctor`: one line per check, `ok`/`missing` and the name.
  - Errors go to stderr as `zjm: <message>`.
- Exit codes: `0` success (including a `find` with nothing accepted), `1` `ZjmError`/`ValueError`,
  `2` usage error (argparse's own), `doctor` exits `1` when `ok` is false.
- Usage errors (unknown subcommand or flag, missing argument, bad `--sort` value) are argparse's
  own, even with `--json`: argparse's usage message on stderr, nothing on stdout, exit `2`. The
  `--json` error object is only for errors raised after parsing (`ZjmError`, `ValueError`).

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 19 tests** (the 13 from spec 01 plus these
6 in `tests/test_cli.py`), all passing with an empty `HOME` and no network. Each calls `main([...])`
with fakes and captures stdout/stderr with `contextlib.redirect_stdout`/`redirect_stderr`:

1. `test_index_json` — `index` output parses as JSON with keys `store`, `sources`, `embedding`, `files`.
2. `test_find_json_passes_options` — `--min-score 0.7 --sort path --type py` reach the library
   (check via the fake runner's argv and the returned `min_score`/`sort`).
3. `test_find_human_output` — score lines and the `rejected:` line.
4. `test_ask_lang` — `--lang da` puts `Answer in da.` in the LLM prompt.
5. `test_error_exit_and_json` — `find` on an empty store: exit 1, stdout `{"error": ...}` with `--json`.
6. `test_doctor_hides_key` — with `OPENROUTER_API_KEY=secret-value`, output never contains `secret-value`.

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

HTTP and MCP servers, install script. Changing library behaviour from spec 01.
