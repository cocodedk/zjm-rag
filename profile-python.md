# Profile: a stdlib Python package, tested with unittest

The lean loop reads the first indented line under each of the three headings below.

## suite_command

    python3 -m unittest discover -s tests -q

The suite runs in a sandbox with an empty home and no network. Tests must not call zg, Jev
(OpenRouter) or any LLM for real: every external call goes through an injectable runner and the
tests pass fakes.

## build_command

    python3 -m unittest discover -s tests -q

There is no build step beyond the suite.

## artifact

    README.md

How to install and call it.
