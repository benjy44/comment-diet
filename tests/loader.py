"""Loads the plugin's linter by path — it ships as a script, not an installed package."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "comment-diet" / "scripts" / "comment_diet.py"

_spec = importlib.util.spec_from_file_location("comment_diet", SCRIPT)
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)


def findings(source, ext, conf=None):
    conf = conf or cd.DEFAULTS
    cfg = cd.lang_for("sample" + ext)
    lines = source.splitlines()
    out = []
    for run in cd.file_runs(lines, source, conf, cfg):
        out.extend(cd.run_findings(run, lines, conf, cfg))
    return out


def blocked(source, ext, conf=None):
    return [f.message for f in findings(source, ext, conf) if f.level == "block"]


def warned(source, ext, conf=None):
    return [f.message for f in findings(source, ext, conf) if f.level == "warn"]
