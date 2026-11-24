---
parent: "[[19-find-names]]"
---

# 191 — the engine's query can search only some files of an index

Issue #44, first of two pieces of spec 19 (`docs/lean/19-find-names.md`). One locker per organisation holds many documents, and a question about some of them must search only those. The engine returns at most `engine.HITS` (40) hits per locker, so other documents can take every candidate and the chosen ones get none. Filtering after the engine does not help, because the cut has already happened. The filter must narrow the chunks the engine ranks, as `--type` does (`engine/src/search.rs`, `search()`). This piece adds that filter to the Rust engine only. The Python package does not send `names` yet (piece 192), so every caller of today gets the same results.

## Behaviour

- The engine's `query` reads an optional `names` key from the stdin JSON, beside the question and the translations (`{"question", "translations", "names"}`, `engine/src/request.rs`). Names never come on argv: file names are locker content, and argv is readable in `/proc`. The query's command-line options are unchanged.
- `names` absent or `null` means every file, as today.
- A file is searched when its path in the index **equals** one of `names` **or starts with it followed by `/`**. `"a"` picks `a` and `a/x.md`, not `ab/y.md`. These are plain prefixes, not globs.
- The engine applies that rule to the entries exactly as given. It drops no trailing `/` and checks no components: validating entries is Python's job (piece 192).
- The engine refuses, with a non-zero exit and the stdin error style of `request.rs`:
  - a `names` that is not an array of strings.
  - an empty array. The engine never reads an empty selection as "every file".
- An entry that matches no file is not an error: it yields no hits.
- `names` and `--type` combine with AND: a file must match a name (when `names` is given) and a type (when `--type` is given).
- The name filter narrows `index.chunks` in `search()` together with the type filters, before ranking. Hit ranks, `limit` and the query/translation split are unchanged, and the translation hits are filtered the same way as the question's.
- `CLAUDE.md`'s suite line gives `profile-python.md`'s suite command, both suites, not only unittest.

## Acceptance tests

Engine (`engine/tests/`), four new tests:

1. A corpus of `a/x.md`, `ab/y.md` and `b/z.md`, all matching the question:
   - `"names": ["a"]` returns only `a/x.md`.
   - `["b/z.md"]` returns only `b/z.md`.
   - `["nope"]` returns none.
   - no `names` returns all three.
2. `"names": ["a", "b"]` with `--type md` over `a/x.md`, `a/x.txt` and `b/z.md` returns `a/x.md` and `b/z.md`.
3. `"names": "a"`, `[1]` and `[]` are each refused with a non-zero exit and the stdin error.
4. With `names` given, the translation hits are filtered the same way as the question's.

The profile's suite (`profile-python.md`) runs both suites and both stay green. The engine's `cargo test` total, the sum of the counts `cargo test -q` prints per test binary, is that sum when this piece's build starts, plus 4. The unittest count is the count when this piece's build starts, plus 0.

## Out of scope

- Everything in the Python package: `find`, `ask`, `engine.query_input`, the HTTP and MCP schemas, the CLI and the README (piece 192).
- Dropping a trailing `/` and refusing bad entries (empty, leading `/`, `.` or `..` components): Python's job, piece 192.
- Globs, regular expressions, and excluding files.
- Any change to translation, ranking, `limit`, `min_score` or the engine's index format.
- `.githooks/pre-commit` and `.github/pull_request_template.md`, which run or name only the Python suite: the lean gate and CI's `engine` job run the engine's tests.

## Decisions

- runner (2026-11-20): plain file-or-folder prefixes, not the globs #44 first asked for. The only caller waiting on this (fits-api's #648 switch, one locker per organisation) selects whole documents or folders of documents, and prefixes need no glob crate in the engine.
- runner (2026-11-20): the key is `names`, as in `file_remove`, which already means locker files or folders with the same matching rule. `paths` already means host source paths in `file_add`.
- runner (2026-11-20): names travel on stdin, not argv, for the same reason the question does (`request.rs`).
- runner (2026-11-20): an empty list is refused in the engine (and in Python, piece 192) rather than read as "every file", so a caller whose selection came out empty never searches the whole locker.
- person (2026-11-24): "prefixes are enough, go ahead" (asked whether plain file-or-folder prefixes are enough, with no globs).
