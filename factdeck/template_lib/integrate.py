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


# ------------------------------------------------------------------ selector input from a slot fill
# (structured data derived mechanically from the fill; shown strings only, no new content)

SKIP_KEYS = {"id", "page", "figure", "source", "data_note", "abbrev", "theme", "variant", "role", "kind", "mark",
             "key", "target", "status", "refs", "short", "rail_label", "legend", "today_label", "axis"}


def flatten(fill, out=None, key=None):
    out = [] if out is None else out
    if key in SKIP_KEYS:
        return out
    if isinstance(fill, str):
        s = " ".join(fill.split())
        if s and s not in out:
            out.append(s)
    elif isinstance(fill, dict):
        for k, v in fill.items():
            flatten(v, out, k)
    elif isinstance(fill, list):
        for v in fill:
            flatten(v, out, key)
    return out


def _tk(fill):
    return [{k: t.get(k) for k in ("value", "unit", "text", "quote", "loc") if t.get(k)}
            for t in fill.get("takeaways") or fill.get("items") or []]


def data_from_fill(family, variant, f):
    if family in ("cover", "section"):
        return {}
    if family == "key_points" and variant == "evidence_takeaways":
        return {"takeaways": _tk(f)}
    if family == "key_points":
        return {"items": [{"heading": i.get("heading"), "body": i.get("body")} for i in f["items"]]}
    if family == "comparison":
        if f.get("rows"):
            return {"sides": [{"label": f["left_label"], "items": [r["left"] for r in f["rows"]]},
                              {"label": f["right_label"], "items": [r["right"] for r in f["rows"]]}]}
        return {"sides": [{"label": f["left_label"], "items": [i["text"] for i in f["left_items"]]},
                          {"label": f["right_label"], "items": [i["text"] for i in f["right_items"]]}]}
    if family == "flow":
        return {"steps": [{"heading": n["heading"], "body": n.get("body")} for n in f["nodes"]]}
    if family == "timeline":
        return {"steps": [{"when": n["label"], "heading": n["heading"], "body": n.get("body")} for n in f["nodes"]]}
    if family == "algorithm_tree":
        return {"conditions": [{"test": f"{f['decision_heading']} {f['decision_threshold']}",
                                "yes": f["yes_heading"], "no": f["no_heading"]}]}
    if family == "assessment_matrix":
        return {"axes": {"x": [f["x_left"], f["x_right"]], "y": [f["y_top"], f["y_bottom"]]},
                "cells": [{"label": f[f"{k}_label"], "value": f[f"{k}_rx"]} for k in ("e", "a", "b")]}
    if family == "dual_path_tree":
        return {"paths": [{"label": f["left_label"], "steps": [n["heading"] for n in f["left_nodes"]]},
                          {"label": f["right_label"], "steps": [n["heading"] for n in f["right_nodes"]]}]}
    d = {"takeaways": _tk(f)}
    if family == "trial_design":
        d.update(arms=[{"name": a["name"], "n": a.get("n")} for a in f["arms"]],
                 timepoints=[t["week"] for t in f["timepoints"]], duration_weeks=f.get("treatment_end_week"))
    elif family == "forest_plot":
        d["effects"] = [{"label": r["label"], "est": r["est"], "lo": r["lo"], "hi": r["hi"]}
                        for r in f["rows"] if r.get("kind") != "group"]
    elif family == "endpoint_readout":
        d.update(series=[{"name": s["name"], "values": s["values"]} for s in f["series"]],
                 stats=f["stats"]["lines"])
        if variant == "line":
            d["x"] = f["x"]
        else:
            d["categories"] = f["categories"]
    elif family == "moa_cascade":
        d.update(chain=[s["label"] for s in f["stages"]], action_points=[c["label"] for c in f["callouts"]])
    elif family == "data_table_highlight":
        d["table"] = {"columns": [c["label"] for c in f["columns"]],
                      "rows": [{"label": r["label"], "cells": r.get("cells") or [], "highlight": bool(r.get("highlight")),
                                "kind": r.get("kind")} for r in f["rows"]]}
    elif family == "landscape_swimlane":
        d["timed_items"] = [{"label": s["name"], "group": ln["label"], "start": s["start"], "end": s["end"],
                             "status": s["status"]} for ln in f["lanes"] for s in ln["studies"]]
    return d


def page_from_fill(pid: str, layout: str, fill: dict, *, kind: str = "content", proposed: str | None = None) -> dict:
    """Selector page built from a plain (resolved) fill: its title, shown strings and mechanically derived data."""
    fam, var = S.LAYOUTS[layout][0], S.LAYOUTS[layout][1]
    try:
        data = data_from_fill(fam, var, fill)
    except (KeyError, TypeError, AttributeError):       # a fill not shaped for its layout: no data, the selector
        data = {}                                       # downgrades, the slot contract reports the fill
    return {"id": pid, "kind": kind, "title": fill.get("title"), "text": flatten(fill),
            "data": data, "proposed_layout": proposed or layout}


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


