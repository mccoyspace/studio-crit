"""Assemble anonymized crit packets for Kevin's calibration crit.

usage: python3 -I build_packets.py [seed]
Reads data/calibration/responses/R01-R24 and controls/K1-K6. Writes data/calibration/packets/:
  packets.json   what the verdict page shows (no sources, makers or methods)
  images/        works renamed by packet number
  _key.json      packet -> source mapping; never served to the page, don't open before judging
"""
import json, random, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from split_text import split_text

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "data" / "calibration"
OUT = CAL / "packets"
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20261028


sources = []
for p in sorted((CAL / "responses").glob("R[0-9][0-9].json")):
    r = json.loads(p.read_text())
    if r["response_id"] == "R00":
        continue
    sources.append({"src": r["response_id"], "kind": "response", "method": r["method"], "dir": "responses", **r})
for p in sorted((CAL / "controls").glob("K*.json")):
    r = json.loads(p.read_text())
    sources.append({"src": r["control_id"], "kind": r["kind"], "method": "T" if not r["works"] else "image", "dir": "controls", **r})

# three sittings of ten; repeat after its original, swaps apart from their originals
rng = random.Random(seed)
by_src = {s["src"]: s for s in sources}
apart = [("K6", "R04", "later"), ("K4", "R08", "different"), ("K5", "R21", "different")]
for _ in range(10000):
    order = sources[:]
    rng.shuffle(order)
    sitting = {s["src"]: 1 + n // 10 for n, s in enumerate(order)}
    if all((sitting[a] > sitting[b]) if rule == "later" else (sitting[a] != sitting[b]) for a, b, rule in apart):
        break
else:
    sys.exit("no valid arrangement")

if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "images").mkdir(parents=True)
packets, key = [], {}
for n, s in enumerate(order, 1):
    pid = f"P{n:02d}"
    parts = split_text(s["response_text"], "T" if s["method"] == "T" else "image")
    images = []
    for k, w in enumerate(s["works"], 1):
        dest = f"{pid}-{k}{Path(w).suffix}"
        shutil.copy2(CAL / s["dir"] / w, OUT / "images" / dest)
        images.append(dest)
    packets.append({"packet_id": pid, "sitting": sitting[s["src"]], "assignment_key": s["assignment_key"],
                    "assignment_text": s["assignment_text"], "images": images, **parts})
    key[pid] = {"source": s["src"], "kind": s["kind"], "method": s["method"],
                **({k: s[k] for k in ("base_response", "swap") if k in s})}

# rankings compare distinct works only: leave out repeats and statement swaps
groups = {}
for p in packets:
    if key[p["packet_id"]]["kind"] in ("repeat", "statement_swap"):
        continue
    groups.setdefault(p["assignment_key"], []).append(p["packet_id"])

(OUT / "packets.json").write_text(json.dumps({"seed": seed, "packets": packets, "ranking_groups": groups},
                                             ensure_ascii=False, indent=2))
(OUT / "_key.json").write_text(json.dumps(key, indent=2))
for s in (1, 2, 3):
    print(f"sitting {s}:", [p["packet_id"] for p in packets if p["sitting"] == s])
print({k: len(v) for k, v in groups.items()})
