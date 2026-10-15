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
users, chats, organizations or tenants. The app decides who may use which locker.

A locker can be **encrypted with its own key**, supplied by the app on every call (see
[Locker keys](#locker-keys)): at rest it is one `age`-encrypted file, and zjm holds neither the
key nor the plaintext outside the single request that needs them.

1. **zg finds.** A hybrid search over a locker's zg index returns candidate files, in zg's rank
   order. For the first `limit` candidate files of each locker (plus up to `limit` more from a translated question), zjm keeps every zg hit as a full chunk (the line ranges of its matches, with
   overlapping or adjacent ranges merged, not a truncated preview), so the text that answers a
   question is never lost between zg and the answer model.
2. **Jev ranks.** One request to Jev (TypeSafe's decisions API) asks, per file, whether it
   contains the information needed to answer the question, judging from those full chunks. Each
   file gets a probability; files at or above a threshold (default `0.5`) are accepted, the rest
   are reported as rejected, never dropped silently.
3. **An LLM answers.** All accepted files (by default; `top_k` caps them) go to a cheap OpenRouter model
   (`deepseek/deepseek-v4-flash` by default) with the instruction to answer from those files only,
   citing the path and lines. Small files are sent whole; larger ones as their chunks, while a
   200 000-character budget lasts. When no file passes the threshold, no LLM is called.

## Install

zjm runs only inside its Docker container, never directly on your computer. The installer builds
that container and sets up the rest.

### What you need

- Docker, installed and running. The installer builds zjm's container with it.
- python3, version 3.10 or newer. The `zjm` command and the project script use it.
- git. The project script uses it to find the project's top folder and the files git can see.
- An OpenRouter API key in `OPENROUTER_API_KEY` and a TypeSafe API key in `TYPESAFE_API_KEY` (Jev),
  only if you turn on sending for a project (see [Set up a project](#set-up-a-project)).

### Run the installer

    curl -fsSL https://raw.githubusercontent.com/cocodedk/zjm-rag/main/install.sh | sh

To read the script first, open the same address in a browser. The installer prints four steps,
`1/4` to `4/4`:

1. Checks that `docker` and `python3` are installed.
2. Builds the `zjm-rag:latest` Docker image. The first build takes a while.
3. Puts the `zjm` launcher (a Python script) in `~/.local/bin`. If no config exists, it creates a
   private one at `~/.config/zjm/config.json` (or `$XDG_CONFIG_HOME/zjm/config.json`) with all
   outside calls turned off. An existing config is kept.
4. Installs the Claude Code skill `zjm-rag` into `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/zjm-rag`.
   It replaces an older copy, so any edits you made to that copy are lost.

If the installer warns that `~/.local/bin` is not on your `PATH`, add this line to your shell profile
(for example `~/.bashrc`) and open a new terminal:

    export PATH="$HOME/.local/bin:$PATH"

Then check the install:

    zjm doctor

`zjm doctor` checks zg, age, the API key, the config, the data folder, outside calls and the lockers.
It exits with status 1 when a check fails. A missing `OPENROUTER_API_KEY` matters only once you turn
sending on (`send` in a project, or `egress` in your config).

### The container

From then on, `zjm ...` on the host runs `docker run` with the container locked down: `--read-only`, `--cap-drop=ALL`,
`--security-opt=no-new-privileges`, a `2g` memory cap, a `256`-pid limit, persistent data in the
`zjm-data` Docker volume, and `--network none` unless the config turns `egress` on.

It also installs the Claude Code skill `zjm-rag` into `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/zjm-rag`,
replacing any older copy: [skills/zjm-rag/SKILL.md](skills/zjm-rag/SKILL.md) says how to index a project's
documents, keep the index fresh and search it.

### Set up a project

zjm keeps a **locker** for each project: a private, searchable index of the project's documents.
The Claude Code skill builds and searches that index. The project is set up by one file,
`zjm-project.json`, which you commit so every session and every teammate uses the same settings.

Index documents and memory folders, not code. A whole code tree makes the index fail, and then every
search comes back empty. Search code with `grep` instead.

The commands below use `~/.claude/skills/zjm-rag/scripts/zjm-project`. If you set
`CLAUDE_CONFIG_DIR`, use that folder instead of `~/.claude`.

1. Open a terminal in the project's top folder: the folder that holds `.git`, or the folder you work
   in if the project does not use git.
2. Create `zjm-project.json` there. Use this content, and change `locker` and `folders` to your own:

       {"locker": "myproj", "folders": ["docs", "memory"], "exclude": ["*.pdf", "drafts/"],
        "send": false, "llm": "deepseek/deepseek-v4-flash", "multilingual": false}

   Expected: the file sits in the top folder. The keys are:
   - `locker`: the name of this project's index. Start with a lowercase letter or a digit, then use lowercase
     letters, digits, `.`, `_` and `-`, up to 64 characters in all. All projects share one store, so the name must be unique. Run `zjm locker-list` to
     see the names in use.
   - `folders`: the folders to index, relative to the top folder. Each must be a real folder inside the
     project, not a symlink, and two folders cannot share a name. A folder that does not exist yet is
     indexed as empty, with a warning.
   - `files`: single files to index, such as `README.md` or `CLAUDE.md`, relative to the top folder. Use
     it for files that sit in the top folder, so you do not index the code around them.
   - `exclude`: files or folders to leave out, by name. End a folder name with `/`.
   - `send`: `false` keeps everything on your machine. `true` lets searches and answers send file text
     to OpenRouter. Leave it `false` unless the project's owner decides otherwise. This switch belongs to
     the skill's project setup; direct use follows the config's `egress` instead.
   - `llm`: the OpenRouter model that writes answers. It is used only when `send` is `true`.
   - `multilingual`: `true` for documents that are not in English.
3. Add `.zvec-grep/` to `.gitignore`, on its own line. Expected: zg's working folder stays out of git.
4. Commit `zjm-project.json` and `.gitignore`. Expected: git lists both as committed.
5. Build the index:

       ~/.claude/skills/zjm-rag/scripts/zjm-project reindex

   Expected: zjm reports what it added, and the prompt returns. Reindex copies each folder into zjm's
   store first. Only text files up to 1 MiB each are copied; larger and binary files are skipped with a
   warning. Paths inside text files are redacted (for example `/home/<user>/` becomes `~/`).
   A file that git ignores and does not track is not copied; a tracked file is copied even if `.gitignore` matches it. Files whose names match zjm's built-in secret-file patterns (`.env*`,
   `*.pem`, `*.key`, `id_rsa*` and the rest of the list under [Safety](#safety)) are left out. The contents
   of documents are not scanned for secrets, so a key pasted into an ordinary document is indexed, and
   sent to OpenRouter if `send` is on.
6. Search by asking a full question:

       ~/.claude/skills/zjm-rag/scripts/zjm-project find "who approves a change before it runs?"

   Expected: a list of file paths, each with a score. The line `rejected: N below 0.5` counts the files
   the judge turned down. With `send` set to `false`, the scores show as `-` and the list is zg's
   candidates in zg's order, with no ranking. Open every file you plan to rely on: a score measures
   relevance, not truth. No hit does not prove that the text is missing, so try other wordings.
7. Optional: get answers with citations. Set `"send": true` in `zjm-project.json`, then run this in
   your terminal, with your own key in place of the placeholder:

       export OPENROUTER_API_KEY=your-key-here
       export TYPESAFE_API_KEY=your-typesafe-key-here

   Expected: `find` now ranks the files through Jev, and this command works:

       ~/.claude/skills/zjm-rag/scripts/zjm-project ask "who approves a change before it runs?"

   Expected: an answer that names the files it used. Check each cited passage. Risk: with `send` on,
   matching file text leaves your machine: ranking sends passages to TypeSafe for Jev and to OpenRouter
   for the other decision models, and answering sends accepted file text to OpenRouter. Each search
   and each answer is a paid call. Keep the key out of `zjm-project.json` and out of git.

After every change to an indexed folder (each commit, merge or pull), run `reindex` again before you
search. If `find` or `ask` prints `STALE:`, a folder changed since the last reindex. Reindex, then
search again.

## Use

zjm never reads, keeps or sends anything you have not allowed in the config file (see
[Config](#config) and [Safety](#safety) below). The `zjm_rag` library runs inside the zjm-rag
container; the host has the `zjm` launcher. With `allow: ["~/projects/agent-linters"]` and
`egress: {"rank": true, "answer": true}` in your config, the calls look like this:

```python
import os, zjm_rag

zjm_rag.locker_create("linters", plain=True)   # or locker_create("linters", key) to encrypt
zjm_rag.file_add("linters", [os.path.expanduser("~/projects/agent-linters")])
hits = zjm_rag.find("which linter checks CSS files", ["linters"])   # {"accepted": [...], "rejected": [...], ...}
reply = zjm_rag.ask("which linter checks CSS files", ["linters"], answer_language="da")
print(reply["answer"], reply["files"])
```

- `locker_create(name, key, multilingual=True)` for non-English queries; the embedding is
  fixed for the locker's lifetime. Drop and recreate it to change models. The CLI's `locker-create`
  needs either `--key-file KEY` (an encrypted locker) or `--plain` (a plain directory locker), and
  fails with neither. The library's `locker_create` needs either `key` or `plain=True`.
- `file_add(locker, paths, key=None)` copies files or directories in (spec 05's
  allow/deny/exclude/gitignore rules apply); `file_put(locker, name, text, key=None)` writes text
  directly; `file_remove(locker, names, key=None)` removes files or whole directory prefixes;
  `file_list(locker, key=None)` lists what is there. `key` is required exactly when the locker is
  encrypted.
- `find(query, lockers, keys=None, limit=8, min_score=0.5, sort="score"|"zg"|"mtime"|"path",
  rank=None, translate=None, file_types=None)` searches one or more lockers at once (plain and
  encrypted mixed freely), interleaving their results; `rank=None` follows the config's
  `egress.rank`, and `rank=True` fails without it. `translate=None` follows `egress.translate` the
  same way, and adds the question's translations into the configured `languages` as further
  candidates (see [Questions in other languages](#questions-in-other-languages)). `keys` maps each
  encrypted locker's name to its key.
- `ask(..., top_k=None, llm=zjm_rag.llm.post)` fails unless the config's `egress.answer` is on.
  `top_k=None` (the default) sends every accepted file, still bounded by the context budget; an
  integer still caps the count. `llm` is injectable, like `jev`, for tests.
- `file_add` prepares the whole batch before replacing existing content, so copy errors leave
  the old files intact; ignored sources leave existing entries unchanged, and replacements may
  change between files and directories. Staging temporarily needs space for both versions.
  If indexing fails on a plain locker, copied files remain and the locker is marked unindexed;
  encrypted lockers retain their previous sealed state.
- `locker_encrypt(name, key)` seals a plain locker into an encrypted one; this is one-way: there
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
zjm doctor                                   # zg, age, OPENROUTER_API_KEY, TYPESAFE_API_KEY, config, home, egress, lockers
zjm help                                     # the workflow guide and this instance's settings; changes nothing
```

For `find`/`ask`, `--key-file` holds a JSON object `{"locker": "key"}` (one entry per encrypted
locker searched); for every other command it holds one key.

Every subcommand takes `--config PATH` and `--json`, which prints the library's return value as
one JSON object (errors as `{"error": "..."}`). Exit codes: `0` ok, `1` error or failed `doctor`,
`2` usage.

Over HTTP (needs `egress` on; the launcher publishes it to loopback only):

```sh
zjm serve   # the launcher publishes 127.0.0.1:${ZJM_PORT:-8765} -> the container's :8765
curl -s localhost:8765/file_add -H 'Content-Type: application/json' -d '{"locker": "linters", "paths": ["/sources/agent-linters"]}'
curl -s localhost:8765/find -H 'Content-Type: application/json' -d '{"query": "which linter checks CSS files", "lockers": ["linters"]}'
```

`GET /health` returns the `doctor` dict; `POST /<op>` (one per row in `zjm_rag/ops.py`'s `OPS`
table: `locker_create`, `locker_list`, `locker_drop`, `locker_encrypt`, `file_add`, `file_put`,
`file_remove`, `file_list`, `find`, `ask`, `doctor`, `help`) takes the library's keyword arguments as a
JSON body (`home`, `store` and `config` are the server's and cannot be set), including `key` /
`keys` where a key is needed, and returns its result. Errors are `{"error": "..."}`: `400` bad
body, `404`, `405`, `413` over 1 MiB, `422` from the library.

For agents, as MCP tools over stdio (`zjm_<op>` for each op above). **Agents: call `zjm_help`
first**. It returns a guide to the workflow, keys and egress, plus this instance's allowed
paths, egress, languages and lockers, and it changes nothing.

```sh
claude mcp add zjm -- zjm mcp          # add --config PATH after `zjm mcp` for another config
```

## Decision models

Ranking tries these models in order, moving on only when a request fails:

1. `perplexity/pplx-decider-v1.1-27b` (default)
2. `jev-1.14.0` (TypeSafe)
3. `openai/gpt-6-luna-decisions`
4. `microsoft/microsoft-decision-1`

Selection precedence is `--model` (or `jev.post(..., model=...)`), request `model`, `JEV_MODEL`,
then the default above. Jev goes straight to TypeSafe (`https://api.typesafe.ai/v1/systemone`,
key `TYPESAFE_API_KEY`) under TypeSafe's own name: `~typesafe/jev-latest` becomes the pinned
`jev-1.14.0`, `typesafe/jev-X.Y` becomes `jev-X.Y.0`, and a bare `jev-*` name is sent as is. Every
other model goes through OpenRouter's Decisions endpoint (`OPENROUTER_API_KEY`). A model whose key is
not set counts as a failed attempt. A selected model in the list starts at that position and falls through
its remaining models; a custom model gets one attempt. Each attempt has a 30-second socket
timeout, with at most four attempts; low scores do not trigger fallback.

`find` and `ask` accept `model=` in Python or JSON requests; the CLI accepts `--model` on both
commands, and the launcher passes `JEV_MODEL` into online containers. These select the ranking
model; config `llm` still selects the answer-writing model. Results include `returned_model`
from the provider response, also shown in human output; it is null when ranking is skipped or
the response supplies no model identity, never guessed from an alias.

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
| `allow` | list of strings | `[]`. Nothing is added to a locker until you add paths here |
| `deny` | list of strings | `[]`. Write real paths; symlinked parents are not resolved |
| `exclude` | list of strings (globs) | `[]`. Entries add to the built-in floor below and never remove from it |
| `egress` | `{"rank": bool, "answer": bool, "translate": bool}` | `{"rank": false, "answer": false, "translate": false}` |
| `embedding` | string, must start with `local/` | `local/potion-code-16m-v2` |
| `llm` | an OpenRouter model id string | `deepseek/deepseek-v4-flash` |
| `languages` | list of non-empty strings | `["English", "German", "Danish", "Norwegian", "Swedish"]` |
| `translate_model` | non-empty string | `upstage/solar-mini4` |

A relative `home`/`allow`/`deny` entry resolves against the config file's own directory; `~`
expands from `$HOME`. In the container, `home` is fixed to `/data` (the `zjm-data` volume) and
`allow` names `/sources/<name>` paths, the mount points the launcher creates from `ZJM_SOURCES`.
`embedding` must be one of the two models baked into the image:
`local/potion-code-16m-v2` or `local/potion-multilingual-128m`.

`llm` names the OpenRouter model `ask` answers with; every request sets
`"provider": {"data_collection": "deny"}`, so OpenRouter itself does not retain the prompt. Avoid
`:free` model variants as the answer model. OpenRouter's free tier usually logs prompts, and
`data_collection: deny` cannot change that, which is why the default is a paid, non-`:free` model.

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

For a first offline search after installation, put a text file in a host folder, set
`allow` to `["/sources/docs"]` in the generated config, then run:

```sh
mkdir -p "$HOME/docs"
printf 'The office opens at nine.\n' > "$HOME/docs/hours.txt"
zjm locker-create demo --plain
ZJM_SOURCES="$HOME/docs" zjm file-add demo /sources/docs
zjm find "office hours" -l demo --no-rank
```

The launcher treats `--config PATH` and `--key-file PATH` as host paths and mounts the selected
files read-only from a private host temporary directory, removed when Docker exits, so the
container can read private files without changing their original permissions; `--key-file -`
still reads stdin and cannot accompany `file-put`.
For `serve`, `--port` selects the container port and defaults the published host port;
`ZJM_PORT` overrides the host port only; the container bind host must remain `0.0.0.0`,
while the published host port stays loopback-only.

## Questions in other languages

An English question finds the Danish, German, Norwegian or Swedish text that answers it, even when
they share no words, and a question in any language finds text in the configured `languages`. zjm
translates the **question**, never the files, into each configured language and searches the
translations in addition to the original; the translations can only **add** candidate files (up to `limit` more), never
displace one the original question already found, and no language detection is needed.

Measured (`evals/recall.py`, 38 questions, potion-code index; prototype):

| approach | English question, foreign text, no shared words | everything else |
|---|---|---|
| no translation | 0/4 | 34/34 |
| local multilingual embeddings | 0 to 1/4 | 33 to 34/34 |
| translations fused into one ranking | 4/4 | 27/34 |
| **translations add files after the original's** | **4/4** | **34/34** |

- `egress.translate` (default `false`) follows the same rule as `egress.rank`/`egress.answer`:
  `translate=True` while it is off raises before any call; CLI `--no-translate` forces it off for
  one `find`/`ask`.
- `languages` (default `["English", "German", "Danish", "Norwegian", "Swedish"]`); an empty list
  turns translation off even with `egress.translate` on.
- `translate_model` (default `upstage/solar-mini4`): the OpenRouter model asked to translate.
- The translation request sends only the question. It never sends file text, paths or snippets. Ranking
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
- With a key (given to `locker_create`, or later to `locker_encrypt`), a locker is exactly one file,
  `<home>/lockers/<name>.age`: the whole locker (its files, zg index and manifest), tarred and
  encrypted. No other per-locker file exists on disk.
- Every request that touches an encrypted locker decrypts it into a private `/tmp` directory for
  that request only, re-encrypts after a write, and deletes both the plaintext and the key file
  before returning, even on error.
- The key travels only in files under `/tmp` and in request bodies. It never appears in argv, the
  environment, logs, error messages or results.
- `find` and `ask` can search plain and encrypted lockers together in one call; pass `keys` (a
  `{locker: key}` map, or `--key-file KEYS.json` on the CLI) for the encrypted ones only.

## Safety

- **Exclude floor**, always skipped, however `exclude` is set: directories `.git`, `node_modules`,
  `.venv`, `__pycache__`, `.zvec-grep`, `.zjm`, `.ssh`, `.gnupg`, `.aws`, `.kube`, `.docker`; files
  `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.kdbx`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`,
  `id_ed25519*`, `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `credentials*`.
- **The floor works on file names only.** Contents are not scanned for secrets: a key pasted into an
  ordinary document is indexed, and sent to OpenRouter with that document when sending is on.
- Symlinks inside a source are never copied. A file that git ignores and does not track is never copied; a tracked file is copied even if `.gitignore` matches it. Denying a single
  file inside an allowed repository's own git metadata is not supported; deny the whole directory.
- **Nothing leaves this machine unless the config allows it.** For a project set up with the skill,
  `"send": true` in `zjm-project.json` turns on ranking and answering. Direct use (the `zjm` CLI, the
  library, the HTTP API and the MCP server) follows `egress`: ranking (Jev via TypeSafe, other decision models via OpenRouter) needs
  `egress.rank`; answering (the OpenRouter model) needs `egress.answer`; translating the question
  (see [Questions in other languages](#questions-in-other-languages)) needs `egress.translate`. All three
  are off by default. The
  answer request has no `tools` key, so the model cannot act; it only ever returns text.
  `OPENROUTER_API_KEY` and `TYPESAFE_API_KEY` are sent only in the request's `Authorization` header. It never appears in argv, logs,
  errors, results or the messages sent to the model.
- `zjm serve` binds to `127.0.0.1`, `localhost` or `::1` only, and checks `Host`/`Origin` on every
  request (in the container, `0.0.0.0` is also accepted, since the launcher publishes only to
  the host's loopback interface).
- The app, not zjm, decides who may use which locker and which lockers a question may search.
- **The container is the only supported way to run zjm.** It runs read-only, as a non-root user,
  with no Linux capabilities, no swap, no core dumps, `--network none` unless `egress` is on, and
  persistent data confined to the `zjm-data` volume.
- **Encryption at rest is chosen per locker.** Each locker is created either with a key (encrypted) or with `--plain`. See [Locker keys](#locker-keys).

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
| Ranking | Jev via TypeSafe; fallback decision models via the OpenRouter Decisions API |
| Answer | an OpenRouter model (`deepseek/deepseek-v4-flash` by default) |
| Code | Python 3.10+, standard library only |

## Author

**Babak Bandpey**: [https://cocode.dk](https://cocode.dk) | [LinkedIn](https://linkedin.com/in/babakbandpey) | [GitHub](https://github.com/cocodedk)

## License

MIT | © 2026 [Cocode](https://cocode.dk) | Created by [Babak Bandpey](https://linkedin.com/in/babakbandpey)
