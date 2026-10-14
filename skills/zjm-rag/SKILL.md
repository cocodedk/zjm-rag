---
name: zjm-rag
description: Search a project's documents by meaning with zjm-rag (zg finds, Jev ranks), or set it up in a new project. Use to find every document that states a rule, to locate where something is written, or to answer a question from the documents with citations.
---

# zjm-rag

Repo: https://github.com/cocodedk/zjm-rag (its README is the full guide). Runs only in its container: the repo's
`install.sh` builds it, puts `zjm` on `~/.local/bin` and installs this skill. `scripts/zjm-project` (in this
skill's folder) indexes and searches from the project root; `scripts/mirror.py` makes the redacted copies it
indexes. Run them; don't read them.

## Set up a project once

Write `zjm-project.json` at the project root and commit it, so every session uses the same settings:

```json
{"locker": "myproj", "folders": ["docs", "memory"], "exclude": ["*.pdf", "drafts/"],
 "send": false, "llm": "deepseek/deepseek-v4-flash", "multilingual": false}
```

- `locker`: a name unique to the project (starts with `a-z` or `0-9`, then `a-z 0-9 . _ -`, up to 64 characters). All projects share one
  store (the Docker volume `zjm-data`); reindex refuses a name built from other folders (`ZJM_FORCE=1` replaces
  it), so check `zjm locker-list` first.
- `folders`: documents and memory only, relative to the root. A whole code tree makes the index fail and every
  search come back empty; search code with grep. Two folders with the same name are refused.
- `exclude`: files and folders (trailing `/`) left out by name.
- `send`: off unless the project's owner decides otherwise. Off, nothing leaves the machine: searches list zg's
  candidates unranked and `ask` is refused. On, ranking and `ask` send the text of matching files to OpenRouter
  (`OPENROUTER_API_KEY` in the shell), so index only what may leave. `llm` picks the answer model among those
  OpenRouter offers.
- `multilingual`: true for documents not in English.

Either way, paths in text files are redacted (`/home/<user>/`, `/Users/<user>/`, `/root/` → `~/`, `/tmp/...` →
`<temp>`; PDFs and other binary files go as they are), and untracked git-ignored files, files named like secrets (zjm's floor:
`.env*`, `*.key`, `credentials*`, ...) and anything reached through a symlink are never copied. File contents are
not scanned: a secret pasted into an ordinary document is indexed, and sent if `send` is on. Keep scratch folders git-ignored and untracked: a tracked file stays eligible even when `.gitignore` matches it. Index from
a checkout that stays (the main folder after a pull), not a temporary worktree. Add `.zvec-grep/` to `.gitignore`:
zg leaves that folder where it runs directly; zjm itself writes nothing in the project. Then run
`scripts/zjm-project reindex`.

## Refresh

The locker is a copy: until reindexed it misses new text and still returns removed text. Reindex after every
change to an indexed folder (each commit, merge or pull) and before the next search, one reindex at a time.
`find` and `ask` print `STALE:` when a folder changed since the last reindex; reindex, then search again.

## Search

- `scripts/zjm-project find "<question>" [--limit 30] [--min-score 0.3]`. Write a full question as a person would
  ask it ("who approves a change before it runs?"); a bare phrase is often rejected by ranking.
- Jev scores relevance, not truth: read every hit in the file on disk before acting on it.
- No hit is not proof of absence. For "every document that says X": ask two or three phrasings, raise `--limit`,
  lower `--min-score`, and grep the exact words too.
- `scripts/zjm-project ask "<question>"` (with `send` on) answers from the accepted files with citations; check
  each cited passage.
- Hits name `<locker>/<folder>/<path>`: the same path under the indexed folder.
- With `send` on, each search and each answer is a paid call: search with intent, not in loops.
- When a rule changes: search its old wording, fix every accepted hit, reindex, search again until none are left.

## When it fails

Every search empty: run `zjm doctor` and check the file count in `zjm locker-list`; a locker with code in it, or
none at all, is the usual cause.
