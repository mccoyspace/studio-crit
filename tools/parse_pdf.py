"""Extract 'I Like Your Work: Art and Etiquette' (scanned PDF) into structured JSON + Markdown.

Works from tesseract TSV output (one file per page, 300dpi, --psm 6), using line geometry
to rebuild paragraphs, numbered lists, and the questionnaire structure.

usage: python3 -I parse_pdf.py <ocr_dir> <corrections.json> <out_dir> <page_png_dir>
"""
import csv, difflib, json, re, shutil, sys
from pathlib import Path
from statistics import median

ocr, corrections_path, out, png_dir = map(Path, sys.argv[1:5])
CORRECTIONS = json.loads(corrections_path.read_text())
DICT = {w.strip().lower() for w in open("/usr/share/dict/words")}

CONTRIBUTORS = """JAMES BAE|JAY BATLLE|ANDREW BERARDINI|DIKE BLAIR|MATTHEW BRANNON|SARI CAREL|NAOMI FRY|
MARIA ELENA GONZALEZ|MICHELLE GRABNER|ETHAN GREENBAUM|SARA GREENBERGER RAFFERTY|A.S. HAMRAH|
STEFFANI JEMISON|PADDY JOHNSON|ANGIE KEEFER|PREM KRISHNAMURTHY|DAVID LEVINE|PAM LINS|JASON MURISON|
DAN NADEL|BOB NICKAS|WENDY OLSOFF|DUSHKO PETROVICH|KASPAR PINCIS|RICHARD RYAN|JESSICA SLAVEN|
RYAN STEADMAN|AMANDA TRAGER|RACHEL UFFNER|ROGER WHITE|ANONYMOUS""".replace("\n", "").split("|")

QUESTIONS = [
    ("rules", "What are the rules of etiquette for the art world?",
     ["What is the role of etiquette in the art world?"]),
    ("memorable_situation", "Was etiquette foregrounded in any memorable situation?", []),
    ("customs", "What customs or mannerisms are particular to the art world?", []),
    ("breach", "When does breach of etiquette play a role in embarrassing or awkward encounters?",
     ["When does breach of etiquette lead to embarrassing or awkward encounters?"]),
    ("maxim", "How should people behave? What would be a maxim for appropriate conduct?",
     ["How should people behave? What would be a maxim for conduct?"]),
    ("financial_shift", "Has there been a shift in etiquette as the financial climate has changed?", []),
    ("bad_manners", "What constitutes bad manners?", []),
]

CONTRIB_PAGES = range(5, 57)   # pdf pages holding contributions (book p.3–54)
BIOS_PAGE, COLOPHON_PAGE, BACK_PAGE = 58, 59, 60
PAGE_OFFSET = 2                # book page = pdf page - 2

# Pam Lins's contribution is an Artforum review page redacted with black marker; OCR of it
# is noise, so it is represented by the page image and a description instead.
IMAGE_PAGES = {45: {
    "image": "images/pam-lins-p43.png",
    "description": "A clipped page from Artforum (March 2009), REVIEWS section: a review of an exhibition "
                   "of painted wooden pedestals topped with small striped acrylic paintings, with most of the "
                   "review text blacked out by hand in heavy marker so that only scattered phrases remain "
                   "legible. The page includes a reproduction of two pedestal sculptures.",
    "kind": "artwork",
}}


def load_lines(path):
    rows = list(csv.DictReader(path.open(), delimiter="\t", quoting=csv.QUOTE_NONE))
    lines = {}
    for r in rows:
        if r["level"] == "5" and r["text"].strip():
            key = (int(r["block_num"]), int(r["par_num"]), int(r["line_num"]))
            lines.setdefault(key, []).append(r)
    out = []
    for words in lines.values():
        left = min(int(w["left"]) for w in words)
        right = max(int(w["left"]) + int(w["width"]) for w in words)
        top = min(int(w["top"]) for w in words)
        height = median(int(w["height"]) for w in words)
        conf = sum(float(w["conf"]) for w in words) / len(words)
        out.append({"left": left, "right": right, "top": top, "height": height, "conf": conf,
                    "text": " ".join(w["text"] for w in words)})
    return sorted(out, key=lambda l: l["top"])


