# 16 — zjm serve accepts named hosts (`--allow-host`)

A caller in another container on the same private Docker network reaches `zjm serve` by its service
name, for example `http://zjm:8765`, and so sends `Host: zjm:8765`. The Host check (spec 05) answers
403 to every name but loopback (#43). This spec lets the operator list the names to accept.

It adds no authentication. The Host check stops a browser being steered at the server (DNS
rebinding); any caller that reaches the port can send any Host, and a request without one is not
checked, as today. So a server opened this way belongs on a private network with no published port.
It is run on that network directly (for example as a compose service), not through the launcher,
which publishes only to the host's loopback.

## Change

- `zjm serve --allow-host NAME`, repeatable, default none.
  `make_server(host="127.0.0.1", port=8765, *, allow_hosts=(), config=None, runner=None, jev=None, llm=None)`.
- The Host check accepts the loopback names (`ALLOWED_HOSTS`) and every listed NAME, compared exactly
  with the header's host part (`_host_of` strips the port, as today). No case folding and no wildcards:
  a NAME such as `*` matches only a literal `*`.
- The Origin check is unchanged and stays loopback only. A server-to-server caller sends no Origin.
- With nothing listed, the server behaves exactly as today.
- The launcher (`bin/zjm`) passes `--allow-host` through untouched and still publishes to loopback only.
- README: the `zjm serve` Safety bullet says that `--allow-host NAME` adds names the Host check accepts,
  that such a server's port must not be published, and that the Host check is not authentication; the
  launcher's `serve` paragraph says how to run the image for a caller on a private network, that NAME
  is a bare host name matched exactly, and that the option has no use through the launcher.

## Tests

Exactly **148** (145 today). New file `tests/test_serve_hosts.py`, 3 tests:

1. `test_listed_host_is_accepted`: `make_server(port=0, allow_hosts=("zjm",))`; `GET /health` with
   `Host: zjm:8765` is 200, with `Host: other:8765` is 403, with `Origin: http://zjm` is 403.
2. `test_nothing_listed_is_unchanged`: `make_server(port=0)`; `Host: zjm:8765` is 403, a request
   with the default Host is 200.
3. `test_cli_passes_allow_host`: `zjm serve --allow-host zjm --allow-host db` calls `make_server`
   with `allow_hosts` holding `zjm` and `db` (`make_server` replaced by a fake that records its
   arguments and returns a server whose `serve_forever` raises `KeyboardInterrupt`).

## Acceptance

1. The suite at 148, green.
2. By hand, once: the image built from this branch runs as container `zjm-s16` on a user-defined
   Docker network with `serve --host 0.0.0.0 --port 8765 --allow-host zjm-s16`. From a second
   container on that network, `GET http://zjm-s16:8765/health` is 200 and the same request with
   `Host: other` is 403. The same container started without `--allow-host` answers 403.

## Not in this spec

A bearer token or any other authentication; the Origin list; a config-file key for the names.
