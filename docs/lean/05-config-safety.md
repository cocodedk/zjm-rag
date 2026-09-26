# 05 — Config file and safety floor

## Goal

zjm never reads, keeps or sends anything its owner has not allowed. One config file says where zjm
may read from, where it must never look, what it never copies, where it keeps its data, and
whether anything may leave the machine. Without that permission, zjm refuses.

This spec changes behaviour that specs 01–04 settled. Where they disagree, this spec wins.

## Behaviour

### The config file: `zjm_rag/config.py`

- `load(path=None, *, cwd=None, environ=None) -> dict` returns the resolved config. `cwd` defaults
  to `os.getcwd()` and `environ` to `os.environ`, so tests never touch the real home.
- The lookup order is below. The first file that exists wins, and files are never merged:
  1. `path`: the library's `config=` argument or the CLI's `--config`. If this file is missing,
     raise `ZjmError`.
  2. `environ["ZJM_CONFIG"]`. If it names a missing file, raise `ZjmError`.
  3. `<cwd>/.zjm/config.json`. Only `cwd` itself is checked. Parent directories are **never**
     searched.
  4. `$XDG_CONFIG_HOME/zjm/config.json`, else `$HOME/.config/zjm/config.json`.
  5. None of the above: the built-in defaults.
- The file is one JSON object. These are the only keys, and every key is optional:

  | key | type | default |
  |---|---|---|
  | `home` | string | `$XDG_DATA_HOME/zjm`, else `$HOME/.local/share/zjm` |
  | `allow` | list of strings | `[]`, so nothing may be indexed |
  | `deny` | list of strings | `[]` |
  | `exclude` | list of strings (globs) | `[]` |
  | `egress` | `{"rank": bool, "answer": bool}` | `{"rank": false, "answer": false}` |
  | `embedding` | string | `local/potion-code-16m-v2` |
  | `llm` | non-empty list of strings (argv) | `DEFAULT_LLM` (below) |

- A partial `egress` object is allowed: each omitted switch is `false`.
- Paths in `home`, `allow` and `deny` expand a leading `~` from `environ["HOME"]`. A relative
  path is relative to the config file's directory. After expansion every path is made absolute
  with `os.path.abspath` (lexical only; nothing is resolved here).
- Any of these raises `ZjmError` naming the file:
  - invalid JSON
  - a value that is not an object
  - an unknown key, or an unknown key inside `egress`
  - a wrong type
- The returned dict holds every key above, fully resolved, plus `"path"`: the file used, or
  `None` for the built-in defaults.

### Every entry point reads the config

- `index`, `find`, `ask` and `doctor` take a keyword argument `config=None`. It can be a dict from
  `load()` or a path, and `None` means `load()`.
- `DEFAULT_STORE` is removed. `store=None` means `<home>/store`.
- The CLI gains `--config PATH` on every subcommand, `serve` and `mcp` included. `--store` stays
  and defaults to `None`. `zjm serve` and `zjm mcp` load the config once at start.
- The `embedding` key replaces the hard-coded code model as the default. Any embedding model,
  from config or an argument, must start with `local/`; anything else raises `ZjmError`, because a
  remote embedding would send file contents out whatever `egress` says. `multilingual=True` still
  picks `local/potion-multilingual-128m`.

### Where zjm may read: `allow` and `deny`

`index` checks every source against these rules **before it reads anything from it**:

1. Take `p = os.path.abspath(source)`. If `p` is inside a `deny` entry or inside `home` (or equal
   to one), raise `ZjmError("<source> is denied by <config path>")`. This lexical check happens
   first, so a denied path is never `stat`ed, listed or resolved.
2. Resolve `r = os.path.realpath(p)`. Check `r` again against `deny` (as written) and against both
   `home` and `os.path.realpath(home)`. Then require `r` to be inside, or equal to, the `realpath`
   of some `allow` entry. Otherwise raise
   `ZjmError("<source> is outside the allowed paths in <config path>; add it to \"allow\"")`.
   With the built-in defaults, `allow` is empty, so every index is refused with this message.
3. "Inside" compares whole path components (`/a/bc` is not inside `/a/b`).
4. `deny` entries are **never resolved**, because resolving would touch the denied path. They
   are compared as written, so they must be written as real paths (no symlinked parents). The
   README says so.

While copying, every entry (directory or file) is checked against `deny` and `home` by its
absolute path **before** it is opened or listed. A denied directory is skipped with everything
under it, unlisted.

### What is never copied

