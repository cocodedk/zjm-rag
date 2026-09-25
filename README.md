# zjm-rag

Find the file that holds the answer: zg (zvec-grep) finds candidate
files, Jev (OpenRouter Decisions API) ranks them, an LLM answers. Stdlib-only Python 3.10+.

## Install

    pip install .

Needs the `zg` binary on `PATH`, `OPENROUTER_API_KEY` for ranking, and `claude` for answers.

## Use

```python
import zjm_rag

zjm_rag.index(["/home/me/projects/agent-linters"])          # copies into zjm_rag.DEFAULT_STORE and indexes
hits = zjm_rag.find("which linter checks CSS files")   # {"accepted": [...], "rejected": [...], ...}
reply = zjm_rag.ask("which linter checks CSS files", answer_language="da")
print(reply["answer"], reply["files"])
```

- `index(sources, multilingual=True)` for non-English queries; changing the model needs `rebuild=True`.
- `find(query, min_score=0.5, sort="score"|"zg"|"mtime"|"path", rank=False, file_types=["py"])`.
- Every call takes `store=`, plus injectable `runner=` and `jev=` for tests.
- Errors raise `zjm_rag.ZjmError`.
