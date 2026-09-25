#!/bin/sh
# One-shot install of zjm-rag: curl -fsSL https://raw.githubusercontent.com/cocodedk/zjm-rag/main/install.sh | sh
# ZJM_INSTALL_DRY_RUN=1 prints each installing command as "+ <command>" instead of running it.
set -u
REPO=git+https://github.com/cocodedk/zjm-rag

die() {
  echo "zjm install: $*" >&2
  exit 1
}

run() {
  if [ "${ZJM_INSTALL_DRY_RUN:-}" = 1 ]; then
    echo "+ $*"
  else
    "$@"
  fi
}

have() {
  command -v "$1" >/dev/null 2>&1
}

echo "1/4 checking python3 >= 3.10"
have python3 || die "python3 3.10 or newer is needed"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "python3 3.10 or newer is needed"

echo "2/4 checking zg"
if ! have zg; then
  have npm || die "zg is missing and installing it needs Node/npm (https://nodejs.org)"
  run npm install -g @zvec/zvec-grep || die "npm install -g @zvec/zvec-grep failed"
  if [ "${ZJM_INSTALL_DRY_RUN:-}" != 1 ]; then
    have zg || die "zg was installed but is not on PATH; add npm's global bin directory (npm prefix -g)/bin to PATH"
  fi
fi

echo "3/4 installing zjm-rag"
if have uv; then
  run uv tool install --force "$REPO" || die "uv tool install failed"
elif have pipx; then
  run pipx install --force "$REPO" || die "pipx install failed"
else
  run python3 -m pip install --user "$REPO" || die "pip install failed"
fi

echo "4/4 running zjm doctor"
if [ "${ZJM_INSTALL_DRY_RUN:-}" != 1 ]; then
  have zjm || die "zjm was installed but is not on PATH; add the installer's bin directory (e.g. ~/.local/bin) to PATH"
  have zg || die "zg was installed but is not on PATH; add its install directory (e.g. ~/.local/bin or npm prefix -g/bin) to PATH"
fi
# A broken install stops above; doctor's remaining checks (store, claude,
# OPENROUTER_API_KEY) are expected to fail on a fresh install, so its exit code is ignored.
run zjm doctor || true
[ -n "${OPENROUTER_API_KEY:-}" ] || echo "warning: OPENROUTER_API_KEY is not set; Jev needs it to rank files"
have claude || echo "warning: claude is not on PATH; zjm ask needs it to answer"
exit 0
