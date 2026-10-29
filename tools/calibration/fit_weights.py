"""Test candidate value orderings against Kevin's within-assignment rankings.

usage: python3 -I fit_weights.py
Reads verdicts.json, packets/_key.json and split.json (run analyze.py first).
Every pair of works in a ranked group is a test: does the ordering put them the way Kevin did?
A pair the ordering ties (e.g. two works that both fail the impact gate) is counted as undecided.
Gold is used for choosing; held-out and control pairs are reported, not used.
Writes data/calibration/fit.json.
"""
import json
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "data" / "calibration"
V = json.loads((ROOT / "cards" / "kevin-mccoy" / "calibration" / "verdicts.json").read_text())
KEY = json.loads((CAL / "packets" / "_key.json").read_text())
SPLIT = json.loads((CAL / "split.json").read_text())
set_of = {p: s for s in ("gold", "held_out", "controls") for p in SPLIT[s]}


def vec(pid):
    v = V["verdicts"][pid]
    s = v.get("scores") or {}
    return (1 if v.get("impact") else 0, s.get("new_ground", 0), s.get("form_content", 0), s.get("holding", 0))


# each ordering maps a packet to a sortable key: higher is better
ORDERINGS = {
    "stated (impact > new ground > form-content > holding)": lambda x: x,
    "impact, then equal sum": lambda x: (x[0], x[1] + x[2] + x[3]),
    "impact, then form-content first": lambda x: (x[0], x[2], x[1], x[3]),
    "impact, then holding first": lambda x: (x[0], x[3], x[1], x[2]),
}

results = {}
for name, f in ORDERINGS.items():
    tally = {s: {"agree": 0, "disagree": 0, "undecided": 0, "disagreements": []} for s in ("gold", "held_out", "controls")}
    for group, r in V["rankings"].items():
        for a, b in combinations(r["ranks"], 2):
            # a pair involving a control counts toward controls
            s = "controls" if "controls" in (set_of[a], set_of[b]) else set_of[a]
            ka, kb = f(vec(a)), f(vec(b))
            kevin = r["ranks"][a] < r["ranks"][b]  # True: Kevin put a above b
            if ka == kb:
                tally[s]["undecided"] += 1
            elif (ka > kb) == kevin:
                tally[s]["agree"] += 1
            else:
                tally[s]["disagree"] += 1
                hi, lo = (a, b) if kevin else (b, a)
                tally[s]["disagreements"].append(f"{hi}>{lo}")
    results[name] = tally

out = {"groups_ranked": sorted(V["rankings"]), "results": results}
(CAL / "fit.json").write_text(json.dumps(out, indent=2))
print("groups ranked:", ", ".join(out["groups_ranked"]))
for name, t in results.items():
    print(f"\n{name}")
    for s, x in t.items():
        print(f"  {s:9} agree {x['agree']:2}  disagree {x['disagree']:2}  undecided {x['undecided']:2}  {' '.join(x['disagreements'])}")
