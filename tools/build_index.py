"""Write corpus/index.json: one row per section across both books.

usage: python3 -I build_index.py <corpus_dir>
"""
import json, sys
from pathlib import Path

corpus = Path(sys.argv[1])
rows = []
for book_dir in sorted(p for p in corpus.iterdir() if (p / "book.json").exists()):
    book = json.loads((book_dir / "book.json").read_text())
    for s in book["sections"]:
        rows.append({
            "book": book_dir.name,
            "order": s["order"],
            "contributor": s["contributor"],
            "title": s["title"],
            # EPUB sections carry kind (contribution/afterword/...); PDF sections carry form
            "kind": s.get("kind", "contribution"),
            "form": s.get("form"),
            "questions_answered": [a["question_id"] for a in s.get("answers", [])] or None,
            "word_count": s["word_count"],
            "figure_count": s.get("figure_count", sum(b["type"] == "figure" for b in s["blocks"])),
            "markdown": f"{book_dir.name}/sections/{s['order']:02d}-{s['slug']}.md",
        })
(corpus / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
print(f"index: {len(rows)} sections")
