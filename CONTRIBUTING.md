# Contributing to zjm-rag

## Local setup

1. Clone the repo and `cd` into it.
2. Python 3.10 or newer. There is nothing to install for the tests: the package is stdlib-only.
3. To run it for real you also need [zg](https://www.npmjs.com/package/@zvec/zvec-grep)
   (`npm install -g @zvec/zvec-grep`), an `OPENROUTER_API_KEY` for Jev, and optionally the
   `claude` CLI for answers. See the README for what the current proof of concept expects.

## Install git hooks

```sh
./scripts/install-hooks.sh
```

This points `core.hooksPath` at `.githooks` for your checkout and activates:

- `pre-commit`: rejects an unfilled owner placeholder or a hardcoded home path in staged files,
  runs `sh -n` on staged shell files, `ruff check` (syntax errors and undefined names) on staged
  Python when `ruff` is on `PATH`, then the unittest suite.
- `commit-msg`: rejects a subject that is not a [Conventional Commit](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, ...).
- `pre-push`: refuses a push to any remote outside `github.com/cocodedk`, and a force-push or
  deletion of `main`.

Caveats:

- `core.hooksPath` is per-checkout config and is not committed. Every fresh clone needs to run
  the script once.
- `git commit --no-verify` and `git push --no-verify` bypass the hooks by design; they stop
  accidents, not deliberate bypasses.
- Pushes from CI or the GitHub web UI never run these hooks. Branch protection on `main` is the
  server-side guard (see below).

## Local git setup

Run once after cloning:

```sh
git config pull.rebase true          # rebase on pull instead of a merge commit
git config core.autocrlf input       # normalize CRLF to LF on commit (macOS/Linux)
git config push.autoSetupRemote true # git push without -u the first time
```

On Windows use `core.autocrlf true` instead of `input`.

## Build and test commands

There is no build step. The suite is the gate, locally and in CI:

```sh
python3 -m unittest discover -s tests -q
ruff check --select E9,F63,F7,F82 .    # what CI enforces: syntax errors, undefined names
```

CI (`.github/workflows/ci.yml`) runs the suite on Python 3.10 and 3.13 with an empty `HOME`, plus
the ruff check above. Its fan-in job `verify` is the one check `main` requires.

## Coding style

- **Stdlib only**, Python 3.10+. No runtime dependency besides the external `zg` binary.
- **Tests never call zg, Jev or an LLM for real** and never open a network connection. Every
  external call goes through an injectable `runner` or `jev` argument; tests pass fakes.
- Each spec in `docs/lean/` states the exact test count the suite must report. Keep it true.
- Keep files small and focused.

## Branches and the lean loop

Most features are built by an autonomous loop (graph-loop's lean loop) from the specs in
`docs/lean/`. It works on branches named `lean/<feature>`, opens one pull request per spec and
waits for it to be merged before starting the next. Its commits are made with `git commit-tree`,
so the commit hooks never run on them: **PR CI is the check on loop work.** Review and merge
those PRs promptly; an unmerged `lean/` branch blocks the loop. Head branches are deleted on
merge. Avoid GitHub's "Update branch" button on a `lean/` PR: it adds a commit the loop does not
have, and its next push to that branch is then rejected.

Human branches use kebab-case with a prefix matching the Conventional Commit type:

| Branch prefix | Commit type | Example |
|---|---|---|
| `feature/` | `feat:` | `feature/answer-cache` |
| `fix/` | `fix:` | `fix/empty-store-message` |
| `docs/` | `docs:` | `docs/mcp-example` |
| `chore/` | `chore:` | `chore/bump-actions` |
| `refactor/` | `refactor:` | `refactor/split-zg-parser` |
| `ci/` | `ci:` | `ci/add-python-3-14` |

## Why everything goes through a pull request

`main` is protected by `scripts/setup-repo.sh`: a pull request is required, the `verify` check
must pass, and force-pushes and deletion are refused. Approvals are set to 0, so the maintainer
can self-merge. `enforce_admins` is `false`, so an admin's direct push to `main` still succeeds
(with a notice); that is a deliberate way out of a jam, not an invitation. Use a branch and a PR.

## PR checklist

- [ ] `python3 -m unittest discover -s tests -q` passes with the count the spec states.
- [ ] No test makes a live zg, Jev or LLM call or opens a network connection.
- [ ] No new runtime dependency.
- [ ] README updated if behaviour visible to a user changed.
- [ ] Commit messages follow Conventional Commits.
