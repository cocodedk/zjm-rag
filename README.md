# zjm-rag

Find the file that holds the answer. zjm-rag searches your folders with
[zg](https://www.npmjs.com/package/@zvec/zvec-grep) (zvec-grep), has Jev judge which of the
candidate files actually contain the answer, and lets an LLM answer from those files only, citing
their paths.

## Website

- [English](https://rag.cocode.dk/)
- [فارسی (Persian)](https://rag.cocode.dk/fa/)

## How it works

zjm works like OpenAI's vector stores: a **locker** is a named index. Files and text go into it,
and they come out again. `find` and `ask` search the lockers the caller names. zjm has no idea of
users, chats, organizations or tenants — the app decides who may use which locker.

1. **zg finds.** A hybrid search over a locker's zg index returns candidate files with short
   snippets, in zg's rank order.
2. **Jev ranks.** One request to Jev (the OpenRouter Decisions API) asks, per file, whether it
   contains the information needed to answer the question. Each file gets a probability; files at
   or above a threshold (default `0.5`) are accepted, the rest are reported as rejected, never
   dropped silently.
3. **An LLM answers.** The top accepted files go to an LLM command-line client (`claude` by
   default) with the instruction to answer from those files only and cite the path. When no file
   passes the threshold, no LLM is called.

## Install

zjm runs only inside its hardened container — never natively on the host.

    curl -fsSL https://raw.githubusercontent.com/cocodedk/zjm-rag/main/install.sh | sh

It checks for `docker` and `python3`, builds the `zjm-rag:latest` image, and puts the `zjm`
launcher (a POSIX `sh` script) on `~/.local/bin`. From then on, `zjm ...` on the host runs
`docker run` with the container locked down: `--read-only`, `--cap-drop=ALL`,
`--security-opt=no-new-privileges`, a `2g` memory cap, a `256`-pid limit, persistent data in the
`zjm-data` Docker volume, and `--network none` unless the config turns `egress` on.

Requirements: `docker` and `python3` on the host; `OPENROUTER_API_KEY` for Jev ranking and
`ANTHROPIC_API_KEY` for answers are needed only once `egress.rank`/`egress.answer` are turned on
in the config, and are passed through by name, never by value.

## Use

zjm never reads, keeps or sends anything you have not allowed in the config file (see
[Config](#config) and [Safety](#safety) below). With `allow: ["~/projects/agent-linters"]` and
`egress: {"rank": true, "answer": true}` in your config:

```python
import os, zjm_rag

zjm_rag.locker_create("linters")
zjm_rag.file_add("linters", [os.path.expanduser("~/projects/agent-linters")])
hits = zjm_rag.find("which linter checks CSS files", ["linters"])   # {"accepted": [...], "rejected": [...], ...}
reply = zjm_rag.ask("which linter checks CSS files", ["linters"], answer_language="da")
print(reply["answer"], reply["files"])
```

- `locker_create(name, multilingual=True)` for non-English queries; the embedding is fixed for the
  locker's lifetime — drop and recreate it to change models.
- `file_add(locker, paths)` copies files or directories in (spec 05's allow/deny/exclude/gitignore
  rules apply); `file_put(locker, name, text)` writes text directly; `file_remove(locker, names)`
  removes files or whole directory prefixes; `file_list(locker)` lists what is there.
- `find(query, lockers, min_score=0.5, sort="score"|"zg"|"mtime"|"path", rank=None,
  file_types=["py"])` searches one or more lockers at once, interleaving their results;
  `rank=None` follows the config's `egress.rank`, and `rank=True` fails without it.
- `ask(...)` fails unless the config's `egress.answer` is on.
- Every call takes `config=` (a path or a `load()`ed dict), plus injectable `runner=` and `jev=`
  for tests.
- Errors raise `zjm_rag.ZjmError`.

The same operations on the command line (`zjm` or `python3 -m zjm_rag`):

```sh
zjm locker-create NAME [--multilingual | --embedding MODEL]
zjm locker-list
zjm locker-drop NAME
zjm file-add LOCKER PATH...
zjm file-put LOCKER NAME                     # reads the text from stdin
zjm file-remove LOCKER NAME...
zjm file-list LOCKER
zjm find "which linter checks CSS files" -l LOCKER [-l LOCKER]... [--limit N] [--type py]... [--min-score 0.5] [--sort score|zg|mtime|path] [--no-rank]
zjm ask "which linter checks CSS files" -l LOCKER --lang da [--top-k 3]
zjm doctor                                   # zg, claude, OPENROUTER_API_KEY, config, home, egress, lockers
```

Every subcommand takes `--config PATH` and `--json`, which prints the library's return value as
one JSON object (errors as `{"error": "..."}`). Exit codes: `0` ok, `1` error or failed `doctor`,
`2` usage.

Over HTTP (needs `egress` on; the launcher publishes it to loopback only):

```sh
zjm serve   # the launcher publishes 127.0.0.1:${ZJM_PORT:-8765} -> the container's :8765
curl -s localhost:8765/file_add -d '{"locker": "linters", "paths": ["/sources/agent-linters"]}'
curl -s localhost:8765/find -d '{"query": "which linter checks CSS files", "lockers": ["linters"]}'
```

`GET /health` returns the `doctor` dict; `POST /<op>` (one per row in `zjm_rag/ops.py`'s `OPS`
table — `locker_create`, `locker_list`, `locker_drop`, `file_add`, `file_put`, `file_remove`,
`file_list`, `find`, `ask`, `doctor`) takes the library's keyword arguments as a JSON body (`home`,
`store` and `config` are the server's and cannot be set) and returns its result. Errors are
`{"error": "..."}`: `400` bad body, `404`, `405`, `413` over 1 MiB, `422` from the library.

For agents, as MCP tools over stdio (`zjm_<op>` for each op above):

```sh
claude mcp add zjm -- zjm mcp          # add --config PATH after `zjm mcp` for another config
```

## Config

zjm reads one JSON config file. The first of these that exists wins (files are never merged):

1. `--config PATH` / the library's `config=` argument
2. `$ZJM_CONFIG`
3. `<cwd>/.zjm/config.json` (only `cwd` itself; parent directories are never searched)
4. `$XDG_CONFIG_HOME/zjm/config.json`, else `$HOME/.config/zjm/config.json`
5. built-in defaults (nothing is allowed, nothing leaves the machine)

| key | type | default |
|---|---|---|
| `home` | string | `$XDG_DATA_HOME/zjm`, else `$HOME/.local/share/zjm`; lockers live under `<home>/lockers/` |
| `allow` | list of strings | `[]` — nothing is added to a locker until you add paths here |
| `deny` | list of strings | `[]` — write real paths; symlinked parents are not resolved |
| `exclude` | list of strings (globs) | `[]` — adds to the built-in floor below, never removes from it |
| `egress` | `{"rank": bool, "answer": bool}` | `{"rank": false, "answer": false}` |
| `embedding` | string, must start with `local/` | `local/potion-code-16m-v2` |
| `llm` | non-empty list of strings (argv) | a no-tools `claude -p` invocation |

A relative `home`/`allow`/`deny` entry resolves against the config file's own directory; `~`
expands from `$HOME`. In the container, `home` is fixed to `/data` (the `zjm-data` volume) and
`allow` names `/sources/<name>` paths — the mount points the launcher creates from `ZJM_SOURCES`.
`embedding` must be one of the two models baked into the image:
`local/potion-code-16m-v2` or `local/potion-multilingual-128m`.

Example config for the launcher (`$XDG_CONFIG_HOME/zjm/config.json`, or `$ZJM_HOST_CONFIG`):

```json
{
  "allow": ["/sources/agent-linters"],
  "home": "/data",
  "egress": {"rank": true, "answer": true}
}
```

Set `ZJM_SOURCES` to a colon-separated list of host folders to mount, one becomes
`/sources/<basename>`: `ZJM_SOURCES=/home/you/projects/agent-linters zjm file-add linters /sources/agent-linters`.

## Safety

- **Exclude floor**, always skipped, however `exclude` is set: directories `.git`, `node_modules`,
  `.venv`, `__pycache__`, `.zvec-grep`, `.zjm`, `.ssh`, `.gnupg`, `.aws`, `.kube`, `.docker`; files
  `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.kdbx`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`,
  `id_ed25519*`, `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `credentials*`.
- Symlinks inside a source are never copied. Gitignored files are never copied (denying a single
  file inside an allowed repository's own git metadata is not supported; deny the whole directory).
- **Nothing leaves this machine unless `egress` says so.** Ranking (Jev/OpenRouter) needs
  `egress.rank`; answering (the LLM) needs `egress.answer`. The answer LLM runs with no tools, no
  MCP servers, a fresh empty `cwd`, and a filtered environment (no `OPENROUTER_API_KEY`).
- `zjm serve` binds to `127.0.0.1`, `localhost` or `::1` only, and checks `Host`/`Origin` on every
  request (in the container, `0.0.0.0` is also accepted, since the launcher publishes only to
  the host's loopback interface).
- The app, not zjm, decides who may use which locker and which lockers a question may search.
- **The container is the only supported way to run zjm.** It runs read-only, as a non-root user,
  with no Linux capabilities, `--network none` unless `egress` is on, and persistent data confined
  to the `zjm-data` volume.

## Build from source

```sh
git clone https://github.com/cocodedk/zjm-rag.git
cd zjm-rag
./scripts/install-hooks.sh                  # git hooks, once per clone
python3 -m unittest discover -s tests -q    # the test suite
```

The package is stdlib-only, so there is nothing else to install. Tests use fakes and never call
zg, Jev or an LLM. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Architecture

```
zjm_rag/            library: lockers, files, search (zg + Jev), ask (claude), ops table
tests/              unittest suite and the zg output fixture
docs/lean/          specs for the library, CLI, HTTP API, MCP server and installer
profile-python.md   gate profile the lean loop builds against
website/            the project site (rag.cocode.dk)
```

| Part | Technology |
|---|---|
| Search | zg (zvec-grep), local hybrid index per locker |
| Ranking | Jev via the OpenRouter Decisions API |
| Answer | an LLM CLI (`claude` by default) |
| Code | Python 3.10+, standard library only |

## Author

**Babak Bandpey** — [https://cocode.dk](https://cocode.dk) | [LinkedIn](https://linkedin.com/in/babakbandpey) | [GitHub](https://github.com/cocodedk)

## License

MIT | © 2026 [Cocode](https://cocode.dk) | Created by [Babak Bandpey](https://linkedin.com/in/babakbandpey)
