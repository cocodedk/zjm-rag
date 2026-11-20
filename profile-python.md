# Profile: a stdlib Python package tested with unittest, and its Rust engine tested with cargo

The lean loop reads the first indented line under each of the three headings below.

## suite_command

    python3 -m unittest discover -s tests -q && cd engine && cargo test --locked --offline -q

The suite runs in a sandbox with an empty home and no network. The Python tests must not call zjm-engine, Jev
(OpenRouter) or any LLM for real: every external call goes through an injectable runner and the
tests pass fakes. The engine's own tests (`engine/tests`) run after them with `cargo test --offline`, from
the crates the host's cargo has already fetched. Measured 2026-11-20: the gate does run them (a deliberately
failing engine test turned it RED).

## build_command

    python3 -m unittest discover -s tests -q && cd engine && cargo test --locked --offline -q

There is no build step beyond the suite: building the engine is part of its tests.

## artifact

    README.md

How to install and call it.
