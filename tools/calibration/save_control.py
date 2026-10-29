"""File one ChatGPT-made control work (fluent failure or slogan) from ~/Downloads.

usage: python3 -I save_control.py <control_id>
Reads ~/Downloads/calib-<id>-0.png and calib-<id>.txt (the statement saved from the page).
"""
import json, shutil, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "calibration" / "controls"
cid = sys.argv[1]
plan = json.loads((ROOT / "data" / "calibration" / "run_plan.json").read_text())
ctrl = next(c for c in plan["controls"] if c["id"] == cid)
assignment = next(a for a in plan["assignments"] if a["key"] == ctrl["key"])
dl = Path.home() / "Downloads"
OUT.mkdir(parents=True, exist_ok=True)

image = OUT / f"{cid}-{ctrl['key']}-{ctrl['kind']}.png"
shutil.move(dl / f"calib-{cid}-0.png", image)
for extra in dl.glob(f"calib-{cid}-0 *.png"):  # a late duplicate of the same download
    extra.unlink()
text_file = dl / f"calib-{cid}.txt"
text = text_file.read_text().strip()
text_file.unlink()

record = {
    "control_id": cid, "kind": ctrl["kind"], "assignment_unit": assignment["unit"],
    "assignment_key": ctrl["key"], "assignment_text": assignment["text"], "maker": "chatgpt",
    "prompt": plan["control_prompts"][ctrl["prompt"]].replace("{assignment}", assignment["text"])
              + "\n\n[second turn] " + plan["control_prompts"]["statement"],
    "settings": "chatgpt.com, regular chat, memory and custom instructions off",
    "works": [image.name], "response_text": text, "generated": date.today().isoformat(),
}
(OUT / f"{cid}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(cid, ctrl["kind"], image.name, len(text.split()), "words")
