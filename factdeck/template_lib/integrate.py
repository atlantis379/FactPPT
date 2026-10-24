"""The layout selector as the decider for template-library pages.

`decide()` runs `selector.select_deck` on every page's content (title, text, structured data) and returns one
inspectable decision per page.  A layout proposed by a worker / page plan (`proposed_layout`, or `layout` when a
plan carries one) is kept only when it is among the selector's *qualified* candidates for that page; otherwise the
selector's choice replaces it and the record says why.  Cover / section pages follow their page kind.

Nothing here edits page content: a layout whose minimum data is missing is never "filled in"; it is downgraded by
the selector (see selector.DOWNGRADE) or the proposal is overridden.  The LLM tie-break stays off unless a
tie-breaker is passed in.
"""
from __future__ import annotations

import math
from typing import Any

from . import selector as S

# Plan-side aliases a worker may write for a selector layout id.
ALIASES = {
    "evidence_takeaways": "key_points/evidence_takeaways",
    "key_points/cards": "key_points",
    "endpoint_readout": ("endpoint_readout/bar", "endpoint_readout/line"),
    "endpoint_bar": "endpoint_readout/bar",
    "endpoint_line": "endpoint_readout/line",
}


def normalize_layout(value: Any) -> tuple[str, ...]:
    """Proposal → acceptable selector layout ids (empty when unknown)."""
    if not isinstance(value, str) or not value.strip():
        return ()
    v = value.strip()
    if v in S.LAYOUTS:
        return (v,)
    a = ALIASES.get(v)
    if isinstance(a, str):
        return (a,)
    return tuple(a or ())


def proposal_of(page: dict) -> str | None:
    for key in ("proposed_layout", "layout"):
        v = page.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _chosen(layout: str) -> dict:
    fam, var, name, chart = S.LAYOUTS[layout]
    return {"layout": layout, "family": fam, "variant": var, "name_zh": name, "is_chart": chart}


def decide(pages: list[dict], *, tiebreaker: S.TieBreaker | None = None, extra_signals: dict | None = None,
           chart_ratio: float = 1 / 3) -> dict:
    """Selector decision per page + proposal keep/override.  Returns {"decisions": [...], "stats": {...}}."""
    sel = S.select_deck(pages, tiebreaker=tiebreaker, extra_signals=extra_signals, chart_ratio=chart_ratio)
    out = []
    kept, overridden, unproposed = [], [], []
    for page, d in zip(pages, sel["decisions"]):
        d = dict(d)
        proposal = proposal_of(page)
        selector_choice = d["chosen"]["layout"]
        qualified = [c["layout"] for c in d["candidates"] if c.get("qualified")]
        rec = {"proposed": proposal, "status": "none", "selector_choice": selector_choice,
               "qualified_candidates": qualified, "reason_zh": ""}
        if d["kind"] in S.EXEMPT_KINDS:
            rec["status"] = "exempt"
            rec["reason_zh"] = f"{S.LAYOUTS[d['kind']][2]}由页面类型决定"
            if proposal and proposal != d["kind"]:
                rec["reason_zh"] += f"，忽略提议版式 {proposal}"
        elif not proposal:
            unproposed.append(d["page_id"])
            rec["reason_zh"] = "页面规划未提议版式，采用选择器结果"
        else:
            want = normalize_layout(proposal)
            ok = [w for w in want if w in qualified]
            if ok:
                keep = selector_choice if selector_choice in ok else ok[0]
                kept.append(d["page_id"])
                rec["status"] = "kept"
                score = next(c["score"] for c in d["candidates"] if c["layout"] == keep)
                if keep == selector_choice:
                    rec["reason_zh"] = f"提议版式 {proposal} 即选择器首选，保留"
                else:
                    rec["reason_zh"] = (f"提议版式 {proposal} 在合格候选中（分数 {score}），保留；"
                                        f"选择器首选为{S.LAYOUTS[selector_choice][2]}")
                    d["chosen"] = _chosen(keep)
                    d["reason_zh"] = f"按页面规划保留{S.LAYOUTS[keep][2]}（合格候选，分数 {score}）；选择器理由：{d['reason_zh']}"
            else:
                overridden.append(d["page_id"])
                rec["status"] = "overridden"
                if not want:
                    why = f"未知版式 {proposal}"
                else:
                    gaps = [S.requirement_gap(w, page) for w in want]
                    gap = next((g for g in gaps if g), None)
                    why = (f"{S.LAYOUTS[want[0]][2]}不满足最低数据要求：{gap}" if gap
                           else f"{S.LAYOUTS[want[0]][2]}不在本页合格候选中（内容未体现该关系）")
                rec["reason_zh"] = f"提议版式 {proposal} 被替换为{S.LAYOUTS[selector_choice][2]}：{why}"
        d["proposal"] = rec
        out.append(d)
    return {"decisions": out, "stats": final_stats(out, chart_ratio, sel["stats"],
                                                   kept=kept, overridden=overridden, unproposed=unproposed)}


def final_stats(decisions: list[dict], chart_ratio: float, selector_stats: dict, **proposals) -> dict:
    """Deck stats recomputed on the *final* layouts (after keeping proposals)."""
    content = [d for d in decisions if d["kind"] not in S.EXEMPT_KINDS]
    charts = sum(d["chosen"]["is_chart"] for d in content)
    need = math.ceil(len(content) * chart_ratio)
    repeats = [b["page_id"] for a, b in zip(content, content[1:]) if a["chosen"]["layout"] == b["chosen"]["layout"]]
    counts: dict[str, int] = {}
    for d in decisions:
        counts[d["chosen"]["layout"]] = counts.get(d["chosen"]["layout"], 0) + 1
    return {**selector_stats, "chart_pages": charts,
            "chart_ratio": round(charts / len(content), 3) if content else 0.0,
            "chart_target_met": charts >= need, "consecutive_repeats": repeats, "layout_counts": counts,
            "selector_only": {k: selector_stats[k] for k in ("chart_pages", "chart_ratio", "consecutive_repeats")},
            "proposals": proposals}


