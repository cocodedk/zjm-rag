"""Per-locker zg queries and cross-locker merging for `find`/`ask` (specs 06, 08, 09 and 10):
runs the original and (when there are translations) the translated zg query inside each locker's
sealed session, then interleaves the "query" and "translation" candidates across lockers, the
query's always first. Split out of search.py to keep it under 200 lines.
"""
from . import evidence
from . import lockers as lockers_mod
from . import sealed
from . import zg
from .errors import ZjmError


def _run_zg_query(argv, corpus, ldir, runner):
    code, out, err = runner(argv, cwd=str(corpus), env=lockers_mod.zg_env(ldir), input=None)
    if code != 0:
        raise ZjmError(f"zg query failed: {err.strip()}")
    return zg.parse(out)


def gather(cfg, names, keys, query, file_types, limit, translations, runner, *, want_text):
    """Query each locker in turn, inside its own sealed session; {locker: {path: record}}. Each
    record's "via" is "query" or "translation" (spec 10)."""
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
                hits = _run_zg_query(zg.query_argv(query, file_types), corpus, ldir, runner)
                translated_hits = None
                if translations:
                    argv = zg.query_argv_translations(translations, file_types)
                    translated_hits = _run_zg_query(argv, corpus, ldir, runner)
                built = evidence.read_candidates(hits, manifest["files"], corpus, limit, want_text=want_text,
                                                 translated_hits=translated_hits)
                for path, rec in built.items():
                    entry = manifest["files"].get(path)
                    record[path] = {"passages": rec["passages"], "whole": rec["whole"], "via": rec["via"],
                                    "source": entry["source"] if entry else None,
                                    "mtime": (corpus / path).stat().st_mtime}
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
    groups = {"query": {}, "translation": {}}
    for name, recs in per_locker.items():
        for via in groups:
            groups[via][name] = [(p, r["passages"]) for p, r in recs.items() if r["via"] == via]
    merged = []
    for via in ("query", "translation"):
        merged += [(n, p, s, via) for n, p, s in _round_robin(groups[via], limit)]
    return merged
