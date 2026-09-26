# 11 — A help operation for agents and apps

## Goal

One read-only operation tells a caller how to use zjm and what this instance allows. Today an
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
                "limits": {"file_put_bytes": 1048576, "find_limit": 8, "ask_chars": <ASK_CHARS>}}}
  ```

  - `allow` is the resolved config list.
  - `lockers` comes from `locker_list`: names and the `encrypted` flag only.
  - `ask_chars` is `evidence.ASK_CHARS`.
  - **Never included:** `deny` (it would reveal paths the owner forbids), `home`, keys, and any
    file content.

### The guide

`GUIDE` is a module constant (`zjm_rag/guide.py`) of at most 3000 characters of plain Markdown. It
covers, in this order:
1. **What zjm is.** Named lockers of files. `find` returns the files and passages (with line
   ranges) that answer a question, and `ask` answers with citations. The calling app decides who
   may use which locker.
2. **Workflow:**
   - `locker_create` (with `key`, or `plain=true`)
   - `file_add` (paths under `instance.allow`) or `file_put` (text)
   - `find` or `ask`
   - `file_list`, `file_remove`, `locker_list`, `locker_drop` and `locker_encrypt` to manage
     lockers
   - `doctor` to check the instance
3. **Keys:**
   - The key is an age identity, `AGE-SECRET-KEY-1…`, one per locker, sent with every call on
     that locker: `key`, or `keys: {locker: key}` for `find`/`ask`.
   - zjm never stores keys, and a lost key means a lost locker.
   - `locker_encrypt` converts a plain locker to encrypted, one-way only.
4. **Egress:**
   - `rank` sends the question, file paths and passages to OpenRouter (Jev).
   - `answer` sends the question and file text to the answer model.
   - `translate` sends only the question.
   - Each switch is off unless the config turns it on. Per-call `rank`/`translate` can only turn
     them off.
5. **Rules:**
   - `file_add` accepts only paths under `allow`.
   - Secret files (`.env*`, `*.pem`, `*.key`, `id_rsa*`, …) and gitignored files are never copied.
   - A file with the same name is replaced.
   - `file_put` accepts at most 1 MiB.
   - `file_remove` is all-or-nothing.
6. **Errors:** they come back as `{"error": "..."}`. A wrong key gives
   `wrong key or damaged locker <name>`.

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
     - `deny`, `home` and the key string appear nowhere in the JSON.
     - No runner, Jev or `llm` call is made.
  2. `test_help_cli_and_http`:
     - `zjm help` prints the guide and an `allow:` line.
     - `zjm help --json` equals the library result.
     - `POST /help` returns `200` and the same dict.

## Out of scope

- Per-operation help pages.
- Translating the guide.
- Listing files or file content.
