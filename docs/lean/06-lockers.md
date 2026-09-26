# 06 — Lockers: named indexes with files added and removed

## Goal

zjm works like OpenAI's vector stores:
- A **locker** is a named index. Files and text go into it, and they come out again.
- `find` and `ask` search the lockers the caller names.
- zjm has no idea of users, chats, organizations or tenants. The app decides who may use which
  locker and which lockers a question searches.

Every operation is available the same way from the library, the CLI, HTTP and MCP.

This spec builds on spec 05. Where they disagree with this one, specs 01–05 lose. The `store`
argument, `--store`, `zjm.json`, `index()` and `zjm index` are removed.

## Behaviour

### Locker layout

- `<home>/lockers/<name>/` holds three things:
  - `corpus/`: the copied files, and zg's `.zvec-grep/` index.
  - `zghome/`: set as `ZVEC_GREP_HOME`.
  - `locker.json`: the manifest.
- A locker name matches `^[a-z0-9][a-z0-9._-]{0,63}$`. Any other name raises `ZjmError` before
  the filesystem is touched. That rules out `/`, `..`, upper case and empty names.
- `<home>` and `<home>/lockers` are created with mode `0700`. The spec 01 rules apply to `home` and
  to every locker directory:
  - refuse to write through a symlink
  - refuse a directory owned by another user
- `locker.json` holds:

  ```json
  {"name": "...", "embedding": "...", "indexed": bool,
   "files": {"<name>": {"source": "<abs path>" | null, "size": int, "sha256": "...", "added": <unix time>}}}
  ```

  - It is written to a temp file in the same directory, then `os.replace`d.
  - `indexed` is `true` after `locker_create`. `file_add`, `file_put` and `file_remove` write it
    as `false` before touching `corpus/`, and as `true` only after zg's index exits `0`.
  - `files` has one entry per file ingested through `file_add` or `file_put`, keyed by its
    relative POSIX path in `corpus/`. zg's `corpus/.zvec-grep/` is never listed.
- One lock file, `<home>/.lock`, guards all lockers with `fcntl.flock` for the whole operation.
  `locker_create`, `locker_drop`, `file_add`, `file_put` and `file_remove` take it exclusive.
  `locker_list`, `file_list`, `find` and `ask` take it shared.

### Operations: `zjm_rag/ops.py`

- `OPS` is a single table. Each entry holds four things:
  - the name
  - the core function
  - a JSON Schema for its arguments (`additionalProperties: false`)
  - a one-sentence description
- HTTP and MCP are generated from `OPS`: routes, tools, body checks and `inputSchema` all come
  from it, replacing spec 03's `KEYS`/`CHECKS` and spec 04's `TOOLS`. The CLI dispatches through
  `OPS` but keeps hand-written argparse adapters for positional arguments and stdin.
- Every function also takes `config=None` (spec 05), plus `runner=` and `jev=` where it calls
  out.

| op | arguments | returns |
|---|---|---|
| `locker_create` | `name`, `multilingual=false`, `embedding=null` | `{"name", "embedding"}` |
| `locker_list` | — | `{"lockers": [{"name", "embedding", "files", "bytes"}]}`, sorted by name |
| `locker_drop` | `name` | `{"name", "files"}` (count removed) |
| `file_add` | `locker`, `paths` (list) | `{"added": [names], "replaced": [names], "excluded": int}` |
| `file_put` | `locker`, `name`, `text` | `{"added": [name], "replaced": [name]}` (one list is empty) |
| `file_remove` | `locker`, `names` (list) | `{"removed": [names]}` |
| `file_list` | `locker` | `{"files": [{"name", "source", "size", "sha256", "added"}]}`, sorted by name |
| `find` | `query`, `lockers` (non-empty list), then spec 01/05 options | spec 01 shape; each hit adds `"locker"` |
| `ask` | `query`, `lockers`, then spec 01/05 options | spec 01 shape; `files` are `"<locker>/<name>"` strings |
| `doctor` | — | spec 05 shape without `checks.store`, plus `"lockers"`: the count |

A missing locker raises `ZjmError("no locker <name>")`, except in `locker_create`, which raises on
an existing one.

### Rules

