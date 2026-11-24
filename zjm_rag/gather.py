"""Per-locker engine queries and cross-locker merging for `find`/`ask` (specs 06, 08, 09, 10 and 14):
makes one engine call per locker, carrying the question and any translations, inside its
sealed session, then interleaves the "query" and "translation" candidates across lockers, the
query's always first. Split out of search.py to keep it under 200 lines.
"""
from . import engine, evidence
from . import lockers as lockers_mod
from . import sealed
from .errors import ZjmError


def _run_query(embedding, ldir, file_types, query, translations, runner, name, file_names):
    """{"query": [hit], "translation": [hit]} from one engine call. A locker with no engine.idx, or an
    index the engine refuses as another version, is read-only until a file operation rebuilds it."""
    index = ldir / engine.INDEX_FILE
    older = ZjmError(f"locker {name} has an index from an older version; re-run a file operation")
    if not index.exists():
        raise older
    code, out, err = runner(engine.query_argv(embedding, index, file_types), cwd=str(ldir),
                            env=engine.child_env(), input=engine.query_input(query, translations, file_names))
    engine.raise_if_timed_out(code, "engine query")
    if code == engine.FORMAT_EXIT:
        raise older
    if code != 0:
        raise ZjmError(f"engine query failed: {err.strip()}")
    return engine.parse(out)


def gather(cfg, names, keys, query, file_types, limit, translations, runner, *, want_text, file_names=None):
    """Query each locker in turn, inside its own sealed session; {locker: {path: record}}. Each
    record's "via" is "query" or "translation" (spec 10). `file_names` narrows the search to those
    locker files or folders (spec 19); `None` searches every file."""
    keys = keys or {}
    for name in names:
        kind = sealed.locker_kind(cfg, name)
        if kind is None:
            raise ZjmError(f"no locker {name}")
        if kind == "age" and not keys.get(name):
            raise ZjmError(f"locker {name} needs its key")
        if kind == "plain" and keys.get(name):
            raise ZjmError(f"locker {name} is not encrypted")
    per_locker = {}
    for name in names:
        key = keys.get(name)
        with sealed.open_locker(cfg, name, key, write=False, runner=runner) as ldir:
            manifest = lockers_mod.read_manifest(ldir)
            record = {}
            if manifest["files"]:
                if not manifest["indexed"]:
                    raise ZjmError(f"locker {name} is not indexed; re-run a file operation")
                corpus = ldir / "corpus"
                found = _run_query(manifest["embedding"], ldir, file_types, query, translations, runner, name,
                                   file_names)
                hits, translated_hits = found["query"], (found["translation"] if translations else None)
                record = evidence.read_candidates(hits, manifest["files"], corpus, limit, want_text=want_text,
                                                  translated_hits=translated_hits)
                for path, rec in record.items():
                    entry = manifest["files"].get(path)
                    rec["source"] = entry["source"] if entry else None
                    rec["mtime"] = (corpus / path).stat().st_mtime
            per_locker[name] = record
    return per_locker


def _round_robin(lists, limit):
    """[(locker, path, passages)] merged round-robin over lockers, deduped, cut to `limit`."""
    seen, merged, i = set(), [], 0
    while len(merged) < limit and any(i < len(v) for v in lists.values()):
        for name, items in lists.items():
            if i < len(items):
                path, passages = items[i]
                if (name, path) not in seen:
                    seen.add((name, path))
                    merged.append((name, path, passages))
                    if len(merged) >= limit:
                        break
        i += 1
    return merged


def interleave(per_locker, limit):
    """[(locker, path, passages, via)], the spec 06 interleave run twice (spec 10): first over the
    "query" candidates, cut to `limit`, then over the "translation" ones, cut to `limit`. The
    second block always follows the first."""
    merged = []
    for via in ("query", "translation"):
        lists = {name: [(p, r["passages"]) for p, r in recs.items() if r["via"] == via]
                 for name, recs in per_locker.items()}
        merged += [(n, p, s, via) for n, p, s in _round_robin(lists, limit)]
    return merged
