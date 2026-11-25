# 22 — find and ask take the caller's translations

Issue: #65 (fits-api's spec 32, slice 1b). fits-api is switching its policy search to zjm. It translates the
question itself, through each organisation's own AI provider, and logs that call, so its zjm runs with
`egress.translate` off. Today zjm searches translations only when it makes the translation call itself
(`_translate_query`, `zjm_rag/search.py`), so fits-api's translations cannot reach the engine.

## Behaviour

- `find(...)` and `ask(...)` (`zjm_rag/search.py`) take `translations=None`, a list of strings.
  - `None` keeps today's behaviour: zjm translates when `translate` and the config say so.
  - A list (an empty one included) is used as the translations, exactly where `_translate_query`'s output is used
    today: in the engine's stdin JSON and in the result's `translations`. zjm makes no translation call, so it needs no
    `egress.translate`, and `translate_error` is `None`.
- Each of these is refused with a `ZjmError`, right after `_check_names`, before the config is read or any call:
  - `translations` together with `translate=True`: `give translations or translate, not both`.
  - `translations` that is not a list of strings.
  - more than `MAX_TRANSLATIONS` (16) entries, a named constant beside `MAX_LIMIT`. The engine searches once per
    translation.
  - an entry that is empty, only whitespace, or longer than `translate.MAX_LEN` (500), the limit zjm puts on its own
    translations.
- Exposed where `names` is (spec 19):
  - the HTTP and MCP `find` and `ask` schemas (`ops._FIND_PROPS`), as `translations`, an array of strings;
  - the CLI `find` and `ask`, as `--translation T`, repeatable;
  - the README's `find` and `ask` lines, and its "Questions in other languages" section: one sentence, that a caller
    can send its own translations, and zjm then makes no translation call.
## Acceptance tests

`python3 -m unittest discover -s tests -q` runs **exactly 191 tests**: the 185 earlier ones, none changed, plus 6 in a
new `tests/test_caller_translations.py`, one per test below (the refusals as subtests of one). Should an earlier test
fail, the builder reports it and does not edit it.

1. **The same search.** With the fake runner, a `find` with `translate=True` whose fake `llm` returns the texts T, and a
   `find` with `translations=T` and `translate` unset, send the engine the same stdin JSON and return the same
   `accepted`, `rejected` and `translations`. The second never calls `llm`.
2. **No egress needed.** With `egress.translate` off, `find(translations=T)` succeeds and the engine gets T.
3. **Empty list.** `find(translations=[])` with `egress.translate` on makes no `llm` call and sends no translations.
4. **`ask`** passes `translations` the same way.
5. **Refusals.** Each case under "Behaviour" raises with its message, and neither the runner nor `llm` is called.
6. **Surfaces.** `ops.check("find", ...)` refuses a `translations` that is not an array of strings. The CLI's
   `find --translation a --translation b` sends `translations: ["a", "b"]`.

## Not the gate

fits-api's proof, a find given zjm's own translations returning what zjm's translating find returned, runs on its eval
after merge.

## Decisions

- runner (2026-11-24): `ask` takes it too, because its schema is built from `find`'s, and one code path is simpler than
  an exception.
- runner (2026-11-24): a cap of 16, twice the 8 that four languages give, so a caller cannot make one find run
  hundreds of searches.

## Out of scope

- Any change to how translations are searched, merged or cut.
- zjm's own translation call, its prompt and its retry.
