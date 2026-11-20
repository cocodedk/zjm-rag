# 20 — an unusable translation reply is asked for once more

Issue #60. Since spec 18 the translation reply is a nested object per language, about three times as long, and the
model sometimes breaks it. Measured 2026-11-20 on fits-api's 192-question eval, run twice on `363a824`: 3 of 384
questions came back with `translation reply not usable` and no translations, each on a different question that parsed
in the other run. The prompt before spec 18 had none in 384. Such a question is searched with its original wording
only, and that eval counts a run holding one as not valid.

## Behaviour

Only `zjm_rag/translate.py` changes in behaviour.

- `translate()` makes at most `MAX_ATTEMPTS` (2) calls, each `llm(model, messages, reasoning=False)` with the same
  `messages`. `MAX_ATTEMPTS` is a named constant beside `MAX_LEN`.
- It asks again in exactly the case that gives `"translation reply not usable"` today: the reply holds no JSON
  object, or the object holds no text that can be kept. The first usable reply is returned as `(texts, None)`.
- When every attempt is unusable it returns `([], "translation reply not usable")`.
- A call that raises is not asked again: it returns `([], "translation request failed")` at once, on the first
  attempt or the second.
- **Unchanged:** the signature, "never raises", the two error strings, the system message, the parsing and its
  filters, `MAX_LEN`, and every result shape. No new result field says that a retry happened.

### Words

- `translate.py`: the docstring of `translate()` says "Makes exactly one call"; it now says at most
  `MAX_ATTEMPTS`, and names this spec.
- `zjm_rag/search.py`, `_translate_query`'s docstring says "the one translation call per find/ask"; it becomes the
  one translation (asked for once more when the reply is not usable).
- `README.md`, "Questions in other languages": one line, that a reply zjm cannot use is asked for once more before
  `translate_error` is set.

## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 166 tests**: the 163 earlier ones, none changed, plus 3 in a
new `tests/test_translate_retry.py`. Should an earlier test fail because it counts calls on an unusable reply, the
builder reports it and does not edit it.

1. `test_unusable_reply_is_asked_again`: an `llm` that returns `not json` and then a usable nested reply gives the
   kept texts and no error. It was called exactly twice, and each recorded call carries the model given, the
   expected messages (the system message for the languages, then the query as the user message) and
   `reasoning=False`. The fake records a copy of the messages at each call, so a change between attempts would show.
2. `test_every_attempt_unusable`: an `llm` that always returns a reply with nothing to keep (once as non-JSON text,
   once as an object of unusable values) gives `([], "translation reply not usable")` after exactly
   `translate.MAX_ATTEMPTS` calls, and `MAX_ATTEMPTS` is 2. A reply that makes the parsing raise (a reply that
   is not a string) and one that has braces but is not JSON are asked again the same way, with the same result.
3. `test_failed_request_is_not_asked_again`: an `llm` that raises gives `([], "translation request failed")` after
   exactly one call. One that returns `not json` and then raises gives the same error after exactly two calls.
   Every recorded call in these scenarios carries the model given, the expected messages and `reasoning=False`.

## Not the gate

The suite uses fake replies. Issue #60 is done when fits-api's eval, run twice against an image built from this
change, has no question with `translate_error`. This build does not run it. No live run is made here either: at
under 1 % of replies the retry cannot be shown cheaply.

## Decisions

- runner (2026-11-20): one retry, two attempts in all. At 3 in 384 a second attempt leaves about one 192-question
  run in a hundred with a failure; fits-api asked for "once or twice".
- runner (2026-11-20): a failed request is not asked again. `llm.post` waits up to 120 s, and a second wait would
  double a search that is already failing; the measured failures were all unusable replies.
- runner (2026-11-20): the same messages are sent again; the reply differs because the model samples.

## Out of scope

- The time the translation call takes (issue #58's time condition, which stays open).
- The system message and the parsing.
- A retry count in the result, or a config key for the number of attempts.
- Retrying Jev or the answer model.
