"""A suite is a folder with assignments.json and maker_prompt.json (benchmark/v1 is the first)."""
import json
from pathlib import Path

from . import ROOT


def load(suite_dir):
    d = Path(suite_dir)
    if not d.is_absolute():
        d = ROOT / d
    assignments = json.loads((d / "assignments.json").read_text())["assignments"]
    maker = json.loads((d / "maker_prompt.json").read_text())
    return {"dir": d, "name": d.name, "assignments": assignments, "maker": maker}


def prompt_for(suite, assignment):
    return suite["maker"]["prompt"].replace("{assignment}", assignment["prompt_text"])