def template_fills(page: dict) -> dict[str, dict]:
    """A deck `template` page's bound fills by selector layout id: `fill` (for `layout`) and/or `fills`."""
    t = page.get("template") if isinstance(page.get("template"), dict) else {}
    out = dict(t.get("fills") or {})
    if isinstance(t.get("fill"), dict) and isinstance(t.get("layout"), str):
        out.setdefault(t["layout"], t["fill"])
    return out


def bind_template_page(page: dict, facts: dict, layout: str, **kw) -> dict:
    """bind.resolve for one of a deck template page's fills; the page title fills the title slot."""
    from . import bind
    fam, var = S.LAYOUTS[layout][0], S.LAYOUTS[layout][1]
    return bind.resolve(fam, var, template_fills(page)[layout], facts, title=page.get("title"), **kw)


def deck_page_input(page: dict, facts: dict) -> dict:
    """Selector input for a FactDeck deck-spec page, built only from the page's own fact references and authored
    labels (fact-only content: no data is derived beyond what the page already shows)."""
    lay = page.get("layout")
    if lay == "template":                       # a bound fill: the selector reads the fill the page would show
        fills = {k: v for k, v in template_fills(page).items() if k in S.LAYOUTS}
        tmpl = page["template"]
        first = tmpl.get("layout") if tmpl.get("layout") in fills else next(iter(fills), None)
        if first:
            res = bind_template_page(page, facts, first, page_checks=False)
            return page_from_fill(page.get("id"), first, res["fill"], kind=tmpl.get("kind") or "content",
                                  proposed=tmpl.get("layout"))
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
    out = {"pages": {}, "stats": res["stats"]}
    for p, d in zip(flagged, res["decisions"]):
        rec = page_record(d)
        if p.get("layout") == "template":       # which bound fill will be rendered, or why none can be
            lay, fill, fallback = resolve_fill({"fills": template_fills(p)}, d)
            rec["rendered_layout"] = lay if fill is not None else None
            rec["fill_fallback"] = fallback
        out["pages"][d["page_id"]] = rec
    return out


def _slot_spec(slots: dict, skip: set) -> dict:
    """Compact slot contract for a worker brief: "*≤16" = required, at most 16 characters; "≤16" optional;
    a list slot is keyed "name[≤n]" (capacity) with its item contract; an object slot (e.g. axis) is "object"."""
    out = {}
    for k, r in slots.items():
        if k in skip or not isinstance(r, dict):
            continue
        req = "*" if r.get("required") else ""
        item = r.get("item")
        if isinstance(item, dict) and item:
            out[f"{req}{k}[{'≤' + str(r['capacity']) if r.get('capacity') else ''}]"] = _slot_spec(item, skip)
        elif r.get("type") == "list":                # a list of shown strings, e.g. a table row's cells
            out[f"{req}{k}[]"] = "*" + (f"≤{r['max_chars']}" if r.get("max_chars") else "")
        elif r.get("type") == "bool":
            out[k] = "true/false"
        elif r.get("type") == "object":
            out[k] = req + "object"
        else:
            out[k] = req + (f"≤{r['max_chars']}" if r.get("max_chars") else "")
    return out


def template_library_brief() -> dict:
    """What a DECK worker needs to write template pages: every selector layout with its family slots (code-written
    chrome left out), capacity variants, the relation it serves and where it downgrades to."""
    from . import bind
    from . import slots as slotmod
    skip = bind.CODE_WRITTEN | {"title"}            # the page title fills the title slot
    by_layout = {lay: rel for rel, (_, lay) in S.RELATIONS.items()}
    m = slotmod.load_manifest()
    out = {}
    for lay, (fam, var, name, chart) in S.LAYOUTS.items():
        spec = m["families"][fam]
        slots_ = dict(spec.get("slots") or {})
        if fam == "key_points" and var == "evidence_takeaways":
            slots_["items"] = {"required": True, "item": spec.get("evidence_takeaways", {}).get("item", {}), "capacity": 4}
        out[lay] = {"name_zh": name, "is_chart": chart,
                    **({"relation_zh": S.RELATIONS[by_layout[lay]][0]} if lay in by_layout else {}),
                    **({"downgrades_to": S.DOWNGRADE[lay]} if lay in S.DOWNGRADE else {}),
                    **({"requires": S.REQUIRES_ZH[lay]} if lay in S.REQUIRES_ZH else {}),
                    "slots": _slot_spec(slots_, skip)}
    return out


def deck_plan(deck: dict, *, note: str | None = None) -> dict:
    """The template pages of a deck spec as a pipeline plan (pipeline.run with `facts` binds and traces them)."""
    pages = []
    for p in deck.get("pages") or []:
        if not isinstance(p, dict) or p.get("layout") != "template":
            continue
        t = p["template"]
        pages.append({"id": p.get("id"), "kind": t.get("kind") or "content", "title": p.get("title"),
                      "proposed_layout": t.get("layout"), "fills": template_fills(p)})
    return {"title": deck.get("title"), "note": note, "layout_signals": deck.get("layout_signals"),
            "bound": True, "pages": pages}