def recover_questions(pg, lines):
    """Questions are set small above a printed rule and tesseract's page pass often drops
    them, leaving a tall gap. Re-OCR each gap (and the page head) in sparse-text mode and
    return any questionnaire prompts found there as synthetic lines."""
    from PIL import Image
    import subprocess
    if not lines:
        return []
    gaps = [b["top"] - a["top"] for a, b in zip(lines, lines[1:])]
    spacing = median(gaps) if gaps else 45
    bands = [(0, lines[0]["top"] - 4)]
    bands += [(a["top"] + a["height"] + 4, b["top"] - 4)
              for a, b in zip(lines, lines[1:]) if b["top"] - a["top"] > 1.8 * spacing]
    im = None
    found = []
    for y0, y1 in bands:
        if y1 - y0 < 30:
            continue
        cache = ocr / "bands" / f"pg-{pg:02d}-{y0}-{y1}.txt"
        if not cache.exists():
            im = im or Image.open(png_dir / f"pg-{pg:02d}.png")
            band = im.crop((0, y0, im.width, y1))
            band = band.resize((band.width * 2, band.height * 2))
            cache.parent.mkdir(exist_ok=True)
            tmp = cache.with_suffix(".png")
            band.save(tmp)
            r = subprocess.run(["tesseract", str(tmp), "-", "--psm", "11"], capture_output=True, text=True)
            cache.write_text(r.stdout)
        for t in cache.read_text().splitlines():
            qid, qtext = match_question(t.strip())
            if qid:
                found.append({"left": 0, "right": 0, "top": (y0 + y1) // 2, "height": 20, "conf": 99,
                              "text": qtext, "recovered": True})
    return found


def norm(s):
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def match_question(text):
    """Return (question_id, cleaned text) if the line is one of the questionnaire prompts.

    Question lines sit above a printed rule, which OCR sometimes appends as junk after
    the final '?', so candidates are cut at each '?' and compared without spaces."""
    cuts = [text[:m.end()] for m in re.finditer(r"\?", text)] or [text]
    best, score, best_cut = None, 0.0, text
    for cut in cuts:
        for qid, canon, variants in QUESTIONS:
            for v in [canon] + variants:
                r = difflib.SequenceMatcher(None, norm(cut).replace(" ", ""), norm(v).replace(" ", "")).ratio()
                if r > score:
                    best, score, best_cut = qid, r, v
    # return the printed wording (canonical or variant) rather than the noisy OCR
    return (best, best_cut) if score >= 0.85 else (None, text)


def match_contributor(text):
    t = re.sub(r"[^A-Z. ]", "", text.upper()).strip()
    if not t or t != re.sub(r"[^A-Z. ]", "", text).strip():  # must already be all caps
        return None
    for name in CONTRIBUTORS:
        if difflib.SequenceMatcher(None, t, name).ratio() >= 0.9:
            return name
    return None


def is_junk(line):
    t = line["text"]
    letters = sum(c.isalpha() for c in t)
    if letters == 0:
        return True
    # rule lines and scan specks read as strings like "a ee OE LUT 5 © 02 oO"
    tokens = [w.strip(".,;:!?()“”\"'’").lower() for w in t.split()]
    tokens = [w for w in tokens if len(w) > 1]
    known = sum(w in DICT or w.rstrip("s") in DICT for w in tokens)
    has_word = any(len(w) > 3 and w in DICT for w in tokens)
    if letters / max(1, len(t.replace(" ", ""))) < 0.5 and not has_word:
        return True
    if line["conf"] < 55 and len(t) <= 14 and not has_word:
        return True
    # foreign-language prose (Keefer's Sartre quote) is also off-dictionary, but junk is
    # mostly short or capitalised fragments
    if line["conf"] < 80 and tokens and known / len(tokens) < 0.5:
        raw = [w for w in t.split() if len(w) > 1]
        mean_len = sum(map(len, raw)) / max(1, len(raw))
        upper = sum(w.isupper() for w in raw) / max(1, len(raw))
        if mean_len < 3.5 or upper > 0.5:
            return True
    return False


