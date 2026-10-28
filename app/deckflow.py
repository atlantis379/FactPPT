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

from app.fact57098 import Store as _BaseStore, WorkflowError, digest, sha, now, uid, require, parse_outline, ROOT, LEASE_SECONDS
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
from app import structure_stage
from app import semantic_map_stage

TEMPLATE = "factdeck.v1"
ENGINE_VERSION = "factdeck-render.1"
TEMPLATE_ROUTE = "TEMPLATE_LIB"      # mainline since 2026-10-25: fixed template library, code-rendered native PPTX
MAX_UPLOAD = 40 * 1024 * 1024
SAMPLE_PAGES = 5
DEIDENTIFIED = ("NO_PATIENT_CONTENT", "DEIDENTIFIED", "IDENTIFIABLE")
# Content-rule version. A project keeps the version it started with; when the rules change mid-project, new content
# tasks wait until someone adopts the new version explicitly (recorded), so rules never change under a running review.
CONTENT_RULES_VERSION = "content-rules.2026-10-16"   # SUMMARY model_understanding.v4 + source_coverage.v2
KINDS = ("READ_SOURCE", "SECOND_READ", "SEMANTIC_MAP", "TOPIC_PASS", "CLAIMS", "STRUCTURE", "STRUCTURE_REVIEW", "SUMMARY", "SUMMARY_AMEND", "SUMMARY_REVIEW", "FACTS", "DECK", "SEMANTIC_REVIEW", "VISUAL_CRITIQUE") + VISUAL_KINDS
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
# A finished task's brief and draft move to a snapshot file (see Store.archive_tasks); these small fields stay for screens.
ARCHIVED_TASK_STATUSES = {"COMPLETE", "CANCELLED"}
CHAPTER_KINDS = ("SUMMARY", "SUMMARY_REVIEW")      # bound to a chapter id when the project is split into chapters
ARCHIVE_MIN_BYTES = 4096
BRIEF_KEPT_ON_ARCHIVE = ("kind", "regression", "summary_algorithm", "chapter")
DRAFT_KEPT_ON_ARCHIVE = ("done_chunks", "saved_at", "workers", "path")


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
# Every candidate relation on a chapter's pages is adopted or declined with one of these reasons.
CANDIDATE_REJECT_REASONS = {"not_between_points": "不是要点之间的关系（版面排列、编号或引用顺序）",
                            "outside_section": "涉及的内容不属于本章要点", "duplicate": "与本章已采纳的关系重复",
                            "unsupported_points": "所涉要点无资料支撑或未纳入本章",
                            "within_one_point": "关系两端在同一条要点内（要点正文已表达，不另列关系）"}


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
    elif "parallel" in m["core"]:
        cores = [names.get(p, p) for p, v in m["roles"].items() if v == "core"]
        out = ["", f"**核心**：并列要点，无单一核心句（{m['core']['parallel']}）：" + "；".join(cores)]
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
    if w.get("structure_first") and structure_stage.structure_current(w):
        return structure_stage.story(w)
    out = []
    summary = w.get("summary") or {}
    mapped = {sid for m in summary.get("outline_coverage") or [] for sid in m.get("section_ids") or []}
    for s in summary.get("sections") or []:
        if s.get("outline_id") or s.get("id") in mapped:
            m = s.get("message")
            text = (f"「{m['core']['quote']}」" if m["core"].get("claim_id") else
                    f"（并列要点：{m['core']['parallel']}）" if "parallel" in m["core"] else
                    f"（无核心句：{m['core'].get('none', '')}）") if m else "（无资料支撑）"
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
            **{x: k[x] for x in ("scope", "qualifiers", "numbers", "cites", "semantic_node_id") if k.get(x)},
            **({"source_kind": k["source_kind"]} if k.get("source_kind") else {})}


def input_hash(w: dict, structure: bool = True) -> str:
    base = {"sources": [{"sha256": s["sha256"], "readings": [p["reading"] for p in s["pages"]],
                         "transcriptions": [{k: u[k] for k in ("id", "location", "text")} for u in s["transcriptions"]],
                         "claims": (s.get("claims") or {}).get("result_sha256")}
                        for s in w["sources"]],
            "outline": w["outline"], "context": w["context"]}
    if structure and w.get("structure_first"):           # the summary is written inside the confirmed structure
        base["structure"] = digest(w["structure"]["result"]) if w.get("structure") else None
    return digest(base)


def summary_current(w: dict) -> bool:
    return bool(w["summary"]) and w["summary"]["input_sha256"] == input_hash(w)


def summary_review_input(w: dict) -> str:
    return digest({"summary": digest(w["summary"]), "input": input_hash(w), "contract": SUMMARY_REVIEW_SCHEMA})


def summary_review_current(w: dict) -> bool:
    r = w.get("summary_review")
    return summary_current(w) and bool(r) and r.get("schema_version") == SUMMARY_REVIEW_SCHEMA and r["input_sha256"] == summary_review_input(w)


# ---- chapters: the summary is written and reviewed one chapter at a time (each task loads only its chapter)
CHAPTER_ID = re.compile(r"^[A-Za-z0-9_]{1,24}$")
CHAPTER_STATE_NAMES = {"WRITE": "待撰写", "STALE": "资料或提纲已变更，须重写", "REVIEW": "待独立审查",
                       "ISSUES": "审查问题待修订或裁定", "DONE": "已审查"}


def chapters(w: dict) -> list[dict]:
    """The project's chapter plan ([] = the whole project is one summary task, as before)."""
    return w.get("chapters") or []


def chapter_problem(w: dict, plan: list | None = None) -> str:
    """Why a chapter plan does not fit the current sources and outline ('' when it does)."""
    plan = chapters(w) if plan is None else plan
    if not plan:
        return ""
    if w.get("structure_first"):
        return "分章撰写不能与“先定整体结构”同时使用"
    ids = [c.get("id") for c in plan]
    if not all(isinstance(i, str) and CHAPTER_ID.match(i) for i in ids) or len(ids) != len(set(ids)):
        return "章节编号须为1–24位字母、数字或下划线，且不重复"
    if not all(str(c.get("title", "")).strip() for c in plan):
        return "每章须有标题"
    src = [x for c in plan for x in c.get("source_ids") or []]
    if not all(c.get("source_ids") for c in plan) or len(src) != len(set(src)) or set(src) != {s["id"] for s in w["sources"]}:
        return "每份资料须恰好属于一章，每章至少一份资料（资料增减后须重新分章）"
    out = [x for c in plan for x in c.get("outline_ids") or []]
    if len(out) != len(set(out)) or set(out) != {o["id"] for o in w["outline"]}:
        return "每个提纲条目须恰好属于一章（提纲修改后须重新分章）"
    return ""


def chapter_of(w: dict, cid: str) -> dict:
    c = next((c for c in chapters(w) if c["id"] == cid), None)
    require(c, f"章节不存在：{cid}", 404)
    return c


def chapter_view(w: dict, c: dict, part: dict | None = None, meta: dict | None = None) -> dict:
    """The project as one chapter's task sees it: its sources and outline items, its summary part. Shares the issue
    ledger and confirmations with the project, so review rounds and rulings land in the project's ledger."""
    ledger.book(w, "summary")
    own = set(c["source_ids"])
    v = dict(w)
    v.update(chapter={"id": c["id"], "title": c["title"]}, sources=[s for s in w["sources"] if s["id"] in own],
             outline=[o for o in w["outline"] if o["id"] in set(c.get("outline_ids") or [])],
             transcription_proposals=[x for x in w.get("transcription_proposals", []) if x["source_id"] in own],
             summary=part, summary_meta=meta, summary_review=None, content_approval=None, summary_fact_candidates=None)
    return v


def reference_units(w: dict) -> set[str]:
    """Units on pages the reader classified REFERENCE that carry no claim: registered by code (source_coverage)."""
    kind = {p["id"]: (p.get("reading") or {}).get("classification") for s in w["sources"] for p in s["pages"]}
    claimed = {sp["unit_id"] for k in all_claims(w).values() for sp in k["spans"]}
    return {u["id"] for u in all_units(w) if kind.get(u["page_id"]) == "REFERENCE" and u["id"] not in claimed}


def summary_check(w: dict) -> str:
    """The ledger check a summary review round answers: the whole summary, or one chapter of it."""
    return f"SUMMARY:{w['chapter']['id']}" if w.get("chapter") else "SUMMARY"


def chapter_input(w: dict, c: dict) -> str:
    return input_hash(chapter_view(w, c))


def chapter_record(w: dict, cid: str) -> dict | None:
    return (w.get("summary_chapters") or {}).get(cid)


def chapter_current(w: dict, c: dict) -> bool:
    r = chapter_record(w, c["id"])
    return bool(r) and r["input_sha256"] == chapter_input(w, c)


def chapter_review_input(w: dict, c: dict) -> str:
    """Equals summary_review_input of the chapter view (its summary is the part whose digest is recorded)."""
    return digest({"summary": chapter_record(w, c["id"])["sha256"], "input": chapter_input(w, c), "contract": SUMMARY_REVIEW_SCHEMA})


def chapter_review_current(w: dict, c: dict) -> bool:
    r = chapter_record(w, c["id"])
    return chapter_current(w, c) and bool(r.get("review")) and r["review"]["input_sha256"] == chapter_review_input(w, c)


def chapter_open_issues(w: dict, c: dict) -> list[dict]:
    return [i for i in ledger.unresolved(w, "summary", f"SUMMARY:{c['id']}") if i["severity"] == "BLOCKER"]


def chapter_status(w: dict) -> list[dict]:
    out = []
    for n, c in enumerate(chapters(w), 1):
        if not chapter_current(w, c):
            state = "STALE" if chapter_record(w, c["id"]) else "WRITE"
        elif not chapter_review_current(w, c):
            state = "REVIEW"
        elif chapter_open_issues(w, c):
            state = "ISSUES"
        else:
            state = "DONE"
        out.append({"id": c["id"], "title": c["title"], "number": n, "state": state, "blocking": len(chapter_open_issues(w, c))})
    return out


def merge_chapter_summaries(w: dict, parts: list[dict]) -> dict:
    """One summary of the whole project from its chapters' parts, in chapter order. Lists are concatenated; indices
    into pending_issues are shifted by the issues of earlier chapters. Code assembles, it does not rewrite."""
    algos = {p.get("summary_algorithm") for p in parts}
    require(len(algos) == 1, "各章总结须使用同一算法版本才能合并", 422)
    out = {"schema_version": "full_source_summary.v3", "input_sha256": input_hash(w),
           "overall_summary": "\n\n".join(f"【{c['title']}】{p['overall_summary']}" for c, p in zip(chapters(w), parts)),
           "sections": [], "outline_coverage": [], "pending_issues": []}
    algo = algos.pop()
    if algo:
        out["summary_algorithm"] = algo
    understanding, index, coverage = None, None, None
    for p in parts:
        shift = len(out["pending_issues"])
        p = copy.deepcopy(p)
        for row in (p.get("evidence_index") or {}).get("points") or []:
            for e in row.get("evidence") or []:
                if isinstance(e.get("pending_issue_index"), int):
                    e["pending_issue_index"] += shift
        for row in (p.get("source_coverage") or {}).get("units") or []:
            for x in row.get("parts") or []:
                if isinstance(x.get("pending_issue_index"), int):
                    x["pending_issue_index"] += shift
        out["sections"] += p["sections"]
        out["outline_coverage"] += p.get("outline_coverage") or []
        out["pending_issues"] += p["pending_issues"]
        if p.get("source_understanding"):
            understanding = understanding or {**{k: v for k, v in p["source_understanding"].items() if k != "sections"}, "sections": []}
            understanding["sections"] += p["source_understanding"]["sections"]
        if p.get("evidence_index"):
            index = index or {"schema_version": p["evidence_index"]["schema_version"], "points": [], "page_decisions": []}
            index["points"] += p["evidence_index"]["points"]
            index["page_decisions"] += p["evidence_index"]["page_decisions"]
        if p.get("source_coverage"):
            led = p["source_coverage"]
            coverage = coverage or {**{k: v for k, v in led.items() if k not in ("units", "conclusions", "source_units_sha256")}, "units": []}
            require(coverage.get("segmenter") == led.get("segmenter") and coverage["schema_version"] == led["schema_version"],
                    "各章逐句登记须使用同一版本与切句器才能合并", 422)
            coverage["units"] += led["units"]
            if "conclusions" in led:                          # facet ledgers of earlier schemas
                coverage.setdefault("conclusions", []).extend(led["conclusions"])
    if understanding:
        out["source_understanding"] = understanding
    if index:
        out["evidence_index"] = index
    if coverage:
        from factdeck.source_coverage import source_hash
        coverage["source_units_sha256"] = source_hash(all_units(w))
        out["source_coverage"] = coverage
    return out