def page_record(decision: dict) -> dict:
    """Compact, inspectable record stored on the page / deck spec."""
    return {
        "layout": decision["chosen"]["layout"], "family": decision["chosen"]["family"],
        "variant": decision["chosen"]["variant"], "name_zh": decision["chosen"]["name_zh"],
        "is_chart": decision["chosen"]["is_chart"],
        "relation": decision["relation"], "relation_zh": decision["relation_zh"], "signals": decision["signals"],
        "candidates": decision["candidates"], "downgrades": decision["downgrades"],
        "tie_break": decision["tie_break"], "rhythm_adjustments": decision["rhythm_adjustments"],
        "reason_zh": decision["reason_zh"], "proposal": decision.get("proposal"),
    }


def resolve_fill(page: dict, decision: dict) -> tuple[str, dict | None, str | None]:
    """The fill for the decided layout.  When the plan has no fill for it, fall back to the best *qualified*
    candidate that has one (recorded); never invent a fill."""
    fills = page.get("fills") or {}
    lay = decision["chosen"]["layout"]
    if lay in fills:
        return lay, fills[lay], None
    for c in decision["candidates"]:
        if c.get("qualified") and c["layout"] in fills:
            return c["layout"], fills[c["layout"]], (f"计划中没有{S.LAYOUTS[lay][2]}的填充，改用合格候选"
                                                     f"{S.LAYOUTS[c['layout']][2]}的填充")
    return lay, None, f"计划中没有{S.LAYOUTS[lay][2]}或任何合格候选的填充，未渲染"


# ------------------------------------------------------------------ FactDeck deck spec pages (factdeck/deck.py)

def _ref_text(ref: Any, facts: dict) -> str:
    if isinstance(ref, dict):
        if "fact" in ref:
            f = facts.get(ref["fact"]) or {}
            return str(f.get("display") or f.get("quote") or "")
        if "text" in ref and len(ref) == 1:
            return str(ref["text"])
    return ""


def _texts(node: Any, facts: dict, skip=frozenset({"id", "layout", "template", "edges", "design", "focus"})) -> list[str]:
    if isinstance(node, dict):
        t = _ref_text(node, facts)
        if t or ("fact" in node or ("text" in node and len(node) == 1)):
            return [t] if t else []
        out: list[str] = []
        for k, v in node.items():
            if k not in skip:
                out += _texts(v, facts)
        return out
    if isinstance(node, list):
        return [t for v in node for t in _texts(v, facts)]
    return []


def deck_page_input(page: dict, facts: dict) -> dict:
    """Selector input for a FactDeck deck-spec page, built only from the page's own fact references and authored
    labels (fact-only content: no data is derived beyond what the page already shows)."""
    lay = page.get("layout")
    data: dict[str, Any] = {}
    if lay == "table" and page.get("rows"):
        cols = [c if isinstance(c, str) else _ref_text(c, facts) for c in page.get("columns") or []]
        data["table"] = {"columns": cols[1:],
                         "rows": [{"label": " ".join(_texts(r[0], facts)) if r else "",
                                   "cells": [" ".join(_texts(c, facts)) for c in r[1:]]} for r in page["rows"]]}
    elif lay == "flow":
        data["steps"] = [{"heading": " ".join(_texts(n.get("ref") or n, facts))} for n in page.get("nodes") or []]
    elif lay == "timeline":
        data["steps"] = [{"when": " ".join(_texts(s.get("when"), facts)), "heading": " ".join(_texts(s.get("what"), facts))}
                         for s in page.get("steps") or []]
    elif lay == "compare" and len(page.get("panels") or []) == 2:
        data["sides"] = [{"items": [{"text": t} for t in _texts(p, facts)]} for p in page["panels"]]
    elif lay in ("bullets", "cards", "grid", "closing"):
        key = {"bullets": "items", "cards": "cards", "grid": "tiles", "closing": "items"}[lay]
        data["items"] = [{"text": " ".join(_texts(x, facts))} for x in page.get(key) or []]
    kind = "cover" if lay == "cover" else "section" if lay == "divider" else "content"
    tmpl = page.get("template") if isinstance(page.get("template"), dict) else {}
    return {"id": page.get("id"), "kind": kind, "title": " ".join(_texts(page.get("title"), facts)),
            "text": _texts({k: v for k, v in page.items() if k != "title"}, facts), "data": data,
            "proposed_layout": tmpl.get("layout")}


def deck_template_decisions(deck: dict, facts: dict, *, extra_signals: dict | None = None) -> dict:
    """For deck specs whose pages opt into the template library (`"template": {"layout": <proposal or null>}`):
    selector decision per opted-in page.  Returns {} when no page opts in."""
    pages = [p for p in deck.get("pages") or [] if isinstance(p, dict)]
    flagged = [p for p in pages if "template" in p]
    if not flagged:
        return {}
    res = decide([deck_page_input(p, facts) for p in flagged], extra_signals=extra_signals)
    return {"pages": {d["page_id"]: page_record(d) for d in res["decisions"]}, "stats": res["stats"]}