- **Symlinks** inside a source are never copied, whether they point to files or to directories.
- **Built-in exclude floor.** Config can add to it (`exclude`) but can never remove from it.
  Matching is `fnmatch` on the lower-cased entry name.
  - Directories: `.git`, `node_modules`, `.venv`, `__pycache__`, `.zvec-grep`, `.zjm`, `.ssh`,
    `.gnupg`, `.aws`, `.kube`, `.docker`.
  - Files: `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.kdbx`, `id_rsa*`, `id_dsa*`,
    `id_ecdsa*`, `id_ed25519*`, `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `credentials*`.
  - In config `exclude`, a glob ending in `/` matches directories only; any other glob matches
    files only.
- **Gitignored files.** zjm first walks the source itself, pruned by `deny`, `home`, the floor,
  `exclude` and the symlink rule, so git never scans anything zjm may not look at. It then passes
  the candidate paths (relative, NUL-separated) as `input` to
  `git -C <resolved source> check-ignore -z --stdin` through the injectable `runner`, with `cwd` set
  to the source.
  - Exit `0` or `1`: the paths git prints are ignored and not copied. Tracked files are never
    printed. Everything else is copied.
  - Any other exit when neither the source nor any of its parent directories contains `.git`:
    copy every candidate.
  - Any other exit when a `.git` exists there: raise `ZjmError` carrying git's stderr, because
    zjm would otherwise copy gitignored files.
- `index` returns one more key, `"excluded"`: the number of **entries** skipped by the rules
  above (the floor, `exclude`, `deny` and symlinks). A skipped directory counts once, and its
  contents are never looked at. Gitignored files are not counted.

### Egress: nothing leaves the machine unless the config says so

- `find(..., rank=None)`: `None` means `config["egress"]["rank"]`. Passing `rank=True` while
  `egress.rank` is `false` raises
  `ZjmError("ranking sends paths and snippets to OpenRouter; set egress.rank in <config path>")`
  before any call. The default sort follows the effective `rank`.
- `ask` raises `ZjmError("answering sends file contents to an LLM; set egress.answer in <config
  path>")` when `egress.answer` is `false`. It raises before searching.
- CLI: without `--no-rank`, `find`/`ask` pass `rank=None`; with it, `rank=False`. There is no
  flag to force ranking on.
- HTTP bodies and MCP arguments keep `rank` as an optional boolean with the same rule. They cannot
  change the config.

### The answer LLM cannot act

- `DEFAULT_LLM = ["claude", "-p", "--tools", "", "--strict-mcp-config", "--model", "sonnet",
  "--effort", "medium"]`. With `--tools ""` it has no tools, and with `--strict-mcp-config` it
  loads no MCP servers.
- The LLM runs with `cwd` set to a fresh empty temporary directory, removed afterwards, never the
  corpus. Its `env` holds only these variables from `os.environ` that are set: `PATH`, `HOME`,
  `USER`, `LANG`, `LC_ALL`, `TMPDIR`, `CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY`.
  `OPENROUTER_API_KEY` is never passed.
- The `llm_command` argument of `ask` is removed. Only config `llm` changes the command. A custom
  `llm` runs with the same `cwd` and `env` rules, but the no-tools guarantee covers only
  `DEFAULT_LLM`; the README says so.

### HTTP only answers the local machine

- `make_server(host=...)` accepts only `127.0.0.1`, `localhost` or `::1`, and raises `ValueError`
  before binding otherwise. `zjm serve --host` with any other value exits `2` with a message on
  stderr.

Checks run on every request before the body is read, in this order:
- A `Host` header whose host part is not `localhost`, `127.0.0.1` or `[::1]` gets `403`
  `{"error": "host not allowed"}`.
- An `Origin` header whose host is not one of those three gets `403` `{"error": "origin not
  allowed"}`. A request without `Origin` is fine.
- A `POST` whose `Content-Type` media type is not `application/json` gets `415`.

### doctor

- The doctor dict gains `"config"` (the path or `null`), `"home"` and `"egress"`.
- `ok` requires `zg`. It requires `OPENROUTER_API_KEY` only when `egress.rank` is on, and `claude`
  (the first word of `llm`) only when `egress.answer` is on.
- The human output adds a line per new key.

### README

- **Config section:** the lookup order, the table of keys, and an example config for testing:
  `allow` holding one project folder, and `egress` with both switches on.
- **Safety section:** list the exclude floor, and state that nothing leaves the machine unless
  `egress` says so.
- **Version:** bump to `0.5.0`.

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 43 tests**, all passing with an empty
`HOME` and no network:

- The 32 earlier tests stay. Update them where needed: pass a config dict built from a temp
  directory, and turn on `egress` where they rank or ask.
- The 11 tests below are new.

The fake runner must answer `git check-ignore` argv: exit `128` unless a test sets an ignored list.

- `tests/test_config.py`:
  1. `test_lookup_order`: explicit path beats `ZJM_CONFIG`, which beats `<cwd>/.zjm/config.json`,
     which beats the XDG file, which beats the built-ins. A `.zjm/config.json` in the parent of
     `cwd` is ignored.
  2. `test_bad_config_names_file`: unknown key, unknown `egress` key, wrong type, bad JSON and a
     missing explicit path each raise `ZjmError` naming the file. So does an `embedding` that does
     not start with `local/`.
  3. `test_defaults`: `home` is under `XDG_DATA_HOME`, `allow` is `[]`, both egress switches are
     `false`, and `path` is `None`. A config with `"egress": {"rank": true}` gives `answer: false`.
- `tests/test_safety.py`:
  4. `test_refused_outside_allow`: with default config, and again with a path outside
     `allow`, `index` raises the "add it to allow" error. The runner is never called and
     `home` is not created.
  5. `test_deny_before_filesystem`: indexing a path under a `deny` entry raises before
     `os.path.realpath` is called (the test patches it to fail). A denied subdirectory of an
     allowed source is neither copied nor listed (the test's patched `os.scandir` fails on it),
     and a denied single file is not copied. A symlink inside an allowed source that points into a
     denied directory is not copied either.
  6. `test_exclude_floor_and_config_exclude`: a source containing `id_rsa`, `x.pem`, `.npmrc`,
     `.env.local`, `.ssh/config`, `app.log` (config `exclude: ["*.log"]`), a symlink and
     `keep.md` copies only `keep.md`. `excluded` is `7`: `.ssh/` counts once.
  7. `test_gitignored_not_copied`: a `check-ignore` answer of `drop.md` (exit `0`) copies only
     `keep.md`, and git's `input` never names a denied or floor-excluded path. Exit `128` with no
     `.git` copies both. Exit `128` with a `.git` directory raises.
  8. `test_egress_ceiling`: with egress off, `rank=True` raises without calling Jev, `rank=None`
     does not call Jev, and `ask` raises without calling the runner. With egress on, both work. CLI `find` without
     `--no-rank` succeeds with egress off.
  9. `test_llm_cannot_act`: the LLM argv contains `--tools`, `""` and `--strict-mcp-config`. Its
     `cwd` is an empty directory that is not under `home`, and its `env` lacks
     `OPENROUTER_API_KEY`.
  10. `test_http_guard`: `Host: evil.example` gives `403`, `Origin: http://evil.example` gives
      `403`, `Content-Type: text/plain` gives `415`, a clean localhost JSON request gives
      `200`, `make_server(host="0.0.0.0")` raises without binding, and `zjm serve --host 0.0.0.0` exits `2`.
  11. `test_doctor_reports_config`: it reports `config`, `home` and `egress`, and `ok` is true
      without `OPENROUTER_API_KEY` when `egress.rank` is off.

## Jev request shape (pinned)

Do not change the payload in `zjm_rag/core.py` or the client in `zjm_rag/jev.py`. The live API
rejects any other shape with HTTP 400. Each `noul` question stays exactly:

```python
{"type": "noul",
 "instructions": "Does file fK (<path>) contain the information needed to answer the question? ...",
 "criteria": {"true": "The file holds the answer.", "false": "The file does not hold the answer."}}
```

Fakes used in this spec's tests must accept only that shape.

## Decisions

- **`deny` is compared as written, never resolved** (review item 2 asked for canonical forms on
  both sides). Resolving a `deny` entry would `stat` the very path the owner forbids. The cost:
  a `deny` entry under a symlinked parent can be bypassed, so the README tells the owner to write
  real paths. `home` is zjm's own directory, so it is checked in both forms.
- **`deny` governs what zjm itself reads and copies, not git's own metadata** (review round 4).
  When zjm asks `git check-ignore` about an allowed source, git reads that repository's `.git/`,
  its `.gitignore` files and the user's global excludes. Denying a single file inside an allowed
  repository's git metadata is not supported; deny the whole directory instead. The README says so.
- **HTTP binds to loopback only.** Serving inside a container (which needs a non-loopback bind) is
  a later spec's concern, not a reason to keep `--host` open now.

## Out of scope

- Named lockers and adding or removing single files: that is spec 06.
- Running inside a container.
- Encryption at rest.
- Authentication on HTTP.
- Migrating an old `/tmp/zjm-rag` store: it is simply ignored.
