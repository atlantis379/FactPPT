"""Context signals for an excerpt: where a verbatim quote may have lost what surrounds it.

Repeated review rounds kept finding the same shapes: a lead-in ("may consider the following:") shown without
its list, a quote opening with "however" whose contrasted sentence is not on the page, and a quote cut from a
longer unit whose remainder carries a condition or a stop rule. These are shape signals only (word lists in
config/factdeck_lexicon.json, `context_signals`); they prompt the page author and the reviewer and never reject.
"""
from __future__ import annotations

from factdeck.lexicon import canon, lexicon, locate

SHOWN_REST = 160


NOTES = {"lead_in": "显示文字是列表或下文的引导句，须同时呈现它引出的全部条目，或在页面说明只展示其中一部分",
         "leading_connective": "以转折/承接词开头：它所承接或对照的前文须在本页（或紧邻页）呈现，否则关系不清",
         "unit_continues": "原文单元在引文之后还有内容：核对其中是否有条件、例外、停止规则或其余列表项",
         "unit_precedes": "原文单元在引文之前还有内容：核对上位条件、适用人群或被转折的前句"}


def _cfg() -> dict:
    return lexicon().get("context_signals") or {}


def signals(quote: str, display: str | None, unit_text: str) -> list[dict]:
    """[{kind, text?}] for one fact (meaning of each kind in NOTES): kinds lead_in, leading_connective, unit_continues, unit_precedes."""
    shown = (display or quote or "").strip()
    out = []
    tail = shown.rstrip("　 ").lower()
    if any(tail.endswith(e.lower()) for e in _cfg().get("lead_in_endings", [])):
        out.append({"kind": "lead_in"})
    head = shown.lstrip("“\"'（( ")
    con = next((c for c in _cfg().get("leading_connectives", []) if head.lower().startswith(c.lower())), None)
    if con:
        out.append({"kind": "leading_connective", "text": con})
    span = locate(unit_text or "", quote or "") if quote else None
    if span:
        before, after = unit_text[:span[0]].strip(), unit_text[span[1]:].strip()
        if canon(after):
            out.append({"kind": "unit_continues", "text": after[:SHOWN_REST]})
        if canon(before):
            out.append({"kind": "unit_precedes", "text": before[-SHOWN_REST:]})
    return out


def unshown_lead_ins(page_facts: list[str], facts: dict, units: dict, next_of: dict) -> list[str]:
    """Lead-in facts on a page with nothing of what they introduce: no other fact from the same unit (its list
    carved into items) and no fact from the unit that follows it in the source."""
    shown = {(facts.get(x) or {}).get("unit") for x in page_facts}
    out = []
    for fid in page_facts:
        f = facts.get(fid) or {}
        u = units.get(f.get("unit"))
        if f.get("figure") or not u:
            continue
        if not any(s["kind"] == "lead_in" for s in signals(f.get("quote", ""), f.get("display"), u["text"])):
            continue
        same = any(x != fid and (facts.get(x) or {}).get("unit") == u["id"] for x in page_facts)
        if not same and next_of.get(u["id"]) not in shown:
            out.append(fid)
    return out
