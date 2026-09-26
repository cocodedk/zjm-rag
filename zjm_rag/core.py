"""doctor: report zg, claude, OPENROUTER_API_KEY and locker presence (spec 06)."""
import os
import shutil

from . import config as config_module
from . import lockers


def doctor(*, config=None, runner=None, jev=None):
    """The checks `zjm doctor` and `GET /health` report, without calling any tool."""
    cfg = config_module.resolve(config)
    _, lockers_dir = lockers.home_dirs(cfg)
    n = sum(1 for d in lockers_dir.iterdir() if (d / "locker.json").exists()) if lockers_dir.is_dir() else 0
    egress = cfg["egress"]
    checks = {"zg": bool(shutil.which("zg")), "claude": bool(shutil.which(cfg["llm"][0])),
              "openrouter_key": bool(os.environ.get("OPENROUTER_API_KEY"))}
    ok = checks["zg"] and (checks["openrouter_key"] or not egress["rank"]) and (checks["claude"] or not egress["answer"])
    return {"ok": ok, "checks": checks, "config": cfg["path"], "home": cfg["home"], "egress": egress, "lockers": n}
