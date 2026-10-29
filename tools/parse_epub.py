"""Extract 'Draw It with Your Eyes Closed' (EPUB) into structured JSON + Markdown.

usage: python3 -I parse_epub.py <unpacked_epub_dir> <image_ocr_dir> <figures.json> <transcriptions_dir> <out_dir>
"""
import json, re, shutil, sys
from pathlib import Path
import warnings
from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

src, ocr_dir, figures_path, trans_dir, out = map(Path, sys.argv[1:6])
FIGS = json.loads(figures_path.read_text())

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def soup(path):
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")

# --- spine + toc -----------------------------------------------------------
opf = soup(src / "content.opf")
manifest = {i["id"]: i["href"] for i in opf.find_all("item")}
spine = [manifest[r["idref"]] for r in opf.find_all("itemref")]
spine = [h for h in spine if h.startswith("index_split_")]

ncx = soup(src / "toc.ncx")
toc = []
for nav in ncx.find_all("navpoint"):
    label = nav.find("text").get_text(strip=True)
    target = nav.find("content")["src"]
    f, _, anchor = target.partition("#")
    toc.append({"label": label, "file": f, "anchor": anchor or None})
toc = [t for t in toc if t["file"] != "index_split_000.html" and t["label"] != "Table of Contents"]

# --- inline text -------------------------------------------------------------
def inline(node):
    """Render inline content to Markdown-ish text (italic/bold kept)."""
    if isinstance(node, NavigableString):
        return str(node)
    if node.name == "br":
        return "\n"
    if node.name == "img":
        return ""
    inner = "".join(inline(c) for c in node.children)
    cls = node.get("class") or []
    if "italic" in cls and inner.strip():
        lead, core, trail = re.match(r"^(\s*)(.*?)(\s*)$", inner, re.S).groups()
        return f"{lead}*{core}*{trail}"
    if "bold" in cls and inner.strip():
        lead, core, trail = re.match(r"^(\s*)(.*?)(\s*)$", inner, re.S).groups()
        return f"{lead}**{core}**{trail}"
    return inner

def clean(s):
    s = s.replace("\xa0", " ")
    s = re.sub(r"\*\*\s*\*\*", "", s)
    s = re.sub(r"\*(\s*)\*", r"\1", s)  # merge adjacent italic runs
    s = re.sub(r"[ \t]+", " ", s)
    return "\n".join(l.strip() for l in s.split("\n")).strip()

def all_bold(node):
    texts = [t for t in node.find_all(string=True) if t.strip()]
    return bool(texts) and all(
        any("bold" in (p.get("class") or []) for p in t.parents if isinstance(p, Tag)) for t in texts)

def header_lines(el):
    # nested bold spans: keep outermost only; <br> separates name from title
    return [clean(b.get_text()) for b in el.find_all(class_="bold")
            if not b.find_parent(class_="bold") and b.get_text(strip=True)]

def all_italic(node):
    texts = [t for t in node.find_all(string=True) if t.strip()]
    return bool(texts) and all(
        any("italic" in (p.get("class") or []) for p in t.parents if isinstance(p, Tag)) for t in texts)

# --- walk the spine into a flat element stream --------------------------------
stream = []  # (file, element)
for href in spine:
    body = soup(src / href).body
    if body.get_text(" ", strip=True).startswith("Table of Contents"):
        continue  # generated nav page; the toc is rebuilt from toc.ncx
    for el in body.find_all(recursive=False):
        stream.append((href, el))

def starts_section(href, el, t):
    if href != t["file"]:
        return False
    if t["anchor"] is None:
        return True
    return el.get("id") == t["anchor"] or el.find(id=t["anchor"]) is not None

# locate start index for each toc entry
starts = []
cursor = 0
for t in toc:
    for i in range(cursor, len(stream)):
        if starts_section(*stream[i], t):
            starts.append(i)
            cursor = i + (1 if t["anchor"] else 0)
            break
    else:
        raise SystemExit(f"toc target not found: {t}")
    t["from_toc"] = True

