---
name: zjm-rag
description: Search a project's documents by meaning with zjm-rag (zg finds, Jev ranks), or set it up in a new project. Use to find every document that states a rule, to locate where something is written, or to answer a question from the documents with citations.
---

# zjm-rag

Repo: https://github.com/cocodedk/zjm-rag (its README is the full guide). Runs only in its container: the repo's
`install.sh` builds it and `~/.local/bin/zjm`; ranking and answers need `OPENROUTER_API_KEY` in the shell.
`scripts/zjm-project` (in this skill's folder) indexes and searches; `scripts/mirror.py` makes the redacted copies
it indexes. Run them; don't read them.

## Set up a project once

1. Pick a locker name unique to the project (lowercase `a-z 0-9 . _ -`, up to 64 characters): all projects share
   one store (the Docker volume `zjm-data`). Reindex refuses a name already built from other folders; `ZJM_FORCE=1`
   replaces it, so check `zjm locker-list` first.
2. Choose the folders: documents and memory only (e.g. `docs governance memory`). A whole code tree makes the index
   fail and every search come back empty; search code with grep. Two folders with the same name are refused.
3. Nothing leaves the machine unless you set `ZJM_SEND=1`: then ranking and `ask` send the text of files to
   OpenRouter, so with it set, index only what may leave. Paths in text
   files are redacted (`/home/<user>/`, `/Users/<user>/`, `/root/` → `~/`, `/tmp/...` → `<temp>`; PDFs and other
   binary files go as they are), git-ignored files and zjm's floor (`.env*`, keys,
   credentials) are never copied, but anything else in a git-visible file is. Keep scratch folders git-ignored.
4. Index from a checkout that stays (the main folder after a pull), not a temporary worktree.
5. Add `.zvec-grep/` to `.gitignore`: zg leaves that folder where it runs directly. zjm itself writes nothing in
   the project.
6. `scripts/zjm-project reindex <locker> <folder>...`, then record the locker name and the exact command in the
   project's own instructions so the next session uses the same ones.

Choosing files: name the folders to index; inside them, leave files and folders out by name with
`ZJM_EXCLUDE="*.pdf,drafts/"` (a trailing `/` means a folder). Put it on every reindex, or the next one indexes them.

## Refresh

The locker is a copy: until reindexed it misses new text and still returns removed text. Reindex after every
change to an indexed folder (each commit, merge or pull) and before the next search, one reindex at a time.
`find` and `ask` print `STALE:` when a folder changed since the last reindex; reindex, then search again.

## Search

- `scripts/zjm-project find <locker> "<question>" [--limit 30] [--min-score 0.3]`: without `ZJM_SEND=1` it lists
  zg's candidates unranked; with it, Jev ranks them and rejects the weak ones. Write a full
  question as a person would ask it ("who approves a change before it runs?"); a bare phrase is often rejected.
- Jev scores relevance, not truth: read every accepted hit in the file on disk before acting on it.
- No hit is not proof of absence. For "every document that says X": ask two or three phrasings, raise `--limit`,
  lower `--min-score`, and grep the exact words too.
- `ZJM_SEND=1 scripts/zjm-project ask <locker> "<question>"` answers from the accepted files with citations;
  check each cited passage.
- Hits name `<locker>/<folder>/<path>`: the same path under the indexed folder.
- Each ranked search and each answer is a paid OpenRouter call: search with intent, not in loops.
- When a rule changes: search its old wording, fix every accepted hit, reindex, search again until none are left.

## When it fails

Every search empty: run `zjm doctor` and check the file count in `zjm locker-list`; a locker with code in it, or
none at all, is the usual cause. Non-English documents: reindex with `ZJM_MULTILINGUAL=1` every time.