I_FOLLOWERS = ("would|imagined|probably|first|think|am|have|had|was|do|did|can|could|guess|know|mean|really|"
               "remember|try|want|wish|just|still|also|never|always|don’t|didn’t|can’t|haven’t|wasn’t|’m|’ve|’d|’ll")


def fix(text):
    # a vertical bar is either a misread capital I or a speck from the scan's gutter
    text = re.sub(rf"(^|\s)[|](?=\s+(?:{I_FOLLOWERS})\b)", r"\1I", text)
    text = re.sub(r"\s[|](?=\s)", "", text)
    text = re.sub(r"(^|\s)1(?=\s?(?:am|think|have)\b)", r"\1I", text).replace("Iam ", "I am ")
    text = text.replace("——", "—")
    for wrong, right in CORRECTIONS["words"].items():
        text = re.sub(rf"(?<![\w’']){re.escape(wrong)}(?!\w)", right, text)
    for wrong, right in CORRECTIONS["phrases"].items():
        text = text.replace(wrong, right)
    return text


def join_lines(parts):
    text = ""
    for p in parts:
        if not text:
            text = p
        elif re.search(r"[a-z]-$", text) and re.match(r"[a-z]", p):
            text = text[:-1] + p          # rejoin word hyphenated across lines
        elif text.endswith("—") or text.endswith("/"):
            text += p
        else:
            text += " " + p
    return text


# item numbers are old-style figures: "9" often reads as "g"; Batlle has an item "5.5"
LIST_START = re.compile(r"^(\d{1,2}(?:[.·:-]\d)?|g)[.:]?\s+(?=[A-Za-z“\"(])")

def normalise_number(num, prev):
    """Map OCR misreads of old-style figures back onto the running sequence."""
    if num == "g":
        return "9"
    if prev and re.fullmatch(r"\d+", prev) and re.fullmatch(r"\d+", num):
        expected = int(prev) + 1
        if int(num) != expected and abs(int(num) - expected) > 5:
            return str(expected)
    return num.replace("-", ".").replace(":", ".").replace("·", ".")


last_number = {}
sections, cur = [], None
pending = []  # lines of the current paragraph: (text)
mode = None   # None | ("list", hang_left)


def close():
    global mode
    if mode:
        flush("list_item", number=mode[2])
    else:
        flush()
    mode = None


def flush(kind="paragraph", **extra):
    global pending
    text = fix(join_lines(pending)).strip() if pending else ""
    if text and cur is not None:
        cur["blocks"].append({"type": kind, "text": text, **extra})
    pending = []


