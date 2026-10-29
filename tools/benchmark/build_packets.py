"""Assemble anonymized crit packets from a benchmark run, in the calibration packet format.

usage: python3 -I build_packets.py <run> [seed]
Reads benchmark/<run>/responses/B##.json (blocked attempts like B22a are left out).
Writes benchmark/<run>/packets/: packets.json, images/, and _key.json (packet -> response; not for the judge).
"""
import json, random, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "calibration"))
run = sys.argv[1]
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20261029
RUN = ROOT / "benchmark" / run
OUT = RUN / "packets"

from split_text import split_text

recs = [json.loads(p.read_text()) for p in sorted((RUN / "responses").glob("B[0-9][0-9].json"))]
random.Random(seed).shuffle(recs)
if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "images").mkdir(parents=True)
packets, key = [], {}
for n, r in enumerate(recs, 1):
    pid = f"P{n:02d}"
    parts = split_text(r["response_text"], "image" if r["works"] else "T")
    images = []
    for k, w in enumerate(r["works"], 1):
        dest = f"{pid}-{k}{Path(w).suffix}"
        shutil.copy2(RUN / "responses" / w, OUT / "images" / dest)
        images.append(dest)
    packets.append({"packet_id": pid, "sitting": 1 + (n - 1) // 8, "assignment_key": r["assignment_id"],
                    "assignment_text": r["assignment_text"], "images": images, **parts})
    key[pid] = {"source": r["response_id"], "kind": "response", "method": r["method"], "family": r["family"]}

(OUT / "packets.json").write_text(json.dumps({"seed": seed, "packets": packets, "ranking_groups": {}}, ensure_ascii=False, indent=2))
(OUT / "_key.json").write_text(json.dumps(key, indent=2))
for p in packets:
    print(p["packet_id"], p["sitting"], len(p["images"]), "| title:", p["title"][:50], "| work_text:", len(p["work_text"]), "| statement:", len(p["statement"]))
