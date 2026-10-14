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

echo "1/4 checking docker and python3"
have docker || die "docker is needed to build and run zjm's container"
have python3 || die "python3 is needed by the zjm launcher"

echo "2/4 building the zjm-rag image"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
context="$REPO"
[ -f "$script_dir/Dockerfile" ] && context="$script_dir"
run docker build -t zjm-rag:latest "$context" || die "docker build failed"

echo "3/4 installing the launcher"
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
config_path="${ZJM_HOST_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/zjm/config.json}"
if [ "${ZJM_INSTALL_DRY_RUN:-}" = 1 ]; then
  echo "+ create default config if absent: $config_path"
else
  python3 - "$config_path" <<'PYCONFIG' || die "cannot create default config"
import json
import os
import sys
from pathlib import Path
path = Path(sys.argv[1]).expanduser()
path.parent.mkdir(parents=True, exist_ok=True)
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    pass
else:
    with os.fdopen(fd, "w") as f:
        json.dump({"home": "/data", "allow": [], "egress": {"rank": False, "answer": False}}, f)
        f.write("\n")
PYCONFIG
fi
echo "4/4 installing the Claude Code skill"
skill_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/zjm-rag"
run rm -rf "$skill_dir" || die "cannot replace $skill_dir"
if [ -d "$script_dir/skills/zjm-rag" ]; then
  run mkdir -p "$(dirname "$skill_dir")" || die "cannot create the skills folder"
  run cp -R "$script_dir/skills/zjm-rag" "$skill_dir" || die "cannot copy the skill"
else
  have curl || die "curl is needed to fetch the skill"
  run mkdir -p "$skill_dir/scripts" || die "cannot create $skill_dir"
  for f in SKILL.md scripts/zjm-project scripts/mirror.py; do
    run curl -fsSL -o "$skill_dir/$f" "https://raw.githubusercontent.com/cocodedk/zjm-rag/main/skills/zjm-rag/$f" \
      || die "cannot download the skill"
  done
  run chmod +x "$skill_dir/scripts/zjm-project" || die "cannot make the skill's script executable"
fi
if [ "${ZJM_INSTALL_DRY_RUN:-}" != 1 ]; then
  have zjm || echo "warning: $bin_dir is not on PATH; add it to use zjm"
fi
exit 0