- **Embedding is fixed per locker.**
  - `locker_create` picks it: `embedding`, else the multilingual model if `multilingual`, else
    config `embedding`.
  - `file_add` and `file_put` always index with the locker's embedding.
  - To change the model, drop and recreate the locker. There is no rebuild operation.
- **`file_add`** applies every spec 05 rule to each path: `allow`, `deny`, `home`, the floor,
  `exclude`, gitignore and symlinks. Every path is checked first; if any fails, it raises and nothing is copied.
  - A file is stored as `<basename>`. A directory is stored as `<basename>/…`.
  - For a single file, spec 05's gitignore check runs in the file's parent directory: `git -C
    <parent> check-ignore -z --stdin` with `<basename>` as `input`. If git prints it, the file is
    skipped and counted in `excluded`.
  - If that name already exists, the old file or whole subtree is removed first. The new one
    **replaces** it, so files that vanished from a re-added directory vanish from the locker.
  - Copies keep mtimes (`shutil.copy2`), so zg's incremental index skips unchanged content.
  - One `zg index . --embedding <locker model> --mode direct --hidden` runs after all paths are
    copied. It uses `cwd=<locker>/corpus` and `ZVEC_GREP_HOME=<locker>/zghome`.
  - A non-zero exit from zg raises `ZjmError`. Files already copied stay in the manifest, and
    `indexed` stays `false`.
- **`file_put`** writes `text` as UTF-8 to `corpus/<name>` and indexes the same way. The manifest
  entry gets `source: null`. `name` is refused with `ZjmError` when:
  - it is empty, absolute or contains `\`
  - it has a segment that is empty, `.` or `..`
  - any segment matches the exclude floor or config `exclude`
  - the text encodes to more than 1 MiB
- **`file_remove`** checks every name first. If any name is not an exact file key or directory
  prefix in the manifest, nothing is removed and it raises `ZjmError` listing the missing names.
  It then removes the files, updates the manifest and runs zg's index, which prunes deleted files
  incrementally.
- **`find` across lockers:**
  - Run spec 01's zg query once per locker, in the order given, and parse up to `limit` files
    from each. A locker whose manifest has no files gives zero hits, and zg is not run for it.
    `locker_create` never runs zg. A locker with `indexed: false` raises
    `ZjmError("locker <name> is not indexed; re-run a file operation")` before any zg call, so
    stale snippets never reach Jev. The next successful `file_add`, `file_put` or `file_remove`
    clears it.
  - Interleave the results: the first file of each locker in the given order, then the second
    of each, and so on. Drop a `(locker, name)` pair already seen and cut to `limit`. `zg_rank`
    is the position in this merged list.
  - If ranking is on (spec 05), send **one** Jev request over the merged list. The evidence
    `path` is `<locker>/<name>`.
  - Each hit is `{"locker", "path": <name>, "source_path": <manifest source or null>, "score",
    "zg_rank", "mtime", "snippets"}`.
  - Duplicates across lockers are kept. Deciding between them is the app's job.
- **`ask`** reads each accepted file from its own locker's corpus, and labels it in the prompt as
  `=== <locker>/<name> ===`. Locker names never contain `/`, so the label is unambiguous.
  Everything else follows spec 01 and spec 05.
- **Human CLI output** names files as `<locker>/<name>` everywhere.

### Surfaces

- **CLI:** one flat subcommand per op, named with `-` for `_`. For example:
  - `zjm locker-create NAME [--multilingual | --embedding M]`
  - `zjm file-add LOCKER PATH...`
  - `zjm file-put LOCKER NAME` (reads the text from stdin)
  - `zjm file-remove LOCKER NAME...`
  - `zjm find QUERY -l LOCKER [-l LOCKER]...` and the same for `ask`

  The spec 02 options, `--json`, `--config`, the exit codes and the human output all carry over.
  Human output for the new ops is one line per item.
- **HTTP:** `POST /<op>` with the arguments as the JSON body. `GET /health` stays as `doctor`.
  - Body checks come from the op's schema, with spec 03's error messages and codes.
  - The spec 05 Host/Origin/Content-Type guard applies first.
- **MCP:** one tool `zjm_<op>` per op, whose `inputSchema` is the op's schema. Spec 04's result
  and error shapes carry over.
- A `store`, `home` or `config` argument is rejected on HTTP and MCP. The server's config is
  used.

### README

- Rewrite the usage section around lockers, with the OpenAI vector-store comparison in one
  sentence.
- One example each for the library, the CLI, HTTP (`/file_add` then `/find`) and MCP.
- Say that the app, not zjm, decides who may use which locker.
- Bump the version to `0.6.0`.

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 49 tests**, all passing with an empty
`HOME` and no network:
- Spec 05 leaves 43 tests. Delete `tests/test_index.py` (5 tests); its checks move into the tests
  below.
- Tests that called `index` or used `store` switch to `locker_create` + `file_add`, or to a locker
  built by `tests/fakes.py`.
- `test_cli.test_index_json` becomes `test_file_add_json`.
- `test_ask.test_prompt_and_language` asserts the `=== <locker>/<name> ===` label. The doctor
  assertions in `test_cli` and `test_http` drop `checks.store`.
- That leaves 38, and the 11 below bring it to 49.

- `tests/test_locker.py`:
  1. `test_create_list_drop`: create two lockers, list them sorted with counts, drop one, list one.
     Creating an existing locker raises, and so does dropping a missing one.
  2. `test_bad_names_refused`: `""`, `A`, `a/b`, `..` and a 65-character name raise without
     creating anything under `home`.
  3. `test_file_add_manifest_and_zg`: add a directory and a single file.
     - The manifest holds each file's source, size and sha256.
     - zg runs exactly once, with the locker's embedding, `cwd` and `ZVEC_GREP_HOME`.
     - Spec 05 refusals still apply (a path outside `allow` raises and copies nothing).
     - The single file's git check runs in its parent directory with `<basename>` as `input`.
     - The manifest never lists anything under `.zvec-grep/`.
  4. `test_same_name_replaces`: re-adding a directory after deleting one of its files reports it
     under `replaced`, and the deleted file is gone from both the corpus and the manifest. When zg
     then fails on a re-add, the locker is left with `indexed: false`, and `find` on it raises.
  5. `test_file_put_rules`: a valid put is listed with `source: null`. `../x`, `/x`, `a//b`,
     `.env`, `x/id_rsa` and text over 1 MiB each raise.
  6. `test_file_remove_all_or_nothing`: removing one existing and one missing name removes
     nothing and names the missing one. Removing a directory prefix removes its files.
  7. `test_embedding_fixed_per_locker`: a `multilingual` locker indexes with the multilingual
     model even when config `embedding` differs. `locker_create(embedding="qwen/x")` raises.
  8. `test_foreign_or_symlinked_locker_refused`: a locker directory that is a symlink, or is owned
     by another user (patched `st_uid`), is refused before any write.
