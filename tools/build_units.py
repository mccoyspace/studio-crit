"""Resolve hand-made unit annotations into corpus/units.jsonl + corpus/units.md.

Annotations live in tools/data/units/<book-dir>.json as {section_slug: [unit, ...]}, where a unit is
  {"t": type, "b": block | [first, last], "q": "verbatim excerpt" | ["opening", "closing"] (optional),
   "l": "label", "tags": [...], "src": "attribution (optional)", "variant_of": n, "about": n}
`b` indexes the section's blocks; `q` narrows the unit to a statement inside those blocks, either
quoted verbatim or as opening/closing fragments that are extracted with everything between.
`"split": "numbered"` turns one numbered-list block into a unit per item (Baldessari's list). `variant_of` / `about` point to another unit (0-based) in the
same section. Every content block must be covered by at least one unit.

usage: python3 -I build_units.py <corpus_dir> <annotations_dir>
"""
import json, re, sys
from collections import Counter
from pathlib import Path

corpus, ann_dir = map(Path, sys.argv[1:3])

TYPES = {
    "assignment": "an instruction someone could carry out: a prompt, exercise, project, game or procedure",
    "rule": "a prescriptive norm of conduct or practice (do / don't / should), including maxims",
    "principle": "a general claim about what art, teaching or critique is or should value; a criterion rather than an action",
    "observation": "a descriptive claim about how the art world or art school actually works",
    "anecdote": "a narrated, specific event",
    "outcome": "what resulted when an assignment or rule was carried out: works made, reactions, lessons",
    "context": "framing, provenance, background or setup needed to read other units",
    "work": "the contribution is itself an artwork or creative text (image, verse, monologue)",
}
TAGS = set("""
studio_visit opening dinner art_fair critique classroom gallery museum online party art_school residency
artist dealer curator critic collector student teacher visitor intern public
introductions money gifts criticism honesty attention networking dress alcohol power memory career
sexuality professionalism status kindness discretion hospitality time humor failure authorship
drawing painting sculpture photography video film performance sound writing installation
social_practice conceptual collaboration research game cooking design reading looking walking
color material process rules chance constraint observation imitation appropriation self history
place body language theater documentation teaching_method
""".split())
BOOK_CODES = {"draw-it-with-your-eyes-closed": "DIWYEC", "i-like-your-work": "ILYW"}
SKIP = {"heading", "subtitle", "question"}
# headings and bare separators ("—") need no unit of their own
# as do italic prompts that some contributors answer ("*The best ... you ever got:*")
NEEDS_UNIT = lambda b: (b["type"] not in SKIP | {"subheading"}
                        and (b["type"] == "figure" or re.search(r"\w", b.get("text", "")))
                        and not (b.get("italic") and b.get("text", "").rstrip("*").endswith(":")))


def block_text(b):
    if b["type"] == "figure":
        return b.get("transcription") or b.get("description", "")
    return b.get("text", "")


def expand_numbered(section, sec_units):
    """A unit with "split": "numbered" covers one block holding a numbered list (Baldessari's
    transcription) and becomes one unit per item. Optional "items": {number: [label, [tags]]}."""
    out = []
    for u in sec_units:
        if u.get("split") != "numbered":
            out.append(u)
            continue
        text = block_text(section["blocks"][u["b"]])
        for m in re.finditer(r"(?m)^(\d+)\. (.+?)(?=\n\n\d+\. |\n\n\\\* |\Z)", text, re.S):
            num, body = m.group(1), m.group(2).strip()
            label, tags = u.get("items", {}).get(num, [None, None])
            first = re.split(r"(?<=[.?!])\s", body, maxsplit=1)[0]
            out.append({"t": u["t"], "b": u["b"], "q": f"{num}. {body}", "item": num,
                        "l": label or (first if len(first) <= 80 else first[:77] + "..."),
                        "tags": tags if tags is not None else u.get("tags", []),
                        **({"src": u["src"]} if u.get("src") else {})})
    return out


