"""SEMANTIC_REVIEW as two independent checklists with ledgers (docs/SEMANTIC_REVIEW_PROTOCOL.md).

COVERAGE   source pages → pages: numbers, units, negations, qualifiers, footnotes, table rows/columns and
           what was left out; every source page and every teaching item gets a status.
RELATIONS  outline/summary relations → pages: context, relation type and direction, grouping and visual
           expression; every relation and every multi-item page structure gets a verdict.

Both are done by workers other than the fact/deck authors and other than each other. Every round re-checks the
unresolved issues of its checklist (app/review_ledger.py). After a revision only the changed pages, the pages
that share their facts or relations, their neighbours and pages with unresolved issues must be re-read; the
others may carry their previous verdict while facts, summary and sources are unchanged.

Carried passes: an item (page, source page, teaching item, relation, chapter) an earlier independent round of the same
checklist passed is not judged again while its content fingerprint is unchanged (the page with its facts' display text
and source units, its neighbours' content, the source pages, the relation and its supporting facts, the check name). It
is left out of the brief and the result and merged back in under its original reviewer; an item an unresolved issue
sits on is never carried. The memory is a snapshot named by the checklist record (`carry_memory`).
"""
from __future__ import annotations

import hashlib
import json

from app import review_ledger as ledger
from app.fact57098 import digest, now, require

CHECKS = ("COVERAGE", "RELATIONS")
CHECK_NAMES = {"COVERAGE": "覆盖/逐字检查", "RELATIONS": "语义/关系检查"}
PAGE_VERDICTS = ("SUPPORTED", "ISSUES", "CARRIED")
ITEM_STATUSES = ("PRESENTED", "EXCLUDED", "NEEDS_HUMAN")
RELATION_VERDICTS = ("SUPPORTED", "UNSUPPORTED", "UNKNOWN", "CARRIED")
# Whether the pages let a reader see a chapter relation: saying too much is judged by the verdict,
# saying too little (lost or flattened into a list) by the expression.
EXPRESSIONS = ("EXPRESSED", "FLATTENED", "MISSING")
YES_NO = ("YES", "NO")


def outcome_sections(w: dict, ctx: dict) -> list[dict]:
    """Chapters with an information structure whose pages are in this review's scope."""
    shown = {sid for p in ctx["pages"] for sid in p["page"].get("section_ids") or []}
    return [s for s in ctx["sections"] if s.get("message") and s["id"] in shown]
NO_STRUCTURE = {"cover", "divider", "closing", "agenda", "figure", "statement", "hero"}


def prior_check(w: dict, check: str) -> dict:
    """Reusable evidence is not current approval. Checkpoints retain actual authorship."""
    return ((w.get("semantic_checks") or {}).get(check)
            or (w.get("semantic_review_baselines") or {}).get(check) or {})


def checkpoint(w: dict, result: dict, reviewer: str, check: str, *, receipt: dict) -> dict:
    """Validate an archived completed review without approving or closing live issues."""
    from copy import deepcopy
    require(receipt.get("input_sha256") == result.get("input_sha256"), "审核存档版本不符", 422)
    require(receipt.get("worker") == reviewer and receipt.get("task_id"), "审核存档须保留真实执行端和任务", 422)
    require(receipt.get("result_sha256") == digest(result), "审核存档结果校验值不符", 422)
    task = next((t for t in w.get('tasks', []) if t['id'] == receipt['task_id']), None)
    require(task and task.get('kind') == 'SEMANTIC_REVIEW' and task.get('worker') == reviewer
            and task.get('binding') == check and task.get('brief', {}).get('input_sha256') == result['input_sha256'],
            '审核存档与项目中实际领取的任务不符', 422)
    shadow = deepcopy(w)
    record = accept(shadow, result, reviewer, check)
    record["receipt"] = dict(receipt)
    record["approval"] = False
    record["recheck_pages"] = [p["page_id"] for p in result["pages"] if p["verdict"] == "ISSUES"]
    w.setdefault("semantic_review_baselines", {})[check] = record
    return record


def _d():
    from app import deckflow
    return deckflow


def check_current(w: dict, check: str) -> bool:
    d = _d()
    r = (w.get("semantic_checks") or {}).get(check)
    return d.deck_current(w) and bool(r) and r["input_sha256"] == d.semantic_input(w)


def current(w: dict) -> bool:
    return all(check_current(w, c) for c in CHECKS)


def sources_print(w: dict) -> str:
    return digest([(s["id"], s["sha256"]) for s in w["sources"]])


# ------------------------------------------------------------------ what the review rests on
def context(w: dict) -> dict:
    d = _d()
    v = d.verified(w)
    chk = d.checked(w, v)
    scoped, _, sections, _, _, scope = d.scope_context(w["deck"]["result"], w["outline"], w["summary"]["sections"],
                                                       w["requirements"], w.get("outline_parts"))
    by_unit = {u["id"]: u for u in d.all_units(w)}
    figs = d.figures(w)
    order = {}
    for s in w["sources"]:
        seq = [u["id"] for u in s["units"]]
        order.update({a: b for a, b in zip(seq, seq[1:])})

    def src_page(fid):
        f = v["facts"].get(fid) or {}
        if f.get("figure"):
            return (figs.get(f["figure"]) or {}).get("page_id")
        return (by_unit.get(f.get("unit")) or {}).get("page_id")

    pages, prints, page_facts, page_units, page_src = [], {}, {}, {}, {}
    for page, res in zip(scoped["pages"], chk["pages"]):
        pid = page["id"]
        ids = res["facts"] + res["edge_facts"]
        page_facts[pid] = ids
        page_units[pid] = {v["facts"][f].get("unit") for f in ids if f in v["facts"]} - {None}
        page_src[pid] = sorted({p for p in (src_page(f) for f in ids) if p})
        view = {"page": page, "facts": [d.semantic_fact(w, v, by_unit, f) for f in res["facts"]],
                "edge_facts": [d.semantic_fact(w, v, by_unit, f) for f in res["edge_facts"]]}
        prints[pid] = digest(view)
        pages.append(view)
    return {"v": v, "chk": chk, "scoped": scoped, "sections": sections, "scope": scope, "by_unit": by_unit,
            "pages": pages, "prints": prints, "page_facts": page_facts, "page_units": page_units, "page_src": page_src,
            "next_of": order, "src_page": src_page, "order": [p["page"]["id"] for p in pages]}


