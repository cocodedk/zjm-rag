# zjm-rag

Find the file that holds the answer. zjm-rag searches your folders with
[zg](https://www.npmjs.com/package/@zvec/zvec-grep) (zvec-grep), has Jev judge which of the
candidate files actually contain the answer, and lets an LLM answer from those files only, citing
their paths.

## Website

- [English](https://rag.cocode.dk/)
- [فارسی (Persian)](https://rag.cocode.dk/fa/)

## How it works

1. **zg finds.** A hybrid search over a local zg index returns candidate files with short
   snippets, in zg's rank order.
2. **Jev ranks.** One request to Jev (the OpenRouter Decisions API) asks, per file, whether it
   contains the information needed to answer the question. Each file gets a probability; files at
   or above a threshold (default `0.5`) are accepted, the rest are reported as rejected, never
   dropped silently.
3. **An LLM answers.** The top accepted files go to an LLM command-line client (`claude` by
   default) with the instruction to answer from those files only and cite the path. When no file
   passes the threshold, no LLM is called.

## Status

This repo is at the proof-of-concept stage: `rag.py` is a single script. The library
(`zjm_rag`), the `zjm` command line with `--json`, a local HTTP JSON API and an MCP server with a
one-line installer are being built from the specs in [docs/lean/](docs/lean/), one pull request
per spec.

## Usage (proof of concept)

Requirements:

- Python 3.10+
- `zg` on `PATH` (`npm install -g @zvec/zvec-grep`)
- the jev-decisions script, by default at `~/.claude/skills/jev-decisions/scripts/jev.py`
  (override with `RAG_JEV`)
- the `claude` CLI, for answers

The script expects an already-indexed corpus. By default that is `/tmp/zjm-rag/corpus` (override
with `RAG_CORPUS`, or move the whole scratch area with `RAG_SCRATCH`), with zg's home at
`/tmp/zjm-rag/zghome`. Copy the folders you want searched into the corpus and index it there:

```sh
mkdir -p /tmp/zjm-rag/corpus && cp -r ~/projects/some-repo /tmp/zjm-rag/corpus/
cd /tmp/zjm-rag/corpus && ZVEC_GREP_HOME=/tmp/zjm-rag/zghome zg index . --mode direct --hidden
```

Then ask:

```sh
python3 rag.py "which linter checks CSS files"             # rank, then answer from the top 3
python3 rag.py --no-answer "which linter checks CSS files" # rank only
```

It prints each candidate file with Jev's probability, best first, then the answer. The proof of
concept has no threshold yet: it answers from the three best-ranked files.

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
rag.py              proof of concept: find (zg), rank (Jev), answer (claude)
tests/              unittest suite and the zg output fixture
docs/lean/          specs for the library, CLI, HTTP API, MCP server and installer
profile-python.md   gate profile the lean loop builds against
website/            the project site (rag.cocode.dk)
```

| Part | Technology |
|---|---|
| Search | zg (zvec-grep), local hybrid index |
| Ranking | Jev via the OpenRouter Decisions API |
| Answer | an LLM CLI (`claude` by default) |
| Code | Python 3.10+, standard library only |

## Author

**Babak Bandpey** — [https://cocode.dk](https://cocode.dk) | [LinkedIn](https://linkedin.com/in/babakbandpey) | [GitHub](https://github.com/cocodedk)

## License

MIT | © 2026 [Cocode](https://cocode.dk) | Created by [Babak Bandpey](https://linkedin.com/in/babakbandpey)
