# 21 — many texts and removals in one call (a batched put)

Issue #42 (part of #39). fits-api is switching its policy search to zjm (fits-api's spec 32, slice 1a). It keeps one
locker per organisation and one file per policy chunk, with the text coming from its database. Today each
`file_put` writes one text, and each call decrypts the locker, indexes it and seals it again: 5.7 to 6.4 s per put,
and 300 puts took 1,779 s. `file_add` adds many files in one session (2,878 files in 2.4 s on 2026-11-24), but only
from paths under the config's `allow` list, and fits-api keeps that text off disk. fits-api also removes the files of
superseded chunks, and two of its syncs can overlap, so a removal must not fail on a name the other one already removed;
today's `file_remove` refuses a missing name (`zjm_rag/files.py`).

## Behaviour

- **`files.file_put_many(locker, files, key=None, *, remove=(), config=None, runner=engine.run, jev=None)`**, exported
  from the package beside `file_put`:
  - `files` is a list of `{"name": str, "text": str}`; `remove` is a list of names.
  - It all happens in one `sealed.open_locker(..., write=True)` session. First it removes every file whose locker
    path equals a `remove` entry or starts with it followed by `/` (`file_remove`'s rule). Then it writes every
    file. Then it makes one `lockers.run_index` call, and an encrypted locker is sealed once.
  - A `remove` entry that matches no file is skipped, not refused.
  - Removals come first, so a name that is both removed and put ends up put, with the new text.
  - It returns `{"added": [...], "replaced": [...], "removed": [...]}`:
    - `added` and `replaced` are in `files` order. A name is `replaced` when the locker still holds it after the
      removals, and `added` otherwise.
    - `removed` lists the `remove` entries that matched at least one file, in the order given.
  - Emptied folders are removed as `file_remove` removes them.
- **Refusals.** Each of these is a `ZjmError`. The ones that need no locker (all but the clash with the locker's
  files) are checked before the locker is opened, in the order listed, as `file_put` checks today; the clash with the
  locker's files is checked after it is opened and before anything in it changes:
  - `files` and `remove` are both empty: `nothing to put or remove`.
  - a `files` entry that is not an object holding exactly a string `name` and a string `text`.
  - a name given twice in `files`.
  - a text over `MAX_PUT_BYTES`, with `file_put`'s message (`text for 'x' exceeds 1 MiB`).
  - a bad name, refused as `file_put` refuses it (`_check_put_name`, same message).
  - a name that is a folder in the locker, or under a path that is a file, once the removals are applied. The message
    is `file_put`'s clash message.
  - two names in `files` where one is a folder of the other (`a` and `a/b.md`): `'a/b.md' clashes with another
    file in this call`.

  A refused call leaves the locker exactly as it was, plain or encrypted: no file, manifest entry or seal changes.
- **`file_put(locker, name, text, ...)`** calls `file_put_many(locker, [{"name": name, "text": text}], ...)` and
  returns its `added` and `replaced` only, as today. Its arguments, errors and messages do not change. So there is
  one implementation, and every caller of `file_put` keeps working.
- **`file_remove`** does not change: it still refuses a missing name.
- **The op.** `OPS["file_put_many"]` makes it an HTTP route (`POST /file_put_many`) and an MCP tool
  (`zjm_file_put_many`), as the other ops are made. Its schema is:
  - `locker` (required) and `key`, both strings;
  - `files`, an array of objects, each with exactly the string properties `name` and `text`, both required;
  - `remove`, an array of strings.

  Its description is "Write many texts as files in a locker, and remove files, with one index run."
  - `ops.check` learns object schemas that list `properties` and `required`: unknown keys, a missing required key
    and a wrong type are refused, as it refuses them at the top level. Over HTTP that is a 400, as today.
  - The HTTP body stays capped at 1 MiB (`http.MAX_BODY`), so a caller with more splits its files over several
    calls.
- **The CLI.** `zjm file-put-many LOCKER [--key-file PATH] [--remove NAME]...` reads a JSON array of
  `{"name", "text"}` from stdin (empty stdin is an empty array) and calls the op; `--remove` is repeatable. A stdin
  that is not a JSON array is refused before any call, with exit code and message as the CLI's other bad input. Its
  human output lists the added, replaced and removed names, as `file-put`'s lists added and replaced.
- **Words:**
  - `guide.py`: the workflow step that names `file_put` also names `file_put_many`, for many texts or removals in
    one session.
  - `README.md`: the library line beside `file_put`, the CLI line beside `file-put`, and the op list.
  - `files.py`'s module docstring names it.

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 185 tests**: the 172 earlier ones unchanged but one, and
13 new ones in `tests/test_file_put_many.py` (5 of them went to `tests/test_file_put_many_surfaces.py`). The one is `tests/test_mcp.py`'s
`test_initialize_and_list`, whose exact set of tool names gains `zjm_file_put_many`, and nothing else in it
changes. `tests/test_ops.py`'s `test_surfaces_match_ops` passes unedited, because the CLI gains the command. Should
any other earlier test fail, the builder reports it and does not edit it.

1. **One session.** Three files put into an encrypted locker, through the fake runner, make exactly one index run and
   one seal. `file_list` then holds all three with their sizes and sha256, and the result lists them as `added`, in
   order. The same on a plain locker makes one index run.
2. **Put and remove together.** A locker holding `p1/a.md`, `p1/b.md` and `p2/c.md` gets `files` with
   `p1/a.md` (new text) and `p3/d.md`, and `remove` with `p1/b.md`, `p2` and `gone.md`:
   - the result is `added` `["p3/d.md"]`, `replaced` `["p1/a.md"]` and `removed` `["p1/b.md", "p2"]`;
   - the locker then holds exactly `p1/a.md`, with the new text, and `p3/d.md`;
   - the emptied `p2` folder is gone;
   - there was one index run.
3. **Removed, then put.** `remove` `["x.md"]` and `files` `x.md` on a locker holding `x.md`: `x.md` is there with
   the new text, `removed` is `["x.md"]` and `added` is `["x.md"]`.
4. **Removals only.** `files` empty and `remove` `["gone.md"]` on a locker without it succeeds, with `removed` empty and
   the locker unchanged.
5. **Refusals change nothing.** On an encrypted locker, and again on a plain one, each refusal under "Refusals" raises
   with its message. Afterwards the `.age` file's bytes (encrypted) or the corpus files and `locker.json` (plain)
   are byte-for-byte what they were, and no index run was made. One case pairs a valid removal with a bad put, to show
   that the removal did not happen either.
6. **`file_put` delegates.** A `file_put` makes exactly one index run and returns only `added` and `replaced`.
7. **The op.** `ops.check("file_put_many", body)` refuses each of these: a `files` entry without `text`, with an
   extra key, or with a non-string `name`; a `remove` that is not an array of strings; an unknown top-level key. It
   accepts a body with only `locker` and `remove`. Over the HTTP test server, `POST /file_put_many` returns 200 and
   the result, and a refused call returns 422 with its message. MCP's `tools/list` includes `zjm_file_put_many`
   with this schema.
8. **The CLI.** `file-put-many` with a JSON array on stdin and `--remove` twice sends the op exactly those `files`
   and `remove`; a stdin that is not a JSON array is refused without a call.
9. **Refusal order.** A bad name or an oversize text sent to a locker that does not exist is refused with the name or
   size message, not `no locker`, through `file_put` and through `file_put_many`.

## Not the gate

The suite uses the fake runner. The timing in fits-api's spec 32 is measured by the runner after merge, on fits-api's
eval locker: 2,878 files put in calls of up to 1 MiB, against `file_add`'s 2.4 s.

## Decisions

- runner (2026-11-25): the exact count, 185, written in after the build (CodeRabbit on #64); the spec had stated only
  the 172 earlier tests.
- runner (2026-11-24): a new op instead of a new shape for `file_put`. The CLI's `file-put`, fits-api's eval and
  any MCP client keep the one-file call, the 172 tests stay unchanged, and `file_put` delegates, so there is one
  implementation.
- runner (2026-11-24): removals before puts, and a missing removal skipped. fits-api sends a policy's missing chunks
  and its extra files in one call, and its overlapping syncs may remove the same name (spec 32's `put_chunks`).
- runner (2026-11-24, after the grill): the CLI gains `file-put-many`, because `test_surfaces_match_ops` holds every
  op to a CLI command; stdin carries the texts, as `file-put`'s does, so no text lands in argv.
- runner (2026-11-24, after the grill): `test_mcp`'s exact tool list is the one earlier test edited: it lists the
  surface on purpose, and a new op must change it.
- runner (2026-11-24, after the grill): the checks that need no locker run before it is opened, so `file_put`'s errors
  and their order do not change.
- runner (2026-11-24): no size limit on the whole batch in the library; HTTP's 1 MiB body limit caps it there, and the
  caller splits.

## Out of scope

- Any change to `file_add`, `file_remove` or the engine.
- `find` taking the caller's translations (fits-api's slice 1b, its own spec).
