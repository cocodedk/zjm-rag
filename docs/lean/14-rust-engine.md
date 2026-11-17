# zjm-engine: a Rust search engine in place of zg

zjm-rag stops calling zg and searches with its own engine, `zjm-engine`, a Rust binary built from
`engine/`. The aim is speed and memory (#39, #40, #49); search quality must not drop, and the
recall eval below is the gate for that. Where any earlier spec describes zg (its argv,
`ZG_HITS`, the two zg calls of a translated search, `zghome` and `.zvec-grep` in a locker, the
doctor's `zg` check, the image), this one wins.

## Why: measured on b18370b (zg 0.3.0)

| | zg 0.3.0 | Prototype (memory-mapped model) |
|---|---|---|
| Start to the first embedding | 4.55 s model load, 5.5 s per call | 2.6 ms |
| Private memory per process | 1.45 GB (an f32 copy of the 489 MiB table, a 500k-entry tokenizer) | 10 MiB; the model's pages are shared through the page cache |
| A find with translation | about 11 s of zg in a 13-14 s search (two zg calls) | not measured end to end |

The prototype's vectors equal model2vec's (cosine 1.0). Embedding text is not free: 1.16 s per
2,000 chunks of about 1,100 characters, 11.6 s per 20,000. So vectors are computed when a file is
written and stored in the locker, and a search embeds only the question.

## The memory rule

A locker's decrypted text, index and vectors exist only for the request that uses them:

- `zjm-engine` runs as one process per call and exits when the call returns. There is no daemon.
  What it held is freed by the exit, not zeroed.
- The model files are read-only and memory-mapped, so their pages are shared by every process and
  hold no locker data.
- The decrypted session folder (`/tmp/zjm/<name>`, spec 08) is removed when the request ends, as today.

## The engine

`engine/` is a Cargo crate with a committed `Cargo.lock` and a pinned toolchain
(`rust-toolchain.toml`). The Python package stays stdlib-only and calls the binary through the
injectable runner, as it calls zg today.

### Models

The same two model2vec models, at the revisions zg 0.3.0 pins:

| Name in the manifest | Hugging Face repo and revision | `model.safetensors` sha256 | `tokenizer.json` sha256 |
|---|---|---|---|
| `local/potion-multilingual-128m` | `minishlab/potion-multilingual-128M` @ `73908c3438cf03b6a01bcb9611d62b23d0726f08` | `14b5eb39cb4ce5666da8ad1f3dc6be4346e9b2d601c073302fa0a31bf7943397` | `19f1909063da3cfe3bd83a782381f040dccea475f4816de11116444a73e1b6a1` |
| `local/potion-code-16m-v2` | `minishlab/potion-code-16M-v2` @ `e9d2a44ca6a05ac6685f3b23709ea57eb7352d5b` | `75cf7a6c2171b230ad19b1e7d8e0b1aee86da5a02af8e7cacedd9921d227623c` | `107bbdcbad4bff1d299b7a4c3a2fb17c52890688b7dd0e4c9deab79d3c4f3d45` |

Each lives in `/opt/zjm/models/<model>/` (`<model>` is the name without `local/`) with
`model.safetensors` and `tokenizer.json`. The multilingual model's tokenizer is a 500,353-entry
Unigram, too slow to load per call, so its folder also has `vocab/`, prebuilt for memory-mapping:
an FST of token to id, a score array, and a tokenizer skeleton that keeps only the normalizer and
pre-tokenizer. The code model's tokenizer is a 63,457-entry WordPiece and is loaded as it is.

A text's vector is zg 0.3.0's: tokenize, keep the first 1,024 tokens, drop the unknown token, take
the mean of their rows in f64, normalize, store as f32. A text with no known token gets the zero
vector, as in zg 0.3.0, so its cosine with any question is 0.

### Commands

- `zjm-engine vocab TOKENIZER_JSON OUT_DIR`: writes `vocab/` for a Unigram tokenizer. Run at image
  build only, for the multilingual model.
- `zjm-engine index --model DIR CORPUS INDEX`: splits every file under `CORPUS` into chunks, embeds
  each chunk, and writes `INDEX`. It always builds the index from scratch. It skips a file that is empty or
  whitespace only, has a NUL byte in its first 8 KiB, or is over 16 MiB; text that is not valid
  UTF-8 is read with replacement characters. These rules differ from zg 0.3.0's per-extension
  rules on purpose: spec 05's copy rules already decide what enters a locker, and one plain rule
  is easier to test than zg's table; a corpus
  with no chunk still writes a valid, empty index. Which files enter a locker is
  still decided by the copy rules of spec 05; the engine adds no path rules.
- `zjm-engine query --model DIR --limit N [--type T]... INDEX -- QUESTION [TRANSLATION]...`:
  prints one JSON object, `{"query": [hit...], "translation": [hit...]}` (`translation` is empty
  when no translation is given), each hit
  `{"path", "start", "end", "rank"}` with 1-based lines and ranks. It never prints file text.

Exit 0 on success; 1 with one line on stderr on any error; 3 when `INDEX` was written by another
format version or for another model.

### Chunks

The engine's rule, with zg 0.3.0's sizes: a markdown file splits at its headings (outside code fences), one chunk per
section. A section, or any other file, longer than 3,600 characters splits into pieces of at most
3,600 characters with 540 overlapping, cut at a line end when one falls in the last 30% of the
piece. Each chunk records its path and first and last line. Whitespace-only text makes no chunk.

### Index

One file, `engine.idx` in the locker's folder, beside `locker.json`, so it is sealed with the
locker and encrypted at rest. Its first line is a JSON header with the format version, the model
name and the chunk count; then the chunk table, each chunk's vector, and each chunk's token-id
counts for the keyword leg.

### Ranking

Every chunk is scored twice for each query text: cosine with its vector, and BM25 (k1 1.2, b 0.75)
over the model's own token ids, so the keyword leg needs no second tokenizer and covers every
language the model reads. The two rankings fuse by reciprocal rank (k = 60). The `query` group is
the question's fused ranking; the `translation` group fuses the translations' rankings the same way. Each group keeps its best `N` chunks; a file may
appear more than once. `--type` takes zg 0.3.0's whole type table (`zg --help file-types`), copied
into the engine: extensions (`markdown` is `.md`, `.mdx`; `python` is `.py`) and file names
(`dockerfile` is `Dockerfile`, `makefile` is `Makefile`). A value matches as in zg 0.3.0: a type name in any
case (`python`, `Python`), an extension with or without its dot (`py`, `.py`), or a file name from
the table (`Dockerfile`). Anything else is refused with an error that names it.

Only markdown splits at headings. zg cuts structured code (python, rust, go, c, cpp, java,
javascript, typescript, jsx, tsx, vue, svelte) at symbols; the engine cuts it as text. That is a
deliberate trade: symbol parsing would add a parser per language, and the lockers this is built for
hold documents. The eval's code rows are the check that code search still finds its file.

## Python changes

1. `zjm_rag/zg.py` becomes `zjm_rag/engine.py`: argv builders, `HITS = 40`, a JSON parser that
   raises `ZjmError("engine returned bad output")` on anything else, and the model folder for a
   manifest's `embedding`.
2. `lockers.run_index` runs `zjm-engine index`; on failure `indexed` stays false, as today. It
   removes `zghome` and `corpus/.zvec-grep` before it calls the engine, so they are never indexed. `zg_env` goes, and `locker_create`
   no longer makes `zghome`.
3. `gather` makes one engine call per locker carrying the question and its translations (#41); a
   hit's `via` is its group.
4. The order stays as `gather` has it today: a locker with no files gives zero hits without
   running the engine; one with files and `indexed` false gets spec 06's "not indexed" error. One
   with files that says `indexed` true but has no `engine.idx`, or whose index the engine refuses with exit 3:
   `find` and `ask` raise
   `ZjmError("locker NAME has an index from an older version; re-run a file operation")` and stay
   read-only. The next `file_add`, `file_put` or `file_remove` builds the new index.
5. `zjm doctor` checks `zjm-engine` on `PATH` instead of zg: `checks["engine"]` replaces
   `checks["zg"]`, and `ok` requires it where it required zg. The image installs the binary as
   `/usr/local/bin/zjm-engine`.
   `config.check_embedding_baked` keeps spec 07's `ZJM_IN_CONTAINER=1` guard and its model list.

## Image and repo

- `Dockerfile`: the zg stage and the two seed steps go, and so do `ZVEC_GREP_MODEL_CACHE` and the
  zg libraries. A build stage on a pinned `rust` image runs `cargo build --release --locked`,
  fetches the four model files at the pinned revisions, checks each sha256 (a mismatch fails the
  build), and runs `zjm-engine vocab` for the multilingual model. The runtime image takes the binary and
  `/opt/zjm/models`, readable by uid 10001.
- CI: a new `engine` job runs `cargo test --locked` in `engine/` and is added to `verify`'s
  `needs`, so the required check covers it.
- Every file outside `docs/lean/` and `evals/corpus/` that names zg as zjm-rag's search tool names
  `zjm-engine` instead: docs, website, skill, issue template, `pyproject.toml`, CI comments,
  docstrings, help text and the op descriptions in `zjm_rag/ops.py`. `rg zg` over those files finds only `zg_rank` and `sort="zg"` afterwards. The result field `zg_rank` and `sort="zg"` keep their names, since
  callers use them; they now carry the engine's rank.
- `evals/recall.py` imports `engine` instead of `zg`, its `TOOLS` holds `zjm-engine` instead of
  `zg`, and its rank column reads the engine's rank.

## Tests

All offline. Cargo tests build a tiny synthetic model (a few-row table and a small Unigram
`tokenizer.json`) in a temporary folder; the real model is never needed.

Rust, exactly **16** tests:
`markdown_splits_at_headings`, `long_section_splits_with_overlap_at_a_line_end`,
`other_files_use_the_same_splitter`, `skipped_files_make_no_chunk_and_empty_index_is_valid`,
`pooling_matches_a_hand_computed_mean`, `unknown_tokens_dropped_and_1024_cap`,
`prebuilt_vocab_matches_the_stock_tokenizer`, `index_round_trip`,
`other_version_or_model_exits_3`, `exact_token_wins_through_the_keyword_leg`,
`paraphrase_wins_through_the_vector_leg`, `fusion_order_matches_a_worked_example`,
`translations_form_their_own_group`, `limit_caps_each_group`, `type_matches_name_in_any_case_extension_and_file_name`,
`unknown_type_is_refused`.

Python: exactly **133** tests (131 today). Tests of zg argv, output, `zghome` or the zg cache are
rewritten for the engine, not added. `test_incompatible_index_is_rebuilt_on_write` is deleted:
every write builds the index from scratch. New:
`test_find_makes_one_engine_call_with_translations`, `test_write_removes_zg_leftovers`,
`test_bad_engine_output_raises`.

## Slices

Two pull requests, in order:

1. The crate: `engine/`, its 16 Rust tests and the `engine` CI job. Python is untouched and stays
   at 131 tests.
2. The switch: the Python changes, the image, the docs and the recall eval, ending at 133 Python
   tests and the acceptance below.

## Acceptance

1. Both suites at the counts above, and CI's `verify` green with the `engine` job in it.
2. Recall: `python3 evals/recall.py` in the new image, without and with `--multilingual`, is no
   worse than zg 0.3.0 on b18370b in every column. zg's numbers:

   | Run (b18370b, no `--jev`) | cand | evid | acc | ctx |
   |---|---|---|---|---|
   | default model (`potion-code-16m-v2`) | 33/38 | 30/38 | 33/38 | 33/38 |
   | `--multilingual` | 34/38 | 30/38 | 34/38 | 34/38 |

   The bar is the ALL row of each run; the per-kind rows may move by one question either way.

3. By hand, once, through the `zjm` launcher (uid 10001, read-only root, no network, 2 GB), on a
   2,010-file multilingual locker, rank and translate off: report a `find`'s time and
   `zjm-engine`'s private memory (`Private_Clean` + `Private_Dirty` in `/proc/<pid>/smaps_rollup`,
   sampled every 5 ms while it runs, the highest sample); the find takes under 1 s
   (zg: 5.9 s) and the engine's private memory stays under 100 MiB (zg: 1.45 GB). After the call
   no `zjm-engine` process and no `/tmp/zjm/<name>` folder remain.
4. A locker made by the b18370b image: `find` gives the older-version error, a `file_add` then
   succeeds, `find` returns hits, and `zghome` and `corpus/.zvec-grep` are gone.

## Not in this spec

- Decrypting inside the engine with no session folder. Python reads passages and file times from
  the session folder, so this would move evidence reading into the engine; it saves at most the
  0.2-0.4 s that `age -d` and the untar take at 2,010 files (#47). The session folder already
  leaves memory when the request ends.
- Reusing the vectors of unchanged files on a write (a full re-index costs about 1.2 s per 2,000
  chunks).
- Zeroing freed memory.
- A per-file filter for `find` (#44): the engine makes it a small follow-up spec.
- Batch `file_put` (#42), `zjm serve` hosts and auth (#43), returning zg order when ranking
  fails (#45), the default decision model (#46) and the read lock and session paths (#48): each
  gets its own spec.