for pg in CONTRIB_PAGES:
    book_page = pg - PAGE_OFFSET
    if pg in IMAGE_PAGES:
        close()
        cur = {"contributor": "PAM LINS", "title": None, "start_page": book_page, "blocks": []}
        sections.append(cur)
        cur["blocks"].append({"type": "figure", **IMAGE_PAGES[pg]})
        shutil.copy2(png_dir / f"pg-{pg:02d}.png", out / IMAGE_PAGES[pg]["image"])
        continue
    lines = load_lines(ocr / f"pg-{pg:02d}.tsv")
    if not lines:
        continue
    # drop page number / folio at the bottom
    if len(lines[-1]["text"]) <= 3:
        lines = lines[:-1]
    body = [l for l in lines if not is_junk(l)]
    have = {match_question(l["text"])[0] for l in body} - {None}
    extra = [q for q in recover_questions(pg, body) if match_question(q["text"])[0] not in have]
    body = sorted(body + extra, key=lambda l: l["top"])
    lefts = sorted(l["left"] for l in body) or [0]
    margin = lefts[max(0, len(lefts) // 10)]
    rights = sorted(l["right"] for l in body if not l.get("recovered")) or [0]
    right_edge = rights[int(len(rights) * 0.9)]
    gaps = [b["top"] - a["top"] for a, b in zip(body, body[1:])]
    spacing = median(gaps) if gaps else 45
    prev = None
    for i, l in enumerate(body):
        text = l["text"].strip()
        name = match_contributor(text)
        if name:
            close()
            cur = {"contributor": name, "title": None, "start_page": book_page, "blocks": []}
            sections.append(cur)
            prev = l
            continue
        qid, qtext = match_question(text)
        if qid:
            close()
            cur["blocks"].append({"type": "question", "question_id": qid, "text": fix(qtext)})
            last_number.pop(id(cur), None)  # each answer numbers its own list
            prev = l
            continue
        no_body_yet = not any(b["type"] != "subtitle" for b in cur["blocks"]) and not pending
        if no_body_yet and text.upper() == text and sum(c.isalpha() for c in text) > 3:
            title = text.strip("()| ")
            cur["title"] = (cur["title"] + " / " + title) if cur["title"] else title
            cur["blocks"].append({"type": "subtitle", "text": text})
            prev = l
            continue
        # scans are skewed, so measure indent and line length against neighbouring lines
        near = [x for x in body[max(0, i - 4):i + 5] if not x.get("recovered")]
        margin = min(x["left"] for x in near)
        right_edge = max(x["right"] for x in near)
        indent = l["left"] - margin
        gap = (l["top"] - prev["top"]) if prev is not None else 0
        m = LIST_START.match(text)
        if m and m.group(1) == "1" and re.match(r"(?:think|am|have|had|was|would)\b", text[m.end():]):
            m = None  # "1 think" is OCR for "I think"
        if m and text[m.end()].islower():
            # lowercase items (one anonymous respondent) only count if they continue a sequence
            prev_num = mode[2] if mode else last_number.get(id(cur))
            ok = m.group(1) == "1" or (prev_num and prev_num.isdigit() and m.group(1) == str(int(prev_num) + 1))
            m = m if ok else None
        if m and indent < 40:
            num = m.group(1)
            prev_num = mode[2] if mode else last_number.get(id(cur))
            num = normalise_number(num, prev_num)
            close()
            mode = ("list", l["left"] + 40, num)
            last_number[id(cur)] = num
            pending = [text[m.end():]]
            cur.setdefault("_items", 0)
            prev = l
            continue
        if mode and l["left"] >= mode[1]:
            pending.append(text)          # hanging-indent continuation of a list item
            prev = l
            continue
        if mode:
            flush("list_item", number=mode[2]); mode = None
        short_prev = (prev is not None and pending and not prev.get("recovered")
                      and prev["right"] < margin + 0.65 * (right_edge - margin) and text[:1].isupper())
        # two consecutive lines at the same indent are a hanging block, not a new paragraph
        hanging = (prev is not None and pending and not prev.get("recovered")
                   and abs(l["left"] - prev["left"]) < 12 and prev["left"] - margin > 20)
        new_para = (indent > 20 and not hanging) or short_prev or (prev is not None and gap > 1.7 * spacing and pending)
        if new_para:
            flush()
        pending.append(text)
        prev = l
    # paragraphs may run across pages: only break on the next page's signals
flush("list_item", number=mode[2]) if mode else flush()

# list items were flushed as plain paragraphs with a number; normalise their type
for s in sections:
    s.pop("_items", None)
    for b in s["blocks"]:
        if "number" in b:
            b["type"] = "list_item"

# --- group questionnaire answers --------------------------------------------
for s in sections:
    qs = [b for b in s["blocks"] if b["type"] == "question"]
    s["form"] = "questionnaire" if len(qs) >= 2 else "essay"
    if s["form"] == "questionnaire":
        preamble, answers, current = [], [], None
        for b in s["blocks"]:
            if b["type"] == "question":
                current = {"question_id": b["question_id"], "question": b["text"], "answer": []}
                answers.append(current)
            elif current is None:
                preamble.append(b)
            else:
                current["answer"].append(b)
        s["answers"] = answers
    text = " ".join(b.get("text", "") for b in s["blocks"] if b["type"] != "question")
    s["word_count"] = len(text.split())

# --- slugs / names -------------------------------------------------------------
seen = {}
for n, s in enumerate(sections, 1):
    s["order"] = n
    name = s["contributor"]
    s["contributor"] = name.title()
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    seen[slug] = seen.get(slug, 0) + 1
    s["slug"] = slug if seen[slug] == 1 else f"{slug}-{seen[slug]}"

# --- bios, colophon, back cover -------------------------------------------------
def plain_lines(path):
    # bios and colophon are mostly proper names, so skip the dictionary-based junk test
    return [fix(l["text"]) for l in load_lines(path)
            if sum(c.isalpha() for c in l["text"]) >= 2 and l["conf"] >= 40]

bio_lines = plain_lines(ocr / "bios-L.tsv") + plain_lines(ocr / "bios-R.tsv")
bios, curb = [], None
for t in bio_lines:
    m = re.match(r"^([A-ZÁÉ][A-ZÁÉ. ]+[A-Z])\s*(?:\((?:p\.)?(\d+)\))?", t)
    if m and m.group(1).strip().replace("Á", "A") in CONTRIBUTORS + ["SARA GREENBERGER"]:
        curb = {"name": m.group(1).strip(), "text": [t]}
        bios.append(curb)
    elif curb:
        curb["text"].append(t)
for b in bios:
    # the bios face uses periods the OCR reads as commas at line ends
    b["text"] = re.sub(r",$", ".", join_lines(b["text"]).replace(", He ", ". He "))
    pm = re.search(r"\(p\.(\d+)\)", b["text"])
    b["page"] = int(pm.group(1)) if pm else None

colophon = "\n".join(plain_lines(ocr / f"pg-{COLOPHON_PAGE:02d}.tsv"))
back = [l for l in load_lines(ocr / f"pg-{BACK_PAGE:02d}.tsv")]
blurb_lines = []
for l in back:
    if l["text"].startswith("CONTRIBUTIONS"):
        break
    blurb_lines.append(l)
blurb, para = [], []
for a, b in zip([None] + blurb_lines, blurb_lines):
    if a is not None and b["top"] - a["top"] > 70:
        blurb.append(join_lines(para)); para = []
    para.append(b["text"])
blurb.append(join_lines(para))

book = {
    "title": "I Like Your Work: Art and Etiquette",
    "editor": "Paper Monument",
    "year": 2009,
    "source_file": "sources/I like your work-art and etiquette.pdf",
    "source_note": "Internet Archive scan (archive.org/details/ilikeyourworkart0000unse), seventh printing 2016.",
    "extraction": "Pages re-OCRed with tesseract (300dpi, psm 6); paragraphs, numbered lists, headings and "
                  "questionnaire questions rebuilt from line geometry; common OCR errors corrected from a "
                  "reviewed list (corrections.json). Expect residual OCR errors.",
    "questionnaire": [{"id": q, "question": c, "variants": v} for q, c, v in QUESTIONS],
    "introduction": [fix(p) for p in blurb],
    "sections": sections,
    "contributors": bios,
    "colophon": colophon,
}
(out / "book.json").write_text(json.dumps(book, ensure_ascii=False, indent=2))


def to_md(s, img_prefix):
    title = f" — {s['title'].title()}" if s["title"] else ""
    lines = [f"## {s['contributor']}{title}", f"*Book page {s['start_page']} · {s['form']}*"]
    for b in s["blocks"]:
        t = b["type"]
        if t == "subtitle":
            continue
        if t == "question":
            lines.append(f"**{b['text']}**")
        elif t == "list_item":
            lines.append(f"{b['number']}. {b['text']}")
        elif t == "paragraph":
            lines.append(b["text"])
        elif t == "figure":
            lines.append(f"![{b['description']}]({img_prefix}{b['image']})\n\n*{b['description']}*")
    return "\n\n".join(lines) + "\n"


(out / "sections").mkdir(exist_ok=True)
full = [f"# {book['title']}\n\nEdited by {book['editor']} ({book['year']}). Extracted from `{book['source_file']}`.\n",
        "## Introduction (back cover)\n\n" + "\n\n".join(book["introduction"])]
for s in sections:
    (out / "sections" / f"{s['order']:02d}-{s['slug']}.md").write_text(to_md(s, "../"))
    full.append(to_md(s, ""))
full.append("## Contributors\n\n" + "\n\n".join(b["text"] for b in bios))
full.append("## Colophon\n\n" + colophon.replace("\n", "  \n"))
(out / "full.md").write_text("\n---\n\n".join(full))
print(f"{len(sections)} sections, {sum(s['word_count'] for s in sections)} words, "
      f"{sum(s['form'] == 'questionnaire' for s in sections)} questionnaires, {len(bios)} bios")
