# Hardening: what a decrypted locker can leak

A security review of spec 14 and the sealed-locker sessions (spec 08) found six gaps in today's
code. Each is fixed here, in Python, before the engine switch. Specs 05, 06, 08 and 13 are
amended where they say otherwise.

## Changes

1. **No plaintext unless `/tmp` is in memory.** In the container (`ZJM_IN_CONTAINER=1`),
   `sealed._ensure_tmp_root` (the one seam that runs before a key file is written or a locker is
   decrypted) reads `/proc/self/mounts` and raises
   `ZjmError("refusing to decrypt: /tmp is not a tmpfs; run zjm with --tmpfs /tmp")` unless `/tmp`
   is mounted as `tmpfs`. Outside the container nothing changes. The mounts path is a module
   constant so a test can point it at a fixture.
2. **No core dumps.** `cli.main` sets `RLIMIT_CORE` to 0 (soft and hard) before it runs a
   command in the container, so a crash cannot write a decrypted locker to disk. Swap cannot be
   seen from inside a container; a deployment keeps `--memory-swap` equal to `--memory`, as
   `bin/zjm` does.
3. **Unpack as a stream.** `decrypt_into` no longer holds the whole decrypted archive in memory:
   `age -d` writes into a pipe that `tarfile.open(mode="r|")` extracts member by member, checking
   each member as it arrives with today's rules (files and folders only, no absolute path, no
   `..`). The runner takes an optional `consume` callback: when given, it receives the process's
   stdout as a binary file object while the process runs, and the runner returns
   `(code, None, stderr)`. A rejected member stops the stream, the process is killed, and the
   error is today's. Reads keep one copy of the plaintext (the session folder) instead of two.
4. **Every child process has a deadline.** The default runner kills a process that runs longer
   than `RUN_TIMEOUT_S = 600` seconds (a 2,000-file `file_add` took 13.4 s) and returns exit 124
   with `timed out after 600 s` on stderr. Callers turn that into their usual `ZjmError`.
5. **Children get only what they need.** `age`, `age-keygen`, `git` and `zg` run with an
   environment built from an allowlist (`PATH`, `HOME`, `LANG`, `LC_ALL`,
   `ZVEC_GREP_MODEL_CACHE`, each only when set) plus what the call adds (`ZVEC_GREP_HOME` for zg).
   API keys and tokens never reach them. One function builds it; nothing passes `os.environ` on.
6. **A cap on result sizes.** `find` and `ask` raise `ZjmError` when `limit` or `top_k` is over
   `MAX_LIMIT = 100`; the HTTP and MCP schemas state the same maximum from that constant.
7. **Locker names cannot collide with session files.** `check_name` also refuses names ending in
   `.key`, `.verify` or `.tmp`, the suffixes `/tmp/zjm` and the lockers folder use for keys,
   verification copies and seal files. Every operation checks the name, so such a locker can no
   longer be opened.

## Tests

All offline; the timeout test runs `sys.executable` with a sleep and a timeout patched to under a
second. Python, exactly **140** tests (131 today). Tests whose fake `age -d` returned bytes are
rewritten to feed `consume`, not added. New:
`test_names_with_session_suffixes_are_refused`, `test_limit_and_top_k_over_the_cap_are_refused`,
`test_runner_kills_a_process_past_its_timeout`, `test_children_get_only_allowlisted_env`,
`test_decrypt_refuses_when_tmp_is_not_tmpfs`, `test_decrypt_runs_when_tmp_is_tmpfs`,
`test_core_dumps_are_off_in_the_container`, `test_decrypt_streams_into_the_session`,
`test_unsafe_member_mid_stream_stops_the_decrypt`.

Spec 14's slice 2 ends at **142** Python tests instead of 133.

## Acceptance

1. The suite at exactly 140, CI's `verify` green.
2. By hand, once, with an image built from this branch and a throwaway volume (never `zjm-data`):
   an encrypted locker is created, filled with `file_put`, and found, through `bin/zjm`'s own
   flags; the same `find` with `/tmp` not a tmpfs is refused with the message above and leaves no
   `/tmp/zjm/<name>` or `<name>.key`; `ulimit -c` inside a `zjm` process reads 0; and a child's
   environment (`/proc/<pid>/environ` of a running `age` or `zg`) holds no `*_API_KEY`.

## Not in this spec

- Authentication for `zjm serve` (#43): its own spec.
- A size limit per locker: a product decision, not taken here.
- Pinning the Rust build image by digest: spec 14's slice 2, which writes that Dockerfile stage.
