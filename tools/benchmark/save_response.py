"""File one benchmark response: move its downloaded files into the project and write its record.

usage: python3 -I save_response.py <run> <response_id> <assignment_id> <n_images> [--followup]
  n_images: how many images the page showed; waits up to 60 s for that many downloads
  --followup: the fixed statement follow-up (maker_prompt.json) was sent because the first reply had no statement
Takes from ~/Downloads, as saved straight from the ChatGPT page:
  bench-<response_id>.txt       the reply text (work text, if any, and statement), never retyped
  bench-<response_id>-<n>.png   the images, in page order (none for a text-only work)
Writes benchmark/<run>/responses/<response_id>.json and moves the files next to it.
Interface text found in the reply is not removed here; use clean_response.py, which logs each removal.
"""
import json, shutil, sys, time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
run, rid, aid, n_images = sys.argv[1:5]
followup = "--followup" in sys.argv[5:]
OUT = ROOT / "benchmark" / run / "responses"
OUT.mkdir(parents=True, exist_ok=True)
spec = json.loads((ROOT / "benchmark" / "v1" / "assignments.json").read_text())
plan = json.loads((ROOT / "benchmark" / "v1" / "maker_prompt.json").read_text())
a = next(x for x in spec["assignments"] if x["assignment_id"] == aid)

dl = Path.home() / "Downloads"
txt = dl / f"bench-{rid}.txt"
if not txt.exists():
    sys.exit(f"missing {txt}")
text = txt.read_text().strip()
if len(text) < 40:
    sys.exit(f"reply text too short ({len(text)} chars): check the download")

for _ in range(60):
    if len(list(dl.glob(f"bench-{rid}-*.png"))) >= int(n_images):
        break
    time.sleep(1)
else:
    sys.exit(f"expected {n_images} images for {rid}, found {len(list(dl.glob(f'bench-{rid}-*.png')))}")
works = []
for n, src in enumerate(sorted(dl.glob(f"bench-{rid}-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))):
    if src.stat().st_size < 10_000:
        sys.exit(f"{src.name} is only {src.stat().st_size} bytes: check the download")
    dest = OUT / f"{rid}-{n}.png"
    shutil.move(src, dest)
    works.append(dest.name)
shutil.move(txt, OUT / f"{rid}.txt")

record = {
    "response_id": rid, "run": run, "assignment_id": aid, "family": a["family"],
    "assignment_text": a["prompt_text"], "maker": "chatgpt", "method": "native",
    "prompt": plan["prompt"].replace("{assignment}", a["prompt_text"]),
    "followup_used": followup, **({"followup": plan["statement_followup"]} if followup else {}),
    "settings": "chatgpt.com, regular chat, memory and custom instructions off",
    "works": works, "has_images": bool(works),
    "response_text": text, "cleanup": [], "generated": date.today().isoformat(),
}
(OUT / f"{rid}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(rid, aid, works, f"{len(text)} chars")