- `tests/test_find.py` (added to the existing file):
  9. `test_find_across_lockers`:
     - Two lockers give interleaved hits, each naming its locker.
     - There is one Jev call whose evidence paths are `<locker>/<name>`.
     - An unknown locker raises before zg runs.
     - An empty locker in the list adds no hits and no zg call.
     - A locker with `indexed: false` raises before any zg or Jev call.
- `tests/test_ops.py`:
  10. `test_surfaces_match_ops`: the CLI subcommands (with `-` mapped to `_`, and `serve`/`mcp`
      excluded), the HTTP `POST` routes and the MCP tool names without the `zjm_` prefix each
      equal the set of names in `OPS`.
  11. `test_file_ops_over_http_and_mcp`: `file_put` then `file_list` round-trip over HTTP and over
      MCP. A `home` key in the body is refused.

## Jev request shape (pinned)

Do not change the payload built by `_rank` or the client in `zjm_rag/jev.py`. Only the evidence
`path` values change, to `<locker>/<name>`. The live API rejects any other shape with HTTP 400.
Each `noul` question stays exactly:

```python
{"type": "noul",
 "instructions": "Does file fK (<path>) contain the information needed to answer the question? ...",
 "criteria": {"true": "The file holds the answer.", "false": "The file does not hold the answer."}}
```

Fakes used in this spec's tests must accept only that shape.

## Out of scope

- Users, chats, tenants and any authorization: those belong to the app.
- Encryption at rest.
- Running inside a container.
- A rebuild or re-embed operation.
- Deduplicating files across lockers.
- Migrating spec 01–05 stores.