# contributor headers the toc omits (e.g. an ANONYMOUS piece in index_split_083)
for i, (href, el) in enumerate(stream):
    # first element with text in its file, all bold, followed by a rule
    first_in_file = all(f != href or not e.get_text(strip=True) for f, e in stream[max(0, i - 3):i])
    nxt = stream[i + 1][1] if i + 1 < len(stream) else None
    if (i not in starts and el.name == "p" and el.find(class_="bold")
            and (("calibre_8" in (el.get("class") or []) and el.get("id"))
                 or (first_in_file and all_bold(el) and nxt is not None and nxt.name == "hr"))):
        label = header_lines(el)[0]
        already = any(stream[k][0] == href and k < i and
                      not any(e.get_text(strip=True) for _, e in stream[k:i]) for k in starts)
        if label == "Table of Contents" or already:
            continue
        toc.append({"label": label, "file": href, "anchor": el.get("id"), "from_toc": False})
        starts.append(i)
order = sorted(range(len(toc)), key=lambda k: starts[k])
toc, starts = [toc[k] for k in order], [starts[k] for k in order]
starts.append(len(stream))

def figure_block(img_src, section_slug):
    name = Path(img_src).stem
    meta = dict(FIGS.get(name, {}))
    block = {"type": "figure", "image": f"images/{name}.jpg"}
    block.update({k: v for k, v in meta.items() if k != "transcription_ref"})
    if "transcription" not in meta:
        ocr = ocr_dir / f"{name}.txt"
        if ocr.exists() and len(ocr.read_text().split()) > 40 and "transcription_ref" not in meta:
            block["ocr_text"] = ocr.read_text().strip()
            block["ocr_note"] = "Raw tesseract OCR of a low-resolution (512px) scan; unverified, contains errors."
    if "transcription_ref" in meta:
        block["transcription_ref"] = meta["transcription_ref"]
    return block

sections = []
for n, t in enumerate(toc):
    els = stream[starts[n]:starts[n + 1]]
    blocks, header_done = [], False
    for href, el in els:
        if el.name in ("hr", "div") and not el.find("img"):
            continue
        if el.name == "p" and not header_done and el.find(class_="bold") and (
                el.get("id") == t["anchor"] or t["anchor"] is None):
            lines = header_lines(el)
            header_done = True
            blocks.append({"type": "heading", "text": lines[0]})
            if len(lines) > 1:
                blocks.append({"type": "subtitle", "text": " ".join(lines[1:])})
            continue
        for img in el.find_all("img") if el.name != "img" else [el]:
            blocks.append(figure_block(img["src"], t["label"]))
        text = clean(inline(el))
        if not text:
            continue
        kind = "quote" if el.name == "blockquote" else "paragraph"
        if el.name == "p" and all_bold(el):
            blocks.append({"type": "subheading", "text": text.replace("**", "")})
            continue
        b = {"type": kind, "text": text}
        if all_italic(el):
            b["italic"] = True
        blocks.append(b)
    title = next((b["text"] for b in blocks if b["type"] == "subtitle"), None)
    label = t["label"]
    heading = next((b["text"] for b in blocks if b["type"] == "heading"), label)
    sections.append({"order": n + 1, "label": label, "contributor": re.sub(r"\bAnd\b", "and", heading.title()) if heading.isupper() else heading,
                     "slug": slugify(label), "title": title, "source_file": t["file"],
                     "in_epub_toc": t["from_toc"], "blocks": blocks})

# disambiguate duplicate slugs (e.g. several ANONYMOUS)
seen = {}
for s in sections:
    seen[s["slug"]] = seen.get(s["slug"], 0) + 1
    if seen[s["slug"]] > 1:
        s["slug"] = f'{s["slug"]}-{seen[s["slug"]]}'

