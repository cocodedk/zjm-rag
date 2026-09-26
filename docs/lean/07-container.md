# 07 — zjm runs only in a container

## Goal

zjm runs only inside a hardened container:
- Persistent data lives in a Docker volume.
- Source folders are mounted read-only.
- With egress off, the container has no network at all.

The host only sees a launcher script. This spec builds on specs 05 and 06; where they disagree,
this one wins.

## Behaviour

### Image: `Dockerfile` at the repo root

- Base `python:3.12-slim`. It adds `git`, `ca-certificates`, Node.js 22 with npm, a pinned
  `@zvec/zvec-grep@0.2.2`, a pinned `@anthropic-ai/claude-code`, and zjm installed from the
  build context with `pip install .`.
- Both local models (`local/potion-code-16m-v2` and `local/potion-multilingual-128m`) are
  downloaded at build time into `/opt/zjm/models`. A throwaway `zg index` over a one-file folder
  per model does the download. Then set `ENV ZVEC_GREP_MODEL_CACHE=/opt/zjm/models`.
- `ENV ZJM_IN_CONTAINER=1 ZJM_CONFIG=/etc/zjm/config.json HOME=/tmp/home`.
- A non-root user with uid `10001`. `/data` is created and owned by that user with mode `0700`,
  and declared as `VOLUME /data`.
- `ENTRYPOINT ["zjm"]`.

### zjm refuses to run outside the container

- `cli.main` exits `1` with `zjm: runs only in its container; use the zjm launcher` on stderr
  when `ZJM_IN_CONTAINER` is not `1`. It checks this before parsing arguments.
- The library functions are not guarded, so tests can still call them. The guard stops
  accidents, not an owner who deliberately bypasses it.
- In the container, `zjm serve --host 0.0.0.0` is allowed. `make_server` accepts `0.0.0.0` only
  when `ZJM_IN_CONTAINER=1`, and loopback always. The spec 05 Host/Origin/Content-Type checks are
  unchanged.
- Config `embedding` values, and `locker_create`'s embedding, must be one of the two baked
  models when `ZJM_IN_CONTAINER=1`. Anything else raises `ZjmError`.

### Launcher: `bin/zjm`

The launcher is POSIX `sh`. It is installed on the host as `zjm` and runs `docker run` with:
- `--rm -i`, `--user 10001:10001`, `--read-only`
- `--tmpfs /tmp:rw,size=256m,mode=1777`
- `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--memory=2g`, `--pids-limit=256`
- `-v zjm-data:/data`, plus the host config mounted as `-v <host config>:/etc/zjm/config.json:ro`
  - The host config is `$ZJM_HOST_CONFIG`, else `$XDG_CONFIG_HOME/zjm/config.json`, else
    `$HOME/.config/zjm/config.json`.
  - If the file is missing, the launcher stops with exit `1` and a message.
- One `-v <dir>:/sources/<basename>:ro` for each directory in the colon-separated
  `ZJM_SOURCES`. A basename clash, or a directory that doesn't exist, stops with exit `1`.
- `--network none` when both `egress.rank` and `egress.answer` in the host config are
  `false` or missing; otherwise the default network. It reads egress with
  `python3 -c` and `json` on the host.
- `-e OPENROUTER_API_KEY` when `egress.rank` is on, and `-e ANTHROPIC_API_KEY` when
  `egress.answer` is on. It passes the variable names only, never the values in argv.
- When the first argument is `serve`, it also adds `-p 127.0.0.1:${ZJM_PORT:-8765}:8765`, and the
  command becomes `serve --host 0.0.0.0 --port 8765`. `serve` with `--network none` stops with
  exit `1`: "HTTP needs egress on, or use MCP".
- The image is `${ZJM_IMAGE:-zjm-rag:latest}`. All remaining arguments go to the container
  unchanged.
- `ZJM_LAUNCH_DRY_RUN=1` prints the full `docker` argv on one line, prefixed with `+ `, instead
  of running it.

`install.sh` now does three things, and no longer installs zjm natively:
1. Checks for `docker` and `python3`.
2. Builds the image (`docker build -t zjm-rag:latest <repo or git URL>`).
3. Copies `bin/zjm` to `~/.local/bin/zjm`.

The existing dry-run variable and the step-per-line output stay.

### Shared lock for reads (spec 06 gap)

`find`, `ask`, `locker_list` and `file_list` take `lockers.lock(cfg, exclusive=False)` for their
whole run, as spec 06 requires.

### README

- **Install:** build the image and put the launcher on `PATH`.
- **Config:** `allow` names `/sources/<name>` paths, and `home` is `/data`.
- **Sources:** set `ZJM_SOURCES` to the host folders to mount.
- **MCP:** `claude mcp add zjm -- zjm mcp`.
- **HTTP:** `zjm serve` (needs egress on).
- **Version:** bump `fallback_version` to `0.7.0`.

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 56 tests**: the 49 earlier ones plus
the 7 below.
- Existing CLI tests set `ZJM_IN_CONTAINER=1` in their environment.
- The install tests are updated to the new steps.
- No test runs docker. The launcher tests run `sh bin/zjm` with `ZJM_LAUNCH_DRY_RUN=1`, a stub
  `PATH` and a temp config.

- `tests/test_container.py`:
  1. `test_cli_refuses_outside_container`: without `ZJM_IN_CONTAINER`, `main([...])` exits `1`
     with the message.
  2. `test_bind_all_only_in_container`: `make_server(host="0.0.0.0")` raises without the
     variable and succeeds (port `0`) with it.
  3. `test_unbaked_embedding_refused_in_container`.
  4. `test_find_takes_shared_lock`: while an exclusive lock is held in a thread, `find` waits.
     It is proven by ordering, not by timing.
- `tests/test_launcher.py`:
  5. `test_offline_argv`: egress off gives `--network none`, the read-only and cap-drop flags,
     the `zjm-data` volume, the config mount `:ro`, and one `/sources/<name>:ro` per
     `ZJM_SOURCES` entry. No `-e` is passed.
  6. `test_online_serve_argv`: with egress on, `serve` publishes `127.0.0.1:8765:8765`, passes
     `-e OPENROUTER_API_KEY` and `-e ANTHROPIC_API_KEY`, and has no `--network none`.
  7. `test_serve_offline_refused_and_bad_sources`: `serve` with egress off exits `1`, and a
     missing source directory exits `1`.

## Out of scope

- Podman or rootless setup instructions.
- Publishing the image to a registry.
- Claude subscription login inside the container (use `ANTHROPIC_API_KEY`).
- Compose files.
