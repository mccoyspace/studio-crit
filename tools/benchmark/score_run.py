"""Score a judged benchmark run.

usage: python3 -I score_run.py <run> <judge_dir>
judge_dir holds step1/P##.json and step2/P##.json from the blind judge (see tools/calibration/prepare_judge.py).
Unblinds with benchmark/<run>/packets/_key.json and writes <judge_dir>/scores.json and <judge_dir>/scores.md.
Also picks the 6-packet Kevin audit sample (fixed seed), listed by packet id only so Kevin judges it blind.
"""
import json, random, sys
from collections import Counter
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
run, jdir = sys.argv[1], Path(sys.argv[2]).resolve()
RUN = ROOT / "benchmark" / run
KEY = json.loads((RUN / "packets" / "_key.json").read_text())
RESP = {json.loads(p.read_text())["response_id"]: json.loads(p.read_text()) for p in (RUN / "responses").glob("B*.json")}
s1 = {p.stem: json.loads(p.read_text()) for p in (jdir / "step1").glob("P*.json")}
s2 = {p.stem: json.loads(p.read_text()) for p in (jdir / "step2").glob("P*.json")}
VALUES = ("new_ground", "form_content", "holding", "economy")
RANKED = ("new_ground", "form_content", "holding")  # economy shapes feedback only, so it stays out of the headline
PROBES = {"DIWYEC-22-01": "self", "DIWYEC-40-08": "self", "DIWYEC-72-01": "failure", "DIWYEC-43-01": "rules", "DIWYEC-32-83": "bare question"}

rows = []
for pid in sorted(s1):
    r = RESP[KEY[pid]["source"]]
    rows.append({"packet": pid, "response": r["response_id"], "assignment": r["assignment_id"], "family": r["family"],
                 "label": " ".join(r["assignment_text"].split())[:60], "impact": s1[pid]["impact"] == "yes", "scores": s1[pid]["scores"] or {},
                 "effect": s2.get(pid, {}).get("statement_effect"), "followup": r.get("followup_used", False),
                 "verdict": s1[pid]["verdict"] or s1[pid]["impact_note"]})


def profile(rs):
    passed = [r for r in rs if r["impact"]]
    return {"n": len(rs), "impact": sum(r["impact"] for r in rs),
            "impact_rate": round(sum(r["impact"] for r in rs) / len(rs), 2) if rs else None,
            **{v: round(mean(r["scores"][v] for r in passed), 2) if passed else None for v in VALUES},
            # headline: the ranked values over every work, a work that fails the gate scoring 0 (the gate is unstable, the values aren't)
            "headline": {v: round(mean(r["scores"].get(v, 0) for r in rs), 2) for v in RANKED} if rs else None,
            "value_score": round(mean(mean(r["scores"].get(v, 0) for v in RANKED) for r in rs), 2) if rs else None}


out = {
    "run": run, "judge": jdir.name, "packets": len(rows),
    "overall": profile(rows),
    "statement_effect": dict(Counter(r["effect"] for r in rows)),
    "statement_effect_by_impact": {k: dict(Counter(r["effect"] for r in rows if r["impact"] == k)) for k in (True, False)},
    "by_family": {f: profile([r for r in rows if r["family"] == f]) for f in sorted({r["family"] for r in rows})},
    "probes": {a: {"probe": p, **next(({"packet": r["packet"], "impact": r["impact"], "scores": r["scores"], "verdict": r["verdict"]} for r in rows if r["assignment"] == a), {})} for a, p in PROBES.items()},
    "followup_responses": profile([r for r in rows if r["followup"]]),
    "kevin_audit_sample": sorted(random.Random(20261029).sample(sorted(s1), 6)),
    "rows": rows,
}
out["statement_effect_by_impact"] = {("impact" if k else "no impact"): v for k, v in out["statement_effect_by_impact"].items()}
(jdir / "scores.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))

o = out["overall"]
h = o["headline"]
md = [f"# Benchmark {run}: scores ({jdir.name})", "",
      f"**Value score: {o['value_score']} / 4** (new ground {h['new_ground']}, form–content {h['form_content']}, holding {h['holding']}; "
      f"every work counted; a work the judge did not score counts 0).", "",
      f"Impact rate {o['impact']}/{o['n']} ({o['impact_rate']:.0%}); report it as a range across cards, not alone. "
      f"Among works that pass: new ground {o['new_ground']}, form–content {o['form_content']}, holding {o['holding']}, economy {o['economy']}.", "",
      "| Family | n | value score | new ground | form–content | holding | impact |", "|---|---|---|---|---|---|---|"]
for f, p in out["by_family"].items():
    hp = p["headline"]
    md.append(f"| {f} | {p['n']} | {p['value_score']} | {hp['new_ground']} | {hp['form_content']} | {hp['holding']} | {p['impact']} |")
md += ["", "| Packet | Response | Assignment | Impact | NG/FC/H/E | Statement | Verdict |", "|---|---|---|---|---|---|---|"]
for r in sorted(rows, key=lambda r: r["response"]):
    s = "/".join(str(r["scores"][v]) for v in VALUES) if r["scores"] else "—"
    md.append(f"| {r['packet']} | {r['response']} | {r['label']} | {'yes' if r['impact'] else 'no'} | {s} | {r['effect']} | {r['verdict']} |")
(jdir / "scores.md").write_text("\n".join(md) + "\n")
print("\n".join(md[:12]))
print("statement effects:", out["statement_effect_by_impact"])
print("audit sample:", out["kevin_audit_sample"])
