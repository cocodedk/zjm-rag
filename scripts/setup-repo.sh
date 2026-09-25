#!/bin/sh
# scripts/setup-repo.sh
# Applies repository merge settings and branch protection to main. Run once, after
# ci.yml is on main and one CI run has completed there (ci.yml runs on push to main,
# so the merge that lands it registers the `verify` check). Requires gh authenticated
# with admin rights on the repo.
#
# Tuned for the lean loop (graph-loop), which opens one PR at a time from `lean/<feature>`
# and waits while that branch is unmerged:
#   - delete-branch-on-merge is ON, so a merged `lean/<feature>` branch is gone and the
#     loop is not blocked by it;
#   - "strict" (branch must be up to date with main) is OFF: GitHub's "Update branch"
#     button adds a merge commit to `lean/<feature>` that the loop does not have, and its
#     next plain push to that branch would then be rejected as non-fast-forward.
set -eu

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
OWNER=$(gh repo view --json owner -q .owner.login)
VISIBILITY=$(gh repo view --json visibility -q .visibility)

echo
echo "=== Repository setup: $REPO ($VISIBILITY) ==="
echo

# ── Merge strategy (works on every plan) ─────────────────────────────────────────
gh repo edit "$REPO" \
    --delete-branch-on-merge \
    --enable-squash-merge \
    --enable-rebase-merge \
    --enable-merge-commit=false
echo "✓ Merge strategy: squash + rebase only, auto-delete head branches"

# ── Branch protection (solo maintainer: PR required, 0 approvals) ────────────────
# "contexts" must match the fan-in job name in ci.yml exactly. After the first run:
#   gh api "/repos/$REPO/commits/$(git rev-parse origin/main)/check-runs" -q ".check_runs[].name"
PROTECTION_PAYLOAD='{
  "required_status_checks": {
    "strict": false,
    "contexts": ["verify"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "block_creations": false
}'

set +e
PROT_RESP=$(printf '%s' "$PROTECTION_PAYLOAD" | gh api \
    --method PUT \
    "/repos/$REPO/branches/$DEFAULT_BRANCH/protection" \
    --input - 2>&1)
PROT_RC=$?
set -e

if [ "$PROT_RC" -eq 0 ]; then
    echo "✓ Branch protection set on $DEFAULT_BRANCH"
elif printf '%s' "$PROT_RESP" | grep -q "Upgrade to GitHub Pro"; then
    cat <<'EOF'
⚠  Branch protection skipped: private repo on GitHub Free. The local pre-push hook is
   then the only guard against force-push and deletion of the default branch — make sure
   scripts/install-hooks.sh has been run in every clone. Upgrading to GitHub Pro and
   re-running this script enables server-side protection; moving to a free org does not.
EOF
else
    echo "✗ Branch protection failed:" >&2
    printf '%s\n' "$PROT_RESP" >&2
    exit 1
fi

# ── CODEOWNERS ──────────────────────────────────────────────────────────────────
# Auto-requests the owner's review on every PR. Does not block merging, because
# required_approving_review_count is 0.
mkdir -p .github
printf '# All files — repo owner auto-requested for review.\n* @%s\n' "$OWNER" \
    > .github/CODEOWNERS
echo "✓ .github/CODEOWNERS written"

echo
echo "Active on $DEFAULT_BRANCH:"
if [ "$PROT_RC" -eq 0 ]; then
    echo "  - CI job 'verify' must pass before merge"
    echo "  - PR required, 0 approvals (self-merge OK)"
    echo "  - No force pushes, no branch deletion"
    echo "  - Admin may bypass in an emergency"
else
    echo "  - No server-side protection; the pre-push hook is the only guard"
fi
echo