SECTION_REF = re.compile(r"^(s\d+)((?:\.k\d+)|(?:/c\d+))?$")


def _prefix_section_ids(x, cid: str):
    """The contract template's section-based ids (s1, s1.k1, s1/c1) renamed to the chapter's (cid-s1 …)."""
    def name(v):
        m = SECTION_REF.match(v) if isinstance(v, str) else None
        return f"{cid}-{m.group(1)}{m.group(2) or ''}" if m else v
    if isinstance(x, dict):
        return {name(k): _prefix_section_ids(v, cid) for k, v in x.items()}
    if isinstance(x, list):
        return [_prefix_section_ids(v, cid) for v in x]
    return name(x)


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


def summary_key_points(w: dict) -> dict[str, str] | None:
    """Key point id -> full point text, for a complete-notes (model_understanding.v4) summary; None otherwise."""
    s = w.get("summary") or {}
    if s.get("summary_algorithm") not in ("model_understanding.v4", semantic_map_stage.SUMMARY_ALGORITHM):
        return None
    return {f"{sec['id']}.k{i}": k.get("point", "") for sec in s["sections"] for i, k in enumerate(sec.get("key_points") or [], 1)}


def summary_point_roles(w: dict) -> dict[str, str] | None:
    """Key point id -> role (core / support / limit) from each section's message, for a v4 summary; None otherwise."""
    if summary_key_points(w) is None:
        return None
    return {k: r for sec in w["summary"]["sections"] for k, r in ((sec.get("message") or {}).get("roles") or {}).items()}


def deck_teaching_notes(w: dict, spec: dict) -> dict[str, str] | None:
    from factdeck.deck import teaching_notes
    kp = summary_key_points(w)
    return teaching_notes(spec.get("pages") or [], kp, summary_point_roles(w)) if kp is not None else None


