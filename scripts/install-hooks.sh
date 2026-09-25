#!/bin/sh
# Install zjm-rag's git hooks for this checkout.
#
#   ./scripts/install-hooks.sh
#
# Sets core.hooksPath to .githooks, which is per-checkout config and is not committed —
# every fresh clone needs to run this once. `git push --no-verify` / `git commit
# --no-verify` bypass the hooks by design; they stop accidents, not malice.
set -eu
cd "$(git rev-parse --show-toplevel)"
chmod +x .githooks/pre-commit .githooks/commit-msg .githooks/pre-push
git config core.hooksPath .githooks
echo "Hooks installed — pre-commit, commit-msg, and pre-push (owner-locked) are active."
