"""Split a maker's reply into title, text work and statement (shared by calibration and benchmark packets)."""
import re


def split_text(text, method):
    """Separate the title (and, for text works, the work) from the statement.
    The title is shown with the statement, after the work has been judged."""
    lines = text.split("\n")
    i = next((n for n, l in enumerate(lines) if re.match(r"^\s*Artist Statement\b", l, re.I)), None)
    if i is None:
        # no label: a short first line without a full stop is the title ("“I Miss You” — Artist Statement")
        first = lines[0].strip()
        if method != "T" and len(first) < 80 and not first.endswith("."):
            title = re.sub(r"\s*[—–-]\s*Artist Statement\s*$", "", first, flags=re.I).strip("“”\" ")
            return {"title": title, "work_text": "", "statement": "\n".join(lines[1:]).strip()}
        return {"title": "", "work_text": text if method == "T" else "", "statement": "" if method == "T" else text}
    head = "\n".join(l for l in lines[:i] if l.strip()).strip()
    label = re.sub(r"^\s*Artist Statement\s*[:—–-]?\s*", "", lines[i], flags=re.I).strip().strip("“”\"")
    statement = "\n".join(lines[i + 1:]).strip()
    if method == "T":
        # text work: the work is everything before the statement (its own heading included)
        return {"title": label, "work_text": head, "statement": statement}
    title = " / ".join(x for x in [head.replace("\n", " · "), label] if x)
    return {"title": title, "work_text": "", "statement": statement}
