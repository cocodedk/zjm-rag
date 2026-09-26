#!/bin/sh
# One-shot install of zjm-rag: curl -fsSL https://raw.githubusercontent.com/cocodedk/zjm-rag/main/install.sh | sh
# ZJM_INSTALL_DRY_RUN=1 prints each installing command as "+ <command>" instead of running it.
set -u
REPO=https://github.com/cocodedk/zjm-rag.git

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

echo "1/3 checking docker and python3"
have docker || die "docker is needed to build and run zjm's container"
have python3 || die "python3 is needed by the zjm launcher"

echo "2/3 building the zjm-rag image"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
context="$REPO"
[ -f "$script_dir/Dockerfile" ] && context="$script_dir"
run docker build -t zjm-rag:latest "$context" || die "docker build failed"

echo "3/3 installing the launcher"
bin_dir="$HOME/.local/bin"
run mkdir -p "$bin_dir" || die "cannot create $bin_dir"
if [ -f "$script_dir/bin/zjm" ]; then
  run cp "$script_dir/bin/zjm" "$bin_dir/zjm" || die "cannot copy the zjm launcher"
else
  have curl || die "curl is needed to fetch the zjm launcher"
  run curl -fsSL -o "$bin_dir/zjm" https://raw.githubusercontent.com/cocodedk/zjm-rag/main/bin/zjm \
    || die "cannot download the zjm launcher"
fi
run chmod +x "$bin_dir/zjm" || die "cannot make the zjm launcher executable"
if [ "${ZJM_INSTALL_DRY_RUN:-}" != 1 ]; then
  have zjm || echo "warning: $bin_dir is not on PATH; add it to use zjm"
fi
exit 0
