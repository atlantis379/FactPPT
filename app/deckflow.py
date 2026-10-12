"""FactDeck mainline workflow: any source material → summary → fact store → deck → PPT.

Stages (each bound to the versions it was made from; changing an input makes
everything downstream stale automatically):

  READ_SOURCE     model reads every source page; pictures/charts are transcribed
  SUMMARY         model writes full_source_summary.v3 covering every page and outline item,
                  with per-section key points that name their supporting units
  content approval  customer confirms the summary
  FACTS           model proposes facts as verbatim quotes of source units; code verifies
  DECK            model writes pages that reference facts only, per the requirements
  SECOND_READ     a different worker re-transcribes pictures/charts blind and re-draws every
                  page crop box blind; code compares
  SEMANTIC_REVIEW a different worker judges each page against the sources
  confirmations   a person confirms derivations, resolves source conflicts, checks transcriptions;
                  for each source figure on a page: crop + de-identification review, customer licence
  render          code renders HTML → PNG/PDF/native PPTX and verifies (no model)
  page review     a person reviews every rendered page; customer confirms style on the first 5
  export          delivery package

Models write authored JSON; code decides what is accepted. No model calls happen
here, and nothing approves on a person's behalf.
"""
from __future__ import annotations

import copy
import io
import json
import re
import shutil
import time
import zipfile
from pathlib import Path

from app.fact57098 import Store as _BaseStore, WorkflowError, digest, sha, now, uid, require, parse_outline, ROOT
from factdeck import facts as fx
from factdeck.deck import check as deck_check, LAYOUTS, LAYOUT_GUIDE, RELATION_LAYOUTS
from factdeck.recipes import RECIPES
from factdeck.ingest import (extract_all, to_dicts, transcription_units, IngestError, check_bbox, crop_pdf_page, iou,
                             CROP_DPI, CROP_AGREE_IOU)
from factdeck.lexicon import canon, critical_tokens
from factdeck.structure import candidates as relation_candidates, RELATION_TYPES
from factdeck.claims import CLAIM_TYPES, SOURCE_KINDS, SPAN_MAX, SPANS_PER_CLAIM, ClaimError, page_claims, profile as claim_profile
from factdeck.render import THEMES
from factdeck.brand import from_template, BrandError
from app.deck_generation import GenerationMixin, VISUAL_KINDS, ROUTE as VISUAL_ROUTE
from app.deck_scope import check_spec, selected_spec, scope_of, context as scope_context
from app import review_ledger as ledger
from app import semantic_review as semrev

TEMPLATE = "factdeck.v1"
ENGINE_VERSION = "factdeck-render.1"
MAX_UPLOAD = 40 * 1024 * 1024
SAMPLE_PAGES = 5
DEIDENTIFIED = ("NO_PATIENT_CONTENT", "DEIDENTIFIED", "IDENTIFIABLE")
KINDS = ("READ_SOURCE", "SECOND_READ", "CLAIMS", "SUMMARY", "SUMMARY_AMEND", "SUMMARY_REVIEW", "FACTS", "DECK", "SEMANTIC_REVIEW", "VISUAL_CRITIQUE") + VISUAL_KINDS
REQUIREMENT_KEYS = {"audience", "purpose", "duration_minutes", "target_pages", "emphasis", "tone", "notes"}


# ------------------------------------------------------------------ outline
BUDGET_HEAD = "建议课件页数分配"


def structured(w: dict) -> bool:
    """The outline carries points (a Markdown outline), so it organises the summary and the deck."""
    return any(o.get("points") for o in w["outline"])


def unsupported_points(w: dict) -> dict[str, str]:
    """Outline points the summary declares unsupported by the sources: point id → reason."""
    if not w.get("summary"):
        return {}
    return {r["point_id"]: str(r["unsupported"]) for s in w["summary"]["sections"] for r in s.get("point_coverage") or []
            if r.get("unsupported") is not None}


ROLES = ("core", "support", "limit")
POINT_VERDICTS = ("ENTAILED", "PARTIAL", "NOT_ENTAILED", "CONTRADICTED")
SUMMARY_REVIEW_SCHEMA = "summary_review.v2"


def key_point_targets(w: dict, section: dict) -> list[dict]:
    """Stable for the exact summary version, and never written into authored content."""
    version = digest(w["summary"])
    return [{**k, "target_id": f"{version}:{section['id']}:key{i}"}
            for i, k in enumerate(section.get("key_points") or [], 1)]
RELATION_NAMES = {"sequence": "先后", "branch": "条件分支", "any_of": "满足任一", "all_of": "均需满足", "compare": "对照",
                  "matrix": "对象×属性", "evidence": "结论←证据", "definition": "定义"}


def relation_candidates_of(w: dict) -> dict[str, dict]:
    """Candidate relations read from every source's structure: id → candidate."""
    return {c["id"]: c for s in w["sources"] for c in s.get("relations") or []}


BASIS_NAMES = {"arrow": "原件箭头", "table": "原件表格", "numbered": "原件编号", "connective": "原文连接词"}


def relation_text(r: dict, names: dict[str, str]) -> str:
    """A relation as a small text diagram over its points' names: A → B, 满足任一：A / B, 对照：A | B …"""
    parts = [names.get(i, i) for i in r["items"]]
    shape = {"sequence": " → ".join(parts), "branch": " → ".join(parts), "compare": " | ".join(parts),
             "evidence": " ← ".join(parts)}.get(r["type"], " / ".join(parts))
    return f"{RELATION_NAMES[r['type']]}：{shape}"


def claim_text(k: dict) -> str:
    return " ｜ ".join(" ".join(sp["quote"].split()) for sp in k["spans"])


def claim_origin(w: dict, k: dict) -> str:
    """Where a claim comes from, for readers: source id, page, claim type, and the kind of source when it is not neutral."""
    page = pages(w).get(k["page_id"], {})
    kind = k.get("source_kind")
    return "，".join([f"{k['source_id']} {page.get('location', k['page_id'])}", CLAIM_TYPES.get(k["type"], k["type"])]
                     + ([f"资料性质：{SOURCE_KINDS[kind]}"] if kind in {"promotional", "other"} else []))


def message_lines(w: dict, s: dict) -> list[str]:
    """The storyboard block of one outline section: core sentence, logic, supporting and limiting points."""
    m = s.get("message")
    if not m:
        return []
    units = {u["id"]: u for u in all_units(w)}
    cands = relation_candidates_of(w)
    names = {r["point_id"]: r.get("statement") or r.get("point") or r["point_id"] for r in s.get("point_coverage") or []}
    if m["core"].get("claim_id"):
        k = all_claims(w).get(m["core"]["claim_id"])
        mark = {"title": "，原件页标题", "emphasis": "，原件强调"}.get(m["core"].get("marked") or "", "")
        where = claim_origin(w, k) if k else m["core"]["claim_id"]
        out = ["", f"**核心句**：「{m['core']['quote']}」（{where}{mark}）"]
    else:
        out = ["", f"**核心句**：无（{m['core'].get('none', '')}）"]
    if m.get("relations"):
        out.append("逻辑：")
        shown: dict[str, list[str]] = {}             # the same relation found in several sources is shown once
        for r in m["relations"]:
            c = cands.get(r.get("from_candidate") or "")
            why = "人工判断，请确认" if r.get("manual") else f"依据{BASIS_NAMES.get(c['basis'], c['basis'])}" if c else "依据原件"
            shown.setdefault(relation_text(r, names), [])
            if why not in shown[relation_text(r, names)]:
                shown[relation_text(r, names)].append(why)
        out += [f"- {text}（{'；'.join(whys)}）" for text, whys in shown.items()]
    else:
        out.append("逻辑：未列出关系，要点将并列呈现")
    for role, head in (("support", "支撑要点"), ("limit", "限定要点（必须上页）")):
        ids = [p for p, v in m["roles"].items() if v == role]
        if ids:
            out.append(f"{head}：" + "；".join(names.get(p, p) for p in ids))
    return out


def story_line(w: dict) -> list[str]:
    """Every outline item's core sentence in order: the talk's line of argument on one page."""
    out = []
    for s in (w.get("summary") or {}).get("sections") or []:
        if s.get("outline_id"):
            m = s.get("message")
            text = (f"「{m['core']['quote']}」" if m["core"].get("claim_id") else f"（无核心句：{m['core'].get('none', '')}）") if m else "（无资料支撑）"
            out.append(f"{len(out) + 1}. {s['title']}：{text}")
    return out


_SUB_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def unbacked_tokens(text: str, evidence: list[str]) -> list[str]:
    """Critical tokens of summary text (numbers with operators, technical tokens) that the cited evidence does not contain.
    Subscript digits count as digits (FEV₁ = FEV1); superscripts are citation marks and stay apart; each line of each
    quote is read on its own so numbers on separate lines never merge; a number matches when only its unit word differs."""
    have = set().union(*[critical_tokens(line.translate(_SUB_DIGITS)) for q in evidence for line in re.split(r"[\n\v]", q)] or [set()])
    stems = {re.match(r"[≥≤<>]?[\d.\-]+", t).group(0) for t in have if re.match(r"[≥≤<>]?\d", t)}
    out = []
    for t in critical_tokens(text.translate(_SUB_DIGITS)):
        m = re.match(r"[≥≤<>]?[\d.\-]+", t)
        if t in have or (m and m.group(0) in stems):
            continue
        out.append(t)
    return sorted(out)


def cite(w: dict, row: dict, page_ids: list[str], where: str, unit_page: dict) -> None:
    """Check what a summary item cites — claims (`claim_ids`) and/or units (`unit_ids`) on the section's pages — and
    record the units it rests on: the units named plus the units of the claims' spans."""
    claims = all_claims(w)
    cids, uids = row.get("claim_ids") or [], row.get("unit_ids") or []
    require(isinstance(cids, list) and isinstance(uids, list) and (cids or uids), f"{where}需列出支撑的论断（claim_ids）或文字单元（unit_ids）", 422)
    bad = [c for c in cids if c not in claims] + [u for u in uids if u not in unit_page]
    require(not bad, f"{where}引用了不存在的论断或文字单元：{'、'.join(map(str, bad))}", 422)
    outside = [c for c in cids if claims[c]["page_id"] not in page_ids] + [u for u in uids if unit_page[u] not in page_ids]
    require(not outside, f"{where}引用了本章未引用页面的论断或单元：{'、'.join(outside)}", 422)
    row["unit_ids"] = list(dict.fromkeys(uids + [u for c in cids for u in claims[c]["unit_ids"]]))


def parse_structured_outline(text: str) -> tuple[list[dict], list[dict]]:
    """A teaching outline written as Markdown: `## part`, `### item`, and the item's points below it.

    Returns (items, parts). Each item keeps the flat `{id: outline_N, text}` shape and adds `part`
    and `points: [{id: outline_N.k, text}]`; parts carry the page range the outline allots them.
    Nested bullets join their parent point; a bold line ending in a colon labels the points under it;
    a suggested table contributes only its column names (its figures are not facts). Text without
    `###` headings is split line by line as before.
    """
    lines = text.splitlines()
    if not any(l.lstrip().startswith("### ") for l in lines):
        return parse_outline(text), []
    items, parts, budgets = [], [], {}
    part = item = None
    label, in_budget = "", False
    for raw in lines:
        s = raw.strip()
        if not s or set(s) <= {"-"}:
            continue
        if s.startswith("## "):
            title = re.sub(r"（建议[^）]*）\s*$", "", s[3:]).strip()
            in_budget = BUDGET_HEAD in title
            part = None if in_budget else title
            if part:
                parts.append({"title": part, "pages": None})
            item, label = None, ""
            continue
        if in_budget:
            m = re.match(r"^[-*]\s*(.+?)[：:]\s*(\d+)(?:\s*[–—~-]\s*(\d+))?\s*页", s)
            if m:
                budgets[m.group(1).replace("+", "与")] = [int(m.group(2)), int(m.group(3) or m.group(2))]
            continue
        if part is None:
            continue                                    # the preamble: title, audience, goals
        if s.startswith("### "):
            name = re.sub(r"^\d+[.、]\s*", "", s[4:]).strip()
            item = {"id": f"outline_{len(items) + 1}", "text": f"{part}：{name}", "part": part, "points": []}
            items.append(item)
            label = ""
            continue
        if item is None:
            continue
        add = lambda body: item["points"].append({"id": f"{item['id']}.{len(item['points']) + 1}", "text": body})
        if s.startswith("|"):
            if not item["points"] and not set(s) <= set("|-: "):
                add("表格：" + "、".join(c.strip() for c in s.strip("|").split("|") if c.strip()))
            continue
        bold = re.fullmatch(r"\*\*(.+?)\*\*", s)
        if bold and bold.group(1).endswith(("：", ":")):
            label = bold.group(1).rstrip("：:")
            continue
        body = re.sub(r"^([-*]|\d+[.、])\s+", "", s).replace("**", "").strip()
        nested = len(raw) - len(raw.lstrip()) >= 2 and re.match(r"^[-*]\s", s)
        if nested and item["points"]:
            prev = item["points"][-1]
            prev["text"] += ("" if prev["text"].endswith(("：", ":", "；", "。")) else "；") + body
            continue
        if not re.match(r"^([-*]|\d+[.、])\s", s) and body.endswith(("：", ":")):
            label = body.rstrip("：:")                  # a plain line introducing the bullets below it
            continue
        add(f"{label}：{body}" if label else body)
    for p in parts:
        key = next((k for k in budgets if p["title"].startswith(k) or k in p["title"]), None)
        p["pages"] = budgets.get(key)
    return items, parts


# ------------------------------------------------------------------ derived state
def pages(w: dict) -> dict[str, dict]:
    return {p["id"]: p for s in w["sources"] for p in s["pages"]}


def all_units(w: dict) -> list[dict]:
    """Quotable units with confirmation state applied (never stored back)."""
    confirmed = w["confirmations"]["transcriptions"]
    out = []
    for s in w["sources"]:
        for u in s["units"]:
            out.append(u)
        for u in s["transcriptions"] + [p for p in w.get("transcription_proposals", []) if p["source_id"] == s["id"]]:
            u = dict(u)
            c = confirmed.get(u["id"])
            if c and c["decision"] == "CONFIRM":
                u["text"], u["needs_confirmation"] = c["text"], False
            elif u.get("second_read", {}).get("agree"):
                u["needs_confirmation"] = False
            elif u.get("second_read"):
                u["confirmation_reason"] = "两次独立转录不一致，须人工对照原件"
            out.append(u)
    return out


def figures(w: dict) -> dict[str, dict]:
    return {g["id"]: g for s in w["sources"] for g in s.get("figures", [])}


def embedded(source: dict) -> list[dict]:
    return [g for g in source.get("figures", []) if g["method"] != "page_crop"]


def page_crops(source: dict) -> list[dict]:
    return [g for g in source.get("figures", []) if g["method"] == "page_crop"]


def needs_second_read(source: dict) -> bool:
    return any(not u.get("second_read") for u in source["transcriptions"]) or any(not g.get("second_read") for g in page_crops(source))


def crop_mismatch(g: dict) -> bool:
    return g["method"] == "page_crop" and bool(g.get("second_read")) and not g["second_read"]["agree"]


def figure_records(w: dict) -> tuple[dict, dict]:
    c = w["confirmations"]
    return c.get("figures", {}), c.get("figure_licenses", {})


def figure_states(w: dict) -> dict[str, dict]:
    """What the fact gate needs to know about each figure (records bind to the figure checksum)."""
    reviews, licences = figure_records(w)
    open_cells: dict[str, list[str]] = {}
    for u in all_units(w):
        if u.get("figure_id") and u.get("needs_confirmation"):
            open_cells.setdefault(u["figure_id"], []).append(u["id"])
    out = {}
    for g in figures(w).values():
        pending, rejected = [], []
        r, lic = reviews.get(g["id"]), licences.get(g["id"])
        r = r if r and r["figure_sha256"] == g["sha256"] else None
        lic = lic if lic and lic["figure_sha256"] == g["sha256"] else None
        if not r:
            pending.append("截取完整与去标识尚未确认")
        elif r["deidentified"] == "IDENTIFIABLE":
            rejected.append("图中含患者可识别信息，不能上页")
        if not lic:
            pending.append("尚未登记图片使用许可")
        elif not lic["permitted"]:
            rejected.append("客户未许可使用此图")
        if open_cells.get(g["id"]):
            pending.append("图中文字转录尚无一致的第二次独立读取或人工确认")
        if g["method"] == "page_crop" and not g.get("second_read"):
            pending.append("截取区域尚无第二次独立截取")
        elif crop_mismatch(g) and r and not r.get("mismatch_checked"):
            pending.append(f"两次独立截取区域不一致（交并比 {g['second_read']['iou']}），须人工对照原页重新确认")
        out[g["id"]] = {"source_id": g["source_id"], "location": g["location"], "pending": pending, "rejected": rejected,
                        "review": r, "licence": lic, "open_cells": open_cells.get(g["id"], [])}
    return out


def fully_read(w: dict) -> bool:
    return bool(w["sources"]) and all(p["reading"] for p in pages(w).values())


def claims_input(source: dict) -> str:
    """What a source's claims rest on: the original, its readings and its transcriptions."""
    return digest({"sha256": source["sha256"], "readings": [p["reading"] for p in source["pages"]],
                   "transcriptions": [{k: u[k] for k in ("id", "location", "text")} for u in source["transcriptions"]]})


def claims_current(source: dict) -> bool:
    c = source.get("claims")
    return bool(c) and c["input_sha256"] == claims_input(source)


def fully_claimed(w: dict) -> bool:
    return fully_read(w) and all(claims_current(s) for s in w["sources"])


def all_claims(w: dict) -> dict[str, dict]:
    """Every current claim by id, with its source and the source's profile."""
    out = {}
    for s in w["sources"]:
        c = s.get("claims")
        if c:
            for k in c["items"]:
                out[k["id"]] = {**k, "source_id": s["id"], "source_kind": c["profile"]["kind"]}
    return out


def claim_view(k: dict) -> dict:
    """A claim as workers see it: its spans' text, type, scope and what code read off it."""
    return {"id": k["id"], "type": k["type"], "text": " ｜ ".join(sp["quote"] for sp in k["spans"]), "unit_ids": k["unit_ids"],
            **{x: k[x] for x in ("scope", "qualifiers", "numbers", "cites") if k.get(x)},
            **({"source_kind": k["source_kind"]} if k.get("source_kind") else {})}


def input_hash(w: dict) -> str:
    return digest({"sources": [{"sha256": s["sha256"], "readings": [p["reading"] for p in s["pages"]],
                                "transcriptions": [{k: u[k] for k in ("id", "location", "text")} for u in s["transcriptions"]],
                                "claims": (s.get("claims") or {}).get("result_sha256")}
                               for s in w["sources"]],
                   "outline": w["outline"], "context": w["context"]})


def summary_current(w: dict) -> bool:
    return bool(w["summary"]) and w["summary"]["input_sha256"] == input_hash(w)


