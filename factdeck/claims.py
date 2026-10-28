"""The claims a source makes, page by page: the evidence layer between reading and the summary.

A claim is one proposition of the source, recorded only as verbatim spans of its units (a sentence, or a table's
row header + column header + cell) plus labels: its type and its scope (population, time, condition), each a verbatim
fragment of the page. Nothing in a claim is reworded. Code adds what it can read off the spans: qualifiers (hedges,
limits, negations from config/factdeck_lexicon.json), critical numbers, and citation marks.
"""
from __future__ import annotations

import re

from .lexicon import canon, critical_tokens, lexicon, locate

CLAIM_TYPES = {"recommendation": "推荐/建议", "definition": "定义", "criterion": "标准/阈值/分级", "result": "研究结果",
               "comparison": "比较", "association": "相关（非因果）", "mechanism": "机制", "interpretation": "作者解读/推测",
               "product_info": "产品信息（适应症、用法、规格、价格、获批、医保）", "background": "背景/流行病学", "question": "问题/讨论题"}
SOURCE_KINDS = {"guideline": "指南", "consensus": "专家共识", "trial": "临床试验报告", "real_world": "真实世界研究",
                "meta_analysis": "荟萃分析", "review": "综述", "promotional": "企业推广材料", "label": "说明书",
                "case": "病例", "lecture": "讲课/培训材料", "other": "其他"}
SCOPE_KEYS = ("population", "time", "condition")
SPAN_MAX = 200               # canon characters in one span: a sentence or a cell, never a whole page
SPANS_PER_CLAIM = 8
COVERED = 0.8                # an author's mark counts as listed when this share of it lies inside claim spans
_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


class ClaimError(ValueError):
    pass


def _need(cond, msg):
    if not cond:
        raise ClaimError(msg)


def cites(text: str) -> list[str]:
    """Citation marks written as superscripts (¹, ²³, ¹⁻⁸, ¹⁰,¹¹): the reference numbers they name."""
    out = []
    for run in re.findall(r"[⁰¹²³⁴⁵⁶⁷⁸⁹][⁰¹²³⁴⁵⁶⁷⁸⁹⁻,，]*", text):
        for part in re.split(r"[,，]", run):
            a, _, b = part.partition("⁻")
            a, b = a.translate(_SUPER), b.translate(_SUPER)
            if a and b and a.isdigit() and b.isdigit() and int(a) < int(b) <= int(a) + 50:
                out += [str(n) for n in range(int(a), int(b) + 1)]
            elif a.isdigit():
                out.append(a)
    return list(dict.fromkeys(out))


def qualifiers(text: str) -> list[str]:
    """Hedges, limits and negations in the text. Words in which a qualifier character is only part of another word
    ("反应" for 应, "不良" for 不; lexicon claim_qualifier_compounds) are masked first."""
    t = canon(text)
    for w in lexicon().get("claim_qualifier_compounds", []):
        t = t.replace(canon(w), "|" * len(canon(w)))
    return [q for q in lexicon().get("claim_qualifiers", []) if canon(q) in t]


def profile(p: dict, source_text: str) -> dict:
    _need(isinstance(p, dict) and p.get("kind") in SOURCE_KINDS, "profile.kind 须是 " + " / ".join(SOURCE_KINDS) + " 之一")
    out = {"kind": p["kind"], "note": str(p.get("note", ""))[:1000]}
    for k in ("sponsor", "date"):
        v = str(p.get(k, "") or "").strip()
        _need(not v or canon(v) in canon(source_text), f"profile.{k} 须是资料中的原文片段：{v}")
        out[k] = v
    return out


def page_claims(page: dict, units: dict[str, dict], rows: list, reading: dict | None) -> tuple[list[dict], list[str]]:
    """Check one page's claims. `units` are the page's quotable units by id (source units and transcriptions).
    Returns (claims, warnings)."""
    where = page["location"]
    text = "\n".join(u["text"] for u in units.values())
    cat = (reading or {}).get("classification")
    _need(isinstance(rows, list), f"{where}：claims 需为列表")
    if cat in {"REFERENCE", "EMPTY"}:
        _need(not rows, f"{where} 是参考文献或空白页，不列论断")
    out, seen = [], set()
    for c in rows:
        _need(isinstance(c, dict), f"{where}：每条论断需为对象")
        cid = str(c.get("id", ""))
        _need(re.fullmatch(r"k[1-9]\d{0,2}", cid) and cid not in seen, f"{where}：论断编号需为 k1、k2…且不重复：{cid!r}")
        seen.add(cid)
        name = f"{where} 论断 {cid}"
        _need(c.get("type") in CLAIM_TYPES, f"{name} 的类型须是 " + " / ".join(CLAIM_TYPES) + " 之一")
        spans = c.get("spans")
        _need(isinstance(spans, list) and 1 <= len(spans) <= SPANS_PER_CLAIM, f"{name} 需有 1–{SPANS_PER_CLAIM} 个原文片段（spans）")
        got = []
        for s in spans:
            uid, quote = (s.get("unit_id"), str(s.get("quote", ""))) if isinstance(s, dict) else (None, "")
            _need(uid in units, f"{name} 的片段须来自本页的文字单元：{uid}")
            n = len(canon(quote))
            _need(1 <= n <= SPAN_MAX, f"{name} 的片段长度须为 1–{SPAN_MAX} 字（一句或一格，不能引整页）")
            at = locate(units[uid]["text"], quote)
            _need(at, f"{name} 的片段不是单元 {uid} 中的原文：{quote[:40]}")
            got.append({"unit_id": uid, "quote": units[uid]["text"][at[0]:at[1]], "start": at[0], "end": at[1]})
        scope = c.get("scope") or {}
        _need(isinstance(scope, dict) and set(scope) <= set(SCOPE_KEYS), f"{name} 的 scope 只能有 {' / '.join(SCOPE_KEYS)}")
        scope = {k: str(scope.get(k, "") or "").strip() for k in SCOPE_KEYS}
        for k, v in scope.items():
            _need(not v or canon(v) in canon(text), f"{name} 的 scope.{k} 须是本页原文片段：{v}")
        joined = "\n".join(s["quote"] for s in got)
        out.append({"id": f"{page['id']}#{cid}", "page_id": page["id"], "type": c["type"], "spans": got, "scope": scope,
                    "unit_ids": list(dict.fromkeys(s["unit_id"] for s in got)), "qualifiers": qualifiers(joined),
                    "numbers": sorted(critical_tokens(joined)), "cites": cites(joined), "note": str(c.get("note", ""))[:500]})
    warnings = []
    if cat == "SUBSTANTIVE" and not out:
        warnings.append(f"{where} 是正文页，但没有列出论断")
    for u in units.values():
        taken = [(s["start"], s["end"]) for c in out for s in c["spans"] if s["unit_id"] == u["id"]]
        for kind, frags in (u.get("signals") or {}).items():
            for f in frags:
                if len(canon(f)) < 4:
                    continue
                spots, pos = [], 0
                while (at := locate(u["text"][pos:], f)):        # every occurrence: a mark may repeat on the page
                    spots.append((pos + at[0], pos + at[1]))
                    pos += at[1]

                def share(at):
                    inside = sum(1 for i in range(*at) if not u["text"][i].isspace() and any(a <= i < b for a, b in taken))
                    return inside / max(1, len(canon(u["text"][at[0]:at[1]])))
                if spots and max(share(at) for at in spots) < COVERED:
                    warnings.append(f"{where} 的原件{'页标题' if kind == 'title' else '强调'}“{f[:30]}”未列入任何论断")
    return out, warnings