units, problems, coverage = [], [], Counter()
for book_dir in sorted(p for p in corpus.iterdir() if (p / "book.json").exists()):
    book = json.loads((book_dir / "book.json").read_text())
    ann = {}  # annotations may be split across <book>.json, <book>-2.json, ...
    for ann_path in sorted(ann_dir.glob(f"{book_dir.name}*.json")):
        ann.update(json.loads(ann_path.read_text()))
    code = BOOK_CODES[book_dir.name]
    for s in book["sections"]:
        sec_units = ann.get(s["slug"])
        content = [i for i, b in enumerate(s["blocks"]) if NEEDS_UNIT(b)]
        if s.get("kind", "contribution") != "contribution" and sec_units is None:
            continue  # bios and colophon stay as apparatus in book.json
        if sec_units is None:
            problems.append(f"{book_dir.name}/{s['slug']}: not annotated")
            continue
        sec_units = expand_numbered(s, sec_units)
        covered = set()
        ids = [f"{code}-{s['order']:02d}-{n + 1:02d}" for n in range(len(sec_units))]
        for n, u in enumerate(sec_units):
            where = f"{book_dir.name}/{s['slug']} unit {n}"
            if u["t"] not in TYPES:
                problems.append(f"{where}: unknown type {u['t']}")
            first, last = (u["b"], u["b"]) if isinstance(u["b"], int) else u["b"]
            if not 0 <= first <= last < len(s["blocks"]):
                problems.append(f"{where}: block range {u['b']} out of bounds")
                continue
            span = s["blocks"][first:last + 1]
            full = "\n\n".join(block_text(b) for b in span if b["type"] not in SKIP)
            text = full
            if u.get("q"):
                # q is a verbatim excerpt, or [opening, closing] fragments of one
                start_frag, end_frag = (u["q"], None) if isinstance(u["q"], str) else u["q"]
                a = full.find(start_frag)
                b = full.find(end_frag, a) + len(end_frag) if end_frag and a >= 0 else a + len(start_frag)
                if a < 0 or (end_frag and full.find(end_frag, a) < 0):
                    problems.append(f"{where}: quote not found: {u['q']!r:.80}")
                text = full[a:b] if a >= 0 else ""
            covered.update(range(first, last + 1))
            for t in u.get("tags", []):
                if t not in TAGS:
                    problems.append(f"{where}: unknown tag {t}")
            # questionnaire units inherit the question they answer
            qid = next((b["question_id"] for b in reversed(s["blocks"][:first + 1]) if b["type"] == "question"), None)
            images = [b["image"] for b in span if b["type"] == "figure"]
            unit = {
                "id": ids[n], "book": book_dir.name, "section": s["order"], "contributor": s["contributor"],
                "section_title": s.get("title"), "type": u["t"], "label": u["l"], "tags": u.get("tags", []),
                "text": text, "blocks": [first, last], "excerpt": bool(u.get("q")),
            }
            if qid:
                unit["question_id"] = qid
            if u.get("src"):
                unit["attribution"] = u["src"]
            if u.get("item"):
                unit["item"] = u["item"]
            for rel in ("variant_of", "about"):
                if rel in u:
                    unit[rel] = ids[u[rel]]
            if images:
                unit["images"] = [f"{book_dir.name}/{i}" for i in images]
            units.append(unit)
            coverage[u["t"]] += 1
        missing = [i for i in content if i not in covered]
        if missing:
            problems.append(f"{book_dir.name}/{s['slug']}: blocks not covered {missing}")

with (corpus / "units.jsonl").open("w") as f:
    for u in units:
        f.write(json.dumps(u, ensure_ascii=False) + "\n")

# browsable overview, grouped by type
lines = ["# Units\n", "Generated from `units.jsonl` by `tools/build_units.py`. One line per unit: id, contributor, label.\n"]
for t, desc in TYPES.items():
    group = [u for u in units if u["type"] == t]
    lines.append(f"\n## {t} ({len(group)})\n\n*{desc}*\n")
    for u in group:
        q = f" · `{u['question_id']}`" if u.get("question_id") else ""
        lines.append(f"- `{u['id']}` **{u['contributor']}**: {u['label']}{q}")
(corpus / "units.md").write_text("\n".join(lines) + "\n")

print(f"{len(units)} units:", dict(coverage))
for p in problems:
    print("PROBLEM", p)
