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

A locker can be **encrypted with its own key**, supplied by the app on every call (see
[Locker keys](#locker-keys)): at rest it is one `age`-encrypted file, and zjm holds neither the
key nor the plaintext outside the single request that needs them.

1. **zg finds.** A hybrid search over a locker's zg index returns candidate files, in zg's rank
   order. zjm keeps every one of zg's hits as a full chunk (its matched heading section, widened
   and merged, not a truncated preview), so the text that answers a question is never lost between
   zg and the answer model.
2. **Jev ranks.** One request to Jev (the OpenRouter Decisions API) asks, per file, whether it
   contains the information needed to answer the question, judging from those full chunks. Each
   file gets a probability; files at or above a threshold (default `0.5`) are accepted, the rest
   are reported as rejected, never dropped silently.
3. **An LLM answers.** The top accepted files (`top_k`, default `8`) go to a cheap OpenRouter model
   (`deepseek/deepseek-v4-flash` by default) with the instruction to answer from those files only,
   citing the path and lines. Small files are sent whole; larger ones as their chunks, while a
   200 000-character budget lasts. When no file passes the threshold, no LLM is called.

## Install

zjm runs only inside its hardened container — never natively on the host.

    curl -fsSL https://raw.githubusercontent.com/cocodedk/zjm-rag/main/install.sh | sh

It checks for `docker` and `python3`, builds the `zjm-rag:latest` image, and puts the `zjm`
launcher (a POSIX `sh` script) on `~/.local/bin`. From then on, `zjm ...` on the host runs
`docker run` with the container locked down: `--read-only`, `--cap-drop=ALL`,
`--security-opt=no-new-privileges`, a `2g` memory cap, a `256`-pid limit, persistent data in the
`zjm-data` Docker volume, and `--network none` unless the config turns `egress` on.

Requirements: `docker` and `python3` on the host; `OPENROUTER_API_KEY` (used for both Jev ranking
and OpenRouter answers) is needed only once `egress.rank` or `egress.answer` is turned on in the
config, and is passed through by name, never by value.

## Use

zjm never reads, keeps or sends anything you have not allowed in the config file (see
[Config](#config) and [Safety](#safety) below). With `allow: ["~/projects/agent-linters"]` and
`egress: {"rank": true, "answer": true}` in your config:

```python
import os, zjm_rag

zjm_rag.locker_create("linters", plain=True)   # or locker_create("linters", key) to encrypt
zjm_rag.file_add("linters", [os.path.expanduser("~/projects/agent-linters")])
hits = zjm_rag.find("which linter checks CSS files", ["linters"])   # {"accepted": [...], "rejected": [...], ...}
reply = zjm_rag.ask("which linter checks CSS files", ["linters"], answer_language="da")
print(reply["answer"], reply["files"])
```

- `locker_create(name, key, multilingual=True)` for non-English queries; the embedding is
  fixed for the locker's lifetime — drop and recreate it to change models. **Lockers are
  encrypted by default**: `locker_create` needs a key, and a plain directory locker needs an
  explicit `plain=True` (CLI `--plain`).
- `file_add(locker, paths, key=None)` copies files or directories in (spec 05's
  allow/deny/exclude/gitignore rules apply); `file_put(locker, name, text, key=None)` writes text
  directly; `file_remove(locker, names, key=None)` removes files or whole directory prefixes;
  `file_list(locker, key=None)` lists what is there. `key` is required exactly when the locker is
  encrypted.
- `find(query, lockers, keys=None, limit=8, min_score=0.5, sort="score"|"zg"|"mtime"|"path",
  rank=None, translate=None, file_types=["py"])` searches one or more lockers at once (plain and
  encrypted mixed freely), interleaving their results; `rank=None` follows the config's
  `egress.rank`, and `rank=True` fails without it. `translate=None` follows `egress.translate` the
  same way, and adds the question's translations into the configured `languages` as further
  candidates (see [Questions in other languages](#questions-in-other-languages)). `keys` maps each
  encrypted locker's name to its key.
- `ask(..., top_k=None, llm=zjm_rag.llm.post)` fails unless the config's `egress.answer` is on.
  `top_k=None` (the default) sends every accepted file, still bounded by the context budget; an
  integer still caps the count. `llm` is injectable, like `jev`, for tests.
- `locker_encrypt(name, key)` seals a plain locker into an encrypted one; this is one-way — there
  is no operation that decrypts a locker back to plain.
- Every call takes `config=` (a path or a `load()`ed dict), plus injectable `runner=` and `jev=`
  for tests.
- Errors raise `zjm_rag.ZjmError`.

The same operations on the command line (`zjm` or `python3 -m zjm_rag`); add `--key-file PATH`
wherever a key is needed (`-` reads it from stdin):

```sh
zjm locker-create NAME (--key-file KEY | --plain) [--multilingual | --embedding MODEL]
zjm locker-list
zjm locker-drop NAME [--key-file KEY]
zjm locker-encrypt NAME --key-file KEY        # one-way: plain -> encrypted
zjm file-add LOCKER PATH... [--key-file KEY]
zjm file-put LOCKER NAME [--key-file KEY]     # reads the text from stdin
zjm file-remove LOCKER NAME... [--key-file KEY]
zjm file-list LOCKER [--key-file KEY]
zjm find "which linter checks CSS files" -l LOCKER [-l LOCKER]... [--key-file KEYS.json] [--limit N] [--type py]... [--min-score 0.5] [--sort score|zg|mtime|path] [--no-rank] [--no-translate]
zjm ask "which linter checks CSS files" -l LOCKER --lang da [--key-file KEYS.json] [--top-k 3] [--no-translate]
zjm doctor                                   # zg, age, OPENROUTER_API_KEY, config, home, egress, lockers
```

For `find`/`ask`, `--key-file` holds a JSON object `{"locker": "key"}` (one entry per encrypted
locker searched); for every other command it holds one key.

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
table — `locker_create`, `locker_list`, `locker_drop`, `locker_encrypt`, `file_add`, `file_put`,
`file_remove`, `file_list`, `find`, `ask`, `doctor`) takes the library's keyword arguments as a
JSON body (`home`, `store` and `config` are the server's and cannot be set), including `key` /
`keys` where a key is needed, and returns its result. Errors are `{"error": "..."}`: `400` bad
body, `404`, `405`, `413` over 1 MiB, `422` from the library.

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
| `egress` | `{"rank": bool, "answer": bool, "translate": bool}` | `{"rank": false, "answer": false, "translate": false}` |
| `embedding` | string, must start with `local/` | `local/potion-code-16m-v2` |
| `llm` | an OpenRouter model id string | `deepseek/deepseek-v4-flash` |
| `languages` | list of non-empty strings | `["English", "German", "Danish", "Norwegian", "Swedish"]` |
| `translate_model` | non-empty string | `upstage/solar-mini4` |

A relative `home`/`allow`/`deny` entry resolves against the config file's own directory; `~`
expands from `$HOME`. In the container, `home` is fixed to `/data` (the `zjm-data` volume) and
`allow` names `/sources/<name>` paths — the mount points the launcher creates from `ZJM_SOURCES`.
`embedding` must be one of the two models baked into the image:
`local/potion-code-16m-v2` or `local/potion-multilingual-128m`.

`llm` names the OpenRouter model `ask` answers with; every request sets
`"provider": {"data_collection": "deny"}`, so OpenRouter itself does not retain the prompt. Avoid
`:free` model variants as the answer model — OpenRouter's free tier usually logs prompts, and
`data_collection: deny` cannot change that — which is why the default is a paid, non-`:free` model.

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

## Questions in other languages

An English question finds the Danish, German, Norwegian or Swedish text that answers it, even when
they share no words, and a question in any language finds text in the configured `languages`. zjm
translates the **question**, never the files, into each configured language and searches the
translations in addition to the original; the translations can only **add** candidate files, never
displace one the original question already found, and no language detection is needed.

Measured (`evals/recall.py`, 38 questions, potion-code index; prototype):

| approach | English question, foreign text, no shared words | everything else |
|---|---|---|
| no translation | 0/4 | 34/34 |
| local multilingual embeddings | 0–1/4 | 33–34/34 |
| translations fused into one ranking | 4/4 | 27/34 |
| **translations add files after the original's** | **4/4** | **34/34** |

- `egress.translate` (default `false`) follows the same rule as `egress.rank`/`egress.answer`:
  `translate=True` while it is off raises before any call; CLI `--no-translate` forces it off for
  one `find`/`ask`.
- `languages` (default `["English", "German", "Danish", "Norwegian", "Swedish"]`); an empty list
  turns translation off even with `egress.translate` on.
- `translate_model` (default `upstage/solar-mini4`) — the OpenRouter model asked to translate.
- The translation request sends only the question — never file text, paths or snippets. Ranking
  and answering keep their own `egress` switches and are unaffected by this one.
- **Why files are not translated:** mixed-language documents work chunk by chunk regardless, the
  model translates a question from any language without first detecting it, and translating one
  short question is far cheaper than translating (and re-indexing on every change) a whole corpus.
- A hit found only through a translation carries `"via": "translation"` (`"via": "query"`
  otherwise, for a hit the original question itself found); `find`'s human output marks such a
  line with a trailing `  (translation)`.

## Locker keys

A locker's key is an [age](https://github.com/FiloSottile/age) X25519 identity string
(`AGE-SECRET-KEY-1…`). Generate one with `age-keygen` (baked into the image) and keep it in the
app, never in zjm: **zjm never stores a key**, and a lost key means a lost locker.

- A plain locker exists only when created with `plain=True` (`--plain`); it is a directory under
  `<home>/lockers/<name>/`, exactly as before.
- With a key — on `locker_create`, or later via `locker_encrypt` — a locker is exactly one file,
  `<home>/lockers/<name>.age`: the whole locker (its files, zg index and manifest), tarred and
  encrypted. No other per-locker file exists on disk.
- Every request that touches an encrypted locker decrypts it into a private `/tmp` directory for
  that request only, re-encrypts after a write, and deletes both the plaintext and the key file
  before returning — even on error.
- The key travels only in files under `/tmp` and in request bodies. It never appears in argv, the
  environment, logs, error messages or results.
- `find` and `ask` can search plain and encrypted lockers together in one call; pass `keys` (a
  `{locker: key}` map, or `--key-file KEYS.json` on the CLI) for the encrypted ones only.

## Safety

- **Exclude floor**, always skipped, however `exclude` is set: directories `.git`, `node_modules`,
  `.venv`, `__pycache__`, `.zvec-grep`, `.zjm`, `.ssh`, `.gnupg`, `.aws`, `.kube`, `.docker`; files
  `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.kdbx`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`,
  `id_ed25519*`, `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `credentials*`.
- Symlinks inside a source are never copied. Gitignored files are never copied (denying a single
  file inside an allowed repository's own git metadata is not supported; deny the whole directory).
- **Nothing leaves this machine unless `egress` says so.** Ranking (Jev/OpenRouter) needs
  `egress.rank`; answering (the OpenRouter model) needs `egress.answer`; translating the question
  (see [Questions in other languages](#questions-in-other-languages)) needs `egress.translate`. The
  answer request has no `tools` key, so the model cannot act; it only ever returns text.
  `OPENROUTER_API_KEY` is sent only in the request's `Authorization` header — never in argv, logs,
  errors, results or the messages sent to the model.
- `zjm serve` binds to `127.0.0.1`, `localhost` or `::1` only, and checks `Host`/`Origin` on every
  request (in the container, `0.0.0.0` is also accepted, since the launcher publishes only to
  the host's loopback interface).
- The app, not zjm, decides who may use which locker and which lockers a question may search.
- **The container is the only supported way to run zjm.** It runs read-only, as a non-root user,
  with no Linux capabilities, no swap, no core dumps, `--network none` unless `egress` is on, and
  persistent data confined to the `zjm-data` volume.
- **Encryption at rest is per locker, opt in.** See [Locker keys](#locker-keys).

## Build from source

```sh
git clone https://github.com/cocodedk/zjm-rag.git
cd zjm-rag
./scripts/install-hooks.sh                  # git hooks, once per clone
python3 -m unittest discover -s tests -q    # the test suite
```

The package is stdlib-only, so there is nothing else to install. Tests use fakes and never call
zg, Jev or the answer model. See [CONTRIBUTING.md](CONTRIBUTING.md).

### Recall eval

`evals/recall.py` measures whether zjm keeps the text that answers a question, from zg's hits
through to the answer model's prompt, over `evals/corpus` plus a generated runbook. It runs the
real `zg` (offline; no network), captures the answer prompt instead of calling the model, and is
not part of the unit suite:

```sh
python3 evals/recall.py                                # ranking off (no network)
python3 evals/recall.py --jev                           # also ranks with the real Jev (network, costs)
python3 evals/recall.py --limit 20 --min-score 0.7 --multilingual --verbose
```

Per question it reports whether the expected file was a candidate (`cand`), whether the answer
text was in that file's evidence (`evid`), whether the file was accepted (`acc`), and whether the
answer text reached the answer model's prompt (`ctx`). The gate: for every question where `cand`
is `yes`, `evid` and `ctx` must be `yes` too.

## Architecture

```
zjm_rag/            library: lockers, files, search, gather (per-locker zg queries), evidence
                    (full chunks), translate (question translation), llm (OpenRouter),
                    sealed (age), ops table
tests/              unittest suite and the zg output fixture
evals/              the recall eval: corpus, golden questions and recall.py
docs/lean/          specs for the library, CLI, HTTP API, MCP server and installer
profile-python.md   gate profile the lean loop builds against
website/            the project site (rag.cocode.dk)
```

| Part | Technology |
|---|---|
| Search | zg (zvec-grep), local hybrid index per locker |
| Ranking | Jev via the OpenRouter Decisions API |
| Answer | an OpenRouter model (`deepseek/deepseek-v4-flash` by default) |
| Code | Python 3.10+, standard library only |

## Author

**Babak Bandpey** — [https://cocode.dk](https://cocode.dk) | [LinkedIn](https://linkedin.com/in/babakbandpey) | [GitHub](https://github.com/cocodedk)

## License

MIT | © 2026 [Cocode](https://cocode.dk) | Created by [Babak Bandpey](https://linkedin.com/in/babakbandpey)
