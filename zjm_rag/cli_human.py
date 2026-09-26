"""Human (non-JSON) CLI output, split out of cli.py to keep it under 200 lines."""


def _where(hit):
    """`<locker>/<path>[:<start>-<end>]`, using the first passage when there is one; a hit found
    only through a translation (spec 10) gets a trailing "  (translation)"."""
    label = f"{hit['locker']}/{hit['path']}"
    passages = hit.get("passages") or []
    where = f"{label}:{passages[0]['start']}-{passages[0]['end']}" if passages else label
    return f"{where}  (translation)" if hit.get("via") == "translation" else where


def human(cmd, r):
    if cmd == "locker-create":
        return [f"created {r['name']} ({r['embedding']})"]
    if cmd == "locker-list":
        lines = []
        for l in r["lockers"]:
            tag = "encrypted" if l["encrypted"] else f"{l['files']} files"
            lines.append(f"{l['name']}  {tag}  {l['bytes']} bytes")
        return lines
    if cmd == "locker-drop":
        return [f"dropped {r['name']} ({r['files']} files)"]
    if cmd == "locker-encrypt":
        return [f"encrypted {r['name']}"]
    if cmd == "file-add":
        lines = [f"added {n}" for n in r["added"]] + [f"replaced {n}" for n in r["replaced"]]
        if r["excluded"]:
            lines.append(f"excluded {r['excluded']} entries")
        return lines
    if cmd == "file-put":
        return [f"added {n}" for n in r["added"]] + [f"replaced {n}" for n in r["replaced"]]
    if cmd == "file-remove":
        return [f"removed {n}" for n in r["removed"]]
    if cmd == "file-list":
        return [f"{f['name']}  {f['size']} bytes" for f in r["files"]]
    if cmd == "find":
        lines = [f"{'-' if h['score'] is None else format(h['score'], '.2f')}  {_where(h)}" for h in r["accepted"]]
        return lines + ([f"rejected: {len(r['rejected'])} below {r['min_score']}"] if r["rejected"] else [])
    if cmd == "ask":
        return [r["answer"] or r["reason"], "", f"sources: {', '.join(r['files'])}"]
    lines = [f"{'ok' if ok else 'missing'} {name}" for name, ok in r["checks"].items()]
    lines.append(f"config {r['config'] or '(built-in defaults)'}")
    lines.append(f"home {r['home']}")
    lines.append(f"egress rank={r['egress']['rank']} answer={r['egress']['answer']} "
                f"translate={r['egress']['translate']}")
    lines.append(f"lockers {r['lockers']}")
    return lines
