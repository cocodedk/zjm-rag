"""Human (non-JSON) CLI output, split out of cli.py to keep it under 200 lines."""


def human(cmd, r):
    if cmd == "locker-create":
        return [f"created {r['name']} ({r['embedding']})"]
    if cmd == "locker-list":
        return [f"{l['name']}  {l['files']} files  {l['bytes']} bytes  ({l['embedding']})" for l in r["lockers"]]
    if cmd == "locker-drop":
        return [f"dropped {r['name']} ({r['files']} files)"]
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
        lines = [f"{'-' if h['score'] is None else format(h['score'], '.2f')}  {h['locker']}/{h['path']}"
                 for h in r["accepted"]]
        return lines + ([f"rejected: {len(r['rejected'])} below {r['min_score']}"] if r["rejected"] else [])
    if cmd == "ask":
        return [r["answer"] or r["reason"], "", f"sources: {', '.join(r['files'])}"]
    lines = [f"{'ok' if ok else 'missing'} {name}" for name, ok in r["checks"].items()]
    lines.append(f"config {r['config'] or '(built-in defaults)'}")
    lines.append(f"home {r['home']}")
    lines.append(f"egress rank={r['egress']['rank']} answer={r['egress']['answer']}")
    lines.append(f"lockers {r['lockers']}")
    return lines