def regression(w: dict, check: str, ctx: dict) -> dict:
    """Which pages this round must read. FULL when there is no earlier round of this checklist or facts, summary,
    sources or scope changed; otherwise IMPACT."""
    d = _d()
    prev = prior_check(w, check)
    order = ctx["order"]
    why = (None if prev and prev.get("page_prints") else "本检查表首次执行")
    if not why and prev.get("facts_sha") != d.facts_sha(w): why = "事实库已变化"
    if not why and prev.get("summary_sha") != digest(w["summary"]): why = "总结已变化"
    if not why and prev.get("sources_sha") != sources_print(w): why = "来源已变化"
    if why:
        return {"mode": "FULL", "reason": why, "changed": order, "affected": order, "carry": {}}
    old = prev["page_prints"]
    changed = [p for p in order if old.get(p) != ctx["prints"][p]]
    affected = set(changed)
    affected.update(p for p in prev.get("recheck_pages", []) if p in order)
    removed = [p for p in prev.get("scope_pages") or [] if p not in ctx["prints"]]
    pos = {p: i for i, p in enumerate(order)}
    for p in changed:                                   # neighbours carry cross-page continuity
        affected |= {order[i] for i in (pos[p] - 1, pos[p] + 1) if 0 <= i < len(order)}
    prev_order = prev.get("scope_pages") or []
    for p in removed:
        i = prev_order.index(p)
        affected |= {x for x in prev_order[max(0, i - 1):i + 2] if x in pos}
    touched = {f for p in changed for f in ctx["page_facts"][p]}
    tunits = {u for p in changed for u in ctx["page_units"][p]}
    for p in order:
        if touched & set(ctx["page_facts"][p]):
            affected.add(p)
    for s in ctx["sections"]:
        for r in (s.get("message") or {}).get("relations") or []:
            if tunits & set(r.get("unit_ids") or []):
                affected |= {p for p in order if ctx["page_units"][p] & set(r["unit_ids"])}
    affected |= {i["ref"] for i in ledger.unresolved(w, "semantic", check) if i["ref"] in pos}
    affected |= {p for p in order if p not in prev.get("page_verdicts", {})}
    carry = {p: prev["page_verdicts"][p] for p in order if p not in affected}
    return {"mode": "IMPACT", "reason": f"仅 {len(changed)} 页改动；复核改动页、共用事实/关系页、相邻页及有未闭环问题的页",
            "changed": changed, "affected": [p for p in order if p in affected], "carry": carry}


def source_pages(w: dict, ctx: dict) -> list[dict]:
    """Inventory of every source page: regions and where its content is on the deck."""
    d = _d()
    cited = {}
    for s in w["summary"]["sections"]:
        for p in s.get("source_page_ids") or []:
            cited.setdefault(p, []).append(s["id"])
    on = {}
    for pid in ctx["order"]:
        for sp in ctx["page_src"][pid]:
            on.setdefault(sp, []).append(pid)
    out = []
    for s in w["sources"]:
        for p in s["pages"]:
            units = [u for u in s["units"] + s["transcriptions"] if u["page_id"] == p["id"]]
            regions = {}
            for u in units:
                k = u.get("method") or "text"
                regions[k] = regions.get(k, 0) + 1
            figs = [g["id"] for g in s.get("figures", []) if g.get("page_id") == p["id"]]
            if figs:
                regions["figure"] = len(figs)
            reading = p.get("reading") or {}
            out.append({"source_page_id": p["id"], "source_id": s["id"], "filename": s["filename"], "location": p["location"],
                        "classification": reading.get("classification"), "reading_note": reading.get("note", ""),
                        "requires_visual": p.get("requires_visual", False), "regions": regions,
                        "presented_on": on.get(p["id"], []), "summary_sections": cited.get(p["id"], []),
                        "image_url": d.page_image_url(w, p) if s["kind"] == "pdf" else None,
                        "file_url": f"/api/deck/workflows/{w['id']}/sources/{s['id']}/file"})
    return out


def teaching_items(w: dict, ctx: dict) -> list[dict]:
    """Outline items and points, summary sections and their key points, each with the pages that present it."""
    d = _d()
    cov = ctx["chk"]["coverage"]
    omitted = {o["section_id"]: o.get("reason", "") for o in cov.get("omissions") or []}
    rows = [{"item_id": o["outline_id"], "kind": "outline", "text": o["text"], "presented_on": o["pages"]} for o in cov.get("outline") or []]
    rows += [{"item_id": p["point_id"], "kind": "point", "text": p["text"], "presented_on": p["pages"],
              **({"unsupported": p["unsupported"]} if p.get("unsupported") is not None else {})} for p in cov.get("points") or []]
    for s in cov.get("sections") or []:
        rows.append({"item_id": s["section_id"], "kind": "section", "text": s["title"], "presented_on": s["pages"],
                     **({"omission": omitted[s["section_id"]]} if s["section_id"] in omitted else {})})
    for sec in ctx["sections"]:
        for k in d.key_point_targets(w, sec):
            units = set(k.get("unit_ids") or [])
            rows.append({"item_id": k["target_id"], "kind": "key_point", "section_id": sec["id"], "text": k["point"],
                         "presented_on": [p for p in ctx["order"] if ctx["page_units"][p] & units]})
    return rows


def relations(w: dict, ctx: dict) -> list[dict]:
    """Every relation the deck states or implies: summary relations, arrows, and multi-item page structures."""
    v = ctx["v"]["facts"]
    out = []
    for sec in ctx["sections"]:
        for i, r in enumerate((sec.get("message") or {}).get("relations") or [], 1):
            units = set(r.get("unit_ids") or [])
            out.append({"relation_id": f"{sec['id']}.relation{i}", "kind": "summary_relation", "type": r["type"],
                        "items": r.get("items"), "manual": bool(r.get("manual")), "unit_ids": sorted(units),
                        "presented_on": [p for p in ctx["order"] if ctx["page_units"][p] & units]})
    shown = lambda f: (v.get(f) or {}).get("display") or (v.get(f) or {}).get("quote") or f
    for b in w["deck"]["result"].get("content_bindings") or []:
        primary = set(b.get("primary_fact_refs") or [])
        out.append({"relation_id":"binding:"+b["id"], "kind":"source_binding", "type":b.get("role"),
                    "unit_ids":b.get("source_unit_refs",[]), "primary_fact_refs":sorted(primary),
                    "dependent_fact_refs":b.get("dependent_fact_refs",[]),
                    "evidence_unit":b.get("relationship_evidence"),
                    "presented_on":[p for p in ctx["order"] if primary & set(ctx["page_facts"][p])]})
    for view in ctx["pages"]:
        page = view["page"]
        nodes = {n.get("id"): n for n in page.get("nodes") or [] if isinstance(n, dict)}
        for e in page.get("edges") or []:
            if isinstance(e, list) and len(e) >= 3:
                ends = [((nodes.get(x) or {}).get("ref") or {}).get("fact") for x in e[:2]]
                out.append({"relation_id": f"{page['id']}.edge.{e[0]}->{e[1]}", "kind": "arrow", "presented_on": [page["id"]],
                            "from": shown(ends[0]) if ends[0] else e[0], "to": shown(ends[1]) if ends[1] else e[1],
                            "backed_by": e[2]})
        for b in page.get("blocks") or []:
            if b.get("kind") == "arrow":
                out.append({"relation_id": f"{page['id']}.arrow.{b.get('from')}->{b.get('to')}", "kind": "arrow",
                            "presented_on": [page["id"]], "from": b.get("from"), "to": b.get("to"), "backed_by": b.get("backed_by")})
        if page.get("layout") not in NO_STRUCTURE and len(view["facts"]) >= 2:
            peers = sorted({b.get("peer") for b in page.get("blocks") or [] if b.get("peer")})
            out.append({"relation_id": f"{page['id']}.structure", "kind": "grouping", "presented_on": [page["id"]],
                        "layout": page.get("layout"), **({"peers": peers} if peers else {}),
                        "question": "页面的分组、并列、顺序与视觉层级是否制造了原文没有的合取、择一、比较、因果或先后"})
    return out


