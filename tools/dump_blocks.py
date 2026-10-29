"""Print corpus sections with block indices, for annotating units.

usage: python3 -I dump_blocks.py <book.json> [first_order] [last_order]
"""
import json, sys

book = json.load(open(sys.argv[1]))
lo = int(sys.argv[2]) if len(sys.argv) > 2 else 1
hi = int(sys.argv[3]) if len(sys.argv) > 3 else 10**6
for s in book["sections"]:
    if not lo <= s["order"] <= hi:
        continue
    print(f"\n=== {s['order']} {s['slug']} | {s['contributor']} | {s.get('title')}")
    for i, b in enumerate(s["blocks"]):
        t = b["type"]
        if t == "figure":
            text = b.get("description", "") + (" || " + b["transcription"] if b.get("transcription") else "")
        else:
            text = b.get("text", "")
        tag = t if t != "list_item" else f"item {b['number']}"
        if t == "question":
            tag = f"Q:{b['question_id']}"
        print(f"[{i}] {tag}: {text}")