def checked(w: dict, v: dict | None = None) -> dict:
    v = v or verified(w)
    return check_spec(w["deck"]["result"], v["facts"], v["terms"], w["outline"], w["summary"]["sections"], w["requirements"], w.get("outline_parts"),
                      key_points=summary_key_points(w), key_roles=summary_point_roles(w))


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
    from factdeck.template_lib.render_deck import VERSION as TEMPLATE_ENGINE, is_template_deck
    engine = TEMPLATE_ENGINE if is_template_deck(w["deck"]["result"]) else ENGINE_VERSION
    payload = {"engine": engine, "deck": w["deck"]["result"], "theme": w["theme"],
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


LEGACY_LAYOUT_RULES = ("先按内容的结构选版式", "每页要有一个结构化主体", "一页一个设计方案", "flow：", "原件图用 figure", "hero：",
                       "chart：", "强调：", "表格每格是引用列表")
TEMPLATE_DECK_RULES = [
    "本项目走模板库主线：每页写成 {\"id\", \"layout\": \"template\", \"title\": 引用, \"template\": {\"layout\": 版式编号, \"fill\": 填充}} "
    "（封面、章节页另写 template.kind 为 \"cover\" / \"section\"，版式编号同为 cover / section）。不写 composed / free / bullets 等旧版式；"
    "旧版式的构图规则不适用。版式编号与槽位见 template_library。",
    "选版式按内容的逻辑关系与数据形状（template_library 中每个版式的 relation_zh）：条件/阈值判断用 algorithm_tree，多行效应量用 forest_plot，"
    "两组终点用 endpoint_readout，步骤用 flow，时间先后用 timeline，A vs B 对照用 comparison，多行多列用 data_table_highlight，并列要点才用 key_points。"
    "程序的选版式器最终决定：写的版式数据不够时会降级（downgrades_to）；没有可用填充的页面被拒。拿不准时可在 template.fills 里为降级目标再写一份填充。"
    "相邻内容页尽量不同版式；内容支持时图表页（is_chart）不少于三分之一。",
    "slots 的写法：\"*≤16\" 表示必填、至多 16 字，\"≤16\" 为选填；\"name[≤4]\" 是至多 4 项的列表，值为每项的槽位；\"object\" 为对象（如 axis 刻度）；空串表示没有字数限制，多为图上画的数值（直接写数字）。"
    "填充按版式的 slots 写：每个显示文字是 {\"fact\": id} 或 {\"text\": 作者标签}（作者标签只组织和命名，不带数字、药名、比较）；"
    "不得写原样字符串。title 由页面 title 填入，填充中不写。图上画的数值（柱高、点估计、CI 上下限、周数、年份）直接写数字，"
    "但每个数字都必须出现在本填充显示的某条事实中（同一行/系列的事实最好），否则本页被拒——不得为了凑版式编数据，数据不够就换版式或拆页。",
    "page、figure、data_note、source、refs、quote、loc 由程序根据所用事实写入（页脚来源、证据号、逐字摘录），填充中不要写；一页的事实至多来自 4 份资料。"
    "槽位有字数上限（max_chars），事实显示文字超过上限时用 display 节选或切出更短的事实，或换容量更大的版式；程序不会截断事实。",
]


def template_deck_brief(b: dict) -> None:
    """DECK brief for the template-library route: the template library, template rules, template example pages."""
    from factdeck.template_lib.integrate import template_library_brief
    b["template_library"] = template_library_brief()
    b["layouts"] = {k: x for k, x in b["layouts"].items() if k == "template"}
    b.pop("recipes", None)
    b.pop("relation_layouts", None)
    b["rules"] = TEMPLATE_DECK_RULES + [r for r in b["rules"] if not r.startswith(LEGACY_LAYOUT_RULES)]
    rc = b["result_contract"]
    rc["pages"] = [{"id": "cover", "layout": "template", "title": {"text": ""}, "outline_ids": [], "section_ids": [],
                    "template": {"kind": "cover", "layout": "cover", "fill": {"subtitle": {"text": ""}}}},
                   {"id": "p1", "layout": "template", "title": {"fact": ""}, "outline_ids": [], "point_ids": [], "section_ids": [],
                    "focus": {"fact": ""}, "template": {"layout": "key_points", "fill": {"items": [{"heading": {"fact": ""}, "body": {"fact": ""}}]}}}]


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


def summary_status(w: dict) -> tuple[str, list[str]] | None:
    """Claims → structure → summary → review → customer confirmation; None once the content is confirmed."""
    if not fully_claimed(w): return "CLAIMS_REQUIRED", ["资料的论断清单尚未全部完成"]
    gate = structure_stage.gate(w)
    if gate: return gate
    if chapters(w) and not content_approved(w):
        if chapter_problem(w): return "CHAPTERS_INVALID", [chapter_problem(w)]
        rows = chapter_status(w)
        todo = [r for r in rows if r["state"] != "DONE"]
        if todo:
            stage_ = ("SUMMARY_REQUIRED" if any(r["state"] in {"WRITE", "STALE"} for r in todo) else
                      "SUMMARY_REVIEW_REQUIRED" if any(r["state"] == "REVIEW" for r in todo) else "SUMMARY_ISSUES")
            return stage_, [f"第{r['number']}章 {r['title']}：{CHAPTER_STATE_NAMES[r['state']]}"
                            + (f"（{r['blocking']}个阻断问题）" if r["blocking"] else "") for r in todo]
    if not summary_current(w): return "SUMMARY_REQUIRED", ["需要当前版本的全文总结"]
    if not content_approved(w):
        if any(t["kind"] == "SUMMARY_AMEND" and t["status"] in {"PENDING", "RUNNING"} for t in w["tasks"]):
            return "SUMMARY_AMEND_RUNNING", ["答复已保存，执行端正在处理对应的来源与需求记录"]
        if not summary_review_current(w): return "SUMMARY_REVIEW_REQUIRED", ["总结需要独立审查"]
        if open_summary_issues(w): return "SUMMARY_ISSUES", [blocker_text("总结审查", open_summary_issues(w))]
        return "CONTENT_CONFIRMATION", ["客户尚未确认全文总结"]
    return None


def status(w: dict) -> tuple[str, list[str]]:
    """(stage, open items) — the first unmet gate and everything still open."""
    if not fully_read(w): return "READING_REQUIRED", ["资料尚未全部阅读"]
    gate = semantic_map_stage.gate(w) if semantic_map_stage.enabled(w) else summary_status(w)
    if gate: return gate
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

    # ---- task archive: a finished task's brief and draft live in a snapshot file, not in the project state
    def before_commit(self, state: dict) -> None:
        self.archive_tasks(state)

    def archive_tasks(self, w: dict) -> int:
        """Move the bulky brief and draft of finished tasks into an immutable snapshot; the task keeps the small fields
        screens show and the snapshot path. Every write and read of a project then handles only live work."""
        moved = 0
        for t in w["tasks"]:
            if t["status"] not in ARCHIVED_TASK_STATUSES or t.get("archive"):
                continue
            heavy = {k: t[k] for k in ("brief", "draft") if t.get(k)}
            size = len(json.dumps(heavy, ensure_ascii=False))
            if size < ARCHIVE_MIN_BYTES:
                continue
            t["archive"] = {"path": self.snapshot(w, "task_archive", heavy), "sha256": digest(heavy), "bytes": size, "at": now()}
            t["brief"] = {k: v for k, v in (t.get("brief") or {}).items() if k in BRIEF_KEPT_ON_ARCHIVE}
            if t.get("draft"):
                t["draft"] = {k: v for k, v in t["draft"].items() if k in DRAFT_KEPT_ON_ARCHIVE}
            moved += 1
        return moved

    def archived_task(self, w: dict, t: dict) -> dict:
        """A finished task with its archived brief and draft restored (read from the snapshot, checked by hash)."""
        if not t.get("archive"):
            return t
        heavy = json.loads(self.path(t["archive"]["path"]).read_text(encoding="utf-8"))["value"]
        require(digest(heavy) == t["archive"]["sha256"], "任务归档文件校验失败")
        return {**t, **heavy}

    # ---- chapters
    def set_chapters(self, workflow_id: str, plan, operator: str, reason: str):
        """Split the summary into chapters (or back to one), explicitly and on record. A summary written under the
        previous plan is kept as a snapshot and set aside; its unresolved review issues are closed by this decision."""
        require(bool(str(operator).strip()) and len(str(reason).strip()) >= 4, "分章须写明操作人和原因", 422)
        with self.transaction(workflow_id, "SET_CHAPTERS") as w:
            if plan == "by_source":
                plan = self._chapters_by_source(w)
            require(isinstance(plan, list) and all(isinstance(c, dict) for c in plan), "分章需为章节列表或 by_source", 422)
            plan = [{"id": str(c.get("id", "")).strip(), "title": str(c.get("title", "")).strip(),
                     "source_ids": list(c.get("source_ids") or []), "outline_ids": list(c.get("outline_ids") or [])} for c in plan]
            problem = chapter_problem(w, plan)
            require(not problem, problem, 422)
            require(plan != chapters(w), "分章与当前相同", 409)
            ruled = []
            for i in ledger.unresolved(w, "summary"):
                ledger.rule(w, "summary", i["id"], {"reviewer": "operator:" + str(operator).strip(),
                                                    "reason": f"总结按新的分章重写，原总结作废：{str(reason).strip()}"}, None)
                ruled.append(i["id"])
            w.setdefault("chapters_history", []).append({
                "from": chapters(w), "to": plan, "operator": str(operator).strip(), "reason": str(reason).strip(), "at": now(),
                "set_aside_summary": self.snapshot(w, "set_aside_summary", w["summary"]) if w.get("summary") else None,
                "set_aside_chapters": copy.deepcopy(w.get("summary_chapters") or {}),
                "had_content_approval": bool(w.get("content_approval")), "ruled_issues": ruled})
            w.update(chapters=plan, summary_chapters={}, summary=None, summary_meta=None, summary_review=None,
                     summary_fact_candidates=None, content_approval=None)
            self.cancel_stale(w)
        return self.get(workflow_id)

    @staticmethod
    def _chapters_by_source(w: dict) -> list[dict]:
        """One chapter per source in import order; outline items pair with sources in order (or there is no outline)."""
        src, outline = w["sources"], w["outline"]
        require(src, "请先导入资料", 422)
        require(not outline or len(outline) == len(src), "提纲条目数与资料数不同，不能按资料自动分章；请逐章给出 source_ids 与 outline_ids", 422)
        return [{"id": f"ch{n}", "title": outline[n - 1]["text"] if outline else s["filename"], "source_ids": [s["id"]],
                 "outline_ids": [outline[n - 1]["id"]] if outline else []} for n, s in enumerate(src, 1)]

    def next_chapters(self, w: dict, kind: str, named=None) -> list[str]:
        """Chapters to queue: the named ones, else the first chapter that needs this step (one chapter at a time)."""
        problem = chapter_problem(w)
        require(not problem, problem, 409)
        if named:
            plan = [chapter_of(w, x) for x in named]
            for c in plan:
                if kind == "SUMMARY":
                    require(fully_claimed(chapter_view(w, c)), f"{c['title']}：请先完成本章资料的阅读和论断清单")
                else:
                    require(chapter_current(w, c), f"{c['title']}：请先完成本章当前版本的总结")
            return [c["id"] for c in plan]
        for c in chapters(w):
            if kind == "SUMMARY":
                if not fully_claimed(chapter_view(w, c)):
                    continue
                revise = chapter_review_current(w, c) and any(i["status"] == "OPEN" for i in chapter_open_issues(w, c))
                if not chapter_current(w, c) or revise:
                    return [c["id"]]
            elif chapter_current(w, c) and not chapter_review_current(w, c):
                return [c["id"]]
        require(False, "没有需要撰写或修订的章节（或其资料尚未完成论断清单）" if kind == "SUMMARY" else "没有待审查的章节")

    def chapter_part(self, w: dict, cid: str) -> dict:
        r = chapter_record(w, cid)
        part = json.loads(self.path(r["path"]).read_text(encoding="utf-8"))["value"]
        require(digest(part) == r["sha256"], "分章总结文件校验失败")
        return part

    def chapter_view_of(self, w: dict, cid: str) -> dict:
        """A chapter's view with its last accepted part (read from its snapshot) as the summary."""
        r = chapter_record(w, cid)
        v = chapter_view(w, chapter_of(w, cid), self.chapter_part(w, cid) if r else None,
                         {k: r[k] for k in ("author", "contributors", "at")} if r else None)
        v["chapter"]["coverage_memory"] = ((r or {}).get("review") or {}).get("coverage_memory") or (r or {}).get("coverage_memory")
        return v

    def coverage_targets(self, w: dict) -> tuple[list[dict], dict]:
        """Coverage targets of the current summary and those an earlier independent review passed with the same
        fingerprint (source text, registration, full point text): {target_id: earlier row}. Those are not judged again."""
        from factdeck import source_coverage as sc
        targets = sc.review_targets(w["summary"], all_units(w))
        path = (w.get("chapter") or {}).get("coverage_memory") if w.get("chapter") else (w.get("summary_review") or {}).get("coverage_memory")
        if not path:
            return targets, {}
        memory = json.loads(self.path(path).read_text(encoding="utf-8"))["value"]
        points = sc.point_texts(w["summary"])
        carried = {}
        for t in targets:
            row = memory.get(sc.target_fingerprint(t, points))
            if row:
                carried[t["target_id"]] = row
        return targets, carried

    def chapter_brief(self, w: dict, kind: str, cid: str) -> dict:
        c = chapter_of(w, cid)
        n = next(i for i, x in enumerate(chapters(w), 1) if x["id"] == cid)
        b = self.brief(self.chapter_view_of(w, cid), kind, None)
        b["chapter"] = {"id": cid, "title": c["title"], "number": n, "of": len(chapters(w)),
                        "source_ids": c["source_ids"], "outline_ids": c["outline_ids"]}
        if kind == "SUMMARY":
            b["result_contract"] = _prefix_section_ids(b["result_contract"], cid)
            b["rules"].insert(0, f"本任务只写第{n}/{len(chapters(w))}章“{c['title']}”：只含本章资料和提纲条目。章节编号以“{cid}-”开头"
                                 f"（如 {cid}-s1，要点编号随之为 {cid}-s1.k1）。overall_summary 写本章概要。各章分别完成并经独立审查后，"
                                 "程序按章序合并为全文总结（章节、要点、索引与逐句登记原样拼接）。")
        else:
            b["rules"].insert(0, f"本任务只审第{n}/{len(chapters(w))}章“{c['title']}”的总结；prior_issues 只含本章未闭环的问题。")
        return b

    def accept_chapter_summary(self, w: dict, t: dict, result: dict):
        c = chapter_of(w, t["binding"])
        problem = chapter_problem(w)
        require(not problem, problem, 409)
        secs = result.get("sections") if isinstance(result, dict) else None
        require(isinstance(secs, list) and all(isinstance(s, dict) and str(s.get("id", "")).startswith(c["id"] + "-") for s in secs),
                f"本章的章节编号须以“{c['id']}-”开头", 422)
        v = chapter_view(w, c)
        self.accept_summary(v, result, t["worker"], t["brief"].get("summary_algorithm"))
        part = v["summary"]
        before = chapter_record(w, c["id"]) or {}
        memory = (before.get("review") or {}).get("coverage_memory") or before.get("coverage_memory")
        w.setdefault("summary_chapters", {})[c["id"]] = {"coverage_memory": memory,
            "input_sha256": part["input_sha256"], "sha256": digest(part), "path": self.snapshot(w, "chapter_summary", part),
            "author": t["worker"], "contributors": sorted({t["worker"], *((t.get("draft") or {}).get("workers") or [])}),
            "at": now(), "review": None}
        self.merge_chapters(w)

    def accept_chapter_review(self, w: dict, cid: str, result: dict, reviewer: str):
        c = chapter_of(w, cid)
        require(chapter_current(w, c), "本章没有当前版本的总结")
        v = self.chapter_view_of(w, cid)
        self.accept_summary_review(v, result, reviewer)
        r = v["summary_review"]
        w["summary_chapters"][cid]["review"] = {k: r[k] for k in ("input_sha256", "reviewer", "at", "round", "sections", "coverage_memory") if k in r}
        self.aggregate_chapter_reviews(w)

    def merge_chapters(self, w: dict) -> bool:
        """When every chapter has a current part, the project summary is their merge, validated as a whole."""
        plan = chapters(w)
        if not all(chapter_current(w, c) for c in plan):
            return False
        merged = merge_chapter_summaries(w, [self.chapter_part(w, c["id"]) for c in plan])
        try:
            self.accept_summary(w, merged, "chapters")
        except WorkflowError as error:
            raise WorkflowError(f"各章合并为全文总结时未通过校验：{error}", 422) from error
        recs = w["summary_chapters"]
        w["summary_meta"] = {"author": "chapters", "chapters": {c["id"]: recs[c["id"]]["author"] for c in plan},
                             "contributors": sorted({x for c in plan for x in [recs[c["id"]]["author"], *recs[c["id"]]["contributors"]]}),
                             "at": now()}
        self.aggregate_chapter_reviews(w)
        return True

    def aggregate_chapter_reviews(self, w: dict):
        """The project's summary review is current when every chapter's review is current for the merged summary."""
        plan = chapters(w)
        if not (summary_current(w) and all(chapter_review_current(w, c) for c in plan)):
            w["summary_review"] = None
            return
        reviews = [w["summary_chapters"][c["id"]]["review"] for c in plan]
        w["summary_review"] = {"schema_version": SUMMARY_REVIEW_SCHEMA, "input_sha256": summary_review_input(w),
                               "reviewer": "、".join(sorted({r["reviewer"] for r in reviews})), "at": now(),
                               "chapters": {c["id"]: {k: r[k] for k in ("reviewer", "at", "round")} for c, r in zip(plan, reviews)},
                               "sections": [row for r in reviews for row in r["sections"]],
                               "round": max(r["round"] for r in reviews), "issues": [], "dismissed": {}}

    def compact(self, workflow_id: str) -> dict:
        """Archive every finished task now (normally this happens on the next write of the project)."""
        with self.transaction(workflow_id, "TASK_ARCHIVE") as w:
            moved = self.archive_tasks(w)
        return {"workflow_id": workflow_id, "archived": moved}

    # ---- project
    def create(self, title: str, outline: str = "", requirements: dict | None = None, context: dict | None = None, theme: str = "navy-teal", generation_route: str = TEMPLATE_ROUTE,
               semantic_map_first: bool = False) -> dict:
        require(bool(title.strip()), "请填写项目名称", 422)
        require(generation_route in {TEMPLATE_ROUTE, VISUAL_ROUTE, "CODE_NATIVE"}, "生成路线无效", 422)
        w = {"id": uid("deck"), "title": title.strip(), "revision": 1, "created_at": now(), "updated_at": now(), "template": TEMPLATE,
             "context": context or {"language": "zh-CN", "external_research_allowed": False},
             "requirements": self._requirements(requirements or {}), "outline": parse_structured_outline(outline)[0],
             "outline_parts": parse_structured_outline(outline)[1], "theme": self._theme(theme),
             "sources": [], "next_source_no": 1, "brand": None, "summary": None, "content_approval": None, "facts": None,
             "confirmations": {"derivations": {}, "resolutions": {}, "transcriptions": {}, "figures": {}, "figure_licenses": {}},
             "deck": None, "semantic_review": None, "render": None, "critique": None, "page_reviews": {}, "style_approval": None,
             "approvals": [], "tasks": [], "deliveries": [], "generation_route": generation_route, "generation": None,
             "source_evidence_policy": "verified-transcription.v1", "rules_version": CONTENT_RULES_VERSION, "rules_history": [],
             "semantic_map_first": semantic_map_first}
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
        w["approval_subjects"] = {"structure": digest(w["structure"]["result"]) if structure_stage.structure_current(w) else None,
                                  "content": digest(w["summary"]) if summary_current(w) else None,
                                  "style": sample_hash(w) if render_current(w) else None}
        for scope, key in (("summary", "summary_review"), ("semantic", "semantic_review")):
            ledger.book(w, scope)
            if w.get(key):                              # earlier screens read issues/dismissed; the ledger is the authority
                w[key]["issues"], w[key]["dismissed"] = ledger.legacy_view(w, scope)
        w["ledger_status"] = {scope: ledger.counts(w, scope) for scope in ("summary", "semantic")}
        w["chapter_status"] = chapter_status(w) if chapters(w) and not chapter_problem(w) else []
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
            if "structure_first" in changes:
                require(isinstance(changes["structure_first"], bool), "structure_first 须为布尔值", 422)
                require(not (changes["structure_first"] and structured(w)),
                        "提纲带要点时章节由提纲逐条组织，不能同时启用“先定整体结构”；请改用不带要点的提纲", 422)
                if bool(w.get("structure_first")) != changes["structure_first"]:
                    # the summary, content confirmation and everything downstream become stale: keep the record
                    w.setdefault("settings_history", []).append({"structure_first": changes["structure_first"], "at": now(),
                                                                 "had_summary": bool(w.get("summary"))})
                w["structure_first"] = changes["structure_first"]
            if "semantic_map_first" in changes:
                require(isinstance(changes["semantic_map_first"], bool), "semantic_map_first 须为布尔值", 422)
                if bool(w.get("semantic_map_first")) != changes["semantic_map_first"]:
                    w.setdefault("settings_history", []).append({"semantic_map_first": changes["semantic_map_first"], "at": now(),
                                                                 "had_claims": any(s.get("claims") for s in w["sources"])})
                w["semantic_map_first"] = changes["semantic_map_first"]
            if "exclusions" in changes:                 # the customer's decisions that rule material out, applied by code
                w["exclusions"] = semantic_map_stage.check_exclusions(changes["exclusions"])
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
                s["relations"] = relation_candidates(s["units"] + s.get("transcriptions", []))
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

    def adopt_rules(self, workflow_id: str, operator: str, reason: str):
        """Move a project to the current content rules, explicitly and on record."""
        require(bool(str(operator).strip()) and len(str(reason).strip()) >= 4, "采纳新规则须写明操作人和原因", 422)
        with self.transaction(workflow_id, "ADOPT_CONTENT_RULES") as w:
            old = w.get("rules_version", "legacy")
            require(old != CONTENT_RULES_VERSION, "本项目已按当前内容规则运行", 409)
            w.setdefault("rules_history", []).append({"from": old, "to": CONTENT_RULES_VERSION, "operator": str(operator).strip(),
                                                      "reason": str(reason).strip(), "at": now()})
            w["rules_version"] = CONTENT_RULES_VERSION
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
        # transcribed diagram arrows ("start→end" cells) are structure too: candidates cover units and transcriptions
        source["relations"] = relation_candidates(source["units"] + transcriptions)
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
            text, parent = str(cells[u["id"]].get("text", "")), str(cells[u["id"]].get("parent") or "").strip()
            u["second_read"] = {"reader": reader, "at": now(), "text": text, "parent": parent,      # the nesting is read twice too
                                "agree": canon(text) == canon(u["text"]) and parent == (u.get("parent") or "")}
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
        meta = w.get("summary_meta") or {}
        require(reviewer != meta.get("author") and reviewer not in (meta.get("contributors") or []), "总结审查须由总结作者之外的执行端完成", 422)
        require(reviewer not in {(s.get("claims") or {}).get("reader") for s in w["sources"]}, "总结审查须由论断清单作者之外的执行端完成", 422)
        require(result.get("input_sha256") == summary_review_input(w), "审查对应的总结已过期")
        require(result.get("schema_version") == SUMMARY_REVIEW_SCHEMA, "总结审查需使用 summary_review.v2 完整覆盖合同", 422)
        from factdeck.summary_evidence import garbled_paths
        bad = garbled_paths(result)
        require(not bad, "审查结果中以下文字已损坏（多为?，通常是写入时编码错误），请用UTF-8重写：" + "、".join(bad[:8]), 422)

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
            if m and (m["core"].get("claim_id") or "parallel" in m["core"]):
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
        from factdeck import source_coverage as sc
        coverage_refs = set()
        if w["summary"].get("source_coverage") and sc.expected_schema(w["summary"]) == sc.SCHEMA_V2:
            # Sentence-level coverage: each part the author registered is judged against the point text it names.
            targets, carried = self.coverage_targets(w)
            rows = result.get("coverage_review")
            require(isinstance(rows, list) and not {r.get("target_id") for r in rows if isinstance(r, dict)} & set(carried),
                    "沿用通过判定的片段不在本轮coverage_review中", 422)
            rows = rows + [{"target_id": tid, **row, "carried": True} for tid, row in carried.items()]
            try:
                problems, fine = sc.check_review(targets, rows, sc.point_texts(w["summary"]))
            except ValueError as error:
                raise WorkflowError(str(error), 422) from error
            points = sc.point_texts(w["summary"])
            passed_rows = {r["target_id"]: r for r in rows if r.get("verdict") in {"FULL", "ACCEPTED"}}
            memory = {sc.target_fingerprint(t, points): {k: passed_rows[t["target_id"]].get(k) for k in ("verdict", "point_evidence")}
                      for t in targets if t["target_id"] in passed_rows}
            for t in targets:
                evidence[t["target_id"]] = t["unit_id"]
                coverage_refs.add(t["target_id"])
            for x in problems:
                issue(x["target_id"], "BLOCKER", f"原文覆盖（{x['verdict']}）：「{x['source_text'][:200]}」——{x['issue']}")
            for ref in fine:
                passed(ref)
        refs = set(evidence) | {s["id"] for s in w["summary"]["sections"]} | {o["id"] for o in w["outline"]} | {"pending_issues"}
        refs |= coverage_refs
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
        rnd = ledger.record_round(w, "summary", summary_check(w), reviewer=reviewer, input_sha256=summary_review_input(w),
                                  dispositions=result.get("prior_issues") or [], new_issues=others, valid_refs=refs,
                                  ok_refs=ok, problem_refs={i["ref"] for i in issues if i["severity"] == "BLOCKER"}, auto_issues=issues)
        self.snapshot(w, "summary_review", result)
        w["summary_review"] = {"schema_version": SUMMARY_REVIEW_SCHEMA, "input_sha256": summary_review_input(w), "reviewer": reviewer, "at": now(),
                               "sections": result["sections"], "round": rnd["round"], "issues": [], "dismissed": {}}
        if coverage_refs:
            w["summary_review"]["coverage_memory"] = self.snapshot(w, "coverage_memory", memory)

    def accept_summary(self, w: dict, result: dict, author: str = "", expected_algorithm: str | None = None):
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
            # An approved course arc may explicitly assign substantive evidence to
            # reference-only reading. summary_checks below still restricts these
            # empty sections to the trailing reference pages of that same arc.
            reference_only = bool(w.get("structure_first") and structure_stage.approved(w) and
                                  set(refs) <= {p for r in w["structure"]["result"].get("reference_only", [])
                                                for p in r["source_page_ids"]})
            require(points or not substantive or reference_only or (structured(w) and s.get("outline_id")),
                    f"章节 {s['id']} 引用了正文页，需至少一条关键依据（key_points）", 422)
            for k in points:
                require(isinstance(k, dict) and len(str(k.get("point", "")).strip()) >= 4, f"章节 {s['id']} 的关键依据需写明归纳（point）", 422)
                cite(w, k, refs, f"章节 {s['id']} 的关键依据", unit_page)
        require(set(known) <= covered, "全文总结未覆盖全部资料页面（含参考文献与空白说明）", 422)
        if structured(w):
            result["outline_coverage"] = self._point_coverage(w, sections, unit_page)
        else:
            # An outline without points: each chapter's key points are its points. Ids are assigned by order.
            for s in sections:
                rows = []
                for i, k in enumerate(s.get("key_points") or [], 1):
                    k["id"] = f"{s['id']}.k{i}"
                    rows.append({"point_id": k["id"], "unit_ids": k.get("unit_ids") or [], "claim_ids": k.get("claim_ids") or []})
                Store._message(w, s, rows, unit_page)
        structure_stage.summary_checks(w, sections)
        mapping = result.get("outline_coverage", [])
        outline_ids = {o["id"] for o in w["outline"]}
        require(isinstance(mapping, list) and len(mapping) == len(outline_ids) and {m.get("outline_id") for m in mapping} == outline_ids,
                "总结需覆盖全部教学提纲条目", 422)
        for m in mapping:
            require(m.get("section_ids") and set(m["section_ids"]) <= set(ids), "提纲映射需指向有效章节", 422)
        require(isinstance(result.get("pending_issues"), list), "需列出待解决问题；无问题时为空列表", 422)
        from factdeck import summary_evidence as se
        if expected_algorithm:
            require(result.get("summary_algorithm") == expected_algorithm, "新SUMMARY任务需按模型理解与同步证据索引合同提交", 422)
        candidate = None
        if result.get("summary_algorithm"):
            require(result["summary_algorithm"] in se.SUPPORTED_ALGORITHMS, "不支持的总结算法版本", 422)
            if result["summary_algorithm"] == se.ALGORITHM and isinstance(result.get("source_coverage"), dict):
                from factdeck import source_coverage as sc
                refs = reference_units(w)
                sc.prefill_reference(result["source_coverage"], all_units(w), refs)
                index = result.get("evidence_index")
                if isinstance(index, dict) and isinstance(index.get("page_decisions"), list):
                    decided = {d.get("page_id") for d in index["page_decisions"] if isinstance(d, dict)}
                    by_page = {}
                    for u in all_units(w):
                        by_page.setdefault(u["page_id"], []).append(u["id"] in refs)
                    index["page_decisions"] += [{"page_id": p, "disposition": "REFERENCE", "reason": sc.CODE_REASON, "point_ids": []}
                                                for p in known if p not in decided and by_page.get(p) and all(by_page[p])]
            try:
                result["evidence_index"] = se.validate(result, all_units(w), all_claims(w), set(known),
                    {g['id'] for s in w['sources'] for g in s.get('figures', [])})
                candidate = se.candidates(result)
                F, D, T = fx.parse(candidate['result'])
                fx.verify(F, D, all_units(w), {}, T)
                require(all(f.status == 'ACCEPTED' for f in F), "同步证据候选未通过逐字核验", 422)
            except ValueError as error:
                raise WorkflowError(str(error), 422) from error
        self.snapshot(w, "summary", result)
        w["summary"] = copy.deepcopy(result)
        w["summary_meta"] = {"author": author, "at": now()}
        w['summary_fact_candidates'] = None
        if candidate is not None:
            candidate['summary_sha256'] = digest(w['summary'])
            candidate['result']['summary_sha256'] = candidate['summary_sha256']
            w['summary_fact_candidates'] = {'summary_sha256': candidate['summary_sha256'],
                'path': self.snapshot(w, 'summary_fact_candidates', candidate),
                'fact_count': len(candidate['result']['facts']), 'state': 'PENDING_CONTENT_CONFIRMATION'}
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
        if "parallel" in core:                     # items set side by side as equals (a graded table, a list of factors)
            require("claim_id" not in core and "none" not in core, f"章节 {sid} 的 core 只能是 claim_id、none 或 parallel 之一", 422)
            require(isinstance(core.get("parallel"), str) and len(core["parallel"].strip()) >= 8,
                    f"章节 {sid} 声明并列时 core 写成 {{parallel: 理由（文字）, claim_ids/unit_ids: 呈现并列结构的论断或单元}}："
                    f"理由说明原文如何把这些要点并列呈现、为何没有一条比其他更重要", 422)
            require(len(cores) >= 2, f"章节 {sid} 声明并列时须把同等重要的要点（至少两条）都标为 core", 422)
            core["parallel"] = str(core["parallel"]).strip()
            cite(w, core, s["source_page_ids"], f"章节 {sid} 的并列依据（core 中呈现并列结构的论断或单元）", unit_page)
        elif "claim_id" not in core:               # e.g. a table: the original has no sentence that states the item
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
            require(len(set(items)) >= 2, f"{where}须涉及至少两条不同的要点；两端都在同一条要点内时不列关系"
                                          f"（来自候选的按 within_one_point 拒绝）", 422)
            cid = r.get("from_candidate")
            explicit = list(r.get("unit_ids") or [])
            if cid:
                require(cid in cands, f"{where}引用了不存在的候选关系 {cid}", 422)
                require(explicit and set(explicit) <= set(cands[cid]["unit_ids"]), f"{where}需列出候选关系 {cid} 中的单元（unit_ids）", 422)
            else:
                require(r.get("claim_ids"), f"{where}没有来自原件的候选，需列出支撑它的论断（claim_ids）", 422)
            cite(w, r, s["source_page_ids"], where, unit_page)
            if not cid:                            # an author's relation rests on a source sentence that states it
                b = r.get("basis")
                require(isinstance(b, dict) and b.get("unit_id") in r["unit_ids"] and str(b.get("quote", "")).strip(),
                        f"{where}没有来自原件的候选：须在 basis 中给出原文直接陈述这一关系的句子 {{unit_id（所引单元之一）, quote（逐字）}}", 422)
                text = next(u["text"] for u in all_units(w) if u["id"] == b["unit_id"])
                require(canon(b["quote"]) in canon(text), f"{where}的 basis.quote 须是单元 {b['unit_id']} 中的逐字原文", 422)
            r["manual"] = not cid
        pages_ = set(s["source_page_ids"])
        mine = sorted(cid for cid, c in cands.items() if any(unit_page.get(u) in pages_ for u in c.get("unit_ids") or []))
        decisions = m.get("candidate_decisions")
        require(isinstance(decisions, list) and all(isinstance(x, dict) for x in decisions),
                f"章节 {sid} 需逐条处理本章页面上的候选关系（candidate_decisions）", 422)
        got = {x.get("candidate"): x for x in decisions}
        missing = [c for c in mine if c not in got]
        require(not missing, f"章节 {sid} 未处理的候选关系：{'、'.join(missing[:12])}{' 等' if len(missing) > 12 else ''}（共 {len(missing)} 条）", 422)
        require(len(got) == len(decisions) and set(got) <= set(mine), f"章节 {sid} 的 candidate_decisions 只列本章页面上的候选，且不重复", 422)
        adopted = {r.get("from_candidate") for r in rels if r.get("from_candidate")}
        for cid, x in got.items():
            if x.get("decision") == "ADOPTED":
                require(cid in adopted, f"章节 {sid} 采纳的候选 {cid} 须在 relations 中以 from_candidate 出现", 422)
            else:
                require(x.get("decision") == "REJECTED" and x.get("reason") in CANDIDATE_REJECT_REASONS,
                        f"章节 {sid} 的候选 {cid} 须为 ADOPTED，或 REJECTED 并给出原因（{' / '.join(CANDIDATE_REJECT_REASONS)}）", 422)
                require(cid not in adopted, f"章节 {sid} 的候选 {cid} 既被采纳又被拒绝", 422)
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
        if w.get("generation_route") == TEMPLATE_ROUTE:
            other = [p.get("id") for p in deck.get("pages") or [] if not isinstance(p, dict) or p.get("layout") != "template"]
            require(not other, "本项目走模板库主线：每页须写成 layout: template（封面、章节页用 template.kind 为 cover / section），"
                    f"以下页面不是：{'、'.join(map(str, other[:8]))}", 422)
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
        chk = check_spec(deck, v["facts"], v["terms"], w["outline"], w["summary"]["sections"], w["requirements"], w.get("outline_parts"),
                         key_points=summary_key_points(w), key_roles=summary_point_roles(w))
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

    def semantic_memory(self, w: dict, check: str | None, path: str | None = None) -> tuple[str | None, dict | None]:
        """(snapshot path, value) of a checklist's carried passes: `path`, or the one its last accepted round left."""
        path = path or ((w.get("semantic_checks") or {}).get(check) or {}).get("carry_memory")
        if not path:
            return None, None
        return path, json.loads(self.path(path).read_text(encoding="utf-8"))["value"]

    def accept_semantic(self, w: dict, result: dict, reviewer: str, check: str | None = None, brief: dict | None = None):
        """One of the two independent checklists; the issue ledger carries every earlier problem forward. Passes are
        carried from the memory the task's brief was built from (a brief without one carries nothing)."""
        check = check or result.get("check")
        if brief is None:
            _, memory = self.semantic_memory(w, check)
        else:
            memory = self.semantic_memory(w, check, brief["carry_memory"])[1] if brief.get("carry_memory") else None
        semrev.accept(w, result, reviewer, check, memory, lambda m: self.snapshot(w, "semantic_carry_memory", m))
        self.snapshot(w, "semantic_review", result)

    # ---- tasks
    def brief(self, w: dict, kind: str, binding: str | None) -> dict:
        from factdeck import summary_evidence as se
        if kind in CHAPTER_KINDS and binding and binding != "within-structure":
            return self.chapter_brief(w, kind, binding)
        b = self._brief(w, kind, binding)
        if kind == 'SUMMARY' and not b.get('summary_algorithm'):
            b['summary_algorithm'] = se.ALGORITHM
            b['context_mode'] = 'FULL_SECTION_CONTEXT_WITH_CLAIM_INDEX'
            b['rules'] = list(se.RULES) + b['rules']
            b['result_contract'].update(summary_algorithm=se.ALGORITHM, source_understanding=se.understanding_contract(), evidence_index=se.contract())
            from factdeck import source_coverage as sc
            b['result_contract']['source_coverage'] = sc.contract(sc.SCHEMA_V2)
            refs = reference_units(w)
            b['source_coverage_input'] = sc.coverage_input(all_units(w))
            for row in b['source_coverage_input']['units']:
                if row['unit_id'] in refs:
                    row['registered_by'] = sc.CODE_REGISTERED
            b['chunks'] = sc.chunks([u for u in all_units(w) if u['id'] not in refs])
            if refs:
                b['rules'].append('source_coverage_input中标registered_by的单元在参考文献页上且没有论断：不必登记，程序逐句登记为REFERENCE_LIST，'
                                  '未写page_decisions的全参考文献页由程序补REFERENCE；这些页仍须列入某章节的source_page_ids（通常放最后一节）。'
                                  '审核会按页核对；某页被退回时，按审核意见为该页单元逐句登记（你的登记取代程序登记）。')
            if w.get('summary') and b.get('review_issues'):
                # a revision starts from the reviewed summary; only what the review ledger names is reopened
                b['revision_base'] = copy.deepcopy(w['summary'])
                b['rules'].insert(0, '带revision_base时是修订任务：在其基础上逐条处理review_issues（逐句覆盖问题的ref是登记片段编号），补写或改正point正文并重新登记受影响的句子；'
                                     '未被指出的内容保持不变，不得为通过审核删减原文含义或改归非论断/待定。分块与草稿规则照旧适用。')
            elif w.get('summary') and summary_current(w):
                # re-queued with nothing to revise (the content rules changed): conform the accepted summary, change nothing else
                b['revision_base'] = copy.deepcopy(w['summary'])
                b['rules'].insert(0, '带revision_base而没有review_issues时，是按现行规则复核已通过的总结：只改不符合现行校验的结构（如关系、core 写法），'
                                     '要点正文、证据与逐句登记保持不变。')
        elif kind == 'SUMMARY_REVIEW' and (w.get('summary') or {}).get('summary_algorithm') in se.SUPPORTED_ALGORITHMS:
            b['evidence_index'] = copy.deepcopy(w['summary']['evidence_index'])
            b['source_understanding'] = copy.deepcopy(w['summary'].get('source_understanding'))
            if w['summary'].get('source_coverage'):
                from factdeck import source_coverage as sc
                audit = sc.audit(w['summary'], all_units(w), all_claims(w))
                if sc.expected_schema(w['summary']) == sc.SCHEMA_V2:
                    # the targets carry every registered part; the whole ledger is not repeated in the brief
                    b['source_coverage_audit'] = {k: audit[k] for k in ('structural_status', 'warnings', 'counts')}
                    light = {r['unit_id'] for r in w['summary']['source_coverage']['units'] if r.get('registered_by') == sc.CODE_REGISTERED}
                    b['chunks'] = sc.chunks(all_units(w), light=light)
                else:
                    b['source_coverage'] = copy.deepcopy(w['summary']['source_coverage'])
                    b['source_coverage_audit'] = audit
                if sc.expected_schema(w['summary']) != sc.SCHEMA_V2:
                    b['rules'].append('逐项核验source_coverage：非论断分类/重复翻译依据是否正确、每条结论六类限定条件是否漏判、多项是否全列、PRESENT的summary_quote是否真正表达原文限定条件。ACCOUNTED仅是登记状态，不是语义通过，不得据此默认ENTAILED。')
                else:
                    targets, carried = self.coverage_targets(w)
                    b['coverage_targets'] = [t for t in targets if t['target_id'] not in carried]
                    b['carried_coverage'] = {'count': len(carried), 'of': len(targets)}
                    b['rules'].append(f'本轮有{len(carried)}/{len(targets)}个片段沿用此前独立审核的通过判定：其原文、登记与所列point全文均未改变（代码按内容指纹核对），'
                                      '不在coverage_targets中，也不需判定。只判定列出的片段。'
                                      'registered_by为程序登记的目标是一整页参考文献（target_id为“页/reference_page”）：读整页，'
                                      '全为文献条目、无实质内容判ACCEPTED；夹有实质内容判REJECTED并写明是哪句。')
                    b['result_contract']['coverage_review'] = [{'target_id': t['target_id'], 'disposition': t['disposition'], 'author_expressions': t.get('expressions', []),
                                                                  'verdict': '', 'point_evidence': [], 'missing_facets': [], 'issue': ''} for t in b['coverage_targets']]
                    b['rules'].append('coverage_review逐句判定coverage_targets，不得抽样或按脚本批量填写：EXPRESSED句先读source_text及其所在单元上下文，再读所列point全文（不只summary_quote），'
                                      'FULL/PARTIAL/CONTRADICTED须在point_evidence写出所依据的point正文逐字片段（point_id+quote），代码核对存在；不得用按位置排列的判定串。PARTIAL/CONTRADICTED在missing_facets标明缺失类别（population/time/threshold/condition/exception/negation/modality/descriptor/relation/enumeration/number/other）。FULL=这句的全部含义（列举各项、数字、比较、人群、时间、条件、例外、否定、模态词）都在point正文；PARTIAL=部分表达，写明缺什么；MISSING=未表达；CONTRADICTED=表达相反。'
                                      '非EXPRESSED片段判ACCEPTED/REJECTED：分类或待定理由是否成立，含实质内容却被归为非论断或待定即REJECTED。每个非FULL/ACCEPTED判定成为阻断问题退回总结作者修订。'
                                      'source_coverage_audit.warnings列出一个短语代表多句原文的情况，须逐句核实。')
                    b['rules'].append('按chunks顺序逐块判定coverage_review；每完成一块，用draft保存当前完整结果对象（已判定的行即可），代码逐块核对并续约。'
                                      '任务带draft时，draft.done_chunks中的块已判定完成，draft.result是此前保存的结果，从下一块继续；全部完成并填好其余判定后再complete。')
            b['rules'].append('审核目标是原文理解、重点选择、上下文完整、结构与关系准确；不奖励压缩或少写。逐项核对source_understanding作者主旨/组织依据/结论及关系；模型组织建议不得充当作者关系。正文必须表达关键条件和分支，不能用图引用或索引存在替代。问题写入现有issues并绑定相关要点。')
            b['rules'].append('先独立阅读原文、判断要点和关系，再查重点选择理由及同步索引是否漏掉条件/限制。选择理由不得作为来源支持证据；问题仍写入既有逐条判定或issues。')
        elif kind == 'FACTS':
            c = w.get('summary_fact_candidates')
            if c and c['summary_sha256'] == digest(w['summary']):
                b['fact_candidates'] = json.loads(self.path(c['path']).read_text(encoding='utf-8'))['value']
                b['rules'].insert(0, '复用SUMMARY已同步建立并逐字核验的fact_candidates及bindings。只补必要的细粒度切分、实体/属性/冲突信息；不得把候选重新机械合并成新的教学要点。PENDING绑定仍须人工裁定，不得静默用于教学。')
        elif kind == 'DECK' and w.get('generation_route') == TEMPLATE_ROUTE:
            template_deck_brief(b)
        if kind == 'DECK' and semantic_map_stage.enabled(w):
            semantic_map_stage.deck_brief(w, b)
        return b

    def _brief(self, w: dict, kind: str, binding: str | None) -> dict:
        req = {"requirements": w["requirements"], "outline": w["outline"], "context": w["context"]}
        if kind == "SEMANTIC_MAP":
            return {**req, **semantic_map_stage.brief(w)}
        if kind == "TOPIC_PASS":
            return semantic_map_stage.topic_brief(w, binding)
        if kind == "STRUCTURE":
            return {**req, **structure_stage.brief(w)}
        if kind == "SUMMARY" and binding is None and w.get("structure_first") and structure_stage.approved(w):
            b = self.brief(w, kind, "within-structure")
            st = w["structure"]["result"]
            b["structure"] = {"course_question": st["course_question"], "story": structure_stage.story(w), "sections": st["sections"],
                              "links": st["links"], "reference_only": st.get("reference_only") or []}
            b["rules"].append("已确认的课程结构（structure）决定总结的组织：章节与结构的部分一一对应、同序，章节 id 与部分 id 相同，"
                              "资料页与该部分一致，message.core 即该部分确认的核心句；要点只写回答该部分问题所需的内容，"
                              "总结的数量与篇幅由完整理解决定，不受该部分页数分配约束；页数与密度在DECK阶段处理。标为参考的资料页放在最后的章节中，不写要点。")
            return b
        if kind == "STRUCTURE_REVIEW":
            return {**req, **structure_stage.review_brief(w)}
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
                              "表格或分类中有上下级的行（原件中缩进在一个分组标题下的子项）：分组标题单独转录为一格，每个子项格写 parent: 分组标题那一格的 id（须在子项之前转录）。",
                              "PDF 文字层（text）因分栏、排版而打断或错排的正文句子（一句被拆到不相邻的位置、夹入别处文字），可按原件画面把整句完整转录为一格，"
                              "location 写“正文 整句”及位置；只照原件转录，不补全、不改写。",
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
                              "某格在原件中缩进在一个分组标题之下（表格子行、分类中的子类）时，parent 写该分组标题那一格的 unit_id；否则留空。",
                              "crops 中每张图按描述在原页上独立找到该图，给出完整包含图例、坐标轴、脚注、标记的截取区域 bbox"
                              "（页面归一化坐标 [x0, y0, x1, y1]，左上角为原点）；不得参考第一次截取（本合同不提供）。"],
                    "result_contract": {"source_sha256": s["sha256"], "cells": [{"unit_id": u["id"], "text": "", "parent": ""} for u in s["transcriptions"]],
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
                view.append({"section_id": sec["id"], "title": sec["title"], "summary": sec["summary"], "source_page_ids": sec["source_page_ids"],
                             "key_points": [{"target_id": k["target_id"], "point": k["point"], **evidence(k)} for k in key_point_targets(w, sec)],
                             "points": [{"point_id": r["point_id"], "point": r.get("point", ""), **({"statement": r["statement"]} if r.get("statement") else {}),
                                         "role": (m.get("roles") or {}).get(r["point_id"]),
                                         "unmatched_tokens": r.get("unmatched_tokens", []), **evidence(r)}
                                        for r in sec.get("point_coverage") or [] if r.get("unsupported") is None],
                             "unsupported": [{"point_id": r["point_id"], "point": r.get("point", ""), "reason": r["unsupported"]}
                                             for r in sec.get("point_coverage") or [] if r.get("unsupported") is not None],
                             **({"core": {"claim": claim_view(claims[m["core"]["claim_id"]])} if m["core"].get("claim_id") in claims else
                                         {"parallel": m["core"]["parallel"], "items": [p for p, v in m["roles"].items() if v == "core"], **evidence(m["core"])}
                                         if "parallel" in m["core"] else m["core"],
                                 "relations": [{**{k: r[k] for k in ("type", "items", "manual")}, "from_candidate": r.get("from_candidate"),
                                                **({"basis": r["basis"]} if r.get("basis") else {}), **evidence(r)}
                                               for r in m.get("relations") or []]} if m else {})})
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
                              "core 为 parallel（并列，无单一核心）时，判断原文是否确把 items 所列要点作为同等重要的并列项呈现"
                              "（如分级表、并列因素清单），且没有一条被原文标为总述或重点、理由成立：成立 SUPPORTED；"
                              "原文有总述句或其中一项明显更重要，判 UNSUPPORTED 并指出该句。"
                              "关系（relations）：该关系是否被所附原文支持，SUPPORTED / UNSUPPORTED。manual 为 true 的是作者判断，"
                              "basis 是作者给出的原文句子：只有这句原文直接陈述了 items 之间的这一关系才判 SUPPORTED；"
                              "从并列、相邻或主题相近推出的关系判 UNSUPPORTED。",
                              "章节总结文字（summary）同样按四级判断（summary_verdict）。",
                              "key_points 的每条主要归纳也必须独立给出四级 verdict 和 issue，使用原样 target_id；不得以章节结论代替逐条审核。",
                              "其他问题（遗漏的重要论断、资料性质未交代、限定要点未标 limit 等）写入 issues：severity、category"
                              "（CONTENT_ERROR 内容错误 / EVIDENCE_MISSING 来源证据缺失 / EXPRESSION_AMBIGUITY 表达歧义 / HUMAN_DECISION 人工决策）、ref、source_ref、problem、suggestion。不得给出医学放行结论。",
                              "先回看 prior_issues（此前全部未闭环问题及历史）：逐条处置 FIXED（evidence_refs 写当前版本的要点/目标编号，evidence 说明所见修订）、"
                              "OPEN、NEEDS_HUMAN（须用户裁定，修订总结不能解决）或 RETAINED（证据不足而保留）。与本轮逐条判定矛盾的处置会被拒绝；"
                              "仍有问题的要点不要另起新问题，程序会并入原问题编号。"],
                    "prior_issues": [ledger.view(i) for i in ledger.unresolved(w, "summary", summary_check(w))],
                    "result_contract": {"schema_version": SUMMARY_REVIEW_SCHEMA, "input_sha256": summary_review_input(w), "issues": [],
                                        "prior_issues": [{"issue_id": i["id"], "status": "", "evidence": "", "evidence_refs": []}
                                                         for i in ledger.unresolved(w, "summary", summary_check(w))],
                                        "sections": [{"section_id": v["section_id"], "summary_verdict": "", "summary_issue": "",
                                                      "points": [{"point_id": p["point_id"], "verdict": "", "issue": ""} for p in v["points"]],
                                                      "key_points": [{"target_id": p["target_id"], "verdict": "", "issue": ""} for p in v["key_points"]],
                                                      **({"core": {"verdict": "", "issue": ""}} if isinstance(v.get("core"), dict)
                                                         and ("claim" in v["core"] or "parallel" in v["core"]) else {}),
                                                      **({"relations": [{"verdict": "", "issue": ""} for _ in v["relations"]]} if "relations" in v else {})}
                                                     for v in view]}}
        if kind == "SUMMARY":
            return {"kind": kind, **req, "input_sha256": input_hash(w),
                    "review_issues": [ledger.view(i) for i in ledger.unresolved(w, "summary", summary_check(w))],
                    "sources": [{"id": s["id"], "filename": s["filename"], "pages": [{**{k: p[k] for k in ("id", "location", "text")}, "reading": p["reading"],
                                                                                     "units": [{k: u[k] for k in ("id", "text")} | ({"signals": u["signals"]} if u.get("signals") else {})
                                                                                               for u in s["units"] if u["page_id"] == p["id"]],
                                                                                     "claims": [claim_view(k) for k in (s.get("claims") or {}).get("items", [])
                                                                                                if k["page_id"] == p["id"]]}
                                                                                    for p in s["pages"]],
                                 "profile": (s.get("claims") or {}).get("profile"),
                                 # transcription cells and correction proposals, with confirmed text applied (all_units)
                                 "transcriptions": [{k: u[k] for k in ("id", "location", "text")} for u in all_units(w)
                                                    if u["id"] in {x["id"] for x in s["transcriptions"]}
                                                    | {x["id"] for x in w.get("transcription_proposals", []) if x["source_id"] == s["id"]}],
                                 "relation_candidates": s.get("relations") or []} for s in w["sources"]],
                    "relation_types": RELATION_NAMES, "claim_types": CLAIM_TYPES, "source_kinds": SOURCE_KINDS,
                    "candidate_reject_reasons": CANDIDATE_REJECT_REASONS,
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
                                 "未纳入任何提纲条目的资料页，放入最后一章“未纳入提纲的资料内容”（不带 outline_id）。"
                                 ] if structured(w) else []),
                              "每章写信息结构 message（该章没有有资料支撑的要点时不写）。要点：有提纲要点时为提纲要点（point_id）；"
                              "提纲没有要点时为本章 key_points，编号按顺序为 <章节id>.k1、<章节id>.k2……（程序按顺序赋号）。"
                              "core 为本章最重要的一句：{claim_id}，须是核心要点所列的论断之一，程序取其原文；"
                              "优先选原件作者标出的句子（units 的 signals：title 为页标题，emphasis 为加粗、标色或放大的片段），"
                              "不得自拟结论。roles 为每条要点标 core / support / limit，恰好一条 core。"
                              "例外：原文把几项作为同等重要的并列项呈现（如分级表的各级、并列的危险因素），且没有总述句、没有一项被标为重点时，"
                              "core 写 {parallel: 理由, claim_ids/unit_ids: 呈现这一并列结构的论断或单元}，并把这些同等重要的要点（至少两条）都标为 core；"
                              "审核会核对是否确实并列。原文有总述句时仍用该句作 core，不用 parallel；"
                              "局限、例外、禁忌、适用范围和注意事项标 limit，它们必须上页。"
                              "relations 列出要点之间的关系 {type, items, from_candidate?, unit_ids?, claim_ids?}，type 取自 relation_types，items 为要点编号；"
                              "优先采用 relation_candidates（来自原件的箭头、表格、编号和连接词），写明候选编号，unit_ids 取候选中的单元；"
                              "原件没有候选的关系，只有原文有一句直接陈述了这一关系时才可以写：列出 claim_ids（在本章页面内），"
                              "并在 basis 中给出该句 {unit_id, quote（逐字）}；客户确认时会标为人工判断。不得从并列、相邻或主题相近推出关系；"
                              "修订时同样如此。每条关系至少涉及两条不同的要点，两端都在同一条要点内的候选按 within_one_point 拒绝。",
                              "candidate_decisions：本章 source_page_ids 页面上的每条候选关系都要处理："
                              "{candidate, decision: ADOPTED}（须在 relations 中以 from_candidate 出现），"
                              "或 {candidate, decision: REJECTED, reason}，reason 取自 candidate_reject_reasons。"],
                    "result_contract": {"schema_version": "full_source_summary.v3", "input_sha256": input_hash(w), "overall_summary": "",
                                        "sections": ([{"id": f"s{i}", "outline_id": o["id"], "title": o["text"], "summary": "", "source_page_ids": [],
                                                       "key_points": [{"point": "", "claim_ids": []}],
                                                       "point_coverage": [{"point_id": p["id"], "point": p["text"], "claim_ids": []} for p in o["points"]],
                                                       "message": {"core": {"claim_id": ""}, "roles": {p["id"]: "" for p in o["points"]},
                                                                   "relations": [], "candidate_decisions": []}}
                                                      for i, o in enumerate(w["outline"], 1)]
                                                     + [{"id": f"s{len(w['outline']) + 1}", "title": "未纳入提纲的资料内容", "summary": "", "source_page_ids": [],
                                                         "key_points": []}]) if structured(w) else
                                        [{"id": "s1", "title": "", "summary": "", "source_page_ids": [], "key_points": [{"point": "", "claim_ids": []}],
                                          "message": {"core": {"claim_id": ""}, "roles": {"s1.k1": ""}, "relations": [], "candidate_decisions": []}}],
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
                    **({"summary_key_points": [{"key_point_id": k, "role": (summary_point_roles(w) or {}).get(k), "point": t}
                                               for k, t in summary_key_points(w).items()],
                        "notes_rules": ["总结是客户已确认的完整笔记：每个内容页用 key_point_ids 标注本页讲的总结要点。role 为 core（每节核心）和 limit（例外、禁忌、条件）的要点每条至少上一页，不得删减；"
                                        "support 要点可以合并上页，也可以不上页——不上页的由程序放进其所在节第一页的演讲者备注（讲稿补充），不会丢失。",
                                        "页数由内容决定：不按时长、目标页数或 outline_parts 的建议区间压缩；一个要点内容多就拆成几页，几页都标注它。",
                                        "页面只放核心句、关键数字/阈值、流程与分支；上页内容的人群、时间、阈值、条件、例外、否定及“可能/尚未证明/至关重要”等强度词必须随之上页。"
                                        "研究细节、机制列举、例子等可不上页：程序把所标要点的总结全文原样放进该页演讲者备注（讲稿），不需要也不得在页面上自行改写补全。"]}
                       if summary_key_points(w) is not None else {}),
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
                    "rules": [("按需求（受众、目的、重点）组织页面；页数由内容决定（见 notes_rules），一页一个认知单元，内容多就拆页。"
                               if summary_key_points(w) is not None else "按需求（受众、目的、时长、目标页数、重点）组织页面；一页一个认知单元，内容多就拆页。"),
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
        return semrev.brief(w, binding, req, self.semantic_memory(w, binding))

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
        if kind in CHAPTER_KINDS and binding:
            c = chapter_of(w, binding)
            return chapter_input(w, c) if kind == "SUMMARY" else chapter_review_input(w, c)
        if kind == "SEMANTIC_MAP":
            return semantic_map_stage.semantic_map_input(w)
        if kind == "TOPIC_PASS":
            return semantic_map_stage.topic_input(w, binding)
        return {"STRUCTURE": structure_stage.structure_input, "STRUCTURE_REVIEW": structure_stage.review_input,
                "SUMMARY": input_hash, "SUMMARY_REVIEW": summary_review_input, "FACTS": facts_input, "DECK": deck_input,
                "VISUAL_CRITIQUE": critique_input}[kind](w)

    def queue(self, workflow_id: str, kind: str, page_ids=None):
        require(kind in KINDS, "任务类型无效", 422)
        if kind in VISUAL_KINDS:
            require(page_ids and len(page_ids) == 1, "请用生成入口自动排队；修订须指定一个页面", 422)
            return self.revise_generation(workflow_id, page_ids[0], kind)
        version = self.get(workflow_id).get("rules_version", "legacy")
        require(version == CONTENT_RULES_VERSION,
                f"本项目按内容规则 {version} 运行，当前代码为 {CONTENT_RULES_VERSION}：须先明确采纳新规则（adopt-rules），记录后再排任务", 409)
        with self.transaction(workflow_id, "QUEUE_" + kind) as w:
            if kind == "READ_SOURCE":
                require(w["sources"], "请先导入资料")
                bindings = [s["id"] for s in w["sources"] if not all(p["reading"] for p in s["pages"])]
            elif kind == "SECOND_READ":
                bindings = [s["id"] for s in w["sources"] if needs_second_read(s)]
                require(bindings, "没有需要第二次独立转录或截取的资料")
            elif kind == "CLAIMS":
                require(fully_read(w), "请先完成全部资料阅读")
                require(not semantic_map_stage.enabled(w), "本项目由代码按语义地图切分原句，不再安排论断清单任务", 422)
                if page_ids:                        # redo named sources (a revised claims list replaces the current one)
                    known = {s["id"] for s in w["sources"]}
                    require(set(page_ids) <= known, "资料不存在：" + "、".join(sorted(set(page_ids) - known)), 404)
                    bindings = list(page_ids)
                else:
                    bindings = [s["id"] for s in w["sources"] if not claims_current(s)]
                require(bindings, "全部资料的论断清单均为当前版本")
            elif kind == "SEMANTIC_MAP":
                require(semantic_map_stage.enabled(w), "本项目未启用“先定语义地图”（设置 semantic_map_first）")
                require(fully_read(w), "请先完成全部资料阅读")
                bindings = [None]
            elif kind == "TOPIC_PASS":
                require(semantic_map_stage.enabled(w) and semantic_map_stage.semantic_map_current(w), "请先完成当前版本的语义地图（SEMANTIC_MAP）")
                if page_ids:                        # redo named topics
                    known = {n["id"] for n in semantic_map_stage.nodes(w)}
                    require(set(page_ids) <= known, "主题不存在：" + "、".join(sorted(set(page_ids) - known)), 404)
                    bindings = list(page_ids)
                else:
                    bindings = semantic_map_stage.pending_topics(w)
                require(bindings, "全部主题的重点梳理均为当前版本")
            elif kind == "STRUCTURE":
                require(w.get("structure_first"), "本项目未启用“先定整体结构”（设置 structure_first）")
                require(not semantic_map_stage.enabled(w), "本项目按语义地图与主题梳理组织内容，不使用整体结构任务", 422)
                require(fully_claimed(w), "请先完成全部资料阅读和论断清单")
                bindings = [None]
            elif kind == "STRUCTURE_REVIEW":
                require(structure_stage.structure_current(w), "请先完成当前版本的课程结构")
                bindings = [None]
            elif kind in CHAPTER_KINDS and chapters(w):
                bindings = self.next_chapters(w, kind, page_ids)
            elif kind == "SUMMARY":
                require(not semantic_map_stage.enabled(w), "本项目按语义地图与主题梳理组织内容，初稿由代码生成", 422)
                require(fully_claimed(w), "请先完成全部资料阅读和论断清单")
                require(not w.get("structure_first") or structure_stage.approved(w), "请先完成课程整体结构的独立审查与客户确认")
                bindings = [None]
            elif kind == "SUMMARY_AMEND":
                require(not chapters(w), "分章项目的待确认事项请在对应章节的修订中处理", 422)
                require(summary_current(w) and w.get("summary_pending_responses", {}).get("subject_sha256") == digest(w["summary"]), "需先保存当前版本的人工答复")
                bindings = [None]
            elif kind == "SUMMARY_REVIEW":
                require(summary_current(w), "请先完成当前版本的总结")
                bindings = [None]
            elif kind == "FACTS":
                require(not semantic_map_stage.enabled(w), "本项目的事实库由代码在客户确认初稿时生成", 422)
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
                # whoever holds verdicts of the other checklist: its current reviewers (carried ones included) and the
                # reviewers of the passes its next round would carry
                done = [x for c in other for x in (semrev.reviewers(w["semantic_checks"][c]) if semrev.check_current(w, c) else set())
                        | set(((w.get("semantic_checks") or {}).get(c) or {}).get("memory_reviewers") or [])]
                running = [x["worker"] for x in w["tasks"] if x["kind"] == "SEMANTIC_REVIEW" and x["status"] == "RUNNING"
                           and x["binding"] in other]
                return worker not in done + running
            if t["kind"] == "SUMMARY_REVIEW":
                if t.get("binding"):                 # one chapter: its authors and its sources' claims readers
                    meta = chapter_record(w, t["binding"]) or {}
                    w = chapter_view(w, chapter_of(w, t["binding"]))
                else:
                    meta = w.get("summary_meta") or {}
                return worker not in {meta.get("author"), *(meta.get("contributors") or [])} | {(s.get("claims") or {}).get("reader") for s in w["sources"]}
            if t["kind"] == "STRUCTURE_REVIEW":
                return worker not in {(w.get("structure") or {}).get("author")} | {(s.get("claims") or {}).get("reader") for s in w["sources"]}
            if t["kind"] == "VISUAL_BLIND_READ":     # never the author of the plan or the clean image it reads
                page = next(p for p in w["generation"]["pages"] if p["id"] == t["binding"])
                return worker not in {(page["assets"].get(k) or {}).get("receipt", {}).get("worker") for k in ("design", "clean")}
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
            if t["kind"] == "CLAIMS" and semantic_map_stage.enabled(w): return False
            if t["kind"] == "TOPIC_PASS" and not (semantic_map_stage.enabled(w) and semantic_map_stage.semantic_map_current(w)
                                                  and any(n["id"] == t["binding"] for n in semantic_map_stage.nodes(w))): return False
            if t["kind"] == "SEMANTIC_MAP" and not (semantic_map_stage.enabled(w) and fully_read(w)): return False
            if t["kind"] == "STRUCTURE" and not (w.get("structure_first") and fully_claimed(w)): return False
            if t["kind"] == "STRUCTURE_REVIEW" and not structure_stage.structure_current(w): return False
            if t["kind"] in CHAPTER_KINDS and t.get("binding"):
                c = chapter_of(w, t["binding"])
                if chapter_problem(w): return False
                if t["kind"] == "SUMMARY" and not fully_claimed(chapter_view(w, c)): return False
                if t["kind"] == "SUMMARY_REVIEW" and not chapter_current(w, c): return False
                return self.fingerprint(w, t["kind"], t["binding"]) == t["input_sha256"]
            if t["kind"] == "SUMMARY" and not fully_claimed(w): return False
            if t["kind"] == "SUMMARY" and w.get("structure_first") and not structure_stage.approved(w): return False
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
        if task["kind"] == "VISUAL_BLIND_READ":
            return self.complete_blind_read(workflow_id, task_id, token, result)
        require(task["kind"] not in VISUAL_KINDS, "生图、去字、矢量化任务须提交实际文件与调用回执", 422)
        with self.transaction(workflow_id, "TASK_COMPLETE") as w:
            t = self.leased(w, task_id, token)
            {"READ_SOURCE": lambda: self.reading(w, t["binding"], result, t["worker"]),
             "SECOND_READ": lambda: self.second_read(w, t["binding"], result, t["worker"]),
             "CLAIMS": lambda: self.accept_claims(w, t["binding"], result, t["worker"]),
             "SEMANTIC_MAP": lambda: (semantic_map_stage.accept(w, result, t["worker"]), self.snapshot(w, "semantic_map", result)),
             "TOPIC_PASS": lambda: (semantic_map_stage.accept_topic(w, t["binding"], result, t["worker"],
                                                                    [r[0] for r in t["brief"].get("referred_from_other_topics") or []]),
                                    self.snapshot(w, "topic_pass", result)),
             "STRUCTURE": lambda: (structure_stage.accept(w, result, t["worker"]), self.snapshot(w, "structure", result)),
             "STRUCTURE_REVIEW": lambda: (structure_stage.accept_review(w, result, t["worker"]), self.snapshot(w, "structure_review", result)),
             "SUMMARY": lambda: (self.accept_chapter_summary(w, t, result) if t.get("binding") else
                                 self.accept_summary(w, result, t["worker"], t['brief'].get('summary_algorithm'))),
             "SUMMARY_AMEND": lambda: self.accept_summary_amend(w, result, t["worker"]),
             "SUMMARY_REVIEW": lambda: (self.accept_chapter_review(w, t["binding"], result, t["worker"]) if t.get("binding") else
                                        self.accept_summary_review(w, result, t["worker"])),
             "FACTS": lambda: self.accept_facts(w, result, t["worker"]),
             "DECK": lambda: self.accept_deck(w, result, t["worker"]),
             "SEMANTIC_REVIEW": lambda: self.accept_semantic(w, result, t["worker"], t["binding"], t["brief"]),
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
            if t["kind"] == "SUMMARY" and w.get("summary_meta") and not t.get("binding"):
                # every session that saved part of the draft authored this summary
                w["summary_meta"]["contributors"] = sorted({t["worker"], *((t.get("draft") or {}).get("workers") or [])})
        return self.get(workflow_id)

    def save_summary_draft(self, workflow_id: str, task_id: str, token: str, draft: dict):
        """Checkpoint a chunked SUMMARY or its sentence-level SUMMARY_REVIEW. Code records which planned chunks are
        complete (registration for the author, judged rows for the reviewer; structure only), renews the lease and keeps
        the draft on the task, so a later session continues instead of restarting."""
        from factdeck import source_coverage as sc
        require(isinstance(draft, dict), "草稿需为结果对象", 422)
        with self.transaction(workflow_id, "SUMMARY_DRAFT") as w:
            t = self.leased(w, task_id, token)
            plan = t["brief"].get("chunks")
            require(t["kind"] in {"SUMMARY", "SUMMARY_REVIEW"} and plan, "只有分块的SUMMARY / SUMMARY_REVIEW任务可以保存草稿", 422)
            v = self.chapter_view_of(w, t["binding"]) if t.get("binding") else w
            try:
                self._refuse_garbled_draft(t["kind"], draft)
            except (KeyError, TypeError, AttributeError) as error:
                raise WorkflowError(f"草稿结构无效：{error}", 422) from error
            if isinstance(draft.get("fragment_chunks"), list):
                # chunk-parallel: one session's section(s) for its chunk(s), merged into the task's draft by code
                from factdeck import summary_fragments as sf
                fragment = {k: x for k, x in draft.items() if k != "fragment_chunks"}
                old = t.get("draft") or {}
                try:
                    if t["kind"] == "SUMMARY":
                        prefix = (t["binding"] + "-") if t.get("binding") else ""
                        require(all(str(x.get("id", "")).startswith(prefix) for x in fragment.get("sections") or []),
                                f"片段的章节编号须以“{prefix}”开头", 422)
                        draft = sf.apply(old.get("summary") or t["brief"].get("revision_base") or {}, fragment,
                                         {u["id"]: u["page_id"] for u in all_units(v)})
                    else:
                        draft = sf.apply_review(old.get("result") or {}, fragment)
                except ValueError as error:
                    raise WorkflowError(f"片段无法合并：{error}", 422) from error
            try:
                if t["kind"] == "SUMMARY":
                    progress = sc.chunk_progress(draft, all_units(v), all_claims(v), plan)
                    done = [c["index"] for c in progress if not c["open_issues"]]
                else:
                    progress = sc.review_progress(t["brief"]["coverage_targets"], draft.get("coverage_review"),
                                                  sc.point_texts(v["summary"]), plan)
                    done = [c["index"] for c in progress if not c["problem"]]
            except (KeyError, TypeError, ValueError, AttributeError) as error:
                raise WorkflowError(f"草稿结构无效：{error}", 422) from error
            before = set((t.get("draft") or {}).get("done_chunks") or [])
            lost = sorted(before - set(done))
            require(not lost, f"草稿丢失了已完成的块 {lost}：请在项目中的当前草稿上续写（tools/chunk_packet.py --draft-out 取出当前草稿），不要从头另写", 422)
            t["draft"] = {("summary" if t["kind"] == "SUMMARY" else "result"): copy.deepcopy(draft), "saved_at": now(),
                          "done_chunks": done, "progress": progress,
                          "workers": sorted({*((t.get("draft") or {}).get("workers") or []), t["worker"]}),
                          "path": self.snapshot(w, "summary_draft" if t["kind"] == "SUMMARY" else "summary_review_draft", draft)}
            if set(done) - before:
                t["attempts"] = 0          # real progress: a session that stops after a chunk is not a failed attempt
            t["lease_until"] = time.time() + LEASE_SECONDS
            return {"task_id": task_id, "done_chunks": done, "chunks": len(plan), "progress": progress, "lease_until": t["lease_until"]}

    @staticmethod
    def _refuse_garbled_draft(kind: str, draft: dict):
        """Text lost to an encoding failure is refused when it is saved, not first at completion: a fragment or draft
        whose authored fields are mostly '?' cannot be merged into a chapter."""
        from factdeck.summary_evidence import ALGORITHM, garbled, authored_text, garbled_paths
        if kind == "SUMMARY":
            if draft.get("summary_algorithm") != ALGORITHM:      # the same scope as the check at completion
                return
            bad = [f for f, x in authored_text(draft) if garbled(x)]
        else:
            bad = garbled_paths(draft)
        require(not bad, "以下文字已损坏（多为?）：" + "、".join(bad[:8]) + (f" 等{len(bad)}处" if len(bad) > 8 else "")
                + "。常见原因是写入时的编码：在 Windows PowerShell 中经管道把中文传给 Python 前，须设 "
                  "$OutputEncoding=[System.Text.UTF8Encoding]::new($false) 和 $env:PYTHONUTF8='1'（或把脚本写成 .py 文件再运行）；"
                  "然后按原文重写这些文字再保存", 422)

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
        require(kind in {"structure", "content", "style"}, "确认类型无效", 422)
        require(all(str(record.get(k, "")).strip() for k in ("customer", "operator", "method")), "需记录客户、操作人和确认方式", 422)
        with self.transaction(workflow_id, f"APPROVE_{kind.upper()}") as w:
            self.source_integrity(w)
            if kind == "structure":
                require(w.get("structure_first") and structure_stage.structure_current(w), "没有当前版本的课程结构")
                require(structure_stage.review_current(w), "课程结构须先经独立审查")
                require(not structure_stage.review_blockers(w), "结构审查的问题需先修订结构")
                expected = digest(w["structure"]["result"])
            elif kind == "content" and semantic_map_stage.enabled(w):
                require(fully_read(w) and semantic_map_stage.draft_ready(w) and summary_current(w), "请先完成语义地图和全部主题的重点梳理")
                pending = semantic_map_stage.unconfirmed_sentences(w)
                require(not pending, "初稿引用了尚未核定的图片/图表转录，请先完成第二次独立读取或人工对照确认：" + "、".join(pending[:10]))
                expected = digest(w["summary"])
            elif kind == "content":
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
            if kind == "content" and semantic_map_stage.enabled(w):    # the confirmed draft's sentences are the fact store
                self.accept_facts(w, semantic_map_stage.draft_facts(w), semantic_map_stage.FACTS_AUTHOR)
        return self.get(workflow_id)

    def confirm_derivation(self, workflow_id: str, der_id: str, record: dict):
        require(record.get("decision") in {"CONFIRM", "REJECT"} and str(record.get("reviewer", "")).strip(), "需填写审核人和结论", 422)
        with self.transaction(workflow_id, "CONFIRM_DERIVATION") as w:
            require(w["facts"], "尚无事实库")
            d = next((d for d in w["facts"]["result"].get("derivations", []) if d.get("id") == der_id), None)
            require(d, "推导不存在", 404)
            if record["decision"] == "CONFIRM":
                checked = next((x for x in verified(w)["derivations"] if x.get("id") == der_id), None)
                require(checked and not checked.get("problems"), "推导证据无效，不能确认", 422)
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
            if rec["changed"]:     # a corrected arrow cell changes the source's diagram candidates
                sid = unit_id.split(":")[0]
                src = next((x for x in w["sources"] if x["id"] == sid), None)
                if src is not None:
                    src["relations"] = relation_candidates([x for x in all_units(w) if x["id"].split(":")[0] == sid])
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
            i = next((i for i in ledger.issues(w, "summary") if issue_id in (i["id"], i.get("legacy_id"))), None)
            if i and str(i.get("check", "")).startswith("SUMMARY:"):      # a chapter's issue: that chapter's review
                c = chapter_of(w, i["check"].split(":", 1)[1])
                require(chapter_review_current(w, c), "该章没有当前的总结审查")
                ledger.rule(w, "summary", issue_id, record, chapter_review_input(w, c))
                return self.get(workflow_id)
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
            spec = selected_spec(w["deck"]["result"])
            from factdeck.template_lib import render_deck
            if render_deck.is_template_deck(spec):
                report = render_deck.render(spec, v["facts"], sources, folder, v["terms"],
                                            teaching_notes=deck_teaching_notes(w, spec))
            else:
                require(w.get("generation_route") != TEMPLATE_ROUTE, "本项目走模板库主线，页面规格须为模板页，请重新安排 DECK")
                report = do_render(spec, v["facts"], sources, folder, self.render_theme(w), v["terms"], figures=figs,
                                   teaching_notes=deck_teaching_notes(w, spec))
        except WorkflowError:
            raise
        except ValueError as e:
            raise WorkflowError(f"渲染未通过：{e}", 422)
        except ImportError as e:
            raise WorkflowError(f"渲染环境缺失：{e}；请安装 factdeck/requirements.txt 并执行 playwright install chromium", 503)
        # per page for the reviewer: the page's own design note, its visual signals (open or justified) and what the
        # semantic reviewer must look at (emphasis inside quotes, excerpts that leave text out, sentences split into steps)
        rpages = [{"id": p["id"], "file": f"slide{i:02d}.png", "sha256": sha((folder / f"slide{i:02d}.png").read_bytes()),
                   "design": sl.get("design") or {}, "signals": sl.get("signals") or [], "review": sl.get("review") or [],
                   "occupancy": sl.get("occupancy"), "hole": (sl.get("hole") or {}).get("share"), "metrics": sl.get("metrics") or {}}
                  for i, (p, sl) in enumerate(zip(selected_spec(w["deck"]["result"])["pages"], report["slides"]), 1)]
        record = {"input_sha256": key, "draft": draft, "path": relative, "at": now(), "hard_errors": report["hard_errors"],
                  **({"route": TEMPLATE_ROUTE, "trace_report": report["trace_report"], "stats": report["stats"]}
                     if report.get("route") == TEMPLATE_ROUTE else {}),
                  "summary": report["summary"], "pages": rpages,
                  "files": {n: sha((folder / n).read_bytes()) for n in ("deck.pptx", "deck.pdf", "deck.html", "render_report.json")
                            + (("template/trace.md", "template/trace.json") if report.get("route") == TEMPLATE_ROUTE else ())},
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
                      "semantic_review": w["semantic_review"], "semantic_checks": {c: {k: x.get(k) for k in ("reviewer", "reviewers", "at", "round", "counts", "carried", "unchecked", "regression", "viewed_source_pages")}
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
            traced = ("trace.md", "trace.json") if r.get("trace_report") else ()   # template route: per-page trace report
            for n in traced:
                shutil.copyfile(src / "template" / n, folder / n)
            with zipfile.ZipFile(folder / "delivery.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for n in ("deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json") + traced:
                    z.write(folder / n, n)
                for i, p in enumerate(r["pages"], 1):
                    z.write(src / p["file"], f"pages/slide-{i:03d}.png")
                if r.get("route") == VISUAL_ROUTE:
                    z.writestr("visual/manifest.json", json.dumps(w["generation"], ensure_ascii=False, indent=2))
                    for i, p in enumerate(w["generation"]["pages"], 1):
                        for kind, asset in p["assets"].items():
                            z.write(self.path(asset["path"]), f"visual/page-{i:03d}/{kind}{Path(asset['path']).suffix}")
                            z.write(self.path(asset["receipt_path"]), f"visual/page-{i:03d}/{kind}-receipt.json")
            files = ("deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json") + traced + ("delivery.zip",)
            w["deliveries"].append({"version": version, "at": now(), "subject_sha256": delivery_subject(w), "path": relative,
                                    "files": [{"name": n, "sha256": sha((folder / n).read_bytes())} for n in files]})
        return self.get(workflow_id)
