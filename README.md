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

The library (`zjm_rag`) is in. The `zjm` command line with `--json`, a local HTTP JSON API and an
MCP server with a one-line installer are being built from the specs in [docs/lean/](docs/lean/),
one pull request per spec.

## Install

    pip install .

Needs the `zg` binary on `PATH`, `OPENROUTER_API_KEY` for ranking, and `claude` for answers.

## Use

```python
import os, zjm_rag

zjm_rag.index([os.path.expanduser("~/projects/agent-linters")])        # copies into zjm_rag.DEFAULT_STORE and indexes
hits = zjm_rag.find("which linter checks CSS files")   # {"accepted": [...], "rejected": [...], ...}
reply = zjm_rag.ask("which linter checks CSS files", answer_language="da")
print(reply["answer"], reply["files"])
```

- `index(sources, multilingual=True)` for non-English queries; changing the model needs `rebuild=True`.
- `find(query, min_score=0.5, sort="score"|"zg"|"mtime"|"path", rank=False, file_types=["py"])`.
- Every call takes `store=`, plus injectable `runner=` and `jev=` for tests.
- Errors raise `zjm_rag.ZjmError`.

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
zjm_rag/            library: index, find (zg), rank (Jev), ask (claude)
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
