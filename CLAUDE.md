# zjm-rag

Find the file that holds the answer: zg (zvec-grep) finds candidate files, Jev ranks them, an LLM answers.

- Gate profile: [profile-python.md](profile-python.md). Suite: `python3 -m unittest discover -s tests -q`.
- Stdlib-only Python 3.10+. No runtime dependency besides the external `zg` binary.
- Tests never make live zg, Jev or LLM calls; inject fakes. Each spec states its expected test count.
- Specs for the lean loop live in `docs/lean/`.
