"""General illustration standard for content pages (config/visual_grammar.json, visual-grammar.5).

The planning unit is one relation a passage states plus its terms. A plan lists, per unit,
the relation (type + the passage's own wording for it), the terms (verbatim fragments) and a
closed list of objects to draw, each bound to a term or the relation, either literally or
through a whitelisted derivation. Nothing outside the list is drawn. An independent blind read
of the text-free image is compared with the plan: every drawn object must map back to the
passage, and every planned relation and term must be read back from the picture.

Nothing here depends on a subject: connective words are language words in the grammar file,
person words come from the lexicon (person_terms).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from factdeck.lexicon import canon, lexicon

GRAMMAR = Path(__file__).resolve().parents[1] / "config" / "visual_grammar.json"
PLAN_MARK = "\n本页作图清单（只画清单中的对象，并按 encoding 的空间排布表达关系；清单外不画任何东西）："


@lru_cache(maxsize=1)
def grammar() -> dict:
    return json.loads(GRAMMAR.read_text(encoding="utf-8"))


def _c(text) -> str:
    return canon(str(text)).lower()


def overlaps(a, b) -> bool:
    a, b = _c(a), _c(b)
    return bool(a and b) and (a in b or b in a)


def illustrated(layout: str) -> bool:
    return layout not in grammar()["layouts"]["no_illustration"]


def candidates(text: str) -> list[str]:
    """Relation types whose connective words occur in the passage. Proposals only."""
    t = _c(text)
    return [k for k, words in grammar()["connectives"].items() if any(_c(w) in t for w in words if _c(w))]


def brief(layout: str, passages: list[str], focus: str = "") -> dict:
    g = grammar()
    return {"version": g["version"], "goal": g["goal"], "relations": g["relations"], "derivations": g["derivations"],
            "omission_reasons": g["omission_reasons"], "suggested": g["layouts"]["suggested"].get(layout, []),
            "passages": [{"text": p, "candidates": candidates(p), "focus": bool(focus) and overlaps(p, focus)} for p in passages],
            "focus": focus, "rules": g["rules"]}


def prompt_text(layout: str) -> str:
    g = grammar(); suggested = g["layouts"]["suggested"].get(layout, [])
    return ("插图目标：" + g["goal"] + ("本页版式常见的关系：" + "、".join(suggested) + "。" if suggested else "")
            + "约束：" + "".join(g["rules"]))


def drawing_list(plan: dict) -> dict:
    """What the image model receives: units, relation encodings and the closed object list only."""
    g = grammar()
    return {"units": [{"text": u["text"], "relation": u["relation"], "encoding": u["encoding"] or g["relations"][u["relation"]["type"]]["encoding"],
                       "draw": u["draw"]} for u in plan.get("units", [])],
            "arrangement": plan.get("arrangement", "")}


def plan_prompt(base: str, plan: dict) -> str:
    return base + PLAN_MARK + json.dumps(drawing_list(plan), ensure_ascii=False)


def check_plan(plan: dict, layout: str, passages: list[str], focus: str = "") -> None:
    """Raise ValueError when the plan breaks the general standard."""
    g = grammar(); page = _c("\n".join(passages))
    persons = [_c(p) for p in lexicon().get("person_terms", []) if p.strip()]
    if not isinstance(plan, dict) or not set(plan) <= {"units", "omitted", "arrangement"}:
        raise ValueError("作图方案须为 {units, omitted, arrangement}")
    units, omitted = plan.get("units", []), plan.get("omitted", [])
    if not isinstance(units, list) or len(units) > 4 or not isinstance(omitted, list):
        raise ValueError("units 至多4个，omitted 须为列表")
    if not isinstance(plan.get("arrangement", ""), str) or len(plan.get("arrangement", "")) > 200:
        raise ValueError("arrangement 须为200字以内文字")
    for u in units:
        if not isinstance(u, dict) or set(u) != {"text", "relation", "terms", "draw", "encoding"}:
            raise ValueError("每个单元须有 text、relation、terms、draw、encoding")
        if not isinstance(u["text"], str) or not u["text"].strip() or _c(u["text"]) not in page:
            raise ValueError("单元原文须逐字出自本页锁定文字：" + str(u["text"])[:40])
        r = u["relation"]
        if not isinstance(r, dict) or set(r) != {"type", "span"} or r["type"] not in g["relations"]:
            raise ValueError("relation 须为 {type, span}，type 取自 grammar.relations：" + str(r)[:60])
        if r["type"] != "entity" and (not str(r["span"]).strip() or _c(r["span"]) not in _c(u["text"])):
            raise ValueError(f"关系 {r['type']} 须在 span 中逐字给出原文表达该关系的词句")
        lo, hi = g["relations"][r["type"]]["terms"]
        terms = u["terms"]
        if not isinstance(terms, list) or not lo <= len(terms) <= hi:
            raise ValueError(f"关系 {r['type']} 须有 {lo}–{hi} 项")
        for t in terms:
            if not isinstance(t, dict) or set(t) != {"span", "role"} or not str(t["span"]).strip() or _c(t["span"]) not in _c(u["text"]):
                raise ValueError("每一项须为 {span, role}，span 逐字出自该单元原文：" + str(t)[:60])
        if len({_c(t["span"]) for t in terms}) != len(terms):
            raise ValueError("同一单元的各项不得重复")
        if not isinstance(u["encoding"], str) or len(u["encoding"]) > 200:
            raise ValueError("encoding 须为200字以内文字（可留空，用该关系的默认排布）")
        anchors = [_c(t["span"]) for t in terms] + ([_c(r["span"])] if str(r["span"]).strip() else [])
        draw = u["draw"]
        if not isinstance(draw, list) or not 1 <= len(draw) <= 8:
            raise ValueError("每个单元的作图清单须有1–8个对象")
        bound = set()
        for d in draw:
            if not isinstance(d, dict) or set(d) != {"object", "bound_to", "derivation"} or not str(d["object"]).strip() or len(str(d["object"])) > 120:
                raise ValueError("清单对象须为 {object, bound_to, derivation}，object 为120字以内的非空描述")
            if _c(d["bound_to"]) not in anchors:
                raise ValueError("清单对象须绑定到本单元的某一项或关系词句：" + str(d["bound_to"])[:40])
            derivation = d["derivation"] or ""
            if derivation and derivation not in g["derivations"]:
                raise ValueError("derivation 只能取允许派生：" + "、".join(g["derivations"]))
            if not derivation and _c(d["bound_to"]) not in _c(d["object"]):
                raise ValueError("非派生对象须就是原文点名的事物（object 含所绑定的原文）：" + str(d["object"])[:40])
            if derivation != "carrier" and any(p in _c(d["object"]) for p in persons) and not any(p in _c(d["bound_to"]) for p in persons):
                raise ValueError("人物只在原文点名的人或 carrier 派生中出现：" + str(d["object"])[:40])
            bound.add(_c(d["bound_to"]))
        missing = [t["span"] for t in terms if _c(t["span"]) not in bound]
        if missing:
            raise ValueError("每一项都要画出来，未绑定：" + "、".join(missing)[:60])
    reasons = g["omission_reasons"]
    for o in omitted:
        if not isinstance(o, dict) or set(o) != {"text", "reason"} or o["reason"] not in reasons or _c(o["text"]) not in page:
            raise ValueError("omitted 每项须为 {text, reason}：text 逐字出自本页，reason 取自 " + "、".join(reasons))
        if focus and overlaps(o["text"], focus) and o["reason"] != "native_graphic":
            raise ValueError("本页焦点不能略去：" + o["text"][:40])
        if candidates(o["text"]) and o["reason"] == "attribution_only":
            raise ValueError("这段原文含有关系词，不能以 attribution_only 略去：" + o["text"][:40])
    # Every passage with a detected relation is either drawn or explicitly omitted; the focus must be drawn.
    for p in passages:
        if not candidates(p):
            continue
        if not any(overlaps(u["text"], p) for u in units) and not any(overlaps(o["text"], p) for o in omitted):
            raise ValueError("这段原文含有关系词，须配图或在 omitted 中说明：" + p[:40])
    if focus and any(overlaps(p, focus) for p in passages) and not any(overlaps(u["text"], focus) for u in units) \
            and not any(overlaps(o["text"], focus) and o["reason"] == "native_graphic" for o in omitted):
        raise ValueError("作图须覆盖本页焦点：" + focus[:40])
    if not units and not omitted:
        raise ValueError("不配插图时须在 omitted 中逐段写明原因")


def read_issues(plan: dict, read: dict, passages: list[str]) -> list[str]:
    """Compare an independent blind read of the text-free image with the plan."""
    page = _c("\n".join(passages)); issues = []
    objects, relations = read.get("objects", []), read.get("relations", [])
    for o in objects:
        b = str(o.get("bound_to", "")).strip()
        if not b or b == "无" or _c(b) not in page:
            issues.append("图中有对象对应不到本页原文：" + str(o.get("description", ""))[:40])
    for u in plan.get("units", []):
        rtype = u["relation"]["type"]
        if rtype != "entity" and not any(r.get("type") == rtype and any(overlaps(s, u["text"]) for s in r.get("spans", [])) for r in relations):
            issues.append(f"盲读未读出关系 {rtype}：" + u["text"][:30])
        for t in u["terms"]:
            if not any(overlaps(o.get("bound_to", ""), t["span"]) for o in objects):
                issues.append("盲读认不出这一项：" + t["span"][:30])
    return issues
