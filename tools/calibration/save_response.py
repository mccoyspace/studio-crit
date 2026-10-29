"""File one calibration response: move its downloaded image(s) into the project and write its record.

usage: python3 -I save_response.py <response_id> <assignment_key> <method> < response_text
  response_text: ChatGPT's reply text (title and statement), read from stdin.
Images are taken from ~/Downloads/calib-<response_id>-<n>.png, and SVG source (method B) from
data/calibration/responses/<response_id>.svg if present (rendered to PNG with rsvg-convert).
"""
import json, shutil, subprocess, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "calibration" / "responses"
rid, key, method = sys.argv[1:4]
text = sys.stdin.read().strip()

plan = json.loads((ROOT / "data" / "calibration" / "run_plan.json").read_text())
assignment = next(a for a in plan["assignments"] if a["key"] == key)
prompt = plan["prompts"][method].replace("{assignment}", assignment["text"])
if method == "A":
    prompt += "\n\n[second turn] " + plan["prompts"]["A_statement"]

works = []
for n, src in enumerate(sorted(Path.home().joinpath("Downloads").glob(f"calib-{rid}-*.png"))):
    dest = OUT / f"{rid}-{key}-{method}-{n}.png"
    shutil.move(src, dest)
    works.append(dest.name)
svg = OUT / f"{rid}.svg"
if svg.exists():
    png = OUT / f"{rid}-{key}-{method}-svg.png"
    subprocess.run(["rsvg-convert", "-w", "1200", "-o", str(png), str(svg)], check=True)
    works.append(png.name)
if method != "T" and not works:
    sys.exit(f"no image found for {rid}")

record = {
    "response_id": rid, "assignment_unit": assignment["unit"], "assignment_key": key,
    "assignment_text": assignment["text"], "maker": "chatgpt", "method": method,
    "prompt": prompt, "settings": "chatgpt.com, regular chat, memory and custom instructions off",
    "works": works, "response_text": text, "generated": date.today().isoformat(),
}
(OUT / f"{rid}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(rid, key, method, works)
