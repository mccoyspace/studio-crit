"""Unblind Kevin's calibration verdicts and split them into gold, held-out and control sets.

usage: python3 -I analyze.py [seed]
Reads cards/kevin-mccoy/calibration/verdicts.json and data/calibration/packets/{packets.json, _key.json}.
Writes data/calibration/analysis.json and data/calibration/split.json.
The split is by assignment (whole ranking groups), so within-assignment rankings stay intact.
"""
import json, random, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "data" / "calibration"
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20261029
HELD_OUT_ASSIGNMENTS = 3

V = json.loads((ROOT / "cards" / "kevin-mccoy" / "calibration" / "verdicts.json").read_text())
PK = json.loads((CAL / "packets" / "packets.json").read_text())
KEY = json.loads((CAL / "packets" / "_key.json").read_text())
packets = {p["packet_id"]: p for p in PK["packets"]}
rows = []
for pid, p in packets.items():
    v = V["verdicts"].get(pid, {})
    rows.append({"packet": pid, "sitting": p["sitting"], "assignment": p["assignment_key"], **KEY[pid],
                 "impact": v.get("impact"), "scores": v.get("scores") or {},
                 "statement_effect": v.get("statement_effect") or None,
                 "notes": " ".join(v.get(k, "") for k in ("impact_note", "verdict", "revised_verdict", "question", "provocation"))})

# split: hold out whole assignments
assignments = sorted({r["assignment"] for r in rows})
held = sorted(random.Random(seed).sample(assignments, HELD_OUT_ASSIGNMENTS))
# controls probe specific card rules, so they are a test set of their own and never used for tuning
split = {"seed": seed, "held_out_assignments": held,
         "gold": sorted(r["packet"] for r in rows if r["kind"] == "response" and r["assignment"] not in held),
         "held_out": sorted(r["packet"] for r in rows if r["kind"] == "response" and r["assignment"] in held),
         "controls": sorted(r["packet"] for r in rows if r["kind"] != "response")}

responses = [r for r in rows if r["kind"] == "response"]
by_src = {r["source"]: r for r in rows}


def rate(rs):
    return f"{sum(1 for r in rs if r['impact'])}/{len(rs)}"


def gate_and_scores(r):
    return {"impact": r["impact"], **r["scores"], "effect": r["statement_effect"]}


controls = {
    "fluent_failures": {r["source"]: {**gate_and_scores(r), "packet": r["packet"]} for r in rows if r["kind"] == "fluent_failure"},
    "slogan": {r["source"]: {**gate_and_scores(r), "packet": r["packet"]} for r in rows if r["kind"] == "slogan"},
    "statement_swaps": {r["source"]: {"swap": gate_and_scores(r), "swap_packet": r["packet"],
                                      "intended": r.get("swap"), "original": gate_and_scores(by_src[r["base_response"]]),
                                      "original_packet": by_src[r["base_response"]]["packet"]}
                        for r in rows if r["kind"] == "statement_swap"},
    "repeat": {r["source"]: {"repeat": gate_and_scores(r), "repeat_packet": r["packet"],
                             "original": gate_and_scores(by_src[r["base_response"]]),
                             "original_packet": by_src[r["base_response"]]["packet"]}
               for r in rows if r["kind"] == "repeat"},
}

effects = Counter((r["impact"], r["statement_effect"]) for r in responses)
themes = {  # recurring words in Kevin's own notes, questions and provocations
    "reduction": r"too much|simplif|strip|less is more|pare|loose|lose|wordy|10 times|not needed",
    "sentiment/cliche": r"cliche|sentiment|cheesy|hallmark|give me a break|cringe",
    "joke/juxtaposition": r"joke|A\+B|juxtaposition|incongruous",
    "texture": r"texture",
}
analysis = {
    "packets_judged": sum(1 for r in rows if r["impact"] is not None),
    "rankings_entered": len(V["rankings"]),
    "impact_rate": {"responses": rate(responses), "all": rate(rows),
                    "by_method": {m: rate([r for r in responses if r["method"] == m]) for m in sorted({r["method"] for r in responses})},
                    "by_assignment": {a: rate([r for r in responses if r["assignment"] == a]) for a in assignments},
                    "by_sitting": {s: rate([r for r in responses if r["sitting"] == s]) for s in (1, 2, 3)}},
    "statement_effect_by_impact": {f"{'impact' if i else 'no impact'}: {e or '(not read)'}": n for (i, e), n in sorted(effects.items(), key=str)},
    "controls": controls,
    "themes_in_feedback": {t: sorted(r["packet"] for r in rows if re.search(pat, r["notes"], re.I)) for t, pat in themes.items()},
}
(CAL / "split.json").write_text(json.dumps(split, indent=2))
(CAL / "analysis.json").write_text(json.dumps(analysis, indent=2))
print(json.dumps(split, indent=1))
print(json.dumps(analysis, indent=1))