def must_view(ctx: dict, reg: dict) -> list[str]:
    """Source pages whose original image must be looked at for the pages this round reads."""
    by_unit, v = ctx["by_unit"], ctx["v"]["facts"]
    out = set()
    for pid in reg["affected"]:
        for f in ctx["page_facts"][pid]:
            fact = v.get(f) or {}
            u = by_unit.get(fact.get("unit")) or {}
            if fact.get("figure") or u.get("method") in {"visual_transcription", "pptx_arrow"} or u.get("figure_id"):
                sp = ctx["src_page"](f)
                if sp:
                    out.add(sp)
    return sorted(out)


# ------------------------------------------------------------------ carried passes
# An item an earlier independent round of this checklist passed, whose content fingerprint is unchanged, is not judged
# again: it leaves the brief and the result, and its verdict is merged back in under its original reviewer. Open
# issues are not carried: every item that is the ref of an unresolved issue of the checklist is judged every round.
CARRY_SCHEMA = "semantic-carry/1"
CARRY_KINDS = {"COVERAGE": ("pages", "source_pages", "teaching_items"), "RELATIONS": ("pages", "relations", "chapters")}
CARRY_NAMES = {"pages": "页面", "source_pages": "来源页", "teaching_items": "教学条目", "relations": "关系", "chapters": "章节"}