def summary_review_input(w: dict) -> str:
    return digest({"summary": digest(w["summary"]), "input": input_hash(w), "contract": SUMMARY_REVIEW_SCHEMA})


def summary_review_current(w: dict) -> bool:
    r = w.get("summary_review")
    return summary_current(w) and bool(r) and r.get("schema_version") == SUMMARY_REVIEW_SCHEMA and r["input_sha256"] == summary_review_input(w)


def open_summary_issues(w: dict) -> list[dict]:
    """Blockers in the summary issue ledger not closed by an evidenced fix or a human ruling."""
    if not summary_review_current(w):
        return []
    return ledger.blocking(w, "summary")


def content_approved(w: dict) -> bool:
    a = w["content_approval"]
    return summary_current(w) and bool(a) and a["subject_sha256"] == digest(w["summary"])


def facts_input(w: dict) -> str:
    return digest({"summary": digest(w["summary"]) if w["summary"] else None})


def facts_current(w: dict) -> bool:
    return content_approved(w) and bool(w["facts"]) and w["facts"]["input_sha256"] == facts_input(w)


def facts_sha(w: dict) -> str | None:
    return w["facts"]["result_sha256"] if w["facts"] else None


CARVED_FIELDS = {"id", "unit", "quote", "display", "entity", "attribute", "value", "note", "section_ids"}


def carved(w: dict) -> list[dict]:
    """Facts the deck author cut verbatim from source units to fit its page slots."""
    return list(((w["deck"] or {}).get("result") or {}).get("facts") or [])


def verified(w: dict, extra: list[dict] | None = None) -> dict:
    """Run the fact gate with the current confirmations over the fact store plus the deck's carved facts.

    `extra` replaces the current deck's carved facts (a deck being submitted, or [] for the store alone).
    """
    if not w["facts"]:
        return {"facts": {}, "derivations": [], "conflicts": [], "terms": [], "objects": ([], [], [])}
    extra = carved(w) if extra is None else extra
    F, D, T = fx.parse({**w["facts"]["result"], "facts": list(w["facts"]["result"]["facts"]) + list(extra)})
    decisions = w["confirmations"]["derivations"]
    for d in D:
        rec = decisions.get(d.id)
        if rec and rec["derivation_sha256"] == digest({"claim": d.claim, "rule": d.rule, "evidence": d.evidence}):
            d.confirmed, d.rejected = rec["decision"] == "CONFIRM", rec["decision"] == "REJECT"
    resolutions = {k: v["fact_id"] for k, v in w["confirmations"]["resolutions"].items()}
    conflicts = fx.verify(F, D, all_units(w), resolutions, T, figure_states(w))
    data = fx.as_dict(F, D, conflicts)
    n_store, by_id = len(w["facts"]["result"]["facts"]), {}
    for i, f in enumerate(data["facts"]):
        f["carved"] = i >= n_store
        by_id.setdefault(f["id"], f)          # a duplicate id never shadows the first (store) fact
    return {"facts": by_id, "derivations": data["derivations"], "conflicts": data["conflicts"],
            "terms": T, "objects": (F, D, conflicts)}


def deck_input(w: dict) -> str:
    return digest({"facts": facts_sha(w), "summary": digest(w["summary"]) if w["summary"] else None,
                   "outline": w["outline"], "requirements": w["requirements"]})


def deck_current(w: dict) -> bool:
    return facts_current(w) and bool(w["deck"]) and w["deck"]["input_sha256"] == deck_input(w)


def deck_sha(w: dict) -> str | None:
    return w["deck"]["result_sha256"] if w["deck"] else None


def checked(w: dict, v: dict | None = None) -> dict:
    v = v or verified(w)
    return check_spec(w["deck"]["result"], v["facts"], v["terms"], w["outline"], w["summary"]["sections"], w["requirements"], w.get("outline_parts"))


def pending_items(w: dict, v: dict, chk: dict) -> list[dict]:
    """Human confirmations still needed for facts that appear on pages (or back a diagram arrow)."""
    used = {fid for p in chk["pages"] for fid in p["facts"] + p["edge_facts"]}
    items = []
    for d in v["derivations"]:
        users = [f for f in used if d["id"] in [x.strip() for x in v["facts"][f]["derivation"].split(",")]]
        if users and not d["confirmed"] and not d["rejected"]:
            items.append({"kind": "derivation", "id": d["id"], "claim": d["claim"], "rule": d["rule"], "evidence": d["evidence"], "facts": users})
    for c in v["conflicts"]:
        ids = [i for ids in c["values"].values() for i in ids]
        if not c["resolution"] and used & set(ids):
            items.append({"kind": "conflict", "id": c["key"], "entity": c["entity"], "attribute": c["attribute"], "values": c["values"]})
    by_unit = {u["id"]: u for u in all_units(w)}
    states, figs = figure_states(w), figures(w)
    wanted = []
    for f in sorted(used):
        fig = v["facts"][f].get("figure")
        wanted += states[fig]["open_cells"] if fig in states else [v["facts"][f]["unit"]]
    for uid_ in wanted:
        u = by_unit.get(uid_)
        if u and u.get("needs_confirmation") and not any(i["kind"] == "transcription" and i["id"] == u["id"] for i in items):
            items.append({"kind": "transcription", "id": u["id"], "location": u["location"], "text": u["text"],
                          "proposal_of":u.get("proposal_of"), "original_text":u.get("original_text"),
                          "page_image_url":page_image_url(w, pages(w)[u["page_id"]]),
                          "second_read": u.get("second_read"), "reason": u.get("confirmation_reason", "尚无一致的第二次独立转录")})
    for fig in sorted({v["facts"][f]["figure"] for f in used if v["facts"][f].get("figure")}):
        st, g = states[fig], figs[fig]
        base = {"id": fig, "source_id": g["source_id"], "location": g["location"], "sha256": g["sha256"],
                "width": g["width"], "height": g["height"], "reading": figure_reading(w, fig), "method": g["method"]}
        if g["method"] == "page_crop":
            base.update(bbox=g["bbox"], second_read=g.get("second_read"), page_image_url=page_image_url(w, pages(w)[g["page_id"]]))
            if not g.get("second_read"):
                items.append({"kind": "figure_second_crop", **base})
        if not st["review"] or (crop_mismatch(g) and not st["review"].get("mismatch_checked")):
            items.append({"kind": "figure_review", **base})
        if not st["licence"]:
            items.append({"kind": "figure_licence", **base})
    return items


def fig_url(w: dict, fig_id: str) -> str:
    return f"/api/deck/workflows/{w['id']}/figures/{fig_id}/file"


def page_image_url(w: dict, page: dict) -> str:
    return f"/api/deck/workflows/{w['id']}/sources/{page['source_id']}/pages/{page['id']}/image"


def semantic_fact(w: dict, v: dict, by_unit: dict, fid: str) -> dict:
    f = v["facts"][fid]
    if f.get("figure"):
        return {"id": fid, "figure": f["figure"], "figure_url": fig_url(w, f["figure"]), "caption": f.get("caption", []),
                "reader_note": (figure_reading(w, f["figure"]) or {}).get("note", ""), "location": f["location"]}
    return {"id": fid, "display": f["display"] or f["quote"], "quote": f["quote"], "dropped_from_quote": f["dropped"],
            "unit_text": by_unit[f["unit"]]["text"], "location": f["location"], "carved_by_deck": f.get("carved", False)}


def figure_inventory(w: dict, v: dict) -> list[dict]:
    """Every source figure on a page, with where it came from and who cleared it (delivery report)."""
    used = {fid for p in checked(w, v)["pages"] for fid in p["facts"]}
    states, figs = figure_states(w), figures(w)
    src = {s["id"]: s["filename"] for s in w["sources"]}
    return [{"fact": fid, "figure": f["figure"], "source": src.get(f["source_id"]), "location": f["location"],
             "method": figs[f["figure"]]["method"], "sha256": figs[f["figure"]]["sha256"],
             "review": states[f["figure"]]["review"], "licence": states[f["figure"]]["licence"]}
            for fid, f in sorted(v["facts"].items()) if fid in used and f.get("figure")]


def figure_reading(w: dict, fig_id: str) -> dict | None:
    g = figures(w).get(fig_id)
    page = pages(w).get(g["page_id"]) if g else None
    return ((page or {}).get("reading") or {}).get("figures", {}).get(fig_id)


def semantic_input(w: dict) -> str:
    return digest({"deck": deck_sha(w), "facts": facts_sha(w)})


def semantic_current(w: dict) -> bool:
    """Both independent checklists (coverage/verbatim and semantics/relations) are done on the current version."""
    return deck_current(w) and semrev.current(w)


def open_issues(w: dict) -> list[dict]:
    """Blockers in the semantic issue ledger, across all rounds, not closed by an evidenced fix or a human ruling."""
    if not semantic_current(w):
        return []
    return ledger.blocking(w, "semantic")


def render_input(w: dict, v: dict | None = None, include_visual: bool = True) -> str | None:
    if not deck_current(w):
        return None
    v = v or verified(w)
    shown = {f["figure"] for f in v["facts"].values() if f.get("figure")}
    states = figure_states(w) if shown else {}
    payload = {"engine": ENGINE_VERSION, "deck": w["deck"]["result"], "theme": w["theme"],
                   "facts": {k: {x: f[x] for x in ("quote", "display", "status", "needs_confirmation", "location", "source_id", "figure", "caption")}
                             for k, f in v["facts"].items()},
                   "figures": {k: {"sha256": g["sha256"], "review": states[k]["review"], "licence": states[k]["licence"]}
                               for k, g in figures(w).items() if k in shown},
                   "sources": [{k: s[k] for k in ("id", "filename")} for s in w["sources"]],
                   "brand": ({"tokens": w["brand"]["tokens"], "font": w["brand"].get("font"), "logo": (w["brand"].get("logo") or {}).get("sha256")}
                             if w["theme"] == "brand" and w.get("brand") else None)}
    if w.get('visual_template'):
        payload['visual_template']=w['visual_template']
    if include_visual and w.get("generation"):
        from app.deck_generation import render_fingerprint
        payload["visual_generation"] = render_fingerprint(w)
    return digest(payload)


def critique_input(w: dict) -> str:
    """What a visual critique rests on: the current render's page images."""
    return digest([(p["id"], p["sha256"]) for p in (w.get("render") or {}).get("pages") or []])


def critique_current(w: dict) -> bool:
    c = w.get("critique")
    return bool(c) and bool(w.get("render")) and c["input_sha256"] == critique_input(w)


def render_current(w: dict, v: dict | None = None) -> bool:
    r = w["render"]
    return bool(r) and not r["draft"] and r["hard_errors"] == 0 and r["input_sha256"] == render_input(w, v)


def reviewed(w: dict, page_id: str) -> bool:
    r = w["page_reviews"].get(page_id)
    p = next((p for p in (w["render"] or {}).get("pages", []) if p["id"] == page_id), None)
    return bool(r and p) and r["png_sha256"] == p["sha256"] and r["visual_status"] == "PASS" and r["content_status"] == "PASS"


def sample_hash(w: dict) -> str | None:
    if not w["render"]:
        return None
    first = w["render"]["pages"][:SAMPLE_PAGES]
    return digest({"render": w["render"]["input_sha256"], "theme": w["theme"],
                   "pages": [{"id": p["id"], "png": p["sha256"], "review": w["page_reviews"].get(p["id"])} for p in first]})


def style_approved(w: dict) -> bool:
    a = w["style_approval"]
    return render_current(w) and bool(a) and a["subject_sha256"] == sample_hash(w)


def delivery_subject(w: dict) -> str:
    return digest({"render": (w["render"] or {}).get("input_sha256"), "content": w["content_approval"], "style": w["style_approval"],
                   "reviews": {p["id"]: w["page_reviews"].get(p["id"]) for p in (w["render"] or {}).get("pages", [])}})


def status(w: dict) -> tuple[str, list[str]]:
    """(stage, open items) — the first unmet gate and everything still open."""
    if not fully_read(w): return "READING_REQUIRED", ["资料尚未全部阅读"]
    if not fully_claimed(w): return "CLAIMS_REQUIRED", ["资料的论断清单尚未全部完成"]
    if not summary_current(w): return "SUMMARY_REQUIRED", ["需要当前版本的全文总结"]
    if not content_approved(w):
        if any(t["kind"] == "SUMMARY_AMEND" and t["status"] in {"PENDING", "RUNNING"} for t in w["tasks"]):
            return "SUMMARY_AMEND_RUNNING", ["答复已保存，执行端正在处理对应的来源与需求记录"]
        if not summary_review_current(w): return "SUMMARY_REVIEW_REQUIRED", ["总结需要独立审查"]
        if open_summary_issues(w): return "SUMMARY_ISSUES", [blocker_text("总结审查", open_summary_issues(w))]
        return "CONTENT_CONFIRMATION", ["客户尚未确认全文总结"]
    if not facts_current(w): return "FACTS_REQUIRED", ["需要根据已确认总结建立事实库"]
    if not deck_current(w): return "DECK_REQUIRED", ["需要根据需求编写页面规格"]
    v = verified(w)
    chk = checked(w, v)
    if chk["errors"]:
        return "DECK_REVISION", [f"页面规格有 {chk['errors']} 处错误"]
    source_pending = []
    if w["deck"].get("source_gate_version") == 1:
        from factdeck.content_obligations import validate_deck
        source_check = validate_deck(w, w["deck"]["result"], v, chk)
        if source_check["errors"]:
            return "DECK_REVISION", source_check["errors"]
        source_pending = source_check["pending"]
    todo = []
    pend = pending_items(w, v, chk)
    if pend: todo.append(f"待人工确认 {len(pend)} 项（推导/冲突/转录/原件图）")
    if source_pending and not pend: todo.append(f"来源约束有 {len(source_pending)} 项待处理：" + "；".join(source_pending[:3]))
    if not semantic_current(w):
        missing = [semrev.CHECK_NAMES[c] for c in semrev.CHECKS if not semrev.check_current(w, c)]
        todo.append("需要独立语义审查：" + "、".join(missing))
    elif open_issues(w): todo.append(blocker_text("语义审查", open_issues(w)))
    if todo:
        stage = "CONFIRMATIONS_REQUIRED" if pend or source_pending else ("SEMANTIC_REVIEW_REQUIRED" if not semantic_current(w) else "SEMANTIC_ISSUES")
        return stage, todo
    if not render_current(w, v):
        if w.get("generation"):
            from app.deck_generation import view
            g = view(w)
            if g["current"]:
                return "GENERATION_FAILED" if g["status"] == "FAILED" else "GENERATION_RUNNING", ["A 原生矢量生成待完成；请查看生成进度与执行端任务"]
        return "RENDER_REQUIRED", ["需要渲染当前版本"]
    rpages = w["render"]["pages"]
    if not all(reviewed(w, p["id"]) for p in rpages[:SAMPLE_PAGES]): return "SAMPLES_REVIEW", ["前5页需逐页审核"]
    if not style_approved(w): return "STYLE_CONFIRMATION", ["客户尚未确认样页风格"]
    if not all(reviewed(w, p["id"]) for p in rpages): return "PAGE_REVIEW", ["其余页面需逐页审核"]
    scope = scope_of(w["deck"]["result"])
    if scope:
        return "PARTIAL_READY", [f"前{scope['page_count']}页已完成本次审核；整套共{scope['total_pages']}页，范围外页面尚未完成当前版本生成"]
    if w["deliveries"] and w["deliveries"][-1]["subject_sha256"] == delivery_subject(w):
        return "DELIVERED", []
    return "READY_TO_EXPORT", []


def blocker_text(label: str, items: list[dict]) -> str:
    human = sum(1 for i in items if i["status"] == "NEEDS_HUMAN")
    return f"{label}有 {len(items)} 个阻断问题" + (f"（其中 {human} 个须人工裁定，页面修订不能关闭）" if human else "")


def stage(w: dict) -> str:
    return status(w)[0]


def context_warnings(w: dict, deck: dict, chk: dict, v: dict) -> list[str]:
    """Excerpt shapes that repeatedly cost review rounds, reported to the page author before review: a list lead-in
    without anything it introduces, and a quote opening with a connective whose preceding unit is not on this page
    or the one before."""
    from factdeck.context import signals, unshown_lead_ins
    units = {u["id"]: u for u in all_units(w)}
    nxt, prv = {}, {}
    for s in w["sources"]:
        seq = [u["id"] for u in s["units"]]
        nxt.update(zip(seq, seq[1:]))
        prv.update(zip(seq[1:], seq))
    facts, out, before = v["facts"], [], set()
    for res in chk["pages"]:
        ids = res["facts"]
        shown = {(facts.get(x) or {}).get("unit") for x in ids}
        out += [f"{res['id']}：{fid} 是列表或下文的引导句，本页没有它引出的条目；请补齐条目或在页面说明只展示其中一部分"
                for fid in unshown_lead_ins(ids, facts, units, nxt)]
        for fid in ids:
            f = facts.get(fid) or {}
            u = units.get(f.get("unit"))
            if f.get("figure") or not u:
                continue
            con = next((x for x in signals(f["quote"], f.get("display"), u["text"]) if x["kind"] == "leading_connective"), None)
            same = any(x != fid and (facts.get(x) or {}).get("unit") == u["id"] for x in ids)
            if con and not same and prv.get(u["id"]) not in shown | before:
                out.append(f"{res['id']}：{fid} 以“{con['text']}”开头，它承接的前文不在本页或上一页")
        before = shown
    return out


# ------------------------------------------------------------------ store
# page review: the visual verdict is broken down into what a page reviewer checks on every page
RUBRIC = {"first_glance": "第一眼能看出本页的主角，且与 design.first 一致",
          "peers": "并列的各项同等处理，没有无故突出其中一项",
          "qualifiers": "节选、强调、拆句没有改变原文的范围或限定",
          "whitespace": "留白服务于内容，没有大片无意义的空白",
          "reading_order": "阅读方向单一（流程顺着箭头，不折返）",
          "repetition": "整组共有的信息只写一次，与相邻页面不重复构图"}

