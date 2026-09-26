# 11 — A help operation for agents and apps

## Goal

One operation tells a caller how to use zjm and what this instance allows. It changes nothing
and creates nothing, not even the home folder. Today an
MCP agent sees only one-line tool descriptions, so it must guess three things:
- which paths `file_add` accepts (only paths under the config's `allow` roots)
- how keys work
- what each egress switch sends out

`help` answers all of it in one call and costs nothing: no zg, age, Jev or model call.

This spec builds on specs 01–10; where they disagree, this one wins.

## Behaviour

### The operation: `help`

- It is a new entry in `OPS`, with no arguments (an empty object schema,
  `additionalProperties: false`) and this description: `"Explain how to use zjm and what this
  instance allows: workflow, keys, egress, allowed source paths and lockers. Call this first."`.
- The surfaces follow the `OPS` rules: `zjm help` (CLI), `POST /help` (HTTP), `zjm_help` (MCP).
- `help(*, config=None, runner=None, jev=None)` returns:

  ```json
  {"guide": "<GUIDE>",
   "instance": {"allow": [...], "egress": {"rank": b, "answer": b, "translate": b},
                "languages": [...], "translate_model": "...", "llm": "...", "embedding": "...",
                "lockers": [{"name": "...", "encrypted": b}],
                "limits": {"file_put_bytes": 1048576, "find_limit_default": 8, "ask_chars": <ASK_CHARS>}}}
  ```

  - `allow` is the resolved config list, minus any entry inside (or equal to) a `deny` entry or
    `home`, compared lexically. Such an entry could never be read anyway.
  - `lockers` lists the names and the `encrypted` flag only. They come from reading the names in
    `<home>/lockers` when that directory exists (like `doctor`'s count), without taking the lock
    and without creating anything. When it does not exist, `lockers` is `[]`. If reading it fails,
    `lockers` is `null`. `help` never raises for that, and no path appears in the result.
  - `find_limit_default` is the default number of candidate files per group (spec 10 can add as
    many again from translations).
  - `ask_chars` is `evidence.ASK_CHARS`.
  - **Never included:** `deny` (it would reveal paths the owner forbids), `home`, keys, and any
    file content.

### The guide

`GUIDE` is a module constant (`zjm_rag/guide.py`) of at most 3000 characters of plain Markdown. It
covers, in this order:
1. **What zjm is.** Named lockers of files. `find` returns the candidate files and passages
   (with line ranges) that may answer a question, split into accepted and rejected. `ask` has a
   model answer from the accepted files and asks it to cite them. The calling app decides who may
   use which locker.
2. **Workflow:**
   - `locker_create` (with `key`, or `plain=true`)
   - `file_add` (paths under `instance.allow`) or `file_put` (text)
   - `find` or `ask`
   - `file_list`, `file_remove`, `locker_list`, `locker_drop` and `locker_encrypt` to manage
     lockers
   - `doctor` to check the instance
3. **Keys:**
   - The key is an age identity, `AGE-SECRET-KEY-1…`, one per encrypted locker, sent with every
     call on that locker: `key`, or `keys: {locker: key}` for `find`/`ask`.
   - A plain locker takes no key. `locker_encrypt` takes the new key and converts a plain locker
     to encrypted, one-way only.
   - zjm never keeps a key: it lives only in a temporary file for the length of one call, and a
     lost key means a lost locker.
4. **Egress:**
   - `rank` sends the question, locker names, file paths and passages to OpenRouter (Jev).
   - `answer` sends the question, locker names, file paths and file text to OpenRouter (the
     answer model, `llm`).
   - `translate` sends only the question to OpenRouter (`translate_model`).
   - Each switch is off unless the config turns it on. Per-call `rank`/`translate` can only turn
     them off.
5. **Rules:**
   - `file_add` accepts only paths under `allow`.
   - Secret files (`.env*`, `*.pem`, `*.key`, `id_rsa*`, …) and gitignored files are never copied.
   - A file with the same name is replaced.
   - `file_put` accepts at most 1 MiB.
   - `file_remove`: if any requested name is missing, nothing is removed.
6. **Errors:**
   - HTTP, MCP and `--json` return an operation error as `{"error": "..."}`.
   - A malformed key gives `invalid key`.
   - A well-formed key that does not match gives `wrong key or damaged locker <name>`.

The guide names every operation in `OPS` (a test enforces this, so a new operation cannot be
forgotten).

### CLI human output

`zjm help` prints the guide, then these lines:
- `allow: <each path>` (one per path)
- `egress: rank=… answer=… translate=…`
- `languages: …`
- `lockers: <name> (encrypted|plain), …`

`--json` prints the dict.

### README

- "Agents: call `zjm_help` first", with one sentence on what it returns.
- Bump `fallback_version` to `0.11.0`.

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 83 tests**: the 81 earlier ones plus
these 2. `test_mcp.test_initialize_and_list` is updated to include `zjm_help`, and
`test_ops.test_surfaces_match_ops` covers the new operation on every surface.

- `tests/test_help.py`:
  1. `test_guide_and_instance`, with a plain and an encrypted locker and egress `translate` on:
     - `guide` is at most 3000 characters and names every `OPS` operation.
     - `instance` matches the config: `allow`, the three switches and `languages`.
     - `lockers` lists both lockers with the right `encrypted` flag.
     - An `allow` entry inside a `deny` entry is left out.
     - The values of the `deny` entries, the `home` path and the key string appear nowhere in the
       JSON.
     - No runner, Jev or `llm` call is made.
     - With a fresh `home` that does not exist, `help` returns `lockers: []` and `home` still does
       not exist afterwards.
  2. `test_help_cli_and_http`:
     - `zjm help` prints the guide and an `allow:` line.
     - `zjm help --json` equals the library result.
     - `POST /help` returns `200` and the same dict.

## Out of scope

- Per-operation help pages.
- Translating the guide.
- Listing files or file content.
