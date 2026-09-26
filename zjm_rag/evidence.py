"""Evidence: turn zg hits into full chunks, read inside the locker's session (spec 09).

Candidates are the first `limit` distinct hit paths, in zg order, that are keys of the locker's
manifest. Every hit on a candidate is kept, whatever its rank; hits on any other path are ignored
and that file is never read. Each candidate's passages are its hit ranges, widened and merged.
`ask` additionally keeps small candidates whole. All reads happen here, while the locker's session
(and for an encrypted locker, its decrypted /tmp copy) is still open; nothing here re-opens a file
once the caller's session has closed.
"""
import array

WIDEN = 0
JEV_CHARS = 12000
ASK_CHARS = 200000


def select_candidates(hits, manifest_files, limit):
    """(ordered candidate paths, {path: [hits]}): the first `limit` distinct hit paths that are
    manifest keys, each carrying every hit on it, in zg order."""
    order, by_path = [], {}
    for hit in hits:
        path = hit["path"]
        if path not in manifest_files:
            continue
        if path in by_path:
            by_path[path].append(hit)
        elif len(order) < limit:
            order.append(path)
            by_path[path] = [hit]
    return order, by_path


def _widen_clamp(hit, n_lines):
    """(start, end) widened by WIDEN and clamped to the file, or None if it starts past EOF."""
    start = max(1, hit["start"] - WIDEN)
    end = min(n_lines, hit["end"] + WIDEN)
    return None if start > n_lines else (start, end)


def _line_offsets(text):
    """Start offset of each 1-based line in `text`, split on "\\n" only (len == its line count).
    Kept as offsets into `text`, in a packed `array` of native ints rather than a Python list of
    line strings (or even a list of int objects): a text file with many short lines would
    otherwise force one Python object per line just to extract a couple of small passages."""
    offsets = array.array("q", (0,))
    pos = text.find("\n")
    while pos != -1:
        offsets.append(pos + 1)
        pos = text.find("\n", pos + 1)
    return offsets


def _slice_lines(text, offsets, start, end):
    """`text`'s lines `start`..`end` (1-based, inclusive) - what "\\n".join(lines[start-1:end])
    would give if `text` had been split on "\\n" into `lines`."""
    begin = offsets[start - 1]
    stop = offsets[end] - 1 if end < len(offsets) else len(text)
    return text[begin:stop]


def build_passages(hits, text, offsets):
    """Merged passages for one file's hits, ordered by the best (lowest) rank merged into each."""
    n_lines = len(offsets)
    ranges = []
    for hit in hits:
        widened = _widen_clamp(hit, n_lines)
        if widened is not None:
            ranges.append((widened[0], widened[1], hit["rank"]))
    ranges.sort(key=lambda r: (r[0], r[1]))
    merged = []
    for start, end, rank in ranges:
        if merged and start <= merged[-1][1] + 1:
            ps, pe, prank = merged[-1]
            merged[-1] = (ps, max(pe, end), min(prank, rank))
        else:
            merged.append((start, end, rank))
    merged.sort(key=lambda r: r[2])
    return [{"start": s, "end": e, "text": _slice_lines(text, offsets, s, e)} for s, e, _rank in merged]


def _whole_text(path, text):
    """The candidate's full text, kept only when both size gates in the spec allow it."""
    if len(text) > ASK_CHARS:
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    return text if size <= 4 * ASK_CHARS else None


def read_candidates(hits, manifest_files, corpus_dir, limit, *, want_text):
    """{path: {"passages": [...], "whole": str|None}} for each candidate, read once here."""
    order, by_path = select_candidates(hits, manifest_files, limit)
    records = {}
    for path in order:
        full = corpus_dir / path
        with open(full, encoding="utf-8", errors="replace", newline="") as f:
            text = f.read()
        offsets = _line_offsets(text)
        records[path] = {"passages": build_passages(by_path[path], text, offsets),
                          "whole": _whole_text(full, text) if want_text else None}
    return records


def jev_snippets(passages, jev_chars=None):
    """Passages rendered as "lines a-b:\\ntext" strings for the Jev payload, capped at `jev_chars`
    total; the first is always sent (cut to fit), later ones stop before the cap would be crossed."""
    jev_chars = JEV_CHARS if jev_chars is None else jev_chars
    out, total = [], 0
    for i, p in enumerate(passages):
        block = f"lines {p['start']}-{p['end']}:\n{p['text']}"
        if i == 0:
            block = block[:jev_chars]
        elif total + len(block) > jev_chars:
            break
        out.append(block)
        total += len(block)
    return out


def build_ask_context(accepted, per_locker, top_k, ask_chars=None):
    """(context string, files list) for `ask`'s prompt: whole text when kept and it fits, else
    passages, while the shared budget lasts; the last block added is cut to the remainder."""
    budget = ASK_CHARS if ask_chars is None else ask_chars
    parts, files = [], []
    for hit in accepted[:top_k]:
        if budget <= 0:
            break
        rec = per_locker[hit["locker"]][hit["path"]]
        label = f"{hit['locker']}/{hit['path']}"
        contributed = False
        whole = rec.get("whole")
        whole_block = f"=== {label} ===\n{whole}" if whole is not None else None
        if whole_block is not None and len(whole_block) <= budget:
            parts.append(whole_block)
            budget -= len(whole_block)
            contributed = True
        else:
            for p in rec["passages"]:
                if budget <= 0:
                    break
                header = f"=== {label}:{p['start']}-{p['end']} ===\n"
                full_block = header + p["text"]
                block = full_block[:budget] if len(full_block) > budget else full_block
                budget -= len(block)
                # A block cut down to (at most) its own header contributed no real file text, so
                # it is dropped rather than left in the prompt as a dangling, content-free header.
                if len(block) > len(header):
                    parts.append(block)
                    contributed = True
        if contributed:
            files.append(label)
    return "\n\n".join(parts), files
