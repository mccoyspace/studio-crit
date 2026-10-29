"""Build the Crit Positions page: every rule and principle unit, grouped into themes.

usage: python3 -I build_reactions_page.py <units.jsonl> <template.html> <out.html>
"""
import json, sys

units_path, template_path, out_path = sys.argv[1:4]

# First matching theme wins, so the order sets priority: criticism before everything else.
THEMES = [
    ("criticism", "Giving criticism", {"criticism", "critique", "honesty", "critic"}),
    ("teaching", "Teaching and assignments", {"teaching_method", "teacher", "art_school", "student", "classroom"}),
    ("making", "Making and process", {"process", "failure", "authorship", "constraint", "looking", "conceptual",
                                      "self", "research", "material", "observation", "chance", "imitation"}),
    ("occasions", "Studio visits and openings", {"studio_visit", "opening", "dinner", "art_fair", "party",
                                                  "hospitality", "alcohol", "museum", "gallery"}),
    ("standing", "Career, money and status", {"networking", "career", "money", "status", "power", "introductions",
                                              "dress", "professionalism", "discretion", "curator", "dealer", "collector"}),
    ("character", "Character and conduct", None),  # everything else
]
BOOKS = {"i-like-your-work": "I Like Your Work", "draw-it-with-your-eyes-closed": "Draw It with Your Eyes Closed"}
QUESTIONS = {
    "rules": "What are the rules of etiquette for the art world?",
    "memorable_situation": "Was etiquette foregrounded in any memorable situation?",
    "customs": "What customs or mannerisms are particular to the art world?",
    "breach": "When does breach of etiquette play a role in embarrassing or awkward encounters?",
    "maxim": "How should people behave? What would be a maxim for appropriate conduct?",
    "financial_shift": "Has there been a shift in etiquette as the financial climate has changed?",
    "bad_manners": "What constitutes bad manners?",
}

units = [json.loads(line) for line in open(units_path)]
picked = []
for u in units:
    if u["type"] not in ("rule", "principle"):
        continue
    tags = set(u["tags"])
    theme = next(tid for tid, _, keys in THEMES if keys is None or tags & keys)
    picked.append({
        "id": u["id"], "theme": theme, "type": u["type"], "book": BOOKS[u["book"]],
        "contributor": u["contributor"], "label": u["label"], "text": u.get("text") or "",
        "question": QUESTIONS.get(u.get("question_id"), ""),
    })
order = {tid: n for n, (tid, _, _) in enumerate(THEMES)}
picked.sort(key=lambda p: (order[p["theme"]], p["id"]))

html = open(template_path).read()
html = html.replace("/*UNITS*/[]", json.dumps(picked, ensure_ascii=False))
html = html.replace("/*THEMES*/[]", json.dumps([{"id": t, "label": l} for t, l, _ in THEMES]))
open(out_path, "w").write(html)
counts = {t: sum(p["theme"] == t for p in picked) for t, _, _ in THEMES}
print(len(picked), "units", counts, f"{len(html) // 1024} KB")
