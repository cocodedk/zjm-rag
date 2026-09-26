"""doctor: report zg, claude, OPENROUTER_API_KEY and locker presence (spec 06)."""
import os
import shutil

from . import config as config_module
from . import lockers


def _locker_count(lockers_dir):
    if not lockers_dir.is_dir():
        return 0
    return sum(1 for p in lockers_dir.iterdir()
              if (p.is_file() and p.suffix == ".age") or (p.is_dir() and (p / "locker.json").exists()))


def doctor(*, config=None, runner=None, jev=None):
    """The checks `zjm doctor` and `GET /health` report, without calling any tool."""
    cfg = config_module.resolve(config)
    _, lockers_dir = lockers.home_dirs(cfg)
    n = _locker_count(lockers_dir)
    egress = cfg["egress"]
    checks = {"zg": bool(shutil.which("zg")), "age": bool(shutil.which("age")),
              "claude": bool(shutil.which(cfg["llm"][0])),
              "openrouter_key": bool(os.environ.get("OPENROUTER_API_KEY"))}
    ok = (checks["zg"] and checks["age"] and (checks["openrouter_key"] or not egress["rank"])
         and (checks["claude"] or not egress["answer"]))
    return {"ok": ok, "checks": checks, "config": cfg["path"], "home": cfg["home"], "egress": egress, "lockers": n}
