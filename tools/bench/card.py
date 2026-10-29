"""Judgement cards: load one, and make the blind copy a judge sees.

The blind copy drops the card's making-of fields and every evidence note, because evidence cites
packet ids and the judge-of-record's own words about works a judge may be about to see.
"""
import hashlib, json, re
from pathlib import Path

from . import ROOT

INTERNAL = ("_status", "calibration", "judge_id", "name", "version", "positions_ref", "merged_values", "canary")
LEAK = r"P\d\d|gold|audit|calibration|\bK\d\b"


def load(card_path):
    p = Path(card_path)
    if not p.is_absolute():
        p = ROOT / p
    if p.is_dir():
        p = p / "judgement_card.draft.json"
    raw = p.read_bytes()
    card = json.loads(raw)
    return {"path": str(p.relative_to(ROOT)), "version": card.get("version"), "sha256": hashlib.sha256(raw).hexdigest()[:16], "card": card}


def _scrub(x):
    if isinstance(x, dict):
        return {k: _scrub(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_scrub(v) for v in x]
    if isinstance(x, str):
        x = re.sub(r"\s*\((gold|audit|the judge does this)[^()]*(\([^()]*\)[^()]*)*\)", "", x, flags=re.I)
        x = re.sub(r"\s*The judge does this \(gold:[^)]*\)[^.]*\.", "", x)
        return re.sub(r"\s*Calibration: .*$", "", x)
    return x


def blind(card, extra_leaks=()):
    """The judge's copy: no making-of fields, no evidence notes. Raises if anything evidence-like survives."""
    c = {k: v for k, v in card.items() if k not in INTERNAL and not k.startswith("_")}
    c["scoring"] = {k: v for k, v in c.get("scoring", {}).items() if k not in ("status", "headline")}
    c["values"] = [{k: v for k, v in val.items() if k != "evidence"} for val in c.get("values", [])]
    c = _scrub(c)
    pattern = "|".join([LEAK, *map(re.escape, extra_leaks)])
    hit = re.search(pattern, json.dumps(c), re.I)
    if hit:
        raise ValueError(f"blind card still cites evidence: {hit.group(0)!r}")
    return c


def ranked_values(card):
    """The values that enter the headline, in rank order (rank set, not the gate, not feedback-only)."""
    vals = [v for v in card["values"] if v.get("rank") and not v.get("gate")]
    return [v["value_id"] for v in sorted(vals, key=lambda v: v["rank"])]


def scored_values(card):
    return [v["value_id"] for v in card["values"] if not v.get("gate")]


def proposal_cap(card):
    """The most a proposal (a visual work described, not made) can score on each ranked value, or None."""
    return (card.get("media", {}).get("made_work") or {}).get("cap")


RECOMMENDED = {"thesis": "a few sentences on what makes work matter to this judge",
               "fluent_failure": "the polished failure this judge most wants to catch",
               "feedback": "how this judge gives feedback (form, length)",
               "statement": "what an artist statement can do for or against a work",
               "anti_goals": "things this judge never does"}


def check(card):
    """(problems, notes) for a card. Problems stop a run; notes are sections the card would be better with."""
    P, N = [], []
    if not isinstance(card.get("values"), list) or not card["values"]:
        return ["the card needs a list of values"], N
    ids = [v.get("value_id") for v in card["values"]]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and re.fullmatch(r"[a-z][a-z0-9_]*", i) for i in ids):
        P.append("every value needs a unique value_id in snake_case (e.g. new_ground)")
    for v in card["values"]:
        for k in ("label", "definition"):
            if not v.get(k):
                P.append(f"value {v.get('value_id')!r} needs a {k}")
    gates = [v for v in card["values"] if v.get("gate")]
    if len(gates) != 1 or gates[0].get("value_id") != "impact":
        P.append("exactly one value must be the gate (\"gate\": true), with value_id \"impact\": judges answer it yes or no")
    elif not gates[0].get("decision"):
        P.append("the impact gate needs a \"decision\": when to say yes and when to say no")
    ranks = [v.get("rank") for v in card["values"] if not v.get("gate") and v.get("rank") is not None]
    if not ranks:
        P.append("at least one non-gate value needs a rank (1 = most important); ranked values make the headline score")
    elif not all(isinstance(r, int) and r > 0 for r in ranks) or len(set(ranks)) != len(ranks):
        P.append("ranks must be distinct positive whole numbers (use null for a value that is scored but not ranked)")
    mw = card.get("media", {}).get("made_work")
    if mw is not None and not (isinstance(mw.get("cap"), int) and 0 <= mw["cap"] <= 4 and mw.get("rule")):
        P.append("media.made_work needs a rule and a cap from 0 to 4")
    if not card.get("version"):
        P.append("the card needs a version, e.g. \"0.1\"")
    try:
        blind(card)
    except ValueError as e:
        P.append(f"{e}: notes citing packet ids or calibration evidence must be removed from the judge's copy")
    for k, why in RECOMMENDED.items():
        if not card.get(k):
            N.append(f"no {k}: {why}")
    return P, N