# attach verified transcriptions referenced by figures
for s in sections:
    refs = sorted({b["transcription_ref"] for b in s["blocks"] if b.get("transcription_ref")})
    for ref in refs:
        md = (trans_dir / f"{ref}.md").read_text()
        note = re.match(r"<!--(.*?)-->", md, re.S)
        body = re.sub(r"^<!--.*?-->\s*", "", md, flags=re.S)
        last = max(i for i, b in enumerate(s["blocks"]) if b.get("transcription_ref") == ref)
        s["blocks"].insert(last + 1, {"type": "transcription", "of": ref, "method": "visual",
                                      "note": note.group(1).strip() if note else None, "text": body.strip()})

KINDS = {"AFTERWORD": "afterword", "CONTRIBUTORS": "contributors", "COLOPHON": "colophon"}
for s in sections:
    s["kind"] = KINDS.get(s["label"], "contribution")
    text = "\n".join(b.get("text", "") for b in s["blocks"] if b["type"] in ("paragraph", "quote", "transcription"))
    s["word_count"] = len(text.split())
    s["figure_count"] = sum(b["type"] == "figure" for b in s["blocks"])

# --- write ------------------------------------------------------------------
out.mkdir(parents=True, exist_ok=True)
(out / "sections").mkdir(exist_ok=True)
(out / "images").mkdir(exist_ok=True)
for img in (src / "images").glob("*.jpg"):
    shutil.copy2(img, out / "images" / img.name)
shutil.copy2(src / "cover.jpeg", out / "images" / "cover.jpeg")

book = {
    "title": "Draw It with Your Eyes Closed: The Art of the Art Assignment",
    "editor": "Paper Monument",
    "publisher": "Paper Monument / n+1 Foundation",
    "year": 2012,
    "source_file": "sources/Draw It with Your Eyes Closed-The Art of the Art Assignment.epub",
    "extraction": "EPUB XHTML parsed in spine order; section boundaries from toc.ncx anchors. "
                  "Italic/bold kept as Markdown emphasis. Images copied; text-bearing images either "
                  "transcribed visually (marked) or given raw OCR (marked unverified).",
    "sections": sections,
}
(out / "book.json").write_text(json.dumps(book, ensure_ascii=False, indent=2))

def to_md(s, img_prefix):
    lines = []
    for b in s["blocks"]:
        t = b["type"]
        if t == "heading":
            lines.append(f"## {b['text']}")
        elif t == "subtitle":
            lines.append(f"### {b['text']}")
        elif t == "subheading":
            lines.append(f"#### {b['text']}")
        elif t == "paragraph":
            lines.append(b["text"])
        elif t == "quote":
            lines.append("\n".join("> " + l for l in b["text"].split("\n")))
        elif t == "figure":
            cap = b.get("description", "")
            lines.append(f"![{cap}]({img_prefix}{b['image']})")
            if b.get("transcription"):
                lines.append("*Image text (transcribed):*\n\n" + "\n".join("> " + l for l in b["transcription"].split("\n")))
            elif b.get("ocr_text"):
                lines.append("<details><summary>Image text (raw OCR, unverified)</summary>\n\n```\n"
                             + b["ocr_text"] + "\n```\n</details>")
        elif t == "transcription":
            lines.append(f"#### Transcription of the typed pages above\n\n*{b['note']}*\n\n{b['text']}")
    if not any(b["type"] == "heading" for b in s["blocks"]):
        lines.insert(0, f"## {s['label']}")
    return "\n\n".join(lines) + "\n"

full = [f"# {book['title']}\n\nEdited by {book['editor']}. Extracted from `{book['source_file']}`.\n"]
for s in sections:
    name = f"{s['order']:02d}-{s['slug']}.md"
    (out / "sections" / name).write_text(to_md(s, "../"))
    full.append(to_md(s, ""))
(out / "full.md").write_text("\n---\n\n".join(full))
print(f"{len(sections)} sections, {sum(s['word_count'] for s in sections)} words, "
      f"{sum(s['figure_count'] for s in sections)} figures")
