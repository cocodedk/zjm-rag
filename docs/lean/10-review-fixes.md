# Review fixes

- Reject file-add sources rooted in excluded directories or reached through excluded ancestors,
  including symlink aliases; apply the existing floor and custom directory patterns.
- Remove each matched file once when removal prefixes overlap, preserving manifest consistency.
- Use Python argv lists in the host launcher; support spaces, explicit host config/key files,
  stdin keys, and serve options without changing the container restrictions.
- Stage selected config/key files in a private temporary directory for Docker's lifetime, bind
  them read-only, preserve original permissions, and remove staged copies after Docker exits.
- Require the container server bind host to remain 0.0.0.0; publish only on host loopback.
- Render expected CLI preparation failures through the same human/JSON error boundary.
- Create a mode-0600 deny-by-default config on installation only if absent; document an offline
  first search and valid HTTP JSON requests.

Acceptance: exactly **79 tests**, including exclusion bypasses, overlapping removals, malformed
CLI inputs, paths with spaces, private mounted files and cleanup, serve options, and preserving
existing config during installation; all external services use fakes.
