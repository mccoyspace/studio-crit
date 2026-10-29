"""Making a judgement card: start one from the template, check it, and run the positions page for it.
Calibration (the crit and the comparison) is in calibrate.py; cards/README.md walks through the steps."""
import json, re, shutil, subprocess, sys
from pathlib import Path

from . import ROOT, card as cardlib

CARDS = ROOT / "cards"


def new(name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        sys.exit("use a short name in lowercase with hyphens, e.g. jane-doe")
    d = CARDS / name
    if d.exists():
        sys.exit(f"{d.relative_to(ROOT)} already exists")
    shutil.copytree(CARDS / "_template", d)
    for f in ("judgement_card.draft.json", "positions.json"):
        p = d / f
        p.write_text(p.read_text().replace("TODO-your-name", name))
    print(f"Started {d.relative_to(ROOT)}/. Next, react to the rules from the books: tools/bench.py positions {d.relative_to(ROOT)}")
    print("Then follow cards/README.md: interview, draft the card, check it, judge the calibration crit, calibrate.")
    return 0


def check(target):
    c = cardlib.load(target)
    problems, notes = cardlib.check(c["card"])
    todos = len(re.findall(r"TODO", json.dumps(c["card"])))
    print(f"{c['path']} (version {c['version']}): {'OK' if not problems else f'{len(problems)} problems'}"
          + (f", {todos} TODOs left" if todos else ""))
    for p in problems:
        print("  problem:", p)
    for n in notes:
        print("  note:", n)
    if not problems:
        print("  headline values, in rank order:", ", ".join(cardlib.ranked_values(c["card"])))
    return 1 if problems else 0


def positions(target, port):
    d = Path(cardlib.load(target)["path"]).parent
    store = d / "positions" / "reactions.json"
    return subprocess.call([sys.executable, "-I", str(ROOT / "tools" / "serve_positions.py"), str(port), str(store)], cwd=ROOT)
