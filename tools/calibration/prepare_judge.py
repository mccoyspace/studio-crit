"""Prepare blind inputs for a model judging the calibration packets with a judgement card.

usage: python3 -I prepare_judge.py <out_dir> step1|step2 [packets_dir]
packets_dir defaults to data/calibration/packets; pass benchmark/<run>/packets for a benchmark run.
step1  writes card.json, protocol.md and per-packet work folders (assignment, images, text work): no titles or statements.
step2  writes per-packet statement.txt (title + statement) next to them; run only after step 1 verdicts are written.
The out_dir must be outside data/calibration, so the judge never sits next to Kevin's verdicts or the key.
"""
import json, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "data" / "calibration"
CARD = ROOT / "cards" / "kevin-mccoy" / "judgement_card.draft.json"
# card fields about its own making, not about judging
INTERNAL = ("_status", "calibration", "judge_id", "name", "version", "positions_ref", "merged_values")

out, step = Path(sys.argv[1]).resolve(), sys.argv[2]
PKD = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else CAL / "packets"
assert CAL not in out.parents and out != CAL and PKD.parent not in (out, *out.parents), "out_dir must be outside the verdicts and packet key"
PK = json.loads((PKD / "packets.json").read_text())

if step == "step1":
    card = {k: v for k, v in json.loads(CARD.read_text()).items() if k not in INTERNAL}
    card["scoring"].pop("status", None)
    for v in card["values"]:
        v.pop("evidence", None)

    def scrub(x):
        # evidence notes cite packet ids the judge is about to see, with Kevin's words: drop them
        if isinstance(x, dict):
            return {k: scrub(v) for k, v in x.items()}
        if isinstance(x, list):
            return [scrub(v) for v in x]
        if isinstance(x, str):
            x = re.sub(r"\s*\((gold|audit|the judge does this)[^()]*(\([^()]*\)[^()]*)*\)", "", x, flags=re.I)
            x = re.sub(r"\s*The judge does this \(gold:[^)]*\)[^.]*\.", "", x)
            return re.sub(r"\s*Calibration: .*$", "", x)
        return x
    card = scrub(card)
    assert not re.search(r"P\d\d|gold|audit|calibration|\bK\d\b|day into night|merely illustrative", json.dumps(card), re.I), "card still cites calibration evidence"
    out.mkdir(parents=True, exist_ok=True)
    (out / "card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2))
    for p in PK["packets"]:
        d = out / "packets" / p["packet_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "assignment.txt").write_text(p["assignment_text"] + "\n")
        if p["work_text"]:
            (d / "work.txt").write_text(p["work_text"] + "\n")
        for img in p["images"]:
            shutil.copy2(PKD / "images" / img, d / img)
    groups = {k: v for k, v in PK["ranking_groups"].items()}
    (out / "ranking_groups.json").write_text(json.dumps(groups, indent=2))
elif step == "step2":
    for p in PK["packets"]:
        d = out / "packets" / p["packet_id"]
        (d / "statement.txt").write_text(f"Title: {p['title'] or '(none)'}\n\nStatement:\n{p['statement'] or '(none)'}\n")
else:
    sys.exit("step must be step1 or step2")
print(f"{step} inputs in {out}")
