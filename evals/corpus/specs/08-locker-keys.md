# 08 — Every locker encrypted with its own key, supplied by the app

## Goal

At rest, each locker is one encrypted file: its files, its zg index and its manifest, sealed
together. The calling app sends the locker's key with each request.
- zjm decrypts the locker into memory only while that request reads or writes it.
- It re-encrypts after a write, then deletes the plaintext and the key.
- Nothing about a locker's contents is readable on disk without its key.

This spec builds on specs 05 to 07; where they disagree, this one wins.

## Behaviour

### Keys and storage

- A key is an [age](https://github.com/FiloSottile/age) X25519 identity string
  (`AGE-SECRET-KEY-1…`). The app generates it and keeps it. **zjm never stores a key**, and a
  lost key means a lost locker.
- The image adds the `age` and `age-keygen` binaries from Debian's `age` package.
- At rest a locker is exactly one file, `<home>/lockers/<name>.age`: an age-encrypted tar of the
  spec 06 locker directory (`corpus/` with `.zvec-grep/`, `zghome/`, `locker.json`). No other
  per-locker file exists on disk. `<home>/.lock` stays.
- A spec 06 locker directory already in the volume is not migrated. `locker_list` ignores it.

### A sealed session: `zjm_rag/sealed.py`

`open_locker(cfg, name, key, *, write, runner)` is a context manager. Every operation on a
locker's contents goes through it:

1. Take the spec 06 lock **exclusive** for the whole session, for reads too: the session path
   below is fixed per locker, so two sessions on one locker must never overlap.
2. Create `/tmp/zjm/<name>/` with mode `0700` (the container's `/tmp` is tmpfs).
   - The path is fixed per locker, so zg's stored root stays stable.
   - Anything left there from a crashed run is removed first.
3. Write the key to `/tmp/zjm/<name>.key` with mode `0600`.
   - Run `age -d -i <that file> <home>/lockers/<name>.age` through the injectable `runner` and
     extract the tar output into the directory with `tarfile`, refusing members that are absolute
     or contain `..`.
   - A non-zero age exit raises `ZjmError("wrong key or damaged locker <name>")`. age's stderr is
     never included.
4. Yield the directory. The spec 06 code runs on it unchanged.
5. On a successful exit with `write`:
   - get the recipient with `age-keygen -y <key file>`
   - tar the directory
   - encrypt it with `age -r <recipient> -o <home>/lockers/<name>.age.tmp`
   - `os.replace` it over `<name>.age`
6. Always, error or not: delete the key file and the directory, then release the lock.

The key only ever travels in files under `/tmp/zjm` and in request bodies. It never appears in
argv, the environment, logs, error messages, results or anything stored in `/data`. The runner
gets the key file's path, never the key.

### Operations

The operation names stay as in spec 06; their arguments change:
- `locker_create(name, key, multilingual, embedding)` writes the first `.age` file. It is an
  error if the key is not a valid age identity (`age-keygen -y` fails).
- `locker_drop(name, key)` needs the key and proves it by decrypting before deleting.
- `file_add`, `file_put`, `file_remove` and `file_list` each take `key`.
- `find` and `ask` take `keys`: an object mapping each name in `lockers` to its key. A missing
  key raises before anything is decrypted.
  - Each locker is opened in turn in `lockers` order and queried inside its session. Hits keep
    their snippets.
  - After the last session closes, `find` ranks them as in spec 06.
  - `ask` does the same, but keeps each locker's session open until its accepted files' text has
    been read into the prompt, and only then closes it. The LLM runs after every session has
    closed.
- `locker_list` takes no keys and returns `{"lockers": [{"name", "bytes"}]}`, where `bytes` is the
  size of the `.age` file.
- `doctor` is unchanged, plus a check that `age` is present.
- **CLI:** `--key-file PATH` is required wherever a key is needed.
  - The file holds one key, or for `find`/`ask` a JSON object `{locker: key}`.
  - `-` means stdin, which cannot be combined with `file-put`'s stdin text.
  - The CLI reads the file and passes the key to the library, never as argv to a subprocess.
- **HTTP and MCP:** `key` and `keys` are body and argument fields. They are validated by the
  `OPS` schema: a string, or an object of strings.

### Container

The launcher adds:
- `--memory-swap` equal to `--memory`, so no swap
- `--ulimit core=0`
- a `/tmp` tmpfs of `1g` instead of `256m`

## Settled details (review, override anything above)

1. **Tar extraction** accepts only regular files and directories. It rejects symlinks, hardlinks
   and device, fifo or other special members, as well as absolute and `..` names, before
   extracting anything.
2. **Binary transport:** age calls go through a bytes runner (`input: bytes | None`, stdout as
   bytes). zg calls keep the text runner. The test fake plays age in bytes.
3. **`ask`:** each session buffers its candidates' text (up to spec 01's 20 000 characters)
   alongside their snippets. Ranking and prompt building happen after every session has closed,
   so no session stays open across ranking.
4. **Single lock owner:** the session holds the only lock. The spec 06 file and search code is
   refactored into helpers that take the session directory and do not lock or resolve paths
   themselves.
5. **`find` hits:** each session records `mtime` and the manifest `source` for its candidates
   before closing.
6. **`locker_create`** is the only operation that opens without decrypting. It builds the empty
   locker in the session directory and seals it. Every other operation on a missing `.age` raises
   `no locker <name>`.
7. **Key validation:** the key must be exactly one line matching `^AGE-SECRET-KEY-1[0-9A-Z]+$`,
   and `age-keygen -y` must print exactly one recipient. Anything else raises
   `ZjmError("invalid key")`.
8. **Sealing failure:** `<name>.age` is replaced only after `age -o <name>.age.tmp` succeeds.
   `.age.tmp` is always removed during cleanup. On any failure the old `.age` stays, so a failed
   write leaves the locker exactly as it was, and the spec 06 `indexed` flag never persists
   `false`.
9. **Existing tests:** `test_locker.test_same_name_replaces` changes its failure assertion to
   "the locker is unchanged and `find` still works". Storage and runner expectations in the other
   tests move to the fakes. The total stays 62.

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 62 tests**: the 56 earlier ones, updated
to pass keys, plus the 6 below.

Tests use a fake `age`/`age-keygen` in the runner that plays both tools:
- `-o` writes a file whose content is a marker, the key's recipient and the plaintext.
- `-d` checks the marker and the key, then returns the plaintext.
- A wrong key exits `1`.

No real age runs in tests.

- `tests/test_sealed.py`:
  1. `test_at_rest_only_one_encrypted_file`: after `locker_create`, `file_add` and `find`,
     `<home>/lockers` holds only `<name>.age`, and `/tmp/zjm/<name>*` does not exist. The
     test points the tmp root at a temp dir through a module constant.
  2. `test_wrong_key_refused_without_leak`: a wrong key raises "wrong key or damaged locker",
     and the message holds neither key.
  3. `test_key_never_in_argv_or_env`: across create, add, find and ask, no runner call's argv or
     env contains the key string.
  4. `test_plaintext_removed_on_error`: when zg fails inside a write session, the directory and
     key file are gone, and the `.age` file is unchanged.
  5. `test_tar_traversal_refused`: a decrypted tar with a `../x` member raises and writes nothing
     outside the session directory.
  6. `test_find_needs_every_key`: `find` with a locker missing from `keys` raises before any
     runner call.

## Out of scope

- Key generation, rotation or recovery.
- Encrypting locker names or sizes.
- Migrating spec 06 lockers.
- Performance work for large lockers: the whole locker is decrypted per request by design.

## Amendment: encryption is optional per locker (owner, 2026-09-26)

- `key` on `locker_create` is **optional**:
  - With a key, the locker is encrypted as described above.
  - Without one, it is a plain spec 06 locker directory `<home>/lockers/<name>/`, and it stays
    plain until it is encrypted with `locker_encrypt` (below). Encrypting is one-way: there is no
    operation that decrypts a locker back to plain.
- For every other operation, `key` (or the locker's entry in `keys`) is required exactly when the
  locker is encrypted:
  - A missing key for an encrypted locker raises `ZjmError("locker <name> needs its key")`.
  - A key given for a plain locker raises `ZjmError("locker <name> is not encrypted")`.
  - Both errors are raised before any runner call.
- `locker_create` refuses a name that already exists in either form.
- `locker_list` adds `"encrypted": bool` to each entry. It keeps spec 06's `files` count for plain
  lockers and omits it for encrypted ones.
- `find` and `ask` can mix both kinds of locker in one call.
- **`locker_encrypt(name, key)`** is a new operation (CLI `locker-encrypt NAME --key-file F`,
  HTTP `/locker_encrypt`, MCP `zjm_locker_encrypt`). It runs under the exclusive lock and:
  1. validates the key (settled detail 7)
  2. seals the plain locker directory into `<name>.age.tmp` exactly as a write session does
  3. checks the result by decrypting it with the key
  4. `os.replace`s it to `<name>.age`
  5. deletes the plain directory

  If any step fails, the plain locker is left untouched and `.age.tmp` is removed. An encrypted
  or missing locker raises. `OPS` grows by one, so `test_surfaces_match_ops` covers it.
- **Tests:** exactly **64**. `tests/test_sealed.py::test_encrypt_plain_locker` checks three
  things: after `locker_encrypt` only `<name>.age` remains and `find` with the key works; a
  second `locker_encrypt` raises; a sealing failure leaves the plain locker intact. Plus The one extra test is `tests/test_sealed.py::test_plain_and_encrypted_mix`:
  - a plain and an encrypted locker are both searched in one `find`
  - each of the two wrong-key errors above is raised
  - `locker_list` shows the `encrypted` flag

## Amendment: encrypted by default (owner, 2026-09-26)

- `locker_create` takes a new boolean `plain` (default `false`; CLI `--plain`). Without a key it
  raises `ZjmError("locker <name> needs a key; pass plain=true for an unencrypted locker")`,
  unless `plain` is true. A key together with `plain=true` raises
  `ZjmError("a plain locker takes no key")`. Both raise before anything is created.
- Tests stay at **64**. `test_plain_and_encrypted_mix` asserts both refusals, and every test
  that creates a plain locker passes `plain=True`.