def _fp(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def reviewers(rec: dict | None) -> set:
    """Everyone whose verdicts a checklist record holds: its reviewer and the original reviewers of carried items."""
    if not rec:
        return set()
    return set(rec.get("reviewers") or [rec.get("reviewer")]) - {None}


def blocked_reviewers(w: dict, check: str) -> set:
    """Identities whose earlier passes of `check` may not be carried: the fact/deck authors, and whoever holds verdicts
    of the other checklist (its current record, or passes its next round would carry)."""
    other = next(c for c in CHECKS if c != check)
    rec = (w.get("semantic_checks") or {}).get(other) or {}
    out = {(w.get("deck") or {}).get("author"), (w.get("facts") or {}).get("author")} | set(rec.get("memory_reviewers") or [])
    if check_current(w, other):
        out |= reviewers(rec)
    return out - {None}


class _Basis:
    """What each review item's verdict rests on, as a fingerprint (check name, item content, the facts with their display
    text, the source text of cited units and their source pages, related pages). Conservative: any change re-opens it."""

    def __init__(self, w: dict, ctx: dict, check: str):
        self.w, self.ctx, self.check = w, ctx, check
        self.order = ctx["order"]
        self.pos = {p: i for i, p in enumerate(self.order)}
        self.view = {p["page"]["id"]: p for p in ctx["pages"]}
        self.sections = {s["id"]: s for s in (w.get("summary") or {}).get("sections") or []}
        self.scoped = {s["id"]: s for s in ctx["sections"]}
        self.src_sha = {s["id"]: s.get("sha256") for s in w["sources"]}
        self.spage = {p["id"]: (s, p) for s in w["sources"] for p in s["pages"]}
        self.by_unit = {u["id"]: u for s in w["sources"] for u in s["units"] + s.get("transcriptions", [])}
        self.unit_src = {u["id"]: s.get("sha256") for s in w["sources"] for u in s["units"] + s.get("transcriptions", [])}
        self.figs = {g["id"]: g for s in w["sources"] for g in s.get("figures", [])}
        self.raw_rel = {f"{sec['id']}.relation{i}": (r, sec) for sec in ctx["sections"]
                        for i, r in enumerate((sec.get("message") or {}).get("relations") or [], 1)}
        deck = w["deck"]["result"]
        self.bindings = deck.get("content_bindings") or []
        self.responses = deck.get("context_responses") or []
        self.base = {"check": check, "scope": ctx["scope"]}
        self.refs = {i["ref"] for i in ledger.unresolved(w, "semantic", check)}
        self._pages = {}

    def prints(self, pages) -> dict:
        return {p: self.ctx["prints"].get(p) for p in sorted(set(pages))}

    def unit(self, uid) -> dict | None:
        """The unit as the review sees it (confirmations applied) and the file it comes from."""
        u = self.ctx["by_unit"].get(uid) or self.by_unit.get(uid)
        return {"unit": u, "source_sha256": self.unit_src.get(uid)} if u else None

    def source_page(self, spid) -> dict | None:
        if spid not in self.spage:
            return None
        s, p = self.spage[spid]
        units = [self.unit(u["id"]) for u in s["units"] + s.get("transcriptions", []) if u["page_id"] == spid]
        return {"source_sha256": s.get("sha256"), "location": p.get("location"), "reading": p.get("reading"),
                "requires_visual": p.get("requires_visual"), "units": units,
                "figures": [(g["id"], g.get("sha256")) for g in s.get("figures", []) if g.get("page_id") == spid]}

    def page(self, pid) -> str:
        if pid not in self._pages:
            self._pages[pid] = self._page(pid)
        return self._pages[pid]

    def _page(self, pid) -> str:
        ctx, facts = self.ctx, self.ctx["page_facts"][pid]
        i = self.pos[pid]
        near = [self.order[j] for j in (i - 1, i + 1) if 0 <= j < len(self.order)]
        raw = {f: ctx["v"]["facts"].get(f) for f in facts}
        fset = set(facts) | {pid}
        return _fp({**self.base, "kind": "pages", "id": pid, "print": ctx["prints"][pid], "facts": raw,
                    "units": {u: self.unit(u) for u in sorted(ctx["page_units"][pid])},
                    "figures": {g: (self.figs.get(g) or {}).get("sha256") for g in sorted({(f or {}).get("figure") for f in raw.values()} - {None})},
                    "source_pages": {sp: self.source_page(sp) for sp in ctx["page_src"][pid]},
                    "neighbours": self.prints(near),
                    "sections": {s: self.sections.get(s) for s in self.view[pid]["page"].get("section_ids") or []},
                    "bindings": [b for b in self.bindings
                                 if (set(b.get("primary_fact_refs") or []) | set(b.get("dependent_fact_refs") or [])) & fset],
                    "context_responses": [x for x in self.responses if any(f in json.dumps(x, ensure_ascii=False, default=str) for f in fset)]})

    def relation(self, rel: dict) -> str:
        v = self.ctx["v"]["facts"]
        raw = self.raw_rel.get(rel["relation_id"])
        units = set(rel.get("unit_ids") or []) | ({rel["evidence_unit"]} if isinstance(rel.get("evidence_unit"), str) else set())
        facts = set(rel.get("primary_fact_refs") or []) | set(rel.get("dependent_fact_refs") or [])
        if isinstance(rel.get("backed_by"), str):
            facts.add(rel["backed_by"])
        pages = rel.get("presented_on") or []
        return _fp({**self.base, "kind": "relations", "id": rel["relation_id"], "relation": rel,
                    "raw": raw[0] if raw else None, "message": (raw[1].get("message") if raw else None),
                    "units": {u: self.unit(u) for u in sorted(units)}, "facts": {f: v.get(f) for f in sorted(facts)},
                    "pages": self.prints(pages), "page_bases": {p: self.page(p) for p in sorted(set(pages)) if p in self.pos}})

    def chapter(self, sid) -> str:
        pages = [p for p in self.order if sid in (self.view[p]["page"].get("section_ids") or [])]
        return _fp({**self.base, "kind": "chapters", "id": sid, "section": self.scoped.get(sid) or self.sections.get(sid),
                    "page_order": pages, "pages": self.prints(pages)})

    def source_item(self, r: dict, row: dict) -> str:
        spid = r["source_page_id"]
        s, _ = self.spage[spid]
        cited = set(r.get("summary_sections") or [])
        topic = [p for p in self.order if cited & set(self.view[p]["page"].get("section_ids") or [])]
        seq = [p["id"] for p in s["pages"]]
        i = seq.index(spid)
        adjacent = {x: {"content": self.source_page(x), "presented_on": self.prints(self._presented(x))}
                    for x in seq[max(0, i - 1):i + 2] if x != spid}
        item = {k: r.get(k) for k in r if k not in ("image_url", "file_url")}
        return _fp({**self.base, "kind": "source_pages", "id": spid, "item": item, "content": self.source_page(spid),
                    "deck_pages": self.prints(list(r.get("presented_on") or []) + list(row.get("deck_pages") or [])),
                    "cited_sections": {x: self.sections.get(x) for x in sorted(cited)}, "topic_pages": self.prints(topic),
                    "adjacent": adjacent, "outline": self.w.get("outline"), "row": row})

    def _presented(self, spid) -> list:
        return [p for p in self.order if spid in self.ctx["page_src"][p]]

    def teaching_item(self, r: dict, row: dict) -> str:
        sid = r.get("section_id") or (r["item_id"] if r.get("kind") == "section" else None)
        return _fp({**self.base, "kind": "teaching_items", "id": r["item_id"], "item": r,
                    "deck_pages": self.prints(list(r.get("presented_on") or []) + list(row.get("deck_pages") or [])),
                    "section": self.sections.get(sid) if sid else None, "outline": self.w.get("outline"), "row": row})


def _items(w: dict, ctx: dict, check: str) -> dict:
    """The current items of each carried kind of `check`: {kind: {id: item}}."""
    out = {"pages": {p: None for p in ctx["order"]}}
    if check == "COVERAGE":
        out["source_pages"] = {r["source_page_id"]: r for r in source_pages(w, ctx)}
        out["teaching_items"] = {r["item_id"]: r for r in teaching_items(w, ctx)}
    else:
        out["relations"] = {r["relation_id"]: r for r in relations(w, ctx)}
        out["chapters"] = {s["id"]: s for s in outcome_sections(w, ctx)}
    return out


def _held_open(basis: "_Basis", kind: str, iid: str, item) -> bool:
    """Whether an unresolved issue of this checklist sits on the item (or, for a page, on its facts, units or source
    pages; for a relation, on its units): such an item is judged again every round."""
    refs, ctx = basis.refs, basis.ctx
    if iid in refs:
        return True
    if kind == "pages":
        return bool(refs & (set(ctx["page_facts"][iid]) | ctx["page_units"][iid] | set(ctx["page_src"][iid])))
    if kind == "relations":
        return bool(refs & set(item.get("unit_ids") or []))
    return False


def _fingerprint(basis: _Basis, kind: str, iid: str, item, row: dict) -> str:
    if kind == "pages":
        return basis.page(iid)
    if kind == "relations":
        return basis.relation(item)
    if kind == "chapters":
        return basis.chapter(iid)
    if kind == "source_pages":
        return basis.source_item(item, row)
    return basis.teaching_item(item, row)


def carried(w: dict, check: str, ctx: dict, memory: dict | None) -> dict:
    """{kind: {id: memory entry}} of the items this round does not judge: an earlier independent round of this checklist
    passed them, their fingerprint is unchanged, no unresolved issue sits on them, and their original reviewer is still
    independent (not an author, not holding verdicts of the other checklist)."""
    out = {k: {} for k in CARRY_KINDS[check]}
    rows = (memory or {}).get("rows") or {}
    if not rows or (memory or {}).get("schema") != CARRY_SCHEMA or memory.get("check") != check:
        return out
    blocked = blocked_reviewers(w, check)
    basis = _Basis(w, ctx, check)
    for kind, items in _items(w, ctx, check).items():
        for iid, item in items.items():
            e = rows.get(f"{kind}:{iid}")
            if not e or e.get("reviewer") in blocked or _held_open(basis, kind, iid, item):
                continue
            if e.get("fingerprint") == _fingerprint(basis, kind, iid, item, e.get("row") or {}):
                out[kind][iid] = e
    return out


def carry_counts(w: dict, ctx: dict, check: str, carry: dict) -> dict:
    items = _items(w, ctx, check)
    return {k: {"count": len(carry[k]), "of": len(items[k])} for k in CARRY_KINDS[check]}


def carry_rule(counts: dict) -> str:
    n = "、".join(f"{CARRY_NAMES[k]}{c['count']}/{c['of']}" for k, c in counts.items())
    return (f"本轮沿用此前独立审核的通过判定：{n}。这些条目的页面内容、所引事实的显示文字与原文、来源单元原文、关系及相关页面均未改变"
            "（代码按内容指纹核对），也没有未闭环问题，不在本轮pages、清单与result_contract中，也不需判定；判定仍记在原审核人名下。"
            "只判定列出的条目；prior_issues中的未闭环问题仍须逐条处置。")


def _without_carried(reg: dict, pages) -> dict:
    return {**reg, "affected": [p for p in reg["affected"] if p not in pages]}


def _source_reread(ctx: dict, reg: dict, prev: dict, ids) -> set:
    """Source pages the COVERAGE brief shows in full (read=true); the others show their archived status (read=false)."""
    affected = {s for p in reg["affected"] for s in ctx["page_src"][p]}
    old = prev.get("source_pages") or {}
    return {s for s in ids if reg["mode"] == "FULL" or s not in old or old[s]["status"] == "NEEDS_HUMAN" or s in affected}


def build_memory(w: dict, ctx: dict, check: str, reviewer: str, rnd: dict, passed: dict, carry: dict) -> dict:
    """The passes this round leaves for later rounds: items this reviewer judged fine plus the carried ones (under their
    original reviewer), each with its fingerprint; items an unresolved issue now sits on are left out."""
    basis = _Basis(w, ctx, check)
    items = _items(w, ctx, check)
    rows = {}
    for kind in CARRY_KINDS[check]:
        for iid, row in passed.get(kind, {}).items():
            if iid not in items[kind] or _held_open(basis, kind, iid, items[kind][iid]):
                continue
            rows[f"{kind}:{iid}"] = {"fingerprint": _fingerprint(basis, kind, iid, items[kind][iid], row), "row": row,
                                     "reviewer": reviewer, "round": rnd["round"], "at": rnd["at"]}
        for iid, e in carry.get(kind, {}).items():
            if not _held_open(basis, kind, iid, items[kind][iid]):
                rows[f"{kind}:{iid}"] = e
    return {"schema": CARRY_SCHEMA, "check": check, "rows": rows}


# ------------------------------------------------------------------ brief
def brief(w: dict, check: str, req: dict, memory: tuple | None = None) -> dict:
    """`memory` is (snapshot path, value) of the checklist's carried passes (Store.semantic_memory)."""
    from factdeck.context import signals, NOTES
    d = _d()
    ctx = context(w)
    reg = regression(w, check, ctx)
    prev = prior_check(w, check)
    memory_path, memory_value = memory or (None, None)
    carry = carried(w, check, ctx, memory_value)
    cpages = carry["pages"]
    counts = carry_counts(w, ctx, check, carry)
    read_reg = _without_carried(reg, cpages)
    by_unit = ctx["by_unit"]
    srcs = {r["source_page_id"]: r for r in source_pages(w, ctx)}
    responses = ((w.get("deck") or {}).get("issue_responses") or {})
    view = []
    for p in ctx["pages"]:
        pid = p["page"]["id"]
        if pid in cpages:                               # an earlier independent pass still holds: not listed
            continue
        if pid in reg["carry"]:                         # not re-read this round: an outline, not the evidence
            view.append({"page": {k: p["page"].get(k) for k in ("id", "layout", "title") if k in p["page"]},
                         "fact_ids": [f["id"] for f in p["facts"]], "read": False, "previous_verdict": reg["carry"][pid]})
            continue
        facts = []
        for f in p["facts"] + p["edge_facts"]:
            fact = ctx["v"]["facts"][f["id"]]
            sig = [] if fact.get("figure") else signals(fact["quote"], fact.get("display"), by_unit[fact["unit"]]["text"])
            facts.append({**f, "source_page_id": ctx["src_page"](f["id"]), **({"context_signals": sig} if sig else {})})
        n = len(p["facts"])
        view.append({"page": p["page"], "facts": facts[:n], "edge_facts": facts[n:],
                     "source_pages": [{k: srcs[s][k] for k in ("source_page_id", "location", "requires_visual", "image_url", "file_url")}
                                      for s in ctx["page_src"][pid] if s in srcs],
                     "read": True})
    prior = [ledger.view(i, responses.get(i["id"])) for i in ledger.unresolved(w, "semantic", check)]
    fixed = [{k: i[k] for k in ("id", "ref", "severity", "problem")} for i in ledger.issues(w, "semantic")
             if i["check"] == check and i["status"] == "FIXED"]
    common = ["这是两张独立检查表之一：" + CHECK_NAMES[check] + "。另一张由不同执行端完成；本表只对本表目标负责，但发现的任何阻断都要记录。",
              "先回看 prior_issues：此前全部未闭环问题及历史、作者回应（author_response）。逐条给出处置：FIXED（须在 evidence_refs 写出当前版本中的页面/要点/关系编号，"
              "并在 evidence 中说明看到的修订）、OPEN（仍未解决）、NEEDS_HUMAN（须人工裁定，例如原文未明确的关系、来源证据缺失、纳入范围）、"
              "RETAINED（现有证据不足以判断而保留）。不得只写“已修复”；页面修订无法解决的问题标 NEEDS_HUMAN，不要让它在修订循环中反复出现。",
              "fixed_issues 是已标为修复的问题；若发现它们再次出现，新问题写 reopens: 问题编号。",
              "在pages.issues中重述prior_issues的同一未闭环事项时写existing_issue_id: 原问题编号；页面或来源定位变化不创建新编号。不同错误仍作为新问题。",
              "pages 中 read=false 的页面在本轮可写 verdict: CARRIED（与上一轮相同、且不受本次修订影响）；read=true 的页面须重新阅读并给出 SUPPORTED 或 ISSUES。",
              "需要核对原件的页面必须打开 source_pages 的 image_url（PDF整页图）或 file_url；must_view_source_pages 中的来源页须实际查看后写入 viewed_source_pages。没看就不要写。",
              "每条新问题写：severity（BLOCKER/NOTE）、category（CONTENT_ERROR 内容错误 / EVIDENCE_MISSING 来源证据缺失 / EXPRESSION_AMBIGUITY 页面表达歧义 / HUMAN_DECISION 人工决策）、"
              "ref（页面、来源页、单元、事实、要点或关系编号）、source_ref（来源位置）、evidence（证据）、problem、relation（涉及的关系，可空）、suggestion（建议处置）。",
              "context_signals 是程序按句形给出的提示（引导句、开头的转折/承接词、单元前后还有内容）；逐条判断是否丢失了条件、例外、列表项或被转折的前句。",
              "unchecked 写明本轮未能检查的范围（例如无法打开的原件），不能用“通过”掩盖。不得给出医学放行结论，不得启动正式生成。"]
    if check == "COVERAGE":
        extra = ["方向：从来源页向页面逐项核对。核对数字、单位、比较符号、否定、限定、人群、时间、脚注、表格行列对应，以及未纳入项；不要从页面反向猜来源内容。",
                 "已上页的每条内容逐项核对六类限定条件（人群、时间、阈值、条件、例外、否定）及模态/强度词（可能、尚未证明、至关重要、弱相关）："
                 "页面压缩后丢失或改变其中任一项即报问题，problem中写明所缺类别；省略的范围标签须在页面某处说明一次。",
                 "范围以客户已确认的教学目标、总结和teaching_items为准。完整登记来源不等于每条来源细节都必须上页；"
                 "claim的推荐/阈值类型只是风险筛查，不自动成为MUST_INCLUDE。未直接引用的页须按具体主题判断："
                 "已选内容不可缺的条件/例外或强制教学要点遗漏才阻断；专科细节、重复证据、未纳入当前教学目标的支持材料可EXCLUDED，"
                 "理由须说明该页内容、对应教学目标及选取深度，不能只写时长/页数。来源不清或与客户范围实际冲突才NEEDS_HUMAN。",
                 "source_pages：每个来源页给出 status：PRESENTED（deck_pages 写出呈现它的页面）、EXCLUDED（reason 写明不纳入的理由，含空白、参考文献、重复、不可读）、"
                 "NEEDS_HUMAN（reason 写明需要用户决定什么）。presented_on 是程序按事实引用算出的页面，regions 是该页的区域统计。",
                 "teaching_items：每个提纲条目、提纲要点、总结章节和关键要点同样给出状态；不能用“整章已覆盖”代替逐项。部分呈现时写 PRESENTED 并另报问题。"]
        open_srcs = [r for r in srcs.values() if r["source_page_id"] not in carry["source_pages"]]
        open_items = [r for r in teaching_items(w, ctx) if r["item_id"] not in carry["teaching_items"]]
        coverage = {"source_pages": [_item_template(r, "source_page_id", prev.get("source_pages")) for r in open_srcs],
                    "teaching_items": [_item_template(r, "item_id", prev.get("teaching_items")) for r in open_items]}
        source_view = []
        reread = _source_reread(ctx, reg, prev, srcs)
        for r in open_srcs:
            old = (prev.get('source_pages') or {}).get(r['source_page_id'])
            source_view.append({**r, 'read': True} if r['source_page_id'] in reread else {
                'source_page_id': r['source_page_id'], 'location': r['location'], 'read': False,
                'previous_status': old, 'presented_on': r['presented_on']})
        inventory = {"source_pages": source_view, "teaching_items": open_items}
        extra.append('read=false的来源页沿用存档分类和理由，不重新阅读全文；仅核对本次变化的映射。来源全文登记仍由代码维护。')
    else:
        extra = ["方向：从大纲要点和来源关系向页面核对：上下文、逻辑类型（条件、因果/相关、先后、并列、包含、分组、比较、阈值归属、跨页承接）、方向、分组和视觉表达。",
                 "relations：逐条判断 verdict：SUPPORTED（原文明确支持该关系及方向）、UNSUPPORTED（原文不支持或方向相反）、UNKNOWN（原文没有说明，页面也不应表达该关系）；"
                 "非 SUPPORTED 须写 issue。kind=grouping 是页面结构本身：列表不能自行解释为“同时满足”或“任选其一”；manual=true 的关系是作者判断。",
                 "没有箭头不代表没有关系；也不能据页面布局补关系。原文未明确的关系标 UNKNOWN，禁止自动补全。",
                 "kind=summary_relation 另判 expression（页面有没有说少）：EXPRESSED（读者从页面能读出这条关系及方向）、"
                 "FLATTENED（相关内容上页了，但被排成并列清单或分散在各页，读不出关系）、MISSING（关系所涉内容未上页）。",
                 "chapters：每章只看本章页面（不看总结），在 restated 写下你能复述的本章核心论点；core_on_pages：页面是否让读者读出总结的核心句（YES/NO）；"
                 "limits_on_pages：标为 limit 的局限、例外和适用范围是否都在页面上（YES/NO；本章没有 limit 时写 YES）。NO 须写 issue。"]
        rels = [r for r in relations(w, ctx) if r["relation_id"] not in carry["relations"]]
        chapters = [c for c in outcome_sections(w, ctx) if c["id"] not in carry["chapters"]]
        carried_rel = {r["relation_id"] for r in rels if all(p in reg["carry"] for p in r["presented_on"]) and r["presented_on"]
                       and r["relation_id"] in (prev.get("relations") or {})}
        coverage = {"relations": [{"relation_id": r["relation_id"], "verdict": "CARRIED" if r["relation_id"] in carried_rel else "",
                                   **({"expression": ""} if r["kind"] == "summary_relation" else {}), "issue": ""} for r in rels],
                    "chapters": [{"section_id": c["id"], "restated": "", "core_on_pages": "", "limits_on_pages": "", "issue": ""}
                                 for c in chapters]}
        inventory = {"relations": rels,
                     "chapter_messages": [{"section_id": c["id"], "title": c.get("title"), "core": (c["message"].get("core") or {}).get("quote"),
                                           "limits": [k for k, v in c["message"]["roles"].items() if v == "limit"]} for c in chapters]}
    summary_view = w['summary']
    if reg['mode'] == 'IMPACT':
        sections = {s for p in ctx['pages'] if p['page']['id'] in read_reg['affected'] for s in p['page'].get('section_ids', [])}
        summary_view = {'sections': [s for s in w['summary']['sections'] if s['id'] in sections],
                        'read_scope': 'IMPACT', 'full_summary_sha256': digest(w['summary'])}
    return {"kind": "SEMANTIC_REVIEW", "check": check, "check_name": CHECK_NAMES[check], **req,
            "context_responses": w["deck"]["result"].get("context_responses", []),
            "input_sha256": d.semantic_input(w), "summary": summary_view, "pages": view, "coverage": w["deck"]["coverage"],
            "scope": ctx["scope"], "regression": {k: reg[k] for k in ("mode", "reason", "changed", "affected")},
            "prior_issues": prior, "fixed_issues": fixed, "must_view_source_pages": must_view(ctx, read_reg), **inventory,
            "context_signal_kinds": NOTES, "carried_review": counts, "carry_memory": memory_path,
            "rules": common + extra + ([carry_rule(counts)] if any(c["count"] for c in counts.values()) else []),
            "result_contract": {"check": check, "input_sha256": d.semantic_input(w),
                                "prior_issues": [{"issue_id": i["id"], "status": "", "evidence": "", "evidence_refs": []} for i in prior],
                                "pages": [{"page_id": p["page"]["id"], "verdict": "CARRIED" if p["page"]["id"] in reg["carry"] else "",
                                           "issues": []} for p in ctx["pages"] if p["page"]["id"] not in cpages],
                                **coverage, "viewed_source_pages": [], "unchecked": [], "issues": []}}


def _item_template(r: dict, key: str, prev: dict | None) -> dict:
    if r.get("presented_on"):
        return {key: r[key], "status": "PRESENTED", "deck_pages": list(r["presented_on"]), "reason": ""}
    if r.get("classification") and r["classification"] != "SUBSTANTIVE":
        return {key: r[key], "status": "EXCLUDED", "deck_pages": [], "reason": f"阅读分类为 {r['classification']}：{r.get('reading_note', '')}".rstrip("：")}
    if r.get("unsupported") is not None:
        return {key: r[key], "status": "EXCLUDED", "deck_pages": [], "reason": f"无资料支撑：{r['unsupported']}"}
    if r.get("omission"):
        return {key: r[key], "status": "EXCLUDED", "deck_pages": [], "reason": f"页面规格 omissions：{r['omission']}"}
    old = (prev or {}).get(r[key])
    if old and old["status"] != "PRESENTED":
        return {key: r[key], **{k: old[k] for k in ("status", "reason")}, "deck_pages": []}
    return {key: r[key], "status": "", "deck_pages": [], "reason": ""}


# ------------------------------------------------------------------ accept
def accept(w: dict, result: dict, reviewer: str, check: str, memory: dict | None = None, keep=None) -> dict:
    """`memory` is the carried-pass snapshot the task's brief was built from; `keep` saves this round's (Store.snapshot)."""
    d = _d()
    require(check in CHECKS, "语义审查须指定检查表：COVERAGE 或 RELATIONS", 422)
    require(d.deck_current(w), "没有当前版本的页面规格")
    require(reviewer not in {w["deck"]["author"], w["facts"]["author"]}, "语义审查须由编写事实库和页面之外的执行端完成", 422)
    require(result.get("check", check) == check, "结果对应的检查表不符", 422)
    require(result.get("input_sha256") == d.semantic_input(w), "审查对应的页面或事实库已过期")
    ledger.book(w, "semantic")
    ctx = context(w)
    reg = regression(w, check, ctx)
    carry = carried(w, check, ctx, memory)
    # carried verdicts stay their original reviewer's: the two checklists' reviewers (carried ones included) are disjoint
    mine = {reviewer} | {e.get("reviewer") for k in carry.values() for e in k.values()}
    other = next(c for c in CHECKS if c != check)
    if check_current(w, other):
        require(not mine & reviewers(w["semantic_checks"][other]), "两张检查表须由不同的独立执行端完成", 422)
    cpages = carry["pages"]
    order = ctx["order"]
    rows = result.get("pages")
    require(isinstance(rows, list), "需按顺序逐页给出审查结论", 422)
    again = [r.get("page_id") for r in rows if isinstance(r, dict) and r.get("page_id") in cpages]
    require(not again, "沿用通过判定的页面不在本轮pages中：" + "、".join(again), 422)
    require([r.get("page_id") for r in rows if isinstance(r, dict)] == [p for p in order if p not in cpages],
            "需按顺序逐页给出审查结论（沿用通过判定的页面除外）", 422)
    refs = _refs(w, ctx)
    new, verdicts, ok, problem, read = [], {}, set(), set(), []
    passed = {k: {} for k in CARRY_KINDS[check]}
    for pid, e in cpages.items():
        verdicts[pid] = (e.get("row") or {}).get("verdict", "SUPPORTED")
        ok.add(pid)
    for r in rows:
        pid, vd = r["page_id"], r.get("verdict")
        require(vd in PAGE_VERDICTS, "每页结论需为 SUPPORTED、ISSUES 或 CARRIED", 422)
        items = r.get("issues") or []
        if vd == "CARRIED":
            require(pid in reg["carry"], f"{pid} 受本次修订影响（或首次检查），须重新阅读后给出结论", 422)
            require(not items, f"{pid} 沿用上一轮结论时不能另列问题；有新问题请改为 ISSUES", 422)
            verdicts[pid] = reg["carry"][pid]
            continue
        read.append(pid)
        require((vd == "ISSUES") == bool(items), "有问题时需列出问题，没有问题时结论为SUPPORTED", 422)
        verdicts[pid] = vd
        if vd == "SUPPORTED":
            ok.add(pid)
            passed["pages"][pid] = {"verdict": "SUPPORTED"}
        for it in items:
            require(isinstance(it, dict), "问题需为对象", 422)
            ref = str(it.get("ref") or "").strip()
            new.append(it if ref in refs else {**it, "ref": pid, "source_ref": it.get("source_ref") or ref})
    new += list(result.get("issues") or [])
    auto, record = [], {}
    if check == "COVERAGE":
        srcs = [r["source_page_id"] for r in source_pages(w, ctx)]
        reread = _source_reread(ctx, reg, prior_check(w, check), srcs)
        for kind, key, expected, label in (("source_pages", "source_page_id", srcs, "来源页"),
                                           ("teaching_items", "item_id", [r["item_id"] for r in teaching_items(w, ctx)], "教学条目")):
            got = result.get(kind)
            again = [r.get(key) for r in got or [] if isinstance(r, dict) and r.get(key) in carry[kind]]
            require(not again, f"沿用通过判定的{label}不在本轮{kind}中：" + "、".join(map(str, again)), 422)
            out = _statuses(got, key, [x for x in expected if x not in carry[kind]], order, label, auto, ok, problem)
            passed[kind] = {rid: x for rid, x in out.items() if x["status"] in {"PRESENTED", "EXCLUDED"}
                            and (kind != "source_pages" or rid in reread)}
            for rid, e in carry[kind].items():
                out[rid] = dict(e["row"])
                ok.add(rid)
            record[kind] = {rid: out[rid] for rid in expected if rid in out}
    else:
        rels = {r["relation_id"]: r for r in relations(w, ctx)}
        got = result.get("relations")
        require(isinstance(got, list) and all(isinstance(x, dict) for x in got), "relations 需为列表", 422)
        ids = [x.get("relation_id") for x in got]
        again = [i for i in ids if i in carry["relations"]]
        require(not again, "沿用通过判定的关系不在本轮relations中：" + "、".join(map(str, again)), 422)
        require(len(ids) == len(set(ids)) and set(ids) == set(rels) - set(carry["relations"]),
                "须逐条判断全部关系（relations 不多不少，沿用通过判定的关系除外）", 422)
        prev = prior_check(w, check).get("relations") or {}
        record["relations"] = {}
        for x in got:
            rid, vd = x["relation_id"], x.get("verdict")
            require(vd in RELATION_VERDICTS, f"关系 {rid} 的结论须是 SUPPORTED / UNSUPPORTED / UNKNOWN", 422)
            if vd == "CARRIED":
                require(rid in prev and rels[rid]["presented_on"] and all(p in reg["carry"] for p in rels[rid]["presented_on"]),
                        f"关系 {rid} 所在页面受本次修订影响，须重新判断", 422)
                vd = prev[rid]["verdict"]
            text = str(x.get("issue") or "").strip()
            if vd != "SUPPORTED" and x.get("verdict") != "CARRIED":
                require(text, f"关系 {rid} 判为 {vd} 时须写明问题", 422)
                where = "、".join(rels[rid]["presented_on"]) or "（未上页）"
                auto.append({"severity": "BLOCKER", "category": "CONTENT_ERROR" if vd == "UNSUPPORTED" else "HUMAN_DECISION",
                             "ref": rid, "source_ref": "、".join(rels[rid].get("unit_ids") or []) or str(rels[rid].get("backed_by") or ""),
                             "evidence": f"页面 {where}", "problem": f"关系{'不被原文支持' if vd == 'UNSUPPORTED' else '原文未明确'}：{text}",
                             "relation": rels[rid]["kind"]})
            expression = None
            if rels[rid]["kind"] == "summary_relation":
                expression = x.get("expression") or ((prev.get(rid) or {}).get("expression") if x.get("verdict") == "CARRIED" else None)
                require(expression in EXPRESSIONS, f"关系 {rid} 须判断 expression：EXPRESSED / FLATTENED / MISSING", 422)
                if expression != "EXPRESSED" and x.get("verdict") != "CARRIED":
                    require(text, f"关系 {rid} 判为 {expression} 时须写明问题", 422)
                    auto.append({"severity": "BLOCKER", "category": "EXPRESSION_AMBIGUITY", "ref": rid,
                                 "source_ref": "、".join(rels[rid].get("unit_ids") or []),
                                 "evidence": f"页面 {'、'.join(rels[rid]['presented_on']) or '（未上页）'}",
                                 "problem": f"总结中的关系在页面上{'被压平为并列内容' if expression == 'FLATTENED' else '缺失'}：{text}",
                                 "relation": "summary_relation"})
            (ok if vd == "SUPPORTED" and expression in (None, "EXPRESSED") else problem).add(rid)
            record["relations"][rid] = {"verdict": vd, "issue": text or (prev.get(rid) or {}).get("issue", ""),
                                        **({"expression": expression} if expression else {})}
            if x.get("verdict") == "SUPPORTED" and expression in (None, "EXPRESSED"):
                passed["relations"][rid] = record["relations"][rid]
        for rid, e in carry["relations"].items():
            record["relations"][rid] = dict(e["row"])
            ok.add(rid)
        record["relations"] = {rid: record["relations"][rid] for rid in rels}
        everyone = [c["id"] for c in outcome_sections(w, ctx)]
        expected = [c for c in everyone if c not in carry["chapters"]]
        chapters = result.get("chapters")
        require(isinstance(chapters, list), "chapters 须按顺序逐章给出（本次范围内有信息结构的章节）", 422)
        again = [c.get("section_id") for c in chapters if isinstance(c, dict) and c.get("section_id") in carry["chapters"]]
        require(not again, "沿用通过判定的章节不在本轮chapters中：" + "、".join(map(str, again)), 422)
        require([c.get("section_id") for c in chapters if isinstance(c, dict)] == expected,
                "chapters 须按顺序逐章给出（本次范围内有信息结构的章节，沿用通过判定的章节除外）", 422)
        record["chapters"] = {}
        for c in chapters:
            sid = c["section_id"]
            require(c.get("core_on_pages") in YES_NO and c.get("limits_on_pages") in YES_NO, f"章节 {sid} 须判断 core_on_pages 与 limits_on_pages（YES/NO）", 422)
            require(str(c.get("restated", "")).strip(), f"章节 {sid} 须写下只看页面能复述的核心论点（restated）", 422)
            issue_text = str(c.get("issue", "")).strip()
            for key, what in (("core_on_pages", "核心句"), ("limits_on_pages", "局限与适用范围")):
                if c[key] == "NO":
                    require(issue_text, f"章节 {sid} 的 {key} 为 NO 时须写明问题", 422)
                    auto.append({"severity": "BLOCKER", "category": "EXPRESSION_AMBIGUITY", "ref": sid, "source_ref": sid,
                                 "evidence": f"复述：{str(c['restated'])[:200]}", "problem": f"只看页面读不出本章的{what}：{issue_text}"})
            (ok if c["core_on_pages"] == "YES" and c["limits_on_pages"] == "YES" else problem).add(sid)
            record["chapters"][sid] = {k: c[k] for k in ("restated", "core_on_pages", "limits_on_pages")} | {"issue": issue_text}
            if c["core_on_pages"] == "YES" and c["limits_on_pages"] == "YES":
                passed["chapters"][sid] = record["chapters"][sid]
        for sid, e in carry["chapters"].items():
            record["chapters"][sid] = dict(e["row"])
            ok.add(sid)
        record["chapters"] = {sid: record["chapters"][sid] for sid in everyone}
    need_view = must_view(ctx, _without_carried(reg, cpages))
    viewed = result.get("viewed_source_pages") or []
    require(isinstance(viewed, list) and set(need_view) <= set(viewed),
            "须实际查看并列出以下来源页原图：" + "、".join(sorted(set(need_view) - set(viewed or []))), 422)
    unchecked = [str(x).strip() for x in result.get("unchecked") or [] if str(x).strip()]
    rnd = ledger.record_round(w, "semantic", check, reviewer=reviewer, input_sha256=d.semantic_input(w),
                              dispositions=result.get("prior_issues"), new_issues=new, valid_refs=refs,
                              ok_refs=ok, problem_refs=problem, auto_issues=auto,
                              meta={"mode": reg["mode"], "pages_read": len(read), "pages_carried": len(order) - len(read),
                                    "carried_passes": {k: len(v) for k, v in carry.items()}})
    memory_out = build_memory(w, ctx, check, reviewer, rnd, passed, carry)
    held = {e["reviewer"] for e in memory_out["rows"].values()}
    units_total = sum(len(s["units"]) + len(s["transcriptions"]) for s in w["sources"])
    shown_units = set().union(*ctx["page_units"].values()) if order else set()
    record.update({"reviewers": sorted(mine - {None}), "memory_reviewers": sorted(held),
                   "carry_memory": keep(memory_out) if keep else None, "carried": carry_counts(w, ctx, check, carry),
                   "input_sha256": d.semantic_input(w), "reviewer": reviewer, "at": now(), "round": rnd["round"],
                   "facts_sha": d.facts_sha(w), "summary_sha": digest(w["summary"]), "sources_sha": sources_print(w),
                   "scope_pages": order, "page_prints": ctx["prints"], "page_verdicts": verdicts,
                   "regression": {k: reg[k] for k in ("mode", "reason", "changed", "affected")},
                   "viewed_source_pages": sorted(set(viewed)), "unchecked": unchecked,
                   "counts": {"source_pages": sum(len(s["pages"]) for s in w["sources"]), "source_units": units_total,
                              "source_units_on_pages": len(shown_units), "teaching_items": len(record.get("teaching_items") or {}),
                              "relations": len(record.get("relations") or {}), "deck_pages": len(order), "deck_pages_read": len(read),
                              "deck_pages_carried": len(order) - len(read), "deck_pages_carried_passes": len(cpages),
                              "prior_issues": len(result.get("prior_issues") or []),
                              "new_issues": len(rnd["new"]), "viewed_source_pages": len(set(viewed))}})
    w.setdefault("semantic_checks", {})[check] = record
    w["semantic_review"] = combined(w)
    return record


def _refs(w: dict, ctx: dict) -> set:
    refs = set(ctx["order"]) | set(ctx["by_unit"]) | set(ctx["v"]["facts"])
    refs |= {p["id"] for s in w["sources"] for p in s["pages"]}
    refs |= {r["item_id"] for r in teaching_items(w, ctx)} | {r["relation_id"] for r in relations(w, ctx)}
    refs |= {s["id"] for s in ctx["sections"]}
    return refs


def _statuses(rows, key: str, expected: list, order: list, label: str, auto: list, ok: set, problem: set) -> dict:
    require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), f"{label}状态需为列表", 422)
    ids = [r.get(key) for r in rows]
    require(len(ids) == len(set(ids)) and set(ids) == set(expected),
            f"每个{label}都须给出状态（不多不少）：缺少 " + "、".join(sorted(set(expected) - set(ids))[:20]), 422)
    out = {}
    for r in rows:
        st, rid = r.get("status"), r[key]
        require(st in ITEM_STATUSES, f"{label} {rid} 的状态须是 PRESENTED / EXCLUDED / NEEDS_HUMAN", 422)
        pages = r.get("deck_pages") or []
        reason = str(r.get("reason") or "").strip()
        if st == "PRESENTED":
            require(isinstance(pages, list) and pages and set(pages) <= set(order), f"{label} {rid} 标为已呈现时须写出本套页面编号", 422)
            ok.add(rid)
        else:
            require(reason, f"{label} {rid} 未呈现时须写明理由", 422)
            if st == "EXCLUDED":
                ok.add(rid)
            else:
                problem.add(rid)
                auto.append({"severity": "BLOCKER", "category": "HUMAN_DECISION", "ref": rid, "source_ref": rid,
                             "evidence": reason, "problem": f"{label}待人工确认是否纳入：{reason}", "relation": ""})
        out[rid] = {"status": st, "deck_pages": list(pages), "reason": reason}
    return out


def combined(w: dict) -> dict:
    """The aggregate earlier screens and reports read; checks and the ledger are the authority."""
    d = _d()
    checks = w.get("semantic_checks") or {}
    done = {c: {k: checks[c][k] for k in ("reviewer", "at", "input_sha256", "round", "counts", "unchecked", "regression")}
            | {"reviewers": sorted(reviewers(checks[c]))} for c in CHECKS if c in checks}
    return {"checks": done, "input_sha256": d.semantic_input(w) if current(w) else None,
            "reviewer": " / ".join(done[c]["reviewer"] for c in CHECKS if c in done),
            "at": max((x["at"] for x in done.values()), default=None), "issues": [], "dismissed": {}}


def task_fingerprint(w: dict, check: str | None) -> str:
    return digest({"input": _d().semantic_input(w), "check": check})


__all__ = ["CHECKS", "CHECK_NAMES", "brief", "accept", "current", "check_current", "combined", "task_fingerprint",
           "carried", "reviewers", "blocked_reviewers"]
