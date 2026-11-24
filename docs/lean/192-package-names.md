---
parent: "[[19-find-names]]"
---

# 192 — find and ask can search only some files of a locker

Issue #44, second of two pieces of spec 19 (`docs/lean/19-find-names.md`). Piece 191 is built first: the engine's `query` already reads `names` from its stdin JSON, searches only the files whose path equals an entry or starts with it followed by `/`, and refuses a non-array, a non-string entry and an empty array. This piece lets the Python package's callers send those names: the library, the HTTP and MCP schemas, the CLI and the README. Today the only narrowing is `file_types` (`--type`), which picks file formats.

## Behaviour

- `find(...)` and `ask(...)` (`zjm_rag/search.py`) take `names=None`: locker files or folders, the key `file_remove` already uses. `None` searches every file, as today.
- A file is searched when its locker path **equals** one of `names` **or starts with it followed by `/`** (`file_remove`'s rule, `zjm_rag/files.py`; the engine applies it). `"a"` picks `a` and `a/x.md`, not `ab/y.md`. One trailing `/` on an entry is dropped first, in Python, which `file_remove` does not do. These are plain prefixes, not globs.
- `names` and `file_types` combine with AND: a file must match a name (when `names` is given) and a type (when `file_types` is given).
- Each of these is refused with a `ZjmError` in `find` and `ask` right after `_check_cap`, before the config is read. So an over-cap `limit` or `top_k` is refused first, and a bad `names` before `egress.answer`, the no-lockers check, the translation call and any locker is opened:
  - an empty list. An empty selection must never search the whole locker.
  - an entry that is not a string.
  - an entry that, after the trailing `/` is dropped, is empty, starts with `/`, or has an empty, `.` or `..` component (`""`, `"/a"`, `"."`, `"./a"`, `"a//b"`, `"a/../b"`).
- An entry that matches no file is not an error: it yields no hits.
- The names go to the engine in the stdin JSON, beside the question and the translations (`{"question", "translations", "names"}`), never on argv: `engine.query_input` gains the `names` key, only when names are given, and `engine.query_argv` is unchanged. File names are locker content, and argv is readable in `/proc`.
- Exposed where `file_types` is in the package:
  - the HTTP and MCP `find` and `ask` schemas (`ops._FIND_PROPS`), as `names`, an array of strings.
  - the CLI `find` and `ask`, as `--name N`, repeatable.
  - the README's `find` and `ask` lines.

## Acceptance tests

Python (`tests/`, through the fake runner), six new tests:

1. `find(names=["a", "b/c.md/"])` puts `"names": ["a", "b/c.md"]` in the engine's stdin JSON, and `find()` puts no `names` key. The argv carries no name in either case.
2. `ask(names=[...])` passes them the same way.
3. `names=[]`, `[""]`, `["/a"]`, `["."]`, `["./a"]`, `["a//b"]`, `["a/../b"]` and `[3]` each raise `ZjmError`, through `find` and through `ask`. Neither the runner nor the translation `llm` is called.
4. HTTP `find` and `ask` with `names` reach `search.find` and `search.ask` with them. A `names` that is not an array of strings is refused by the schema.
5. The MCP `find` and `ask` tools list `names` in their input schema.
6. `zjm find ... --name a --name b` and `zjm ask ... --name a --name b` each send `["a", "b"]`.

The profile's suite (`profile-python.md`) runs both suites and both stay green. The unittest count is the count when this piece's build starts (with piece 191 present), plus 6. The engine's `cargo test` total, the sum of the counts `cargo test -q` prints per test binary, is that sum when this piece's build starts, plus 0.

## Out of scope

- The engine (`engine/`): piece 191 built its side; nothing there changes here.
- Globs, regular expressions, and excluding files.
- The `zjm-rag` skill (`skills/zjm-rag/SKILL.md`, `scripts/zjm-project`): it indexes a project's own documents and keeps its own option list. It gains no `--name`.
- `file_list`, `file_remove` and the other file operations: they are unchanged.
- Any change to translation, ranking, `limit`, `min_score` or the engine's index format.
- `.githooks/pre-commit` and `.github/pull_request_template.md`, which run or name only the Python suite: the lean gate and CI's `engine` job run the engine's tests.

## Decisions

- runner (2026-11-20): plain file-or-folder prefixes, not the globs #44 first asked for. The only caller waiting on this (fits-api's #648 switch, one locker per organisation) selects whole documents or folders of documents, and prefixes need no glob crate in the engine.
- runner (2026-11-20): the key is `names`, as in `file_remove`, which already means locker files or folders with the same matching rule. `paths` already means host source paths in `file_add`.
- runner (2026-11-20): names travel on stdin, not argv, for the same reason the question does (`request.rs`).
- runner (2026-11-20): an empty list is refused in Python (and in the engine, piece 191) rather than read as "every file", so a caller whose selection came out empty never searches the whole locker.
- runner (2026-11-24): inside the package the builder may give the new parameter another name where it meets `gather(cfg, names, ...)`, whose `names` are locker names; the public key stays `names`.
- runner (2026-11-24): the names check sits right after `_check_cap`, so both pure input checks run before the config and every egress or locker check.
- person (2026-11-24): "prefixes are enough, go ahead" (asked whether plain file-or-folder prefixes are enough, with no globs).