class Store(GenerationMixin, _BaseStore):
    def __init__(self, data_root: Path | None = None):
        super().__init__(data_root or ROOT / "data" / "deckflow")

    # ---- project
    def create(self, title: str, outline: str = "", requirements: dict | None = None, context: dict | None = None, theme: str = "navy-teal", generation_route: str = VISUAL_ROUTE) -> dict:
        require(bool(title.strip()), "请填写项目名称", 422)
        require(generation_route in {VISUAL_ROUTE, "CODE_NATIVE"}, "生成路线无效", 422)
        w = {"id": uid("deck"), "title": title.strip(), "revision": 1, "created_at": now(), "updated_at": now(), "template": TEMPLATE,
             "context": context or {"language": "zh-CN", "external_research_allowed": False},
             "requirements": self._requirements(requirements or {}), "outline": parse_structured_outline(outline)[0],
             "outline_parts": parse_structured_outline(outline)[1], "theme": self._theme(theme),
             "sources": [], "next_source_no": 1, "brand": None, "summary": None, "content_approval": None, "facts": None,
             "confirmations": {"derivations": {}, "resolutions": {}, "transcriptions": {}, "figures": {}, "figure_licenses": {}},
             "deck": None, "semantic_review": None, "render": None, "critique": None, "page_reviews": {}, "style_approval": None,
             "approvals": [], "tasks": [], "deliveries": [], "generation_route": generation_route, "generation": None,
             "source_evidence_policy": "verified-transcription.v1"}
        with self.connect() as db:
            db.execute("INSERT INTO workflows VALUES(?,?,?)", (w["id"], 1, json.dumps(w, ensure_ascii=False)))
            db.execute("INSERT INTO events(workflow_id,created_at,event,details) VALUES(?,?,?,?)", (w["id"], now(), "CREATE", digest(w)))
        return self.get(w["id"])

    @staticmethod
    def _requirements(r: dict) -> dict:
        unknown = set(r) - REQUIREMENT_KEYS
        require(not unknown, "未知需求字段：" + "、".join(sorted(unknown)), 422)
        if r.get("target_pages") is not None:
            require(isinstance(r["target_pages"], int) and 1 <= r["target_pages"] <= 300, "目标页数需为1至300", 422)
        return {k: r[k] for k in sorted(r) if r[k] not in (None, "")}

    @staticmethod
    def _theme(theme: str, w: dict | None = None) -> str:
        if theme == "brand":
            require(bool(w and w.get("brand")), "尚未导入客户模板，不能使用客户配色", 422)
            return theme
        require(theme in THEMES, "可选配色：" + "、".join(THEMES) + "（导入客户模板后可选 brand）", 422)
        return theme

    def get(self, workflow_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT state FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        require(row, "项目不存在", 404)
        w = json.loads(row[0])
        from app.deck_generation import view
        w["generation_status"] = view(w)
        if w.get("generation"):
            w["generation"]["render"].pop("lease_token", None)
        w["stage"], w["open_items"] = status(w)
        w["approval_subjects"] = {"content": digest(w["summary"]) if summary_current(w) else None,
                                  "style": sample_hash(w) if render_current(w) else None}
        for scope, key in (("summary", "summary_review"), ("semantic", "semantic_review")):
            ledger.book(w, scope)
            if w.get(key):                              # earlier screens read issues/dismissed; the ledger is the authority
                w[key]["issues"], w[key]["dismissed"] = ledger.legacy_view(w, scope)
        w["ledger_status"] = {scope: ledger.counts(w, scope) for scope in ("summary", "semantic")}
        w["content_acknowledge"] = ledger.to_acknowledge(w, "summary") if summary_review_current(w) else []
        for t in w["tasks"]:
            t.pop("lease_token", None)
        return w

    def list(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT state FROM workflows ORDER BY rowid DESC").fetchall()
        return [{"id": w["id"], "title": w["title"], "stage": stage(w), "sources": len(w["sources"]),
                 "pages": len(w["deck"]["result"]["pages"]) if w["deck"] else 0, "updated_at": w["updated_at"]}
                for w in (json.loads(r[0]) for r in rows)]

    def settings(self, workflow_id: str, changes: dict):
        with self.transaction(workflow_id, "SETTINGS") as w:
            if "title" in changes:
                require(bool(changes["title"].strip()), "名称不能为空", 422)
                w["title"] = changes["title"].strip()
            if "outline" in changes:
                w["outline"], w["outline_parts"] = parse_structured_outline(changes["outline"])
            if "context" in changes:
                w["context"] = changes["context"]
            if "requirements" in changes:
                w["requirements"] = self._requirements(changes["requirements"])
            if "theme" in changes:
                w["theme"] = self._theme(changes["theme"], w)
            if "visual_template" in changes:
                from app.academic_templates import snapshot
                w['visual_template']=snapshot(self,w,changes['visual_template'])
            self.cancel_stale(w)
        return self.get(workflow_id)

    # ---- sources
    def add_source(self, workflow_id: str, filename: str, content: bytes):
        require(0 < len(content) <= MAX_UPLOAD, "资料为空或超过40MB", 422)
        name = Path(filename.replace("\\", "/")).name
        with self.transaction(workflow_id, "SOURCE_IMPORT") as w:
            require(not any(s["sha256"] == sha(content) for s in w["sources"]), "相同资料已导入", 422)
            sid = f"S{w['next_source_no']:02d}"
            try:
                pgs, us, figs = extract_all(name, content, sid)
            except IngestError as e:
                raise WorkflowError(str(e), 422)
            except Exception as e:                           # corrupt or unsupported internals
                raise WorkflowError(f"无法读取资料：{e}", 422)
            p, u = to_dicts(pgs, us)
            for page in p:
                page["reading"] = None
            path = self.immutable(workflow_id, "sources", content, Path(name).suffix.lower())
            fig_rows = [{"id": g.id, "source_id": sid, "page_id": g.page_id, "location": g.location, "method": g.method,
                         "width": g.width, "height": g.height, "original_format": g.original_format, "sha256": sha(g.png),
                         "path": self.immutable(workflow_id, "figures", g.png, ".png")} for g in figs]
            w["sources"].append({"id": sid, "filename": name, "title": Path(name).stem, "sha256": sha(content), "path": path,
                                 "kind": Path(name).suffix.lower().lstrip("."), "pages": p, "units": u, "transcriptions": [],
                                 "figures": fig_rows, "relations": relation_candidates(u)})
            w["next_source_no"] += 1
            self.cancel_stale(w)
        return self.get(workflow_id)

    def backfill_structure(self, workflow_id: str) -> dict:
        """Bring sources imported by an earlier ingest up to date: diagram arrow units (PPTX), the author's marks
        (`signals`) and candidate relations.

        Re-reads each archived original with the current ingest. Only when every existing unit comes out identical
        (same ids, same texts, in the same number) are arrow units appended and marks attached, so nothing already
        quoted moves. Candidate relations are then recomputed from the units the source now has.
        """
        added, marked, skipped = {}, {}, []
        with self.transaction(workflow_id, "STRUCTURE_BACKFILL") as w:
            for s in w["sources"]:
                try:
                    _, us, _ = extract_all(s["filename"], self.path(s["path"]).read_bytes(), s["id"])
                except Exception:
                    skipped.append(s["id"])
                    continue
                _, fresh = to_dicts([], us)
                old = {u["id"]: u for u in s["units"]}
                base = [u for u in fresh if u["method"] != "pptx_arrow"]
                if any(u["id"] not in old or old[u["id"]]["text"] != u["text"] for u in base) or \
                        len(base) != len([u for u in s["units"] if u["method"] != "pptx_arrow"]):
                    skipped.append(s["id"])
                    continue
                new = [u for u in fresh if u["method"] == "pptx_arrow" and u["id"] not in old]
                by_page = {p["id"]: p for p in s["pages"]}
                for u in new:
                    s["units"].append(u)
                    by_page[u["page_id"]]["unit_ids"].append(u["id"])
                    by_page[u["page_id"]]["text"] = (by_page[u["page_id"]]["text"] + "\n" + u["text"]).strip()
                if new:
                    added[s["id"]] = len(new)
                n = 0
                for u in fresh:
                    if u.get("signals") and u["id"] in old and old[u["id"]].get("signals") != u["signals"]:
                        old[u["id"]]["signals"] = u["signals"]
                        n += 1
                if n:
                    marked[s["id"]] = n
                s["relations"] = relation_candidates(s["units"])
            self.snapshot(w, "structure_backfill", {"added": added, "marked": marked, "skipped": skipped})
        return {"added": added, "marked": marked, "skipped": skipped,
                "relations": {s["id"]: len(s.get("relations") or []) for s in self.get(workflow_id)["sources"]}}

    backfill_arrows = backfill_structure          # the earlier name, kept for existing callers

    # ---- client brand (appearance only)
    def brand_template(self, workflow_id: str, filename: str, content: bytes):
        """Colours and fonts from the customer's PowerPoint template; switches the project to the brand theme."""
        require(0 < len(content) <= MAX_UPLOAD, "模板为空或超过40MB", 422)
        name = Path(filename.replace("\\", "/")).name
        require(Path(name).suffix.lower() in {".pptx", ".potx"}, "请导入 .pptx 或 .potx 模板", 422)
        try:
            b = from_template(content)
        except BrandError as e:
            raise WorkflowError(str(e), 422)
        with self.transaction(workflow_id, "BRAND_TEMPLATE") as w:
            old = w.get("brand") or {}
            w["brand"] = {"filename": name, "sha256": sha(content), "path": self.immutable(workflow_id, "brand", content, Path(name).suffix.lower()),
                          "at": now(), "logo": old.get("logo"), **b}
            w["theme"] = "brand"
        return self.get(workflow_id)

    def brand_logo(self, workflow_id: str, filename: str, content: bytes):
        from PIL import Image
        require(0 < len(content) <= 5 * 1024 * 1024, "标志图片为空或超过5MB", 422)
        suffix = Path(filename).suffix.lower()
        require(suffix in {".png", ".jpg", ".jpeg"}, "标志请用 PNG 或 JPG", 422)
        try:
            with Image.open(io.BytesIO(content)) as im:
                im.verify()
        except Exception:
            raise WorkflowError("无法读取标志图片", 422)
        with self.transaction(workflow_id, "BRAND_LOGO") as w:
            require(w.get("brand"), "请先导入客户模板", 409)
            w["brand"]["logo"] = {"filename": Path(filename).name, "sha256": sha(content),
                                  "path": self.immutable(workflow_id, "brand", content, suffix)}
        return self.get(workflow_id)

    def remove_brand(self, workflow_id: str):
        with self.transaction(workflow_id, "BRAND_REMOVE") as w:
            w["brand"] = None
            if w["theme"] == "brand":
                w["theme"] = "navy-teal"
        return self.get(workflow_id)

    def render_theme(self, w: dict):
        """What the renderer gets: a built-in theme name, or the brand tokens, font and logo file."""
        if w["theme"] != "brand":
            return w["theme"]
        b = w["brand"]
        logo = b.get("logo")
        if logo:
            require(sha(self.path(logo["path"]).read_bytes()) == logo["sha256"], "标志文件已被修改，请重新上传")
        return {"tokens": b["tokens"], "font": b.get("font"), "logo": str(self.path(logo["path"])) if logo else None}

    def remove_source(self, workflow_id: str, source_id: str):
        with self.transaction(workflow_id, "SOURCE_REMOVE") as w:
            require(any(s["id"] == source_id for s in w["sources"]), "资料不存在", 404)
            w["sources"] = [s for s in w["sources"] if s["id"] != source_id]
            self.cancel_stale(w)
        return self.get(workflow_id)

    def cancel_stale(self, w: dict):
        for t in w["tasks"]:
            if t["status"] in {"PENDING", "RUNNING"} and not self.task_current(w, t):
                t.update(status="CANCELLED", lease_token=None)

    # ---- model results
    def reading(self, w: dict, source_id: str, result: dict, reader: str):
        source = next((s for s in w["sources"] if s["id"] == source_id), None)
        require(source, "资料不存在", 404)
        require(result.get("source_sha256") == source["sha256"], "阅读结果对应的资料已变更")
        rows = result.get("pages")
        require(isinstance(rows, list) and {r.get("id") for r in rows} == {p["id"] for p in source["pages"]} and len(rows) == len(source["pages"]),
                "需提交资料全部页面的阅读记录（不多不少）", 422)
        by_id = {r["id"]: r for r in rows}
        transcriptions, crops = [], []
        original = self.path(source["path"]).read_bytes() if any(r.get("crops") for r in rows) else b""
        require(not original or sha(original) == source["sha256"], "资料原件缺失或已被修改，请重新导入")
        for page in source["pages"]:
            row = by_id[page["id"]]
            cat = row.get("classification")
            require(cat in {"SUBSTANTIVE", "REFERENCE", "EMPTY"}, "需标记正文、参考文献或空白页", 422)
            require(not page["requires_visual"] or row.get("visual_inspected") is True, f"{page['location']} 必须核对原件视觉内容", 422)
            require(cat != "EMPTY" or (not page["unit_ids"] and str(row.get("reason", "")).strip()), "只有无文字页可标为空白，并需说明原因", 422)
            cells = row.get("transcription") or []
            require(isinstance(cells, list), "transcription 需为列表", 422)
            new_crops = self._crops(w, source, page, row.get("crops") or [], original, reader)
            crops += new_crops
            on_page = [g["id"] for g in embedded(source) if g["page_id"] == page["id"]]
            fig_rows = row.get("figures") or []
            require(isinstance(fig_rows, list) and sorted(str(f.get("id")) for f in fig_rows) == sorted(on_page),
                    f"{page['location']} 需逐张说明本页登记的图（不多不少）：{'、'.join(on_page) or '无'}", 422)
            fig_notes = {}
            for f in fig_rows:
                require(len(str(f.get("note", "")).strip()) >= 4, f"图 {f['id']} 需说明画面内容（仅供审核，不上页）", 422)
                caps = f.get("caption_unit_ids") or []
                require(isinstance(caps, list) and set(caps) <= set(page["unit_ids"]), f"图 {f['id']} 的图注单元须是本页的文字单元", 422)
                fig_notes[f["id"]] = {"note": str(f["note"])[:2000], "caption_unit_ids": caps,
                                      "may_contain_patient_info": f.get("may_contain_patient_info") is True}
            for g, f in new_crops:
                caps = f.get("caption_unit_ids") or []
                require(isinstance(caps, list) and set(caps) <= set(page["unit_ids"]), f"截取图 {g['id']} 的图注单元须是本页的文字单元", 422)
                fig_notes[g["id"]] = {"note": str(f["note"])[:2000], "caption_unit_ids": caps, "bbox": g["bbox"], "sha256": g["sha256"],
                                      "may_contain_patient_info": f.get("may_contain_patient_info") is True}
            on_page += [g["id"] for g, _ in new_crops]
            if cat == "SUBSTANTIVE" and not page["unit_ids"]:
                require(cells or str(row.get("note", "")).strip(), f"{page['location']} 没有可提取文字，需转录图中文字或说明画面内容", 422)
            try:
                transcriptions += transcription_units(page, cells, reader, set(on_page))
            except IngestError as e:
                raise WorkflowError(str(e), 422)
            page["reading"] = {"reader": reader, "at": now(), "classification": cat, "visual_inspected": row.get("visual_inspected") is True,
                               "note": str(row.get("note", ""))[:4000], "reason": str(row.get("reason", ""))[:1000],
                               "transcribed_cells": len(cells), "figures": fig_notes}
        source["transcriptions"] = transcriptions
        source["figures"] = embedded(source) + [g for g, _ in crops]
        for u in transcriptions:
            w["confirmations"]["transcriptions"].pop(u["id"], None)

    def _crops(self, w: dict, source: dict, page: dict, rows: list, original: bytes, reader: str) -> list[tuple[dict, dict]]:
        """Regions of a PDF page the reader asks to show as figures: code renders the page and cuts each box."""
        require(isinstance(rows, list), "crops 需为列表", 422)
        if not rows:
            return []
        require(source["kind"] == "pdf", f"{page['location']}：只有PDF资料可以按区域截取图（其他资料请导出PDF后作为原件导入）", 422)
        number = int(page["id"].rsplit(":p", 1)[1])
        out, seen = [], set()
        for f in rows:
            cid = str(f.get("id", "")) if isinstance(f, dict) else ""
            require(re.fullmatch(r"c[1-9]\d?", cid) and cid not in seen, f"{page['location']} 截取图编号需为 c1、c2…且不重复：{cid!r}", 422)
            seen.add(cid)
            require(len(str(f.get("note", "")).strip()) >= 4, f"截取图 {cid} 需说明画面内容（仅供审核，不上页）", 422)
            try:
                bbox = check_bbox(f.get("bbox"))
                png, width, height = crop_pdf_page(original, number, bbox)
            except IngestError as e:
                raise WorkflowError(f"{page['location']} 截取图 {cid}：{e}", 422)
            fid = f"{page['id']}:{cid}"
            out.append(({"id": fid, "source_id": source["id"], "page_id": page["id"], "location": f"{page['location']} 截取图{cid[1:]}",
                         "method": "page_crop", "bbox": bbox, "dpi": CROP_DPI, "width": width, "height": height,
                         "original_format": "pdf", "sha256": sha(png), "path": self.immutable(w["id"], "figures", png, ".png"),
                         "reader": reader, "second_read": None}, f))
        return out

    def second_read(self, w: dict, source_id: str, result: dict, reader: str):
        source = next((s for s in w["sources"] if s["id"] == source_id), None)
        crops = page_crops(source) if source else []
        require(source and (source["transcriptions"] or crops), "该资料没有需复核的转录或截取图", 404)
        require(result.get("source_sha256") == source["sha256"], "复核结果对应的资料已变更")
        first = {u["reader"] for u in source["transcriptions"]} | {g["reader"] for g in crops}
        require(reader not in first, "第二次转录和截取须由不同的执行端完成", 422)
        cells = {c.get("unit_id"): c for c in result.get("cells") or []}
        require(set(cells) == {u["id"] for u in source["transcriptions"]}, "需逐个提交全部转录单元的独立读取结果", 422)
        boxes = {c.get("figure_id"): c for c in result.get("crops") or [] if isinstance(c, dict)}
        require(set(boxes) == {g["id"] for g in crops}, "需逐张提交全部截取图的独立截取区域", 422)
        checked = {}
        for g in crops:
            try:
                checked[g["id"]] = check_bbox(boxes[g["id"]].get("bbox"))
            except IngestError as e:
                raise WorkflowError(f"截取图 {g['id']}：{e}", 422)
        for u in source["transcriptions"]:
            text = str(cells[u["id"]].get("text", ""))
            u["second_read"] = {"reader": reader, "at": now(), "text": text, "agree": canon(text) == canon(u["text"])}
        for g in crops:
            overlap = iou(g["bbox"], checked[g["id"]])
            g["second_read"] = {"reader": reader, "at": now(), "bbox": checked[g["id"]], "iou": overlap, "agree": overlap >= CROP_AGREE_IOU}

    def accept_claims(self, w: dict, source_id: str, result: dict, reader: str):
        """A source's claims, page by page: verbatim spans with type and scope, and the source's profile."""
        source = next((s for s in w["sources"] if s["id"] == source_id), None)
        require(source, "资料不存在", 404)
        require(all(p["reading"] for p in source["pages"]), "该资料尚未完成阅读")
        require(result.get("input_sha256") == claims_input(source), "论断清单对应的资料、阅读或转录已变更")
        rows = result.get("pages")
        require(isinstance(rows, list) and [r.get("id") for r in rows if isinstance(r, dict)] == [p["id"] for p in source["pages"]],
                "需按顺序提交资料全部页面的论断（不多不少）", 422)
        own = {p["id"] for p in source["pages"]}
        units: dict[str, dict] = {}
        for u in all_units(w):
            if u["page_id"] in own:
                units.setdefault(u["page_id"], {})[u["id"]] = u
        items, warnings = [], []
        try:
            prof = claim_profile(result.get("profile"), "\n".join(u["text"] for page in units.values() for u in page.values()))
            for page, row in zip(source["pages"], rows):
                got, warn = page_claims(page, units.get(page["id"], {}), row.get("claims") or [], page["reading"])
                if page["reading"]["classification"] == "SUBSTANTIVE" and not got:
                    require(len(str(row.get("no_claims", "")).strip()) >= 4,
                            f"{page['location']} 是正文页：请列出论断，或在 no_claims 中说明为何没有", 422)
                    warn = [x for x in warn if "没有列出论断" not in x] + [f"{page['location']} 无论断：{row['no_claims']}"]
                items += got
                warnings += warn
        except ClaimError as e:
            raise WorkflowError(str(e), 422)
        self.snapshot(w, "claims", result)
        source["claims"] = {"input_sha256": claims_input(source), "reader": reader, "at": now(), "profile": prof,
                            "items": items, "warnings": warnings, "result_sha256": digest({"profile": prof, "items": items})}

    def accept_summary_review(self, w: dict, result: dict, reviewer: str):
        """An independent reader checks each outline point, core sentence and relation of the summary against the claims
        and units they cite. Points not entailed or contradicted, and unsupported cores or relations, are blockers."""
        require(summary_current(w), "没有当前版本的总结")
        require(reviewer != (w.get("summary_meta") or {}).get("author"), "总结审查须由总结作者之外的执行端完成", 422)
        require(reviewer not in {(s.get("claims") or {}).get("reader") for s in w["sources"]}, "总结审查须由论断清单作者之外的执行端完成", 422)
        require(result.get("input_sha256") == summary_review_input(w), "审查对应的总结已过期")
        require(result.get("schema_version") == SUMMARY_REVIEW_SCHEMA, "总结审查需使用 summary_review.v2 完整覆盖合同", 422)

        def unique_rows(value, field, expected, label):
            require(isinstance(value, list) and all(isinstance(r, dict) for r in value), f"{label}需为列表", 422)
            ids = [r.get(field) for r in value]
            require(all(isinstance(i, str) for i in ids) and len(ids) == len(set(ids)) and set(ids) == set(expected),
                    f"{label}需逐条审查全部目标（不多不少，ID不得重复）", 422)
            return {r[field]: r for r in value}

        rows = unique_rows(result.get("sections"), "section_id", [s["id"] for s in w["summary"]["sections"]], "章节")
        ledger.book(w, "summary")                          # seed from an earlier review before this one replaces it
        issues, ok = [], set()
        evidence = {}
        for sec in w["summary"]["sections"]:
            for r in sec.get("point_coverage") or []:
                evidence[r["point_id"]] = "、".join(r.get("claim_ids") or r.get("unit_ids") or [])
            for k in key_point_targets(w, sec):
                evidence[k["target_id"]] = "、".join(k.get("claim_ids") or k.get("unit_ids") or [])

        def issue(ref, severity, problem):
            issues.append({"ref": ref, "severity": severity, "category": "CONTENT_ERROR", "source_ref": evidence.get(ref, ref),
                           "evidence": "独立审查判定", "problem": str(problem)[:2000]})

        def passed(ref):
            ok.add(ref)

        for sec in w["summary"]["sections"]:
            r = rows.get(sec["id"])
            require(isinstance(r, dict), f"需逐章给出审查结论：缺少 {sec['id']}", 422)
            v = r.get("summary_verdict")
            require(v in POINT_VERDICTS, f"章节 {sec['id']} 的 summary_verdict 须是 {' / '.join(POINT_VERDICTS)} 之一", 422)
            if v != "ENTAILED":
                require(str(r.get("summary_issue", "")).strip(), f"章节 {sec['id']} 的总结文字未判为 ENTAILED 时需写明问题", 422)
                issue(sec["id"], "NOTE" if v == "PARTIAL" else "BLOCKER", f"章节总结（{v}）：{r['summary_issue']}")
            else:
                passed(sec["id"])
            supported = [p["point_id"] for p in sec.get("point_coverage") or [] if p.get("unsupported") is None]
            pts = unique_rows(r.get("points"), "point_id", supported, f"章节 {sec['id']} 要点")
            for pid in supported:
                x = pts[pid]
                require(x.get("verdict") in POINT_VERDICTS, f"要点 {pid} 的结论须是 {' / '.join(POINT_VERDICTS)} 之一", 422)
                if x["verdict"] != "ENTAILED":
                    require(str(x.get("issue", "")).strip(), f"要点 {pid} 未判为 ENTAILED 时需写明问题", 422)
                    issue(pid, "NOTE" if x["verdict"] == "PARTIAL" else "BLOCKER", f"{x['verdict']}：{x['issue']}")
                else:
                    passed(pid)
            targets = key_point_targets(w, sec)
            keys = unique_rows(r.get("key_points"), "target_id", [k["target_id"] for k in targets], f"章节 {sec['id']} key_points")
            for target in targets:
                x = keys[target["target_id"]]
                require(x.get("verdict") in POINT_VERDICTS, "关键要点结论须使用四级判定", 422)
                if x["verdict"] != "ENTAILED":
                    require(str(x.get("issue", "")).strip(), "关键要点未判为 ENTAILED 时需写明问题", 422)
                    issue(target["target_id"], "NOTE" if x["verdict"] == "PARTIAL" else "BLOCKER", f"{x['verdict']}：{x['issue']}")
                else:
                    passed(target["target_id"])
            m = sec.get("message")
            if m and m["core"].get("claim_id"):
                c = r.get("core") or {}
                require(c.get("verdict") in {"SUPPORTED", "UNSUPPORTED"}, f"章节 {sec['id']} 需判断核心句（core.verdict：SUPPORTED / UNSUPPORTED）", 422)
                if c["verdict"] == "UNSUPPORTED":
                    require(str(c.get("issue", "")).strip(), f"章节 {sec['id']} 的核心句判为 UNSUPPORTED 时需写明问题", 422)
                    issue(f"{sec['id']}.core", "BLOCKER", c["issue"])
                else:
                    passed(f"{sec['id']}.core")
            if m:
                rels = r.get("relations") or []
                require(isinstance(rels, list) and len(rels) == len(m.get("relations") or []), f"章节 {sec['id']} 需按顺序逐条审查全部要点关系", 422)
                for i, x in enumerate(rels, 1):
                    require(isinstance(x, dict) and x.get("verdict") in {"SUPPORTED", "UNSUPPORTED"},
                            f"章节 {sec['id']} 第{i}条关系的结论须是 SUPPORTED / UNSUPPORTED", 422)
                    if x["verdict"] == "UNSUPPORTED":
                        require(str(x.get("issue", "")).strip(), f"章节 {sec['id']} 第{i}条关系判为 UNSUPPORTED 时需写明问题", 422)
                        issue(f"{sec['id']}.relation{i}", "BLOCKER", x["issue"])
                    else:
                        passed(f"{sec['id']}.relation{i}")
        refs = set(evidence) | {s["id"] for s in w["summary"]["sections"]} | {o["id"] for o in w["outline"]} | {"pending_issues"}
        refs |= {f"{s['id']}.core" for s in w["summary"]["sections"]}
        refs |= {f"{s['id']}.relation{i}" for s in w["summary"]["sections"] for i in range(1, len((s.get("message") or {}).get("relations") or []) + 1)}
        refs |= {p["id"] for s in w["sources"] for p in s["pages"]} | set(all_claims(w))
        others = []
        for x in result.get("issues") or []:               # anything else: omissions, weight of a source, wording
            require(isinstance(x, dict) and x.get("severity") in {"BLOCKER", "NOTE"} and str(x.get("problem", "")).strip(),
                    "其他问题需给出严重程度（BLOCKER / NOTE）和说明", 422)
            ref = str(x.get("ref") or "general").strip()
            others.append({"category": "CONTENT_ERROR", "evidence": x["problem"], "suggestion": "修订总结或人工裁定",
                           **x, "ref": ref if ref in refs else "general", "source_ref": x.get("source_ref") or ref})
        rnd = ledger.record_round(w, "summary", "SUMMARY", reviewer=reviewer, input_sha256=summary_review_input(w),
                                  dispositions=result.get("prior_issues") or [], new_issues=others, valid_refs=refs,
                                  ok_refs=ok, problem_refs={i["ref"] for i in issues if i["severity"] == "BLOCKER"}, auto_issues=issues)
        self.snapshot(w, "summary_review", result)
        w["summary_review"] = {"schema_version": SUMMARY_REVIEW_SCHEMA, "input_sha256": summary_review_input(w), "reviewer": reviewer, "at": now(),
                               "sections": result["sections"], "round": rnd["round"], "issues": [], "dismissed": {}}

    def accept_summary(self, w: dict, result: dict, author: str = ""):
        self.source_integrity(w)
        require(fully_claimed(w), "全部资料完成阅读和论断清单后才能提交总结")
        require(result.get("schema_version") == "full_source_summary.v3", "总结版本需为full_source_summary.v3", 422)
        require(result.get("input_sha256") == input_hash(w), "总结对应的资料、提纲或阅读版本已过期")
        require(len(str(result.get("overall_summary", "")).strip()) >= 40, "需提供有实质内容的全文总结", 422)
        sections = result.get("sections")
        require(isinstance(sections, list) and sections, "需提供章节总结", 422)
        ids = [s.get("id") for s in sections]
        require(all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)), "章节ID不能为空或重复", 422)
        known, covered = pages(w), set()
        unit_page = {u["id"]: u["page_id"] for u in all_units(w)}
        for s in sections:
            require(bool(str(s.get("title", "")).strip()) and len(str(s.get("summary", "")).strip()) >= 20, "章节标题及总结不能为空", 422)
            refs = s.get("source_page_ids")
            require(isinstance(refs, list) and refs and set(refs) <= set(known), "章节需引用有效的资料页面", 422)
            covered.update(refs)
            # key points: each generalisation names the units it rests on, so the customer can check it against the original
            points = s.get("key_points")
            require(isinstance(points, list), f"章节 {s['id']} 需提供 key_points 列表", 422)
            substantive = any(known[r]["reading"]["classification"] == "SUBSTANTIVE" for r in refs)
            require(points or not substantive or (structured(w) and s.get("outline_id")),
                    f"章节 {s['id']} 引用了正文页，需至少一条关键依据（key_points）", 422)
            for k in points:
                require(isinstance(k, dict) and len(str(k.get("point", "")).strip()) >= 4, f"章节 {s['id']} 的关键依据需写明归纳（point）", 422)
                cite(w, k, refs, f"章节 {s['id']} 的关键依据", unit_page)
        require(set(known) <= covered, "全文总结未覆盖全部资料页面（含参考文献与空白说明）", 422)
        if structured(w):
            result["outline_coverage"] = self._point_coverage(w, sections, unit_page)
        mapping = result.get("outline_coverage", [])
        outline_ids = {o["id"] for o in w["outline"]}
        require(isinstance(mapping, list) and len(mapping) == len(outline_ids) and {m.get("outline_id") for m in mapping} == outline_ids,
                "总结需覆盖全部教学提纲条目", 422)
        for m in mapping:
            require(m.get("section_ids") and set(m["section_ids"]) <= set(ids), "提纲映射需指向有效章节", 422)
        require(isinstance(result.get("pending_issues"), list), "需列出待解决问题；无问题时为空列表", 422)
        self.snapshot(w, "summary", result)
        w["summary"] = copy.deepcopy(result)
        w["summary_meta"] = {"author": author, "at": now()}
        w["content_approval"] = None

    @staticmethod
    def _point_coverage(w: dict, sections: list[dict], unit_page: dict) -> list[dict]:
        """A structured outline organises the summary: one section per outline item, in the outline's order,
        and every point of the item either rests on source units or is declared unsupported with a reason."""
        items = [o["id"] for o in w["outline"]]
        mapped = [s.get("outline_id") for s in sections if s.get("outline_id")]
        unknown = [m for m in mapped if m not in items]
        require(not unknown, "章节引用了不存在的提纲条目：" + "、".join(unknown), 422)
        require(sorted(mapped) == sorted(items) and len(mapped) == len(set(mapped)), "每个提纲条目需对应且只对应一个章节（outline_id）", 422)
        require(mapped == items, "章节须按提纲顺序排列；未纳入提纲的资料内容放在最后、不带 outline_id", 422)
        for s in sections:
            if not s.get("outline_id"):
                continue
            item = next(o for o in w["outline"] if o["id"] == s["outline_id"])
            rows = s.get("point_coverage")
            require(isinstance(rows, list) and [r.get("point_id") for r in rows if isinstance(r, dict)] == [p["id"] for p in item["points"]],
                    f"章节 {s['id']} 需按顺序逐条说明提纲要点（point_coverage）", 422)
            for r in rows:
                if r.get("unsupported") is not None:
                    require(len(str(r["unsupported"]).strip()) >= 4 and not r.get("unit_ids") and not r.get("claim_ids"),
                            f"要点 {r['point_id']} 标为无资料支撑时需写明原因，且不列单元或论断", 422)
                    continue
                require(r.get("claim_ids"), f"要点 {r['point_id']} 需列出支撑它的论断（claim_ids），或标为无资料支撑（unsupported）", 422)
                cite(w, r, s["source_page_ids"], f"要点 {r['point_id']}", unit_page)
                claims = all_claims(w)
                quotes = [sp["quote"] for c in r["claim_ids"] for sp in claims[c]["spans"]]
                if r.get("statement") is not None:   # the outline's wording goes further than the sources: say what they say
                    require(len(str(r["statement"]).strip()) >= 4, f"要点 {r['point_id']} 的 statement（资料实际说）不能为空", 422)
                    r["statement"] = str(r["statement"]).strip()
                    r["unmatched_tokens"] = unbacked_tokens(r["statement"], quotes)
                    r["outline_unmatched_tokens"] = unbacked_tokens(str(r.get("point", "")), quotes)
                else:
                    r["unmatched_tokens"] = unbacked_tokens(str(r.get("point", "")), quotes)
            Store._message(w, s, rows, unit_page)
        return [{"outline_id": s["outline_id"], "section_ids": [s["id"]]} for s in sections if s.get("outline_id")]

    @staticmethod
    def _message(w: dict, s: dict, rows: list[dict], unit_page: dict) -> None:
        """The section's information structure: its core sentence (verbatim from one unit), the role of each supported
        point (exactly one core; support; limit) and the relations between points, each resting on units. Relations
        the author adds without a candidate from the originals are marked manual for the customer's review."""
        supported = {r["point_id"]: r["unit_ids"] for r in rows if r.get("unsupported") is None}
        m = s.get("message")
        if not supported:
            require(not m, f"章节 {s['id']} 的要点均无资料支撑，不写 message", 422)
            return
        sid = s["id"]
        require(isinstance(m, dict), f"章节 {sid} 需提供信息结构 message：核心句、要点角色和要点关系", 422)
        units = {u["id"]: u for u in all_units(w)}
        claims = all_claims(w)
        core = m.get("core")
        require(isinstance(core, dict), f"章节 {sid} 需提供核心句 core：{{claim_id}}，或说明为何没有 {{none: 原因}}", 422)
        roles = m.get("roles")
        require(isinstance(roles, dict) and set(roles) == set(supported),
                f"章节 {sid} 需为每条有资料支撑的要点标注角色（roles），且只标这些要点", 422)
        bad = sorted({v for v in roles.values() if v not in ROLES})
        require(not bad, f"章节 {sid} 的要点角色只能是 core / support / limit：{'、'.join(map(str, bad))}", 422)
        cores = [p for p, v in roles.items() if v == "core"]
        if "claim_id" not in core:                 # e.g. a table: the original has no sentence that states the item
            require(len(str(core.get("none", "")).strip()) >= 4 and not cores,
                    f"章节 {sid} 没有核心句时需写明原因（core.none），且不标 core 要点", 422)
            core["none"] = str(core["none"]).strip()
        else:
            Store._core(w, s, core, cores, rows, claims, units)
        Store._relations(w, s, m, supported, unit_page)

    @staticmethod
    def _core(w, s, core, cores, rows, claims, units):
        sid = s["id"]
        require(core.get("claim_id") in claims, f"章节 {sid} 的核心句需指向存在的论断（core.claim_id）", 422)
        kc = claims[core["claim_id"]]
        require(kc["page_id"] in s["source_page_ids"], f"章节 {sid} 的核心句须来自本章引用的页面", 422)
        core.update(unit_id=kc["spans"][0]["unit_id"], quote=" ｜ ".join(" ".join(sp["quote"].split()) for sp in kc["spans"]),
                    spans=kc["spans"], claim_type=kc["type"])
        quote = core["quote"]
        sig = units[core["unit_id"]].get("signals") or {}
        core["marked"] = next((k for k in ("title", "emphasis") if any(canon(quote) in canon(x) or canon(x) in canon(quote)
                                                                       for x in sig.get(k) or [])), None)
        require(len(cores) == 1, f"章节 {sid} 须恰好有一条核心要点（现有 {len(cores)} 条）", 422)
        core_row = next(r for r in rows if r["point_id"] == cores[0])
        require(core["claim_id"] in core_row["claim_ids"], f"章节 {sid} 的核心句须是核心要点 {cores[0]} 所列的论断之一", 422)

    @staticmethod
    def _relations(w, s, m, supported, unit_page):
        sid = s["id"]
        rels = m.get("relations")
        require(isinstance(rels, list), f"章节 {sid} 需列出要点关系（relations）；确实没有关系时为空列表", 422)
        cands = relation_candidates_of(w)
        for i, r in enumerate(rels, 1):
            where = f"章节 {sid} 的第{i}条关系"
            require(isinstance(r, dict) and r.get("type") in RELATION_TYPES,
                    f"{where}类型须是 {' / '.join(RELATION_TYPES)} 之一", 422)
            items = r.get("items")
            require(isinstance(items, list) and items and set(items) <= set(supported), f"{where}需列出涉及的本章有资料支撑的要点（items）", 422)
            cid = r.get("from_candidate")
            explicit = list(r.get("unit_ids") or [])
            if cid:
                require(cid in cands, f"{where}引用了不存在的候选关系 {cid}", 422)
                require(explicit and set(explicit) <= set(cands[cid]["unit_ids"]), f"{where}需列出候选关系 {cid} 中的单元（unit_ids）", 422)
            else:
                require(r.get("claim_ids"), f"{where}没有来自原件的候选，需列出支撑它的论断（claim_ids）", 422)
            cite(w, r, s["source_page_ids"], where, unit_page)
            r["manual"] = not cid
        m["warnings"] = ([f"章节 {sid} 没有列出要点关系，页面会排成并列清单"] if not rels else []) + \
                        [f"章节 {sid} 的第{i}条关系没有来自原件的候选，客户确认时标为人工判断" for i, r in enumerate(rels, 1) if r["manual"]]

    def accept_facts(self, w: dict, result: dict, author: str):
        require(content_approved(w), "请先完成客户全文内容确认")
        require(result.get("summary_sha256") == digest(w["summary"]), "事实库对应的总结已过期")
        require(isinstance(result.get("facts"), list) and result["facts"], "事实库不能为空", 422)
        require(isinstance(result.get("derivations", []), list), "derivations 需为列表", 422)
        terms = result.get("terms", [])
        require(isinstance(terms, list) and all(isinstance(t, str) and t.strip() for t in terms), "terms 需为非空字符串列表", 422)
        blob = canon("\n".join(u["text"] for u in all_units(w)))
        missing = [t for t in terms if canon(t) not in blob]
        require(not missing, "术语须逐字出现在资料中：" + "、".join(missing), 422)
        section_ids = {s["id"] for s in w["summary"]["sections"]}
        for f in result["facts"]:
            require(isinstance(f, dict) and ({"id", "unit", "quote"} <= set(f) or {"id", "figure"} <= set(f)),
                    "每条事实需有 id、unit、quote；图事实需有 id、figure", 422)
            require(set(f.get("section_ids", [])) <= section_ids, f"事实 {f.get('id')} 引用了不存在的总结章节", 422)
        F, D, T = fx.parse(result)
        fx.verify(F, D, all_units(w), {}, T, figure_states(w))
        accepted = [f for f in F if f.status == "ACCEPTED"]
        uncertain = [f.id for f in accepted if not f.figure and f.needs_confirmation]
        if w.get("source_evidence_policy") == "verified-transcription.v1":
            require(not uncertain, "事实库引用了未核定的视觉转录；请先独立第二次读取或人工对照确认：" + "、".join(uncertain), 422)
        require(accepted, "没有一条事实通过核对：" + "；".join(f"{f.id}：{'；'.join(f.problems)}" for f in F[:5]), 422)
        self.snapshot(w, "facts", result)
        w["facts"] = {"result": copy.deepcopy(result), "result_sha256": digest(result), "input_sha256": facts_input(w),
                      "author": author, "at": now(), "accepted": len(accepted), "rejected": len(F) - len(accepted)}

    def accept_deck(self, w: dict, result: dict, author: str):
        require(facts_current(w), "请先建立当前版本的事实库")
        require(result.get("facts_sha256") == facts_sha(w), "页面规格对应的事实库已过期")
        self._transcription_proposals(w, result.get("transcription_proposals", []), author)
        deck = {k: v for k, v in result.items() if k not in {"facts_sha256", "issue_responses"}}
        responses = self._issue_responses(w, result.get("issue_responses"), [p.get("id") for p in deck.get("pages") or []])
        cut = deck.get("facts") or []
        require(isinstance(cut, list), "facts 需为列表", 422)
        store_ids = {f.get("id") for f in w["facts"]["result"]["facts"]}
        section_ids = {s["id"] for s in w["summary"]["sections"]}
        seen = set()
        for f in cut:
            require(isinstance(f, dict) and {"id", "unit", "quote"} <= set(f) and set(f) <= CARVED_FIELDS,
                    "页面切出的事实需有 id、unit、quote，只能再带 " + "、".join(sorted(CARVED_FIELDS - {"id", "unit", "quote"}))
                    + "（不能带推导或图）", 422)
            require(isinstance(f["id"], str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", f["id"]), f"事实编号不合法：{f['id']}", 422)
            require(f["id"] not in store_ids and f["id"] not in seen, f"切出的事实编号与已有事实重复：{f['id']}", 422)
            require(set(f.get("section_ids") or []) <= section_ids, f"事实 {f['id']} 引用了不存在的总结章节", 422)
            seen.add(f["id"])
        v = verified(w, cut)
        scope=scope_of(deck)
        if scope:
            require(w.get('deck') and scope['base_page_ids']==[p['id'] for p in w['deck']['result']['pages']], '前N页生成须保留现有整套规格的页面编号',422)
            n=scope['page_count']
            require(deck['pages'][n:]==w['deck']['result']['pages'][n:], '本次范围之外的页面不得修改',422)
        chk = check_spec(deck, v["facts"], v["terms"], w["outline"], w["summary"]["sections"], w["requirements"], w.get("outline_parts"))
        from factdeck.content_obligations import validate_deck
        prevention = validate_deck(w, deck, v, chk)
        used = {fid for p in chk["pages"] for fid in p["facts"] + p["edge_facts"]}
        cut_problems = [f"切出的事实 {f['id']} 未通过核对：{'；'.join(v['facts'][f['id']]['problems'])}"
                        for f in cut if v["facts"][f["id"]]["status"] != "ACCEPTED"]
        cut_problems += [f"切出的事实 {f['id']} 没有在任何页面使用" for f in cut if f["id"] not in used]
        if chk["errors"] or cut_problems or prevention["errors"]:
            problems = cut_problems + prevention["errors"] + chk["deck_errors"] + [f"{p['id']}：{e}" for p in chk["pages"] for e in p["errors"]]
            raise WorkflowError("页面规格未通过：" + "；".join(problems[:12]) + ("…" if len(problems) > 12 else ""), 422)
        if deck.get("theme"):
            w["theme"] = self._theme(deck["theme"], w)
        self.snapshot(w, "deck", result)
        w["deck"] = {"result": deck, "result_sha256": digest(deck), "input_sha256": deck_input(w), "author": author, "at": now(),
                     "source_gate_version": 1,
                     "warnings": chk["warnings"] + context_warnings(w, deck, chk, v), "coverage": chk["coverage"],
                     "source_pending": prevention["pending"],
                     "issue_responses": responses}

    def _transcription_proposals(self, w: dict, rows: list, author: str):
        """Correction proposals are new, pending units; originals and human decisions are retained."""
        require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), "transcription_proposals 需为列表", 422)
        originals = {u["id"]:(s,u) for s in w["sources"] for u in s["units"] + s["transcriptions"]}
        seen = set()
        proposals = {p["id"]:p for p in w.get("transcription_proposals", [])}
        for r in rows:
            uid_ = r.get("source_unit_id")
            require(uid_ in originals and uid_ not in seen, "更正提案须引用不重复的既有来源单元", 422)
            seen.add(uid_)
            s,u = originals[uid_]
            require(r.get("source_sha256") == s["sha256"], "更正提案的来源版本已过期", 422)
            text, reason = str(r.get("text", "")).strip(), str(r.get("reason", "")).strip()
            require(text and reason and len(text) <= 12000, "更正提案须有文字和原图更正依据", 422)
            pid = "correction:" + uid_
            previous = proposals.get(pid)
            if previous and previous["text"] != text:
                w["confirmations"]["transcriptions"].pop(pid, None)
                self.snapshot(w, "superseded_transcription_proposal", previous)
            proposals[pid] = {"id":pid,"source_id":s["id"],"page_id":u["page_id"],"location":u["location"]+"（更正提案）",
                "method":"visual_transcription","text":text,"reader":author,"at":now(),"needs_confirmation":True,
                "proposal_of":uid_,"original_text":u["text"],"reason":reason,
                "confirmation_reason":"更正提案尚未人工确认；保留原转录，需对照原图裁定"}
        w["transcription_proposals"] = list(proposals.values())

    @staticmethod
    def _issue_responses(w: dict, rows, page_ids: list) -> dict:
        """A revised deck answers every unresolved semantic issue: what changed where, why nothing changed, or
        that it waits for a human ruling. The reviewer still decides whether an issue is fixed."""
        need = {i["id"] for i in ledger.unresolved(w, "semantic")}
        if not need:
            return {}
        rows = [] if rows is None else rows
        require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), "issue_responses 需为列表", 422)
        got = [r.get("issue_id") for r in rows]
        require(len(got) == len(set(got)) and set(got) == need,
                "修订版须逐条回应语义审查中全部未闭环的问题（issue_responses）：缺少 " + "、".join(sorted(need - set(got))), 422)
        out = {}
        for r in rows:
            act, note = r.get("action"), str(r.get("note") or "").strip()
            require(act in {"CHANGED", "NOT_CHANGED", "NEEDS_HUMAN"}, f"{r['issue_id']} 的 action 须是 CHANGED / NOT_CHANGED / NEEDS_HUMAN", 422)
            pages = r.get("pages") or []
            if act == "CHANGED":
                require(isinstance(pages, list) and pages and set(pages) <= set(page_ids), f"{r['issue_id']} 标为已修改时须写出修改的页面编号", 422)
            require(note, f"{r['issue_id']} 需说明修改内容或不修改的理由", 422)
            out[r["issue_id"]] = {"action": act, "pages": list(pages), "note": note[:2000]}
        return out

    def accept_critique(self, w: dict, result: dict, critic: str):
        """A visual critique of the current render: per page, the rubric verdicts and concrete fixes. It informs the
        page author and the human page reviewer; it never records a page review."""
        require(render_current(w), "没有当前的正式渲染")
        require(critic != w["deck"]["author"], "版面评审须由页面作者之外的执行端完成", 422)
        require(result.get("input_sha256") == critique_input(w), "评审对应的渲染已过期")
        by_id = {p["id"]: p for p in w["render"]["pages"]}
        got = {x.get("page_id"): x for x in result.get("pages") or [] if isinstance(x, dict)}
        require(set(got) == set(by_id), "须逐页给出评审：缺少 " + "、".join(sorted(set(by_id) - set(got))) or "页面编号不符", 422)
        pages_out = {}
        for pid, x in got.items():
            require(x.get("png_sha256") == by_id[pid]["sha256"], f"{pid} 的评审对应的页面图片不是当前版本", 422)
            rub = x.get("rubric") or {}
            require(set(rub) == set(RUBRIC) and all(v in {"PASS", "REVISE"} for v in rub.values()),
                    f"{pid} 须对 {'、'.join(RUBRIC)} 逐项给出 PASS / REVISE", 422)
            fixes = [str(f).strip() for f in x.get("fixes") or [] if str(f).strip()]
            require(fixes or "REVISE" not in rub.values(), f"{pid} 有需修改项时须写出具体修改意见", 422)
            pages_out[pid] = {"rubric": rub, "fixes": fixes, "png_sha256": x["png_sha256"]}
        w["critique"] = {"input_sha256": critique_input(w), "critic": critic, "at": now(), "pages": pages_out,
                         "revise": sorted(pid for pid, x in pages_out.items() if "REVISE" in x["rubric"].values())}

    def accept_semantic(self, w: dict, result: dict, reviewer: str, check: str | None = None):
        """One of the two independent checklists; the issue ledger carries every earlier problem forward."""
        semrev.accept(w, result, reviewer, check or result.get("check"))
        self.snapshot(w, "semantic_review", result)

    # ---- tasks
    def brief(self, w: dict, kind: str, binding: str | None) -> dict:
        req = {"requirements": w["requirements"], "outline": w["outline"], "context": w["context"]}
        if kind == "SUMMARY_AMEND":
            return {"kind": kind, "mode": "pending_responses_only", "input_sha256": self.fingerprint(w, kind, None),
                    "baseline_summary": copy.deepcopy(w["summary"]), "responses": w["summary_pending_responses"],
                    "rules": ["仅处理人工答复对应的待确认事项和来源限制；不得重新编写要点或改变任何临床事实、引用、覆盖。",
                              "用户陈述保留其人工确认身份，不伪造成原PDF中的事实或已验证授权。",
                              "只有有明确答复的事项可以从pending_issues移除；UNKNOWN保持待确认。",
                              "完成后系统自动排队独立复核；停在人工内容确认。"],
                    "result_contract": copy.deepcopy(w["summary"])}
        if kind == "READ_SOURCE":
            s = next(s for s in w["sources"] if s["id"] == binding)
            return {"kind": kind, "source": {k: s[k] for k in ("id", "filename", "sha256", "kind")},
                    "source_url": f"/api/deck/workflows/{w['id']}/sources/{s['id']}/file",
                    "pages": [{**{k: p[k] for k in ("id", "location", "text", "requires_visual")},
                               **({"page_image_url": page_image_url(w, p)} if s["kind"] == "pdf" else {}),
                               "figures": [{**{k: g[k] for k in ("id", "location", "width", "height")}, "url": fig_url(w, g["id"])}
                                           for g in embedded(s) if g["page_id"] == p["id"]]} for p in s["pages"]],
                    "rules": ["逐页阅读原件；requires_visual 的页面必须查看原始画面（图片、图表、表格截图、流程图）。",
                              "图/表中的文字和数字逐格转录到 transcription（id、location、text），只转录看到的内容，不推测、不补全。",
                              "流程图、机制图、分类树：每个框/节点的文字各转录为一格；每条箭头另转录为一格，location 写明“箭头”及位置，"
                              "text 写“起点文字→终点文字”，两端与对应节点格的文字完全一致（箭头上有文字的写成“起点文字→终点文字（箭头文字）”）。"
                              "只记录画面上确实存在的箭头及其方向。",
                              "程序从原件取出的图（figures）逐张查看并在 figures 中说明：note 写画面内容（仅供审核，不上页）；"
                              "caption_unit_ids 填本页中作为该图图题/图注的文字单元；图中若可能有患者姓名、编号、日期、面部等信息，"
                              "may_contain_patient_info 填 true。图中的文字逐格转录，并在该转录格上写 figure: 图编号。",
                              *(["PDF 页面上值得上页、但不是一张内嵌图片的图（矢量图表、森林图、由多块拼成的图）可在 crops 中给出截取区域："
                                 "id 为 c1、c2…，bbox 为页面归一化坐标 [x0, y0, x1, y1]（左上角为原点），由程序按 " + str(CROP_DPI) + " dpi 渲染后截取；"
                                 "区域须完整包含图例、坐标轴、脚注、显著性标记、风险人数表等全部组成部分，宁宽勿窄；note、caption_unit_ids、"
                                 "may_contain_patient_info 同上。截取图的编号为 页面编号:c1，图中文字的转录格写 figure: 该编号。"
                                 "page_image_url 是程序渲染的整页图，可用来量取坐标。"] if s["kind"] == "pdf" else []),
                              "参考文献页标 REFERENCE；无任何内容的页标 EMPTY 并说明原因。"],
                    "result_contract": {"source_sha256": s["sha256"], "pages": [{"id": p["id"], "classification": "SUBSTANTIVE",
                                        "visual_inspected": False, "note": "", "reason": "", "transcription": [],
                                        "figures": [{"id": g["id"], "note": "", "caption_unit_ids": [], "may_contain_patient_info": False}
                                                    for g in embedded(s) if g["page_id"] == p["id"]],
                                        **({"crops": []} if s["kind"] == "pdf" else {})} for p in s["pages"]]}}
        if kind == "SECOND_READ":
            s = next(s for s in w["sources"] if s["id"] == binding)
            return {"kind": kind, "source": {k: s[k] for k in ("id", "filename", "sha256")},
                    "source_url": f"/api/deck/workflows/{w['id']}/sources/{s['id']}/file",
                    "cells": [{"unit_id": u["id"], "location": u["location"]} for u in s["transcriptions"]],
                    "crops": [{"figure_id": g["id"], "page_id": g["page_id"], "location": g["location"],
                               "description": (figure_reading(w, g["id"]) or {}).get("note", ""),
                               "page_image_url": page_image_url(w, pages(w)[g["page_id"]])} for g in page_crops(s)],
                    "rules": ["独立查看原件，按位置逐格读出文字；不得参考第一次转录（本合同不提供）。", "看不清时如实写出看到的内容并在文字中标注“[不清]”。",
                              "crops 中每张图按描述在原页上独立找到该图，给出完整包含图例、坐标轴、脚注、标记的截取区域 bbox"
                              "（页面归一化坐标 [x0, y0, x1, y1]，左上角为原点）；不得参考第一次截取（本合同不提供）。"],
                    "result_contract": {"source_sha256": s["sha256"], "cells": [{"unit_id": u["id"], "text": ""} for u in s["transcriptions"]],
                                        "crops": [{"figure_id": g["id"], "bbox": [0, 0, 1, 1]} for g in page_crops(s)]}}
        if kind == "CLAIMS":
            s = next(s for s in w["sources"] if s["id"] == binding)
            by_page: dict[str, list] = {}
            for u in all_units(w):
                by_page.setdefault(u["page_id"], []).append(u)
            return {"kind": kind, "source": {k: s[k] for k in ("id", "filename", "kind")}, "input_sha256": claims_input(s),
                    "source_url": f"/api/deck/workflows/{w['id']}/sources/{s['id']}/file",
                    "claim_types": CLAIM_TYPES, "source_kinds": SOURCE_KINDS, "span_max": SPAN_MAX,
                    "pages": [{"id": p["id"], "location": p["location"], "classification": p["reading"]["classification"],
                               "reading_note": p["reading"]["note"],
                               "units": [{k: u[k] for k in ("id", "text")} | ({"signals": u["signals"]} if u.get("signals") else {})
                                         | ({"needs_confirmation": True} if u.get("needs_confirmation") else {}) for u in by_page.get(p["id"], [])]}
                              for p in s["pages"]],
                    "rules": ["逐页列出这一页原文说了什么（论断 claims），只做摘录和标注，不改写、不归纳、不推理、不补常识。",
                              "每条论断是一个命题：spans 为 1–" + str(SPANS_PER_CLAIM) + " 个原文片段 {unit_id, quote}，quote 是该单元中的逐字原文，"
                              "一句话或一个表格格子，每段不超过 " + str(SPAN_MAX) + " 字（不能整页引用）。表格中的一个取值写成“行名 + 列名 + 格子”三个片段；"
                              "流程图的一条路径可写成节点和箭头的片段。一句话里有两个独立的命题时拆成两条。",
                              "type 取自 claim_types：推荐、定义、标准/阈值、研究结果、比较、相关（非因果）、机制、作者解读/推测、产品信息、背景、讨论题。"
                              "“与……相关”是相关不是因果；“提示”“可能”是解读不是结果；事后分析、真实世界研究的结论照原文标注。",
                              "scope 写适用范围：population（人群）、time（时间点或疗程）、condition（条件、剂量、前提），各为本页原文片段；原文没有写就留空，不得推断。",
                              "页标题和原件强调（signals）通常是作者的结论，应列为论断；程序会提示未列入的标记。",
                              "profile 说明整份资料的性质：kind 取自 source_kinds；sponsor 为资料中写明的出品方或赞助方（原文片段，无则留空），date 为资料中的日期（原文片段）。"
                              "企业产品推广材料标 promotional，其中的比较和评价性说法照录并如实标注类型。",
                              "参考文献页和空白页不列论断；正文页没有可列的命题时在 no_claims 说明原因。程序会从片段中自动标出限定词、数字和引文角标。"],
                    "result_contract": {"input_sha256": claims_input(s), "profile": {"kind": "other", "sponsor": "", "date": "", "note": ""},
                                        "pages": [{"id": p["id"], "claims": [{"id": "k1", "type": "result", "spans": [{"unit_id": "", "quote": ""}],
                                                                              "scope": {"population": "", "time": "", "condition": ""}}],
                                                   "no_claims": ""} for p in s["pages"]]}}
        if kind == "SUMMARY_REVIEW":
            claims = all_claims(w)
            units = {u["id"]: u for u in all_units(w)}

            def evidence(row):
                return {"claims": [claim_view(claims[c]) for c in row.get("claim_ids") or [] if c in claims],
                        "units": [{"id": u, "location": units[u]["location"], "text": units[u]["text"]} for u in row.get("unit_ids") or [] if u in units]}

            view = []
            for sec in w["summary"]["sections"]:
                m = sec.get("message") or {}
                view.append({"section_id": sec["id"], "title": sec["title"], "summary": sec["summary"],
                             "key_points": [{"target_id": k["target_id"], "point": k["point"], **evidence(k)} for k in key_point_targets(w, sec)],
                             "points": [{"point_id": r["point_id"], "point": r.get("point", ""), **({"statement": r["statement"]} if r.get("statement") else {}),
                                         "role": (m.get("roles") or {}).get(r["point_id"]),
                                         "unmatched_tokens": r.get("unmatched_tokens", []), **evidence(r)}
                                        for r in sec.get("point_coverage") or [] if r.get("unsupported") is None],
                             "unsupported": [{"point_id": r["point_id"], "point": r.get("point", ""), "reason": r["unsupported"]}
                                             for r in sec.get("point_coverage") or [] if r.get("unsupported") is not None],
                             **({"core": {"claim": claim_view(claims[m["core"]["claim_id"]])} if m["core"].get("claim_id") in claims else m["core"],
                                 "relations": [{**{k: r[k] for k in ("type", "items", "manual")}, "from_candidate": r.get("from_candidate"),
                                                **evidence(r)} for r in m.get("relations") or []]} if m else {})})
            return {"kind": kind, **req, "input_sha256": summary_review_input(w), "overall_summary": w["summary"]["overall_summary"],
                    "pending_issues": w["summary"]["pending_issues"], "sections": view,
                    "profiles": {s["id"]: (s.get("claims") or {}).get("profile") for s in w["sources"]},
                    "relation_types": RELATION_NAMES, "claim_types": CLAIM_TYPES,
                    "rules": ["独立判断总结是否忠实于原文，只依据所附论断和单元原文，不参考总结作者的理由，不做外部检索。",
                              "要点有 statement（资料实际说）时按 statement 判断，point 是客户提纲的措辞，二者的差异由客户确认，不作为总结的问题；"
                              "逐条判断要点（points）：ENTAILED 原文完整支持；PARTIAL 大体支持但有扩大、缺限定词或范围不符；"
                              "NOT_ENTAILED 原文不支持；CONTRADICTED 与原文矛盾。除 ENTAILED 外都写明问题（issue）。",
                              "重点检查：相关被写成因果；解读、推测被写成结果；“可能”“约”“部分”等限定词或人群、时间、剂量条件丢失；"
                              "数字与原文不一致（unmatched_tokens 列出要点文字中不见于所引论断的数字）；推广材料的说法被当作中立结论。",
                              "核心句（core）：是否确是该条目原文中的重点，SUPPORTED / UNSUPPORTED。"
                              "关系（relations）：该关系是否被所附原文支持，manual 为 true 的是作者判断，须特别核对，SUPPORTED / UNSUPPORTED。",
                              "章节总结文字（summary）同样按四级判断（summary_verdict）。",
                              "key_points 的每条主要归纳也必须独立给出四级 verdict 和 issue，使用原样 target_id；不得以章节结论代替逐条审核。",
                              "其他问题（遗漏的重要论断、资料性质未交代、限定要点未标 limit 等）写入 issues：severity、category"
                              "（CONTENT_ERROR 内容错误 / EVIDENCE_MISSING 来源证据缺失 / EXPRESSION_AMBIGUITY 表达歧义 / HUMAN_DECISION 人工决策）、ref、source_ref、problem、suggestion。不得给出医学放行结论。",
                              "先回看 prior_issues（此前全部未闭环问题及历史）：逐条处置 FIXED（evidence_refs 写当前版本的要点/目标编号，evidence 说明所见修订）、"
                              "OPEN、NEEDS_HUMAN（须用户裁定，修订总结不能解决）或 RETAINED（证据不足而保留）。与本轮逐条判定矛盾的处置会被拒绝；"
                              "仍有问题的要点不要另起新问题，程序会并入原问题编号。"],
                    "prior_issues": [ledger.view(i) for i in ledger.unresolved(w, "summary")],
                    "result_contract": {"schema_version": SUMMARY_REVIEW_SCHEMA, "input_sha256": summary_review_input(w), "issues": [],
                                        "prior_issues": [{"issue_id": i["id"], "status": "", "evidence": "", "evidence_refs": []}
                                                         for i in ledger.unresolved(w, "summary")],
                                        "sections": [{"section_id": v["section_id"], "summary_verdict": "ENTAILED", "summary_issue": "",
                                                      "points": [{"point_id": p["point_id"], "verdict": "ENTAILED", "issue": ""} for p in v["points"]],
                                                      "key_points": [{"target_id": p["target_id"], "verdict": "ENTAILED", "issue": ""} for p in v["key_points"]],
                                                      **({"core": {"verdict": "SUPPORTED", "issue": ""}} if isinstance(v.get("core"), dict) and "claim" in v["core"] else {}),
                                                      **({"relations": [{"verdict": "SUPPORTED", "issue": ""} for _ in v["relations"]]} if "relations" in v else {})}
                                                     for v in view]}}
        if kind == "SUMMARY":
            return {"kind": kind, **req, "input_sha256": input_hash(w),
                    "review_issues": [ledger.view(i) for i in ledger.unresolved(w, "summary")],
                    "sources": [{"id": s["id"], "filename": s["filename"], "pages": [{**{k: p[k] for k in ("id", "location", "text")}, "reading": p["reading"],
                                                                                     "units": [{k: u[k] for k in ("id", "text")} | ({"signals": u["signals"]} if u.get("signals") else {})
                                                                                               for u in s["units"] if u["page_id"] == p["id"]],
                                                                                     "claims": [claim_view(k) for k in (s.get("claims") or {}).get("items", [])
                                                                                                if k["page_id"] == p["id"]]}
                                                                                    for p in s["pages"]],
                                 "profile": (s.get("claims") or {}).get("profile"),
                                 "transcriptions": [{k: u[k] for k in ("id", "location", "text")} for u in s["transcriptions"]],
                                 "relation_candidates": s.get("relations") or []} for s in w["sources"]],
                    "relation_types": RELATION_NAMES, "claim_types": CLAIM_TYPES, "source_kinds": SOURCE_KINDS,
                    "rules": ["全文综合总结；不得新增资料以外的事实。", "所有资料页面都要被章节引用；教学提纲全部映射到章节。",
                              "保留人群、剂量、阈值、时间、证据等级和限制条件；不确定或冲突之处列入 pending_issues。",
                              "依据是论断清单（pages[].claims）：每条论断是原文片段加类型和适用范围，qualifiers 是其中的限定词，numbers 是关键数字，"
                              "profile 说明资料的性质（指南、研究、推广材料等）。归纳不得强于论断：相关不能写成因果，解读不能写成结果，"
                              "推广材料的说法要让客户看得出出处，限定词和适用范围不能丢。",
                              "每章在 key_points 中列出主要归纳：point 为一句归纳，claim_ids 为支撑它的论断（也可补充 unit_ids），"
                              "须位于本章 source_page_ids 的页面内；引用正文页的章节至少一条。",
                              *(["提纲带要点时由提纲组织总结：每个提纲条目一章（outline_id），按提纲顺序排列；章内 point_coverage 逐条说明该条目的每个要点："
                                 "有资料支撑时列出 claim_ids（须在本章页面内）；资料没有、或客户已决定不上页时写 unsupported 原因，不得凭提纲补写。"
                                 "要点文字中的数字若不见于所引论断，程序会列入 unmatched_tokens 供审查。"
                                 "提纲措辞比资料说得更多、更强或不同（如“优先”“至少12个月”、把相关写成因果、换了指标或人群）时，"
                                 "在该要点写 statement（资料实际说）：只用所引论断的内容，保留限定词、人群、定义和研究设计；"
                                 "确认稿会并列提纲写法与资料写法，由客户决定。不得改写 point。"
                                 "提纲中的数字和结论不是事实来源，要点与原文不一致时以原文为准并列入 pending_issues。"
                                 "未纳入任何提纲条目的资料页，放入最后一章“未纳入提纲的资料内容”（不带 outline_id）。",
                                 "每个提纲条目的章节写信息结构 message（要点全部无资料支撑时不写）："
                                 "core 为本条目最重要的一句：{claim_id}，须是核心要点所列的论断之一，程序取其原文；"
                                 "优先选原件作者标出的句子（units 的 signals：title 为页标题，emphasis 为加粗、标色或放大的片段），"
                                 "不得自拟结论。roles 为每条有资料支撑的要点标 core / support / limit，恰好一条 core；"
                                 "局限、例外、禁忌、适用范围和注意事项标 limit，它们必须上页。"
                                 "relations 列出要点之间的关系 {type, items, from_candidate?, unit_ids?, claim_ids?}，type 取自 relation_types；"
                                 "优先采用 relation_candidates（来自原件的箭头、表格、编号和连接词），写明候选编号，unit_ids 取候选中的单元；"
                                 "原件没有候选而你判断存在的关系也可以写，须列出支撑它的 claim_ids（在本章页面内），客户确认时会标为人工判断。"
                                 "没有关系时写空列表，页面会排成并列清单。"] if structured(w) else [])],
                    "result_contract": {"schema_version": "full_source_summary.v3", "input_sha256": input_hash(w), "overall_summary": "",
                                        "sections": ([{"id": f"s{i}", "outline_id": o["id"], "title": o["text"], "summary": "", "source_page_ids": [],
                                                       "key_points": [{"point": "", "claim_ids": []}],
                                                       "point_coverage": [{"point_id": p["id"], "point": p["text"], "claim_ids": []} for p in o["points"]],
                                                       "message": {"core": {"claim_id": ""}, "roles": {p["id"]: "support" for p in o["points"]},
                                                                   "relations": [{"type": "sequence", "items": [], "claim_ids": [], "from_candidate": ""}]}}
                                                      for i, o in enumerate(w["outline"], 1)]
                                                     + [{"id": f"s{len(w['outline']) + 1}", "title": "未纳入提纲的资料内容", "summary": "", "source_page_ids": [],
                                                         "key_points": []}]) if structured(w) else
                                        [{"id": "s1", "title": "", "summary": "", "source_page_ids": [], "key_points": [{"point": "", "claim_ids": []}]}],
                                        "outline_coverage": [{"outline_id": o["id"], "section_ids": []} for o in w["outline"]], "pending_issues": []}}
        if kind == "FACTS":
            return {"kind": kind, **req, "summary": w["summary"],
                    "units": [{k: u[k] for k in ("id", "source_id", "location", "text")} | {"needs_confirmation": u.get("needs_confirmation", False)} for u in all_units(w)],
                    "figures": [{**{k: g[k] for k in ("id", "source_id", "location", "width", "height")}, "url": fig_url(w, g["id"]),
                                 "reading": figure_reading(w, g["id"])} for g in figures(w).values()],
                    "rules": ["每条事实是某个来源单元中的逐字引文（quote）；display 只能是 quote 的逐字节选，不得改写、不得删去否定或限定词。",
                              "一条事实表达一个可上页的要点；数字、单位、比较符号、人群、时间、条件必须与原文一致。",
                              "同一对象同一属性在不同资料中的取值，分别建事实并填写 entity/attribute/value，程序会标出冲突。",
                              "确需改写、单位换算、表格列与药名的对应等非逐字内容，写入 derivations（claim、rule、evidence），由人工确认。",
                              "terms 列出药名、研究名、量表名等专有名称（须逐字出现在资料中），它们在作者文字中不能出现。",
                              "section_ids 标注事实所属的总结章节；覆盖总结中所有需要上页的要点。",
                              "原件中的流程图、机制图、分类树、判断路径要能重画成 flow：除整句要点外，每个节点的转录格各建一条短事实（quote 为节点文字原样），"
                              "每个“起点→终点”箭头转录格各建一条事实（quote 原样），note 写“图示节点”或“图示箭头”及所属页。节点关系只来自原件箭头或文字，不得推断。",
                              "并列的指标、阈值、条件，可把名称与取值分别建事实（例如指标名一条、阈值一条），供 cards/compare 的标签与主值使用；两者须来自同一处原文。",
                              "需要展示原件中的图时，建图事实 {id, figure: 图编号, caption: [图题的文字事实id], section_ids}，不写 unit/quote。"
                              "关于图的任何说法只能引用资料文字；不得根据图读数、推算或描述趋势。图须经截取/去标识确认和客户逐张许可后才能正式上页。"],
                    "result_contract": {"summary_sha256": digest(w["summary"]), "terms": [], "facts": [
                        {"id": "f1", "unit": "来源单元id", "quote": "逐字引文", "display": "", "entity": "", "attribute": "", "value": "",
                         "derivation": "", "note": "", "section_ids": []}], "derivations": []}}
        if kind == "DECK":
            v = verified(w, [])
            from factdeck.content_obligations import build_obligations
            return {"kind": kind, **req, "summary": w["summary"], "theme": w["theme"], "themes": list(THEMES) + (["brand"] if w.get("brand") else []),
                    "content_obligations": build_obligations(w, (w.get("deck") or {}).get("result"), verified(w)),
                    "facts": [{k: f[k] for k in ("id", "unit", "display", "quote", "location", "source_id", "section_ids", "needs_confirmation", "figure", "caption")}
                              for f in v["facts"].values() if f["status"] == "ACCEPTED"],
                    "units": [{k: u[k] for k in ("id", "source_id", "location", "text")} | {"needs_confirmation": u.get("needs_confirmation", False)}
                              | ({"arrow": u["arrow"]} if u.get("arrow") else {}) for u in all_units(w)],
                    "layouts": {k: {"required": sorted(req_keys), "use_for": LAYOUT_GUIDE[k][0], "example": LAYOUT_GUIDE[k][1]}
                                for k, (req_keys, _) in LAYOUTS.items()},
                    "recipes": {k: {"use_for": use, "slots_example": ex} for k, (_, use, ex) in RECIPES.items()},
                    "visual_critique": ({pid: x for pid, x in w["critique"]["pages"].items() if "REVISE" in x["rubric"].values()}
                                        if w.get("critique") else {}),
                    "review_issues": [ledger.view(i) for i in ledger.unresolved(w, "semantic")],
                    "outline_parts": w.get("outline_parts") or [], "unsupported_points": unsupported_points(w),
                    "relation_layouts": {k: sorted(v) for k, v in RELATION_LAYOUTS.items()},
                    "outline_rules": (["提纲带要点时，课件按提纲组织：每个部分以章节页（divider）开头，页面顺序与提纲条目顺序一致；"
                                       "每个内容页（含结束页）用 point_ids 标注本页讲的提纲要点，每条有资料支撑的要点至少上一页；"
                                       "unsupported_points 中的要点不上页，由程序列为无资料支撑。各部分页数参照 outline_parts 的建议区间。"
                                       "一页可以讲同一条目下的几条要点；不要为凑页数拆碎，也不要把不同部分的内容放在同一页。",
                                       "总结各章的 message 给出信息结构：core 是该条目最重要的一句，roles 标出核心、支撑、限定要点，relations 是要点之间的关系。"
                                       "据此设计页面：每个内容页写 focus: {\"fact\": id}，指本页最强的元素，须是本页显示的事实，并来自核心要点或某条关系的单元；"
                                       "关系按 relation_layouts 选版式（先后、条件分支用 flow/timeline，满足任一、均需满足用 cards/grid，对照用 compare/table，"
                                       "对象×属性用 table，结论←证据用 hero/cards）；标为 limit 的要点必须在标注它的页面上显示其原文事实，不能在排版时丢掉。"]
                                      if structured(w) else []),
                    "rules": ["按需求（受众、目的、时长、目标页数、重点）组织页面；一页一个认知单元，内容多就拆页。",
                              "源头约束：content_bindings将主事实与适用范围/条件/限制/脚注的逐字事实绑定，同页显示全部依赖；不明关系留待人工。"
                              "content_obligations的实际使用主事实及lead_in/leading_connective强信号必须逐项回应context_responses；"
                              "COVERED引用同页或明确允许相邻页的真实可见事实；EXCERPT须给出明确上页节选marker及理由；NEEDS_HUMAN不得用于绕过已锁定条件。"
                              "更正原视觉转录须提交transcription_proposals({source_unit_id,source_sha256,text,reason})，"
                              "代码创建correction:原unit_id待人工单元，保留原转录。只可制作待确认页面，不能据此确认或正式生成。",
                              "页面上的实质内容只能是 {\"fact\": id}；作者文字 {\"text\": ...} 只做组织和命名，不得包含数字、比较、药名/专有名称、评价或方向性措辞。",
                              "每页标注 outline_ids 与 section_ids；全部提纲条目都要有页面；未上页的总结章节写入 omissions 并给出原因。",
                              "先设计页面，再定每个格子放什么：事实库的颗粒度不合适时（整句要拆成标签与数值、节点、表格单元、对照面板的各项），"
                              "在结果的 facts 中从 units 里切出新事实 {id, unit, quote, display?, section_ids, note?}：quote 须逐字出现在该单元中，"
                              "display 只能是 quote 的逐字节选，不得删去否定或限定词；编号不得与事实库重复，每条都须在页面上用到。"
                              "切出的事实与事实库走同一道程序核对，并由语义审查逐条检查；不能带推导、不能切图。改写或换算仍须回到事实库阶段写推导。",
                              "先按内容的结构选版式（见 layouts 的 use_for 与 example）：流程、机制、判断路径用 flow；并列指标或阈值用 cards；"
                              "两三组对照用 compare；先后顺序用 timeline；多个维度用 grid；只有确实没有更强结构的要点才用 bullets。连续多页列表或表格程序会提示。",
                              "每页要有一个结构化主体，参照“主体 + 辅助说明”的构图（如指标卡片 + 注释、流程图 + 侧栏、对照面板 + 结论条）；"
                              "列表页和陈述页属于纯文字页，全篇超过三成程序会提示。陈述页只用于整页只有一句话要讲；一句导语加若干要点时，导语放 lead。"
                              "关键数字用 emph 标出，或放进 cards / hero。字号由程序决定，不要为了填满页面拆碎或拼凑内容。",
                              "一页一个设计方案：固定版式是起点，内容需要时用 composed 为这一页单独构图（见 layouts.composed）。"
                              "构图前先写 design：first 第一眼看到什么、then 随后读什么、reference 供查阅什么、strong 唯一的强元素及为什么用这种形状。"
                              "并列的各项（两类通路、两份指南、几种药物）同等处理，用同一 peer 键；重点靠位置、关系和局部标记表达，不要把其中一项涂深。"
                              "整组共有的标签只写一次：节选删去“中国：”这类范围标签时，本页须另有事实写明它（如图例）。"
                              "渲染报告会逐页给出留白、重复等提示：按这一页的内容去改，或在 design.exceptions 中写明为什么这样是对的。",
                              "flow：节点给网格位置 col 0–4、row 0–3，节点文字用事实（原件图示的节点事实）；每条箭头 [起点, 终点, 支持事实, 标签?]，"
                              "支持事实须在本页引用，或是原件箭头单元（method 为 pptx_arrow 的单元由程序从原件图形取出，记录两端单元；"
                              "或图片中转录的“起点→终点”）建成的事实：两个节点须分别引用箭头两端单元的事实，方向一致，程序核对。"
                              "箭头标签（是/否/无效等，至多5字）写在第四项 {\"fact\": id}；原件箭头带标签时必须引用原件的那个标签单元。",
                              "表格每格是引用列表；列头是作者文字。glossary 中的词须出现在对应事实引文中，可用于作者文字。",
                              "原件图用 figure 版式：figure 放图事实 {\"fact\": id}，side 放 0–3 条文字事实；compare 的面板也可用 {\"heading\": …, \"figure\": {\"fact\": id}} 放一张图（不再放条目）；一页至多两张图，两张并排不得暗示原文没有的比较。图注由程序随图显示。图事实只能放在 figure 位置，图上不加任何标注。",
                              "hero：一个短数值（≤16字）做主视觉，label 与 support 为补充；timeline：2–6 步，每步 when + what；grid：2–6 格，每格 heading + 1–3 条 items。",
                              "chart：柱状图，chart.bars 为 2–8 根柱，每根 {label, value: {\"fact\": id}}，orientation 可为 vertical/horizontal。"
                              "柱长由程序从 value 事实的文字中读出数字计算：每条 value 事实须恰好含一个数字，不能有比较符号、区间或负号，各柱单位一致；从 0 起画，不画刻度数字。"
                              "不同研究或人群的数值不应放进同一图表暗示可比；来自多份资料时程序会提示，由语义审查判断。",
                              "强调：任一事实引用可写 {\"fact\": id, \"emph\": [片段]}，片段须按顺序逐字出现在该事实的显示文字中，最多 3 段，只改变字重和颜色。",
                              "review_issues 是语义审查台账中全部未闭环的问题（含历史）：修订时一次处理全部，而不是只改最新一轮提到的页面；"
                              "在 issue_responses 中逐条回应：CHANGED（pages 写修改的页面，note 写改了什么）、NOT_CHANGED（note 写理由）、"
                              "NEEDS_HUMAN（页面修订无法解决，例如原文未明确的关系、待人工确认的转录或纳入范围；note 写需要用户决定什么）。是否修复由独立复核判定。",
                              "同类问题全套排查：引导句（以“：”“以下”结尾）要和它引出的全部条目一起出现；以“然而/但/因此”等开头的节选要带上前文；"
                              "节选之后原文还有条件、例外或停止规则时一并呈现。程序在提交时给出这类提示（warnings）。"],
                    "result_contract": {"facts_sha256": facts_sha(w), "title": w["title"], "theme": w["theme"], "glossary": [], "omissions": [], "facts": [],
                                        **({"issue_responses": [{"issue_id": i["id"], "action": "", "pages": [], "note": ""}
                                                                for i in ledger.unresolved(w, "semantic")]} if ledger.unresolved(w, "semantic") else {}),
                                        "pages": [{"id": "cover", "layout": "cover", "title": {"text": ""}, "outline_ids": [], "section_ids": []}]
                                        + ([{"id": "p1", "layout": "bullets", "title": {"text": ""}, "items": [], "outline_ids": [],
                                             "point_ids": [], "section_ids": []}] if structured(w) else [])}}
        if kind == "VISUAL_CRITIQUE":
            r = w["render"]
            return {"kind": kind, **req, "input_sha256": critique_input(w), "rubric": RUBRIC,
                    "pages": [{"page_id": p["id"], "png": str(self.path(r["path"] + "/" + p["file"])), "png_sha256": p["sha256"],
                               **{k: p.get(k) for k in ("design", "signals", "review", "metrics")}} for p in r["pages"]],
                    "rules": ["逐页打开 png 查看画面（不得未看图就给结论）；对照该页的 design（作者说明的第一眼、随后、查阅、强元素）与 rubric 各项逐项判断 PASS / REVISE。",
                              "REVISE 时写出具体、可执行的修改意见：指明哪一块、怎么改（换构图方案、合并相邻内容、调整并列项处理、改变强调位置等），不要泛泛而谈。",
                              "signals 是程序量出的提示：已说明理由的（justified）判断理由是否成立；未说明的判断是否需要修改。",
                              "只评版面，不评医学内容；不得放行页面——逐页审核仍由人完成。"],
                    "result_contract": {"input_sha256": critique_input(w), "pages": [
                        {"page_id": p["id"], "png_sha256": p["sha256"], "rubric": {k: "PASS" for k in RUBRIC}, "fixes": []} for p in r["pages"]]}}
        # SEMANTIC_REVIEW: one of the two checklists (binding COVERAGE / RELATIONS)
        return semrev.brief(w, binding, req)

    def fingerprint(self, w: dict, kind: str, binding: str | None) -> str:
        if kind == "SUMMARY_AMEND":
            return digest({"summary": w["summary"], "responses": w.get("summary_pending_responses"), "input": input_hash(w)})
        if kind in VISUAL_KINDS:
            return self.generation_fingerprint(w, kind, binding)
        if kind == "READ_SOURCE":
            return next(s["sha256"] for s in w["sources"] if s["id"] == binding)
        if kind == "SECOND_READ":
            s = next(s for s in w["sources"] if s["id"] == binding)
            fp = {"sha": s["sha256"], "cells": [(u["id"], u["text"]) for u in s["transcriptions"]]}
            if page_crops(s):
                fp["crops"] = [(g["id"], g["sha256"]) for g in page_crops(s)]
            return digest(fp)
        if kind == "CLAIMS":
            return claims_input(next(s for s in w["sources"] if s["id"] == binding))
        if kind == "SEMANTIC_REVIEW":
            return semrev.task_fingerprint(w, binding)
        return {"SUMMARY": input_hash, "SUMMARY_REVIEW": summary_review_input, "FACTS": facts_input, "DECK": deck_input,
                "VISUAL_CRITIQUE": critique_input}[kind](w)

    def queue(self, workflow_id: str, kind: str, page_ids=None):
        require(kind in KINDS, "任务类型无效", 422)
        if kind in VISUAL_KINDS:
            require(page_ids and len(page_ids) == 1, "请用生成入口自动排队；修订须指定一个页面", 422)
            return self.revise_generation(workflow_id, page_ids[0], kind)
        with self.transaction(workflow_id, "QUEUE_" + kind) as w:
            if kind == "READ_SOURCE":
                require(w["sources"], "请先导入资料")
                bindings = [s["id"] for s in w["sources"] if not all(p["reading"] for p in s["pages"])]
            elif kind == "SECOND_READ":
                bindings = [s["id"] for s in w["sources"] if needs_second_read(s)]
                require(bindings, "没有需要第二次独立转录或截取的资料")
            elif kind == "CLAIMS":
                require(fully_read(w), "请先完成全部资料阅读")
                if page_ids:                        # redo named sources (a revised claims list replaces the current one)
                    known = {s["id"] for s in w["sources"]}
                    require(set(page_ids) <= known, "资料不存在：" + "、".join(sorted(set(page_ids) - known)), 404)
                    bindings = list(page_ids)
                else:
                    bindings = [s["id"] for s in w["sources"] if not claims_current(s)]
                require(bindings, "全部资料的论断清单均为当前版本")
            elif kind == "SUMMARY":
                require(fully_claimed(w), "请先完成全部资料阅读和论断清单")
                bindings = [None]
            elif kind == "SUMMARY_AMEND":
                require(summary_current(w) and w.get("summary_pending_responses", {}).get("subject_sha256") == digest(w["summary"]), "需先保存当前版本的人工答复")
                bindings = [None]
            elif kind == "SUMMARY_REVIEW":
                require(summary_current(w), "请先完成当前版本的总结")
                bindings = [None]
            elif kind == "FACTS":
                require(content_approved(w), "请先完成客户全文内容确认")
                bindings = [None]
            elif kind == "DECK":
                require(facts_current(w), "请先建立当前版本的事实库")
                bindings = [None]
            elif kind == "VISUAL_CRITIQUE":
                require(render_current(w), "请先完成当前版本的正式渲染")
                bindings = [None]
            else:
                require(deck_current(w), "请先完成页面规格")
                require(not checked(w)["errors"], "页面规格有程序核对错误，请先修订再安排语义审查")
                wanted = [c for c in (page_ids or semrev.CHECKS)]
                require(set(wanted) <= set(semrev.CHECKS), "语义审查的检查表为 COVERAGE / RELATIONS", 422)
                bindings = [c for c in wanted if not semrev.check_current(w, c)]
                require(bindings, "两张语义检查表均为当前版本")
            for b in bindings:
                fp = self.fingerprint(w, kind, b)
                if any(t["kind"] == kind and t["binding"] == b and t["input_sha256"] == fp and t["status"] in {"PENDING", "RUNNING"} for t in w["tasks"]):
                    continue
                w["tasks"].append({"id": uid("task"), "kind": kind, "binding": b, "input_sha256": fp, "status": "PENDING", "attempts": 0,
                                   "created_at": now(), "worker": None, "lease_token": None, "lease_until": 0, "error": None,
                                   "brief": self.brief(w, kind, b)})
        return self.get(workflow_id)

    def eligible(self, w: dict, t: dict, worker: str) -> bool:
        """Independent tasks are not handed to an identity whose result would be refused for independence."""
        try:
            if t["kind"] == "SEMANTIC_REVIEW":
                if worker in {(w.get("deck") or {}).get("author"), (w.get("facts") or {}).get("author")}:
                    return False
                other = [c for c in semrev.CHECKS if c != t["binding"]]
                done = [w["semantic_checks"][c]["reviewer"] for c in other if semrev.check_current(w, c)]
                running = [x["worker"] for x in w["tasks"] if x["kind"] == "SEMANTIC_REVIEW" and x["status"] == "RUNNING"
                           and x["binding"] in other]
                return worker not in done + running
            if t["kind"] == "SUMMARY_REVIEW":
                return worker not in {(w.get("summary_meta") or {}).get("author")} | {(s.get("claims") or {}).get("reader") for s in w["sources"]}
        except (KeyError, TypeError):
            return True
        return True

    def task_current(self, w: dict, t: dict) -> bool:
        try:
            if t["kind"] in VISUAL_KINDS:
                from app.deck_generation import current
                if not current(w) or not semantic_current(w) or open_issues(w): return False
                return self.generation_fingerprint(w, t["kind"], t["binding"]) == t["input_sha256"]
            if t["kind"] in {"READ_SOURCE", "SECOND_READ", "CLAIMS"} and not any(s["id"] == t["binding"] for s in w["sources"]):
                return False
            if t["kind"] == "CLAIMS" and not fully_read(w): return False
            if t["kind"] == "SUMMARY" and not fully_claimed(w): return False
            if t["kind"] == "SUMMARY_REVIEW" and not summary_current(w): return False
            if t["kind"] == "FACTS" and not content_approved(w): return False
            if t["kind"] == "DECK" and not facts_current(w): return False
            if t["kind"] == "SEMANTIC_REVIEW" and (not deck_current(w) or t["binding"] not in semrev.CHECKS): return False
            if t["kind"] == "VISUAL_CRITIQUE" and not render_current(w): return False
            return self.fingerprint(w, t["kind"], t["binding"]) == t["input_sha256"]
        except (StopIteration, KeyError, TypeError, WorkflowError):
            return False

    def complete(self, workflow_id: str, task_id: str, token: str, result: dict):
        task = next((t for t in self.get(workflow_id)["tasks"] if t["id"] == task_id), None)
        require(task, "任务不存在", 404)
        if task["kind"] == "VISUAL_LAYOUT":
            return self.complete_layout(workflow_id, task_id, token, result)
        require(task["kind"] not in VISUAL_KINDS, "生图、去字、矢量化任务须提交实际文件与调用回执", 422)
        with self.transaction(workflow_id, "TASK_COMPLETE") as w:
            t = self.leased(w, task_id, token)
            {"READ_SOURCE": lambda: self.reading(w, t["binding"], result, t["worker"]),
             "SECOND_READ": lambda: self.second_read(w, t["binding"], result, t["worker"]),
             "CLAIMS": lambda: self.accept_claims(w, t["binding"], result, t["worker"]),
             "SUMMARY": lambda: self.accept_summary(w, result, t["worker"]),
             "SUMMARY_AMEND": lambda: self.accept_summary_amend(w, result, t["worker"]),
             "SUMMARY_REVIEW": lambda: self.accept_summary_review(w, result, t["worker"]),
             "FACTS": lambda: self.accept_facts(w, result, t["worker"]),
             "DECK": lambda: self.accept_deck(w, result, t["worker"]),
             "SEMANTIC_REVIEW": lambda: self.accept_semantic(w, result, t["worker"], t["binding"]),
             "VISUAL_CRITIQUE": lambda: self.accept_critique(w, result, t["worker"])}[t["kind"]]()
            t.update(status="COMPLETE", completed_at=now(), lease_token=None, result_sha256=digest(result))
            t["result_path"] = self.snapshot(w, "task_result", result)
            self.cancel_stale(w)
            if t["kind"] == "READ_SOURCE" and w.get("source_evidence_policy") == "verified-transcription.v1":
                s = next(s for s in w["sources"] if s["id"] == t["binding"])
                if needs_second_read(s):
                    binding = s["id"]
                    fp = self.fingerprint(w, "SECOND_READ", binding)
                    if not any(x["kind"] == "SECOND_READ" and x["binding"] == binding and x["input_sha256"] == fp and x["status"] in {"PENDING","RUNNING","COMPLETE"} for x in w["tasks"]):
                        w["tasks"].append({"id":uid("task"),"kind":"SECOND_READ","binding":binding,"input_sha256":fp,
                            "status":"PENDING","attempts":0,"created_at":now(),"worker":None,"lease_token":None,
                            "lease_until":0,"error":None,"brief":self.brief(w,"SECOND_READ",binding)})
            if t["kind"] == "SUMMARY_AMEND":
                self.enqueue_once(w, "SUMMARY_REVIEW")
        return self.get(workflow_id)

    def enqueue_once(self, w: dict, kind: str):
        fp = self.fingerprint(w, kind, None)
        if any(t["kind"] == kind and t["input_sha256"] == fp and t["status"] in {"PENDING", "RUNNING", "COMPLETE"} for t in w["tasks"]):
            return
        w["tasks"].append({"id": uid("task"), "kind": kind, "binding": None, "input_sha256": fp,
                           "status": "PENDING", "attempts": 0, "created_at": now(), "worker": None,
                           "lease_token": None, "lease_until": 0, "error": None, "brief": self.brief(w, kind, None)})

    def accept_summary_amend(self, w: dict, result: dict, author: str):
        original = w["summary"]
        responses = w.get("summary_pending_responses", {})
        require(responses.get("subject_sha256") == digest(original), "人工答复对应的总结已过期")
        before, after = copy.deepcopy(original), copy.deepcopy(result)
        for item in (before, after):
            item.pop("overall_summary", None)
            item.pop("pending_issues", None)
            for section in item.get("sections", []): section.pop("summary", None)
        require(before == after, "局部修订不得更改要点、引用、覆盖或其他锁定字段", 422)
        required = [a["issue"] for a in responses["answers"] if a["answer"] == "UNKNOWN"]
        require(all(i in result.get("pending_issues", []) for i in required), "尚不确定的事项必须保留待确认", 422)
        require(all(i in original["pending_issues"] for i in result.get("pending_issues", [])), "局部修订不能新增无关待确认事项", 422)
        w["summary_amendment"] = {"baseline_summary": copy.deepcopy(original), "baseline_review": copy.deepcopy(w.get("summary_review")),
                                  "responses": copy.deepcopy(responses), "at": now()}
        self.accept_summary(w, result, author)

    def author(self, workflow_id: str, kind: str, result: dict, operator: str):
        """Operator edits (summary / facts / deck) outside the task queue."""
        require(bool(operator.strip()), "请填写编辑人", 422)
        with self.transaction(workflow_id, kind + "_EDIT") as w:
            who = "operator:" + operator.strip()
            {"SUMMARY": lambda: self.accept_summary(w, result, who), "FACTS": lambda: self.accept_facts(w, result, who),
             "DECK": lambda: self.accept_deck(w, result, who)}[kind]()
            self.cancel_stale(w)
        return self.get(workflow_id)

    # ---- human decisions
    def record_summary_responses(self, workflow_id: str, record: dict):
        """Record version-bound human answers; only reviewed summary edits resolve issues."""
        require(str(record.get("operator", "")).strip(), "请填写操作人姓名", 422)
        with self.transaction(workflow_id, "SUMMARY_PENDING_RESPONSES") as w:
            require(summary_current(w), "总结已过期，请刷新后处理")
            require(record.get("subject_sha256") == digest(w["summary"]), "总结版本已变化，请刷新后重新回答")
            pending = w["summary"]["pending_issues"]
            answers = record.get("answers", [])
            require(pending and len(answers) == len(pending) and {a.get("index") for a in answers} == set(range(len(pending))),
                    "请逐项回答全部待确认事项", 422)
            for answer in answers:
                require(answer.get("answer") in {"AVAILABLE", "UNAVAILABLE", "UNKNOWN"}, "答复选项无效", 422)
                require(answer["answer"] != "AVAILABLE" or str(answer.get("note", "")).strip(), "已有依据时，请填写文件名或依据说明", 422)
            rec = {"subject_sha256": record["subject_sha256"], "operator": record["operator"].strip(),
                   "at": now(), "answers": [{**a, "issue": pending[a["index"]]} for a in answers]}
            previous = w.get("summary_pending_responses")
            if previous and all(previous.get(k) == rec[k] for k in ("subject_sha256", "operator", "answers")):
                rec = previous
            w["summary_pending_responses"] = rec
            self.snapshot(w, "summary_pending_responses", rec)
            self.cancel_stale(w)
            self.enqueue_once(w, "SUMMARY_AMEND")
        return self.get(workflow_id)

    def approval(self, workflow_id: str, kind: str, record: dict):
        require(kind in {"content", "style"}, "确认类型无效", 422)
        require(all(str(record.get(k, "")).strip() for k in ("customer", "operator", "method")), "需记录客户、操作人和确认方式", 422)
        with self.transaction(workflow_id, f"APPROVE_{kind.upper()}") as w:
            self.source_integrity(w)
            if kind == "content":
                require(fully_read(w) and summary_current(w), "请先完成全文阅读和当前版本总结")
                require(not w["summary"]["pending_issues"], "总结中的待解决问题需先处理")
                require(summary_review_current(w), "总结须先经独立审查")
                require(not open_summary_issues(w), "总结审查的阻断问题需先修订总结或由审核人书面裁定")
                notes = ledger.to_acknowledge(w, "summary")
                require(sorted(record.get("acknowledged_issues") or []) == notes,
                        "确认前须逐项查看并确认已知悉尚未闭环的提示：" + "、".join(notes), 422)
                expected = digest(w["summary"])
            else:
                require(render_current(w) and all(reviewed(w, p["id"]) for p in w["render"]["pages"][:SAMPLE_PAGES]), "前5页须完成逐页审核后才能确认风格")
                expected = sample_hash(w)
            require(record.get("subject_sha256") == expected, "确认稿已更新，请刷新后重新核对")
            a = {"id": uid("approval"), "kind": kind, "at": now(), "subject_sha256": expected, "customer": record["customer"],
                 "operator": record["operator"], "method": record["method"], "feedback": str(record.get("feedback", "")),
                 "acknowledged_issues": sorted(record.get("acknowledged_issues") or []),
                 "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            w[kind + "_approval"] = a
            w["approvals"].append(a)
            self.snapshot(w, kind + "_approval", a)
        return self.get(workflow_id)

    def confirm_derivation(self, workflow_id: str, der_id: str, record: dict):
        require(record.get("decision") in {"CONFIRM", "REJECT"} and str(record.get("reviewer", "")).strip(), "需填写审核人和结论", 422)
        with self.transaction(workflow_id, "CONFIRM_DERIVATION") as w:
            require(w["facts"], "尚无事实库")
            d = next((d for d in w["facts"]["result"].get("derivations", []) if d.get("id") == der_id), None)
            require(d, "推导不存在", 404)
            rec = {"decision": record["decision"], "reviewer": record["reviewer"], "at": now(), "note": str(record.get("note", "")),
                   "derivation_sha256": digest({"claim": d.get("claim"), "rule": d.get("rule"), "evidence": d.get("evidence")}),
                   "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            w["confirmations"]["derivations"][der_id] = rec
            self.snapshot(w, "derivation_decision", {"id": der_id, **rec})
        return self.get(workflow_id)

    def resolve_conflict(self, workflow_id: str, record: dict):
        require(str(record.get("reviewer", "")).strip() and record.get("fact_id"), "需填写审核人和采用的事实", 422)
        key = f"{record.get('entity')}|{record.get('attribute')}"
        with self.transaction(workflow_id, "RESOLVE_CONFLICT") as w:
            c = next((c for c in verified(w)["conflicts"] if c["key"] == key), None)
            require(c, "冲突不存在", 404)
            require(any(record["fact_id"] in ids for ids in c["values"].values()), "采用的事实不在该冲突中", 422)
            rec = {"fact_id": record["fact_id"], "reviewer": record["reviewer"], "at": now(), "note": str(record.get("note", "")),
                   "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            w["confirmations"]["resolutions"][key] = rec
            self.snapshot(w, "conflict_resolution", {"key": key, **rec})
        return self.get(workflow_id)

    def confirm_transcription(self, workflow_id: str, unit_id: str, record: dict):
        require(str(record.get("reviewer", "")).strip() and str(record.get("text", "")).strip(), "需填写审核人和对照原件确认后的文字", 422)
        require(record.get("original_checked") is True, "请对照原件核对后再确认", 422)
        with self.transaction(workflow_id, "CONFIRM_TRANSCRIPTION") as w:
            u = next((u for u in [u for s in w["sources"] for u in s["transcriptions"]] + w.get("transcription_proposals", []) if u["id"] == unit_id), None)
            require(u, "转录单元不存在", 404)
            rec = {"decision": "CONFIRM", "text": record["text"], "reviewer": record["reviewer"], "at": now(),
                   "changed": canon(record["text"]) != canon(u["text"]), "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            w["confirmations"]["transcriptions"][unit_id] = rec
            self.snapshot(w, "transcription_confirmation", {"unit_id": unit_id, **rec})
        return self.get(workflow_id)

    def page_image(self, workflow_id: str, source_id: str, page_id: str, dpi: int = 110) -> bytes:
        """The whole PDF page rendered by code, for choosing and checking crop boxes (not stored, not shown on slides)."""
        from factdeck.ingest import render_pdf_page
        w = self.get(workflow_id)
        s = next((s for s in w["sources"] if s["id"] == source_id), None)
        require(s and s["kind"] == "pdf", "只有PDF资料提供整页图", 404)
        require(any(p["id"] == page_id for p in s["pages"]), "页面不存在", 404)
        content = self.path(s["path"]).read_bytes()
        require(sha(content) == s["sha256"], "资料原件缺失或已被修改，请重新导入")
        out = io.BytesIO()
        render_pdf_page(content, int(page_id.rsplit(":p", 1)[1]), dpi).save(out, "PNG")
        return out.getvalue()

    def _figure(self, w: dict, fig_id: str) -> dict:
        g = figures(w).get(fig_id)
        require(g, "图不存在", 404)
        require(sha(self.path(g["path"]).read_bytes()) == g["sha256"], "图文件缺失或已被修改，请重新导入资料")
        return g

    def confirm_figure(self, workflow_id: str, fig_id: str, record: dict):
        """A reviewer compared the figure with the original: nothing cut off, and its patient-information status."""
        require(str(record.get("reviewer", "")).strip(), "请填写审核人", 422)
        require(record.get("crop_complete") is True, "请对照原件确认图完整（图例、坐标轴、脚注、标记均在）；不完整时不要登记", 422)
        require(record.get("deidentified") in DEIDENTIFIED, "去标识结论需为：" + "、".join(DEIDENTIFIED), 422)
        with self.transaction(workflow_id, "CONFIRM_FIGURE") as w:
            g = self._figure(w, fig_id)
            mismatch = crop_mismatch(g)
            require(not mismatch or str(record.get("note", "")).strip(),
                    f"两次独立截取区域不一致（交并比 {(g.get('second_read') or {}).get('iou')}），请对照原页说明现有截取为何完整", 422)
            rec = {"figure_sha256": g["sha256"], "crop_complete": True, "deidentified": record["deidentified"],
                   "reviewer": record["reviewer"], "note": str(record.get("note", ""))[:4000], "at": now(),
                   "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            if mismatch:
                rec["mismatch_checked"] = g["second_read"]["bbox"]
            w["confirmations"].setdefault("figures", {})[fig_id] = rec
            self.snapshot(w, "figure_review", {"figure_id": fig_id, **rec})
        return self.get(workflow_id)

    def license_figure(self, workflow_id: str, fig_id: str, record: dict):
        """The customer's permission to reuse one figure, recorded by an operator."""
        require(all(str(record.get(k, "")).strip() for k in ("customer", "operator", "method")), "需记录客户、操作人和确认方式", 422)
        require(isinstance(record.get("permitted"), bool), "请登记是否许可使用", 422)
        with self.transaction(workflow_id, "LICENSE_FIGURE") as w:
            g = self._figure(w, fig_id)
            rec = {"figure_sha256": g["sha256"], "permitted": record["permitted"], "scope": str(record.get("scope", ""))[:1000],
                   "customer": record["customer"], "operator": record["operator"], "method": record["method"], "at": now(),
                   "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            w["confirmations"].setdefault("figure_licenses", {})[fig_id] = rec
            self.snapshot(w, "figure_licence", {"figure_id": fig_id, **rec})
        return self.get(workflow_id)

    def source_integrity(self, w: dict):
        super().source_integrity(w)
        for g in figures(w).values():
            file = self.path(g["path"])
            require(file.is_file() and sha(file.read_bytes()) == g["sha256"], "图文件缺失或已被修改，请重新导入资料")

    def dismiss_issue(self, workflow_id: str, issue_id: str, record: dict):
        """A person's written ruling on a semantic-ledger issue: unfounded, or a decision (include/exclude, relation)."""
        with self.transaction(workflow_id, "DISMISS_ISSUE") as w:
            require(semantic_current(w), "没有当前的语义审查")
            ledger.rule(w, "semantic", issue_id, record, semantic_input(w))
        return self.get(workflow_id)

    def dismiss_summary_issue(self, workflow_id: str, issue_id: str, record: dict):
        with self.transaction(workflow_id, "DISMISS_SUMMARY_ISSUE") as w:
            require(summary_review_current(w), "没有当前的总结审查")
            ledger.rule(w, "summary", issue_id, record, summary_review_input(w))
        return self.get(workflow_id)

    # ---- render / review / export
    def render(self, workflow_id: str, draft: bool = False):
        """Render with code (no model). A draft may show pending marks and is not reviewable."""
        from factdeck.render import render as do_render
        w = self.get(workflow_id)
        if not draft and w.get("generation_route") == VISUAL_ROUTE:
            return self.start_generation(workflow_id)
        require(deck_current(w), "请先完成当前版本的页面规格")
        v = verified(w)
        chk = checked(w, v)
        require(not chk["errors"], "页面规格有错误，请先修订")
        if not draft:
            st, todo = status(w)
            require(st not in {"CONFIRMATIONS_REQUIRED", "SEMANTIC_REVIEW_REQUIRED", "SEMANTIC_ISSUES"}, "正式渲染前需完成：" + "；".join(todo))
        key = render_input(w, v)
        relative = f"{workflow_id}/renders/{'draft-' if draft else ''}{key[:24]}"
        folder = self.path(relative)
        if folder.exists():
            shutil.rmtree(folder)
        sources = {s["id"]: {"title": s["title"], "filename": s["filename"]} for s in w["sources"]}
        shown = {v["facts"][f]["figure"] for p in chk["pages"] for f in p["facts"] if v["facts"][f].get("figure")}
        figs = {k: {"path": str(self.path(g["path"])), "sha256": g["sha256"], "width": g["width"], "height": g["height"]}
                for k, g in figures(w).items() if k in shown}
        try:
            report = do_render(selected_spec(w["deck"]["result"]), v["facts"], sources, folder, self.render_theme(w), v["terms"], figures=figs)
        except ImportError as e:
            raise WorkflowError(f"渲染环境缺失：{e}；请安装 factdeck/requirements.txt 并执行 playwright install chromium", 503)
        # per page for the reviewer: the page's own design note, its visual signals (open or justified) and what the
        # semantic reviewer must look at (emphasis inside quotes, excerpts that leave text out, sentences split into steps)
        rpages = [{"id": p["id"], "file": f"slide{i:02d}.png", "sha256": sha((folder / f"slide{i:02d}.png").read_bytes()),
                   "design": sl.get("design") or {}, "signals": sl.get("signals") or [], "review": sl.get("review") or [],
                   "occupancy": sl.get("occupancy"), "hole": (sl.get("hole") or {}).get("share"), "metrics": sl.get("metrics") or {}}
                  for i, (p, sl) in enumerate(zip(selected_spec(w["deck"]["result"])["pages"], report["slides"]), 1)]
        record = {"input_sha256": key, "draft": draft, "path": relative, "at": now(), "hard_errors": report["hard_errors"],
                  "summary": report["summary"], "pages": rpages,
                  "files": {n: sha((folder / n).read_bytes()) for n in ("deck.pptx", "deck.pdf", "deck.html", "render_report.json")},
                  "figure_files": sorted(x.name for x in folder.glob("figure_*.png")),
                  "logo_file": next((x.name for x in folder.glob("logo.*")), None), "font": report.get("font"),
                  "warnings": {"figure_low_dpi": [x for sl in report["slides"] for x in sl.get("figure_low_dpi", [])],
                               "render": report.get("warnings", []),
                               "deck": checked(w, v)["warnings"]}}
        record['scope']=chk.get('scope');record['complete_deck']=not bool(chk.get('scope'))
        with self.transaction(workflow_id, "RENDER_DRAFT" if draft else "RENDER") as w2:
            require(render_input(w2) == key, "渲染期间内容已变更，请重新渲染")
            if draft:
                w2["draft_render"] = record
            else:
                w2["render"] = record
        return self.get(workflow_id)

    def review(self, workflow_id: str, page_id: str, record: dict):
        require(str(record.get("reviewer", "")).strip(), "请填写审核人", 422)
        require(record.get("visual_status") in {"PASS", "REVISE"} and record.get("content_status") in {"PASS", "REVISE"}, "请分别记录版面和内容审核结论", 422)
        require(record.get("sources_checked") is True, "请对照页面备注中的来源位置核对内容", 422)
        rubric = record.get("rubric") or {}
        require(isinstance(rubric, dict) and set(rubric) <= set(RUBRIC) and all(v in {"PASS", "REVISE"} for v in rubric.values()),
                "版面评分项须为 " + "、".join(RUBRIC) + "，取值 PASS / REVISE", 422)
        require(not (record["visual_status"] == "PASS" and "REVISE" in rubric.values()), "有评分项需修改时，版面结论不能为通过", 422)
        with self.transaction(workflow_id, "PAGE_REVIEW") as w:
            require(render_current(w), "没有当前的正式渲染")
            p = next((p for p in w["render"]["pages"] if p["id"] == page_id), None)
            require(p, "页面不存在", 404)
            require(record.get("png_sha256") == p["sha256"], "页面已重新渲染，请刷新后审核")
            require(sha(self.path(w["render"]["path"] + "/" + p["file"]).read_bytes()) == p["sha256"], "页面图片已被修改")
            rec = {"reviewer": record["reviewer"], "at": now(), "png_sha256": p["sha256"], "visual_status": record["visual_status"],
                   "content_status": record["content_status"], "sources_checked": True, "feedback": str(record.get("feedback", "")),
                   "rubric": rubric,
                   "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            w["page_reviews"][page_id] = rec
            self.snapshot(w, "page_review", {"page_id": page_id, **rec})
        return self.get(workflow_id)

    def facts_report(self, workflow_id: str) -> str:
        w = self.get(workflow_id)
        require(w["facts"], "尚无事实库")
        F, D, C = verified(w)["objects"]
        return fx.report(F, D, C, [{"id": s["id"], "title": s["filename"]} for s in w["sources"]])

    def export(self, workflow_id: str):
        with self.transaction(workflow_id, "EXPORT") as w:
            self.source_integrity(w)
            require(not scope_of((w.get('deck') or {}).get('result', {})), '当前为前N页生成结果，不能记录为整套交付')
            require(stage(w) in {"READY_TO_EXPORT", "DELIVERED"}, "全部页面渲染、逐页审核和两次确认完成后才能交付")
            r = w["render"]
            src = self.path(r["path"])
            for name, digest_ in r["files"].items():
                require(sha((src / name).read_bytes()) == digest_, f"渲染文件 {name} 已被修改")
            for p in r["pages"]:
                require(sha((src / p["file"]).read_bytes()) == p["sha256"], "页面图片已被修改")
            if r.get("route") == VISUAL_ROUTE:
                for p in w["generation"]["pages"]:
                    for asset in p["assets"].values():
                        require(sha(self.path(asset["path"]).read_bytes()) == asset["sha256"], "视觉资产已被修改")
                        require(self.path(asset["receipt_path"]).is_file(), "视觉回执缺失")
            version = len(w["deliveries"]) + 1
            relative = f"{workflow_id}/deliveries/v{version:03d}"
            folder = self.path(relative)
            folder.mkdir(parents=True, exist_ok=True)
            v = verified(w)
            F, D, C = v["objects"]
            (folder / "facts_report.md").write_text(fx.report(F, D, C, [{"id": s["id"], "title": s["filename"]} for s in w["sources"]]), encoding="utf-8")
            report = {"schema_version": "factdeck.delivery.v1", "template": TEMPLATE, "engine": ENGINE_VERSION, "project": w["title"], "at": now(),
                      "version": version, "requirements": w["requirements"], "page_count": len(r["pages"]),
                      "source_inventory": [{k: s[k] for k in ("id", "filename", "sha256")} for s in w["sources"]],
                      "content_approval": w["content_approval"], "style_approval": w["style_approval"],
                      "facts": {"author": w["facts"]["author"], "result_sha256": w["facts"]["result_sha256"],
                                "used": sorted({fid for p in checked(w, v)["pages"] for fid in p["facts"] + p["edge_facts"]})},
                      "confirmations": w["confirmations"], "deck": {"author": w["deck"]["author"], "result_sha256": w["deck"]["result_sha256"],
                                                                    "coverage": w["deck"]["coverage"], "warnings": w["deck"]["warnings"]},
                      "semantic_review": w["semantic_review"], "semantic_checks": {c: {k: x.get(k) for k in ("reviewer", "at", "round", "counts", "unchecked", "regression", "viewed_source_pages")}
                                                                                 for c, x in (w.get("semantic_checks") or {}).items()},
                      "issue_ledger": w.get("issue_ledger"), "render": {k: r[k] for k in ("input_sha256", "summary", "files", "at")},
                      "pages": [{"id": p["id"], "png_sha256": p["sha256"], "review": w["page_reviews"][p["id"]]} for p in r["pages"]],
                      "figures": figure_inventory(w, v),
                      "visual_generation": r.get("visual_provenance"), "office": r.get("office"),
                      "appearance": {"theme": w["theme"], "font": r.get("font"),
                                     "brand": {k: w["brand"][k] for k in ("filename", "sha256", "tokens", "template_colors", "contrast")}
                                     if w["theme"] == "brand" else None},
                      "verification_limits": "页面上的实质内容均为来源逐字节选并经程序核对；节选语境由独立语义审查和人工逐页审核把关。"
                                             "审核与确认为本地记录，不是在线身份认证。"}
            (folder / "verification_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            shutil.copyfile(src / "deck.pptx", folder / "deck.pptx")
            shutil.copyfile(src / "deck.pdf", folder / "deck.pdf")
            with zipfile.ZipFile(folder / "delivery.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for n in ("deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json"):
                    z.write(folder / n, n)
                for i, p in enumerate(r["pages"], 1):
                    z.write(src / p["file"], f"pages/slide-{i:03d}.png")
                if r.get("route") == VISUAL_ROUTE:
                    z.writestr("visual/manifest.json", json.dumps(w["generation"], ensure_ascii=False, indent=2))
                    for i, p in enumerate(w["generation"]["pages"], 1):
                        for kind, asset in p["assets"].items():
                            z.write(self.path(asset["path"]), f"visual/page-{i:03d}/{kind}{Path(asset['path']).suffix}")
                            z.write(self.path(asset["receipt_path"]), f"visual/page-{i:03d}/{kind}-receipt.json")
            files = ("deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json", "delivery.zip")
            w["deliveries"].append({"version": version, "at": now(), "subject_sha256": delivery_subject(w), "path": relative,
                                    "files": [{"name": n, "sha256": sha((folder / n).read_bytes())} for n in files]})
        return self.get(workflow_id)
