"""FactDeck mainline workflow: any source material → summary → fact store → deck → PPT.

Stages (each bound to the versions it was made from; changing an input makes
everything downstream stale automatically):

  READ_SOURCE     model reads every source page; pictures/charts are transcribed
  SUMMARY         model writes full_source_summary.v2 covering every page and outline item
  content approval  customer confirms the summary
  FACTS           model proposes facts as verbatim quotes of source units; code verifies
  DECK            model writes pages that reference facts only, per the requirements
  SECOND_READ     a different worker re-transcribes pictures/charts blind; code compares
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
import json
import shutil
import time
import zipfile
from pathlib import Path

from app.fact57098 import Store as _BaseStore, WorkflowError, digest, sha, now, uid, require, parse_outline, ROOT
from factdeck import facts as fx
from factdeck.deck import check as deck_check, LAYOUTS
from factdeck.ingest import extract_all, to_dicts, transcription_units, IngestError
from factdeck.lexicon import canon
from factdeck.render import THEMES

TEMPLATE = "factdeck.v1"
ENGINE_VERSION = "factdeck-render.1"
MAX_UPLOAD = 40 * 1024 * 1024
SAMPLE_PAGES = 5
DEIDENTIFIED = ("NO_PATIENT_CONTENT", "DEIDENTIFIED", "IDENTIFIABLE")
KINDS = ("READ_SOURCE", "SECOND_READ", "SUMMARY", "FACTS", "DECK", "SEMANTIC_REVIEW")
REQUIREMENT_KEYS = {"audience", "purpose", "duration_minutes", "target_pages", "emphasis", "tone", "notes"}


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
        for u in s["transcriptions"]:
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
        out[g["id"]] = {"source_id": g["source_id"], "location": g["location"], "pending": pending, "rejected": rejected,
                        "review": r, "licence": lic, "open_cells": open_cells.get(g["id"], [])}
    return out


def fully_read(w: dict) -> bool:
    return bool(w["sources"]) and all(p["reading"] for p in pages(w).values())


def input_hash(w: dict) -> str:
    return digest({"sources": [{"sha256": s["sha256"], "readings": [p["reading"] for p in s["pages"]],
                                "transcriptions": [{k: u[k] for k in ("id", "location", "text")} for u in s["transcriptions"]]}
                               for s in w["sources"]],
                   "outline": w["outline"], "context": w["context"]})


def summary_current(w: dict) -> bool:
    return bool(w["summary"]) and w["summary"]["input_sha256"] == input_hash(w)


def content_approved(w: dict) -> bool:
    a = w["content_approval"]
    return summary_current(w) and bool(a) and a["subject_sha256"] == digest(w["summary"])


def facts_input(w: dict) -> str:
    return digest({"summary": digest(w["summary"]) if w["summary"] else None})


def facts_current(w: dict) -> bool:
    return content_approved(w) and bool(w["facts"]) and w["facts"]["input_sha256"] == facts_input(w)


def facts_sha(w: dict) -> str | None:
    return w["facts"]["result_sha256"] if w["facts"] else None


def verified(w: dict) -> dict:
    """Run the fact gate with the current confirmations."""
    if not w["facts"]:
        return {"facts": {}, "derivations": [], "conflicts": [], "terms": [], "objects": ([], [], [])}
    F, D, T = fx.parse(w["facts"]["result"])
    decisions = w["confirmations"]["derivations"]
    for d in D:
        rec = decisions.get(d.id)
        if rec and rec["derivation_sha256"] == digest({"claim": d.claim, "rule": d.rule, "evidence": d.evidence}):
            d.confirmed, d.rejected = rec["decision"] == "CONFIRM", rec["decision"] == "REJECT"
    resolutions = {k: v["fact_id"] for k, v in w["confirmations"]["resolutions"].items()}
    conflicts = fx.verify(F, D, all_units(w), resolutions, T, figure_states(w))
    data = fx.as_dict(F, D, conflicts)
    return {"facts": {f["id"]: f for f in data["facts"]}, "derivations": data["derivations"], "conflicts": data["conflicts"],
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
    return deck_check(w["deck"]["result"], v["facts"], v["terms"], w["outline"], w["summary"]["sections"], w["requirements"])


def pending_items(w: dict, v: dict, chk: dict) -> list[dict]:
    """Human confirmations still needed for facts that appear on pages."""
    used = {fid for p in chk["pages"] for fid in p["facts"]}
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
                          "second_read": u.get("second_read"), "reason": u.get("confirmation_reason", "尚无一致的第二次独立转录")})
    for fig in sorted({v["facts"][f]["figure"] for f in used if v["facts"][f].get("figure")}):
        st, g = states[fig], figs[fig]
        base = {"id": fig, "source_id": g["source_id"], "location": g["location"], "sha256": g["sha256"],
                "width": g["width"], "height": g["height"], "reading": figure_reading(w, fig)}
        if not st["review"]:
            items.append({"kind": "figure_review", **base})
        if not st["licence"]:
            items.append({"kind": "figure_licence", **base})
    return items


def fig_url(w: dict, fig_id: str) -> str:
    return f"/api/deck/workflows/{w['id']}/figures/{fig_id}/file"


def semantic_fact(w: dict, v: dict, by_unit: dict, fid: str) -> dict:
    f = v["facts"][fid]
    if f.get("figure"):
        return {"id": fid, "figure": f["figure"], "figure_url": fig_url(w, f["figure"]), "caption": f.get("caption", []),
                "reader_note": (figure_reading(w, f["figure"]) or {}).get("note", ""), "location": f["location"]}
    return {"id": fid, "display": f["display"] or f["quote"], "quote": f["quote"], "dropped_from_quote": f["dropped"],
            "unit_text": by_unit[f["unit"]]["text"], "location": f["location"]}


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
    r = w["semantic_review"]
    return deck_current(w) and bool(r) and r["input_sha256"] == semantic_input(w)


def open_issues(w: dict) -> list[dict]:
    if not semantic_current(w):
        return []
    dismissed = w["semantic_review"]["dismissed"]
    return [i for i in w["semantic_review"]["issues"] if i["severity"] == "BLOCKER" and i["id"] not in dismissed]


def render_input(w: dict, v: dict | None = None) -> str | None:
    if not deck_current(w):
        return None
    v = v or verified(w)
    shown = {f["figure"] for f in v["facts"].values() if f.get("figure")}
    states = figure_states(w) if shown else {}
    return digest({"engine": ENGINE_VERSION, "deck": w["deck"]["result"], "theme": w["theme"],
                   "facts": {k: {x: f[x] for x in ("quote", "display", "status", "needs_confirmation", "location", "source_id", "figure", "caption")}
                             for k, f in v["facts"].items()},
                   "figures": {k: {"sha256": g["sha256"], "review": states[k]["review"], "licence": states[k]["licence"]}
                               for k, g in figures(w).items() if k in shown},
                   "sources": [{k: s[k] for k in ("id", "filename")} for s in w["sources"]]})


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
    if not summary_current(w): return "SUMMARY_REQUIRED", ["需要当前版本的全文总结"]
    if not content_approved(w): return "CONTENT_CONFIRMATION", ["客户尚未确认全文总结"]
    if not facts_current(w): return "FACTS_REQUIRED", ["需要根据已确认总结建立事实库"]
    if not deck_current(w): return "DECK_REQUIRED", ["需要根据需求编写页面规格"]
    v = verified(w)
    chk = checked(w, v)
    if chk["errors"]:
        return "DECK_REVISION", [f"页面规格有 {chk['errors']} 处错误"]
    todo = []
    pend = pending_items(w, v, chk)
    if pend: todo.append(f"待人工确认 {len(pend)} 项（推导/冲突/转录/原件图）")
    if not semantic_current(w): todo.append("需要独立语义审查")
    elif open_issues(w): todo.append(f"语义审查有 {len(open_issues(w))} 个阻断问题")
    if todo:
        stage = "CONFIRMATIONS_REQUIRED" if pend else ("SEMANTIC_REVIEW_REQUIRED" if not semantic_current(w) else "SEMANTIC_ISSUES")
        return stage, todo
    if not render_current(w, v): return "RENDER_REQUIRED", ["需要渲染当前版本"]
    rpages = w["render"]["pages"]
    if not all(reviewed(w, p["id"]) for p in rpages[:SAMPLE_PAGES]): return "SAMPLES_REVIEW", ["前5页需逐页审核"]
    if not style_approved(w): return "STYLE_CONFIRMATION", ["客户尚未确认样页风格"]
    if not all(reviewed(w, p["id"]) for p in rpages): return "PAGE_REVIEW", ["其余页面需逐页审核"]
    if w["deliveries"] and w["deliveries"][-1]["subject_sha256"] == delivery_subject(w):
        return "DELIVERED", []
    return "READY_TO_EXPORT", []


def stage(w: dict) -> str:
    return status(w)[0]


# ------------------------------------------------------------------ store
class Store(_BaseStore):
    def __init__(self, data_root: Path | None = None):
        super().__init__(data_root or ROOT / "data" / "deckflow")

    # ---- project
    def create(self, title: str, outline: str = "", requirements: dict | None = None, context: dict | None = None, theme: str = "navy-teal") -> dict:
        require(bool(title.strip()), "请填写项目名称", 422)
        w = {"id": uid("deck"), "title": title.strip(), "revision": 1, "created_at": now(), "updated_at": now(), "template": TEMPLATE,
             "context": context or {"language": "zh-CN", "external_research_allowed": False},
             "requirements": self._requirements(requirements or {}), "outline": parse_outline(outline), "theme": self._theme(theme),
             "sources": [], "next_source_no": 1, "summary": None, "content_approval": None, "facts": None,
             "confirmations": {"derivations": {}, "resolutions": {}, "transcriptions": {}, "figures": {}, "figure_licenses": {}},
             "deck": None, "semantic_review": None, "render": None, "page_reviews": {}, "style_approval": None,
             "approvals": [], "tasks": [], "deliveries": []}
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
    def _theme(theme: str) -> str:
        require(theme in THEMES, "可选配色：" + "、".join(THEMES), 422)
        return theme

    def get(self, workflow_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT state FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        require(row, "项目不存在", 404)
        w = json.loads(row[0])
        w["stage"], w["open_items"] = status(w)
        w["approval_subjects"] = {"content": digest(w["summary"]) if summary_current(w) else None,
                                  "style": sample_hash(w) if render_current(w) else None}
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
                w["outline"] = parse_outline(changes["outline"])
            if "context" in changes:
                w["context"] = changes["context"]
            if "requirements" in changes:
                w["requirements"] = self._requirements(changes["requirements"])
            if "theme" in changes:
                w["theme"] = self._theme(changes["theme"])
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
                                 "figures": fig_rows})
            w["next_source_no"] += 1
            self.cancel_stale(w)
        return self.get(workflow_id)

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
        transcriptions = []
        for page in source["pages"]:
            row = by_id[page["id"]]
            cat = row.get("classification")
            require(cat in {"SUBSTANTIVE", "REFERENCE", "EMPTY"}, "需标记正文、参考文献或空白页", 422)
            require(not page["requires_visual"] or row.get("visual_inspected") is True, f"{page['location']} 必须核对原件视觉内容", 422)
            require(cat != "EMPTY" or (not page["unit_ids"] and str(row.get("reason", "")).strip()), "只有无文字页可标为空白，并需说明原因", 422)
            cells = row.get("transcription") or []
            require(isinstance(cells, list), "transcription 需为列表", 422)
            on_page = [g["id"] for g in source.get("figures", []) if g["page_id"] == page["id"]]
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
        for u in transcriptions:
            w["confirmations"]["transcriptions"].pop(u["id"], None)

    def second_read(self, w: dict, source_id: str, result: dict, reader: str):
        source = next((s for s in w["sources"] if s["id"] == source_id), None)
        require(source and source["transcriptions"], "该资料没有需复核的转录", 404)
        require(result.get("source_sha256") == source["sha256"], "复核结果对应的资料已变更")
        first = {u["reader"] for u in source["transcriptions"]}
        require(reader not in first, "第二次转录须由不同的执行端完成", 422)
        cells = {c.get("unit_id"): c for c in result.get("cells") or []}
        require(set(cells) == {u["id"] for u in source["transcriptions"]}, "需逐个提交全部转录单元的独立读取结果", 422)
        for u in source["transcriptions"]:
            text = str(cells[u["id"]].get("text", ""))
            u["second_read"] = {"reader": reader, "at": now(), "text": text, "agree": canon(text) == canon(u["text"])}

    def accept_summary(self, w: dict, result: dict):
        self.source_integrity(w)
        require(fully_read(w), "全部资料完成阅读后才能提交总结")
        require(result.get("schema_version") == "full_source_summary.v2", "总结版本需为full_source_summary.v2", 422)
        require(result.get("input_sha256") == input_hash(w), "总结对应的资料、提纲或阅读版本已过期")
        require(len(str(result.get("overall_summary", "")).strip()) >= 40, "需提供有实质内容的全文总结", 422)
        sections = result.get("sections")
        require(isinstance(sections, list) and sections, "需提供章节总结", 422)
        ids = [s.get("id") for s in sections]
        require(all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)), "章节ID不能为空或重复", 422)
        known, covered = pages(w), set()
        for s in sections:
            require(bool(str(s.get("title", "")).strip()) and len(str(s.get("summary", "")).strip()) >= 20, "章节标题及总结不能为空", 422)
            refs = s.get("source_page_ids")
            require(isinstance(refs, list) and refs and set(refs) <= set(known), "章节需引用有效的资料页面", 422)
            covered.update(refs)
        require(set(known) <= covered, "全文总结未覆盖全部资料页面（含参考文献与空白说明）", 422)
        mapping = result.get("outline_coverage", [])
        outline_ids = {o["id"] for o in w["outline"]}
        require(isinstance(mapping, list) and len(mapping) == len(outline_ids) and {m.get("outline_id") for m in mapping} == outline_ids,
                "总结需覆盖全部教学提纲条目", 422)
        for m in mapping:
            require(m.get("section_ids") and set(m["section_ids"]) <= set(ids), "提纲映射需指向有效章节", 422)
        require(isinstance(result.get("pending_issues"), list), "需列出待解决问题；无问题时为空列表", 422)
        self.snapshot(w, "summary", result)
        w["summary"] = copy.deepcopy(result)
        w["content_approval"] = None

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
        require(accepted, "没有一条事实通过核对：" + "；".join(f"{f.id}：{'；'.join(f.problems)}" for f in F[:5]), 422)
        self.snapshot(w, "facts", result)
        w["facts"] = {"result": copy.deepcopy(result), "result_sha256": digest(result), "input_sha256": facts_input(w),
                      "author": author, "at": now(), "accepted": len(accepted), "rejected": len(F) - len(accepted)}

    def accept_deck(self, w: dict, result: dict, author: str):
        require(facts_current(w), "请先建立当前版本的事实库")
        require(result.get("facts_sha256") == facts_sha(w), "页面规格对应的事实库已过期")
        deck = {k: v for k, v in result.items() if k != "facts_sha256"}
        v = verified(w)
        chk = deck_check(deck, v["facts"], v["terms"], w["outline"], w["summary"]["sections"], w["requirements"])
        if chk["errors"]:
            problems = chk["deck_errors"] + [f"{p['id']}：{e}" for p in chk["pages"] for e in p["errors"]]
            raise WorkflowError("页面规格未通过：" + "；".join(problems[:12]) + ("…" if len(problems) > 12 else ""), 422)
        if deck.get("theme"):
            w["theme"] = self._theme(deck["theme"])
        self.snapshot(w, "deck", result)
        w["deck"] = {"result": deck, "result_sha256": digest(deck), "input_sha256": deck_input(w), "author": author, "at": now(),
                     "warnings": chk["warnings"], "coverage": chk["coverage"]}

    def accept_semantic(self, w: dict, result: dict, reviewer: str):
        require(deck_current(w), "没有当前版本的页面规格")
        require(reviewer != w["deck"]["author"] and reviewer != w["facts"]["author"], "语义审查须由编写事实库和页面之外的执行端完成", 422)
        require(result.get("input_sha256") == semantic_input(w), "审查对应的页面或事实库已过期")
        rows = result.get("pages")
        deck_pages = [p["id"] for p in w["deck"]["result"]["pages"]]
        require(isinstance(rows, list) and [r.get("page_id") for r in rows] == deck_pages, "需按顺序逐页给出审查结论", 422)
        issues = []
        for r in rows:
            require(r.get("verdict") in {"SUPPORTED", "ISSUES"}, "每页结论需为SUPPORTED或ISSUES", 422)
            items = r.get("issues") or []
            require((r["verdict"] == "ISSUES") == bool(items), "有问题时需列出问题，没有问题时结论为SUPPORTED", 422)
            for i, it in enumerate(items, 1):
                require(it.get("severity") in {"BLOCKER", "NOTE"} and str(it.get("problem", "")).strip(), "问题需给出严重程度和说明", 422)
                issues.append({"id": f"{r['page_id']}#{i}", "page_id": r["page_id"], "severity": it["severity"],
                               "ref": str(it.get("ref", "")), "problem": str(it["problem"])[:2000]})
        coverage = result.get("coverage") or []
        for c in coverage:
            if c.get("missing") and str(c.get("problem", "")).strip():
                issues.append({"id": f"coverage#{c.get('section_id')}", "page_id": None, "severity": c.get("severity", "BLOCKER"),
                               "ref": str(c.get("section_id", "")), "problem": str(c["problem"])[:2000]})
        self.snapshot(w, "semantic_review", result)
        w["semantic_review"] = {"input_sha256": semantic_input(w), "reviewer": reviewer, "at": now(), "issues": issues, "dismissed": {}}

    # ---- tasks
    def brief(self, w: dict, kind: str, binding: str | None) -> dict:
        req = {"requirements": w["requirements"], "outline": w["outline"], "context": w["context"]}
        if kind == "READ_SOURCE":
            s = next(s for s in w["sources"] if s["id"] == binding)
            return {"kind": kind, "source": {k: s[k] for k in ("id", "filename", "sha256", "kind")},
                    "source_url": f"/api/deck/workflows/{w['id']}/sources/{s['id']}/file",
                    "pages": [{**{k: p[k] for k in ("id", "location", "text", "requires_visual")},
                               "figures": [{**{k: g[k] for k in ("id", "location", "width", "height")}, "url": fig_url(w, g["id"])}
                                           for g in s.get("figures", []) if g["page_id"] == p["id"]]} for p in s["pages"]],
                    "rules": ["逐页阅读原件；requires_visual 的页面必须查看原始画面（图片、图表、表格截图、流程图）。",
                              "图/表中的文字和数字逐格转录到 transcription（id、location、text），只转录看到的内容，不推测、不补全。",
                              "程序从原件取出的图（figures）逐张查看并在 figures 中说明：note 写画面内容（仅供审核，不上页）；"
                              "caption_unit_ids 填本页中作为该图图题/图注的文字单元；图中若可能有患者姓名、编号、日期、面部等信息，"
                              "may_contain_patient_info 填 true。图中的文字逐格转录，并在该转录格上写 figure: 图编号。",
                              "参考文献页标 REFERENCE；无任何内容的页标 EMPTY 并说明原因。"],
                    "result_contract": {"source_sha256": s["sha256"], "pages": [{"id": p["id"], "classification": "SUBSTANTIVE",
                                        "visual_inspected": False, "note": "", "reason": "", "transcription": [],
                                        "figures": [{"id": g["id"], "note": "", "caption_unit_ids": [], "may_contain_patient_info": False}
                                                    for g in s.get("figures", []) if g["page_id"] == p["id"]]} for p in s["pages"]]}}
        if kind == "SECOND_READ":
            s = next(s for s in w["sources"] if s["id"] == binding)
            return {"kind": kind, "source": {k: s[k] for k in ("id", "filename", "sha256")},
                    "source_url": f"/api/deck/workflows/{w['id']}/sources/{s['id']}/file",
                    "cells": [{"unit_id": u["id"], "location": u["location"]} for u in s["transcriptions"]],
                    "rules": ["独立查看原件，按位置逐格读出文字；不得参考第一次转录（本合同不提供）。", "看不清时如实写出看到的内容并在文字中标注“[不清]”。"],
                    "result_contract": {"source_sha256": s["sha256"], "cells": [{"unit_id": u["id"], "text": ""} for u in s["transcriptions"]]}}
        if kind == "SUMMARY":
            return {"kind": kind, **req, "input_sha256": input_hash(w),
                    "sources": [{"id": s["id"], "filename": s["filename"], "pages": [{**{k: p[k] for k in ("id", "location", "text")}, "reading": p["reading"]} for p in s["pages"]],
                                 "transcriptions": [{k: u[k] for k in ("id", "location", "text")} for u in s["transcriptions"]]} for s in w["sources"]],
                    "rules": ["全文综合总结；不得新增资料以外的事实。", "所有资料页面都要被章节引用；教学提纲全部映射到章节。",
                              "保留人群、剂量、阈值、时间、证据等级和限制条件；不确定或冲突之处列入 pending_issues。"],
                    "result_contract": {"schema_version": "full_source_summary.v2", "input_sha256": input_hash(w), "overall_summary": "",
                                        "sections": [{"id": "s1", "title": "", "summary": "", "source_page_ids": []}],
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
                              "需要展示原件中的图时，建图事实 {id, figure: 图编号, caption: [图题的文字事实id], section_ids}，不写 unit/quote。"
                              "关于图的任何说法只能引用资料文字；不得根据图读数、推算或描述趋势。图须经截取/去标识确认和客户逐张许可后才能正式上页。"],
                    "result_contract": {"summary_sha256": digest(w["summary"]), "terms": [], "facts": [
                        {"id": "f1", "unit": "来源单元id", "quote": "逐字引文", "display": "", "entity": "", "attribute": "", "value": "",
                         "derivation": "", "note": "", "section_ids": []}], "derivations": []}}
        if kind == "DECK":
            v = verified(w)
            return {"kind": kind, **req, "summary": w["summary"], "theme": w["theme"], "themes": list(THEMES),
                    "facts": [{k: f[k] for k in ("id", "display", "quote", "location", "source_id", "section_ids", "needs_confirmation", "figure", "caption")}
                              for f in v["facts"].values() if f["status"] == "ACCEPTED"],
                    "layouts": {k: sorted(req_keys) for k, (req_keys, _) in LAYOUTS.items()},
                    "rules": ["按需求（受众、目的、时长、目标页数、重点）组织页面；一页一个认知单元，内容多就拆页。",
                              "页面上的实质内容只能是 {\"fact\": id}；作者文字 {\"text\": ...} 只做组织和命名，不得包含数字、比较、药名/专有名称、评价或方向性措辞。",
                              "每页标注 outline_ids 与 section_ids；全部提纲条目都要有页面；未上页的总结章节写入 omissions 并给出原因。",
                              "流程/机制图用 flow：节点给网格位置 col 0–4、row 0–3，每条箭头 [起点, 终点, 支持事实]，支持事实须在本页引用。",
                              "表格每格是引用列表；列头是作者文字。glossary 中的词须出现在对应事实引文中，可用于作者文字。",
                              "原件图用 figure 版式：figure 放图事实 {\"fact\": id}，side 放 0–3 条文字事实；图注由程序随图显示。图事实只能放在 figure 位置，图上不加任何标注。"],
                    "result_contract": {"facts_sha256": facts_sha(w), "title": w["title"], "theme": w["theme"], "glossary": [], "omissions": [],
                                        "pages": [{"id": "cover", "layout": "cover", "title": {"text": ""}, "outline_ids": [], "section_ids": []}]}}
        # SEMANTIC_REVIEW
        v = verified(w)
        by_unit = {u["id"]: u for u in all_units(w)}
        chk = checked(w, v)
        view = []
        for page, res in zip(w["deck"]["result"]["pages"], chk["pages"]):
            view.append({"page": page, "facts": [semantic_fact(w, v, by_unit, fid) for fid in res["facts"]]})
        return {"kind": "SEMANTIC_REVIEW", **req, "input_sha256": semantic_input(w), "summary": w["summary"], "pages": view,
                "coverage": w["deck"]["coverage"],
                "rules": ["逐页判断：页面整体表达的意思是否被所引原文支持。重点检查：节选是否丢掉了人群、条件、时间、否定或不确定性（见 dropped_from_quote）；",
                          "并列或对比是否暗示原文没有的比较或因果；箭头方向与原文是否一致；作者文字（标题、导语、标签）是否带出原文没有的判断；",
                          "对照总结，是否漏掉了需求或提纲要求讲到的重要内容。严重问题标 BLOCKER，一般建议标 NOTE。不得给出医学放行结论。",
                          "有原件图的页面须打开图片（url）查看：页面文字是否说出了图外的结论，图与相邻文字放在一起是否暗示原文没有的比较或因果。"],
                "result_contract": {"input_sha256": semantic_input(w), "pages": [{"page_id": p["id"], "verdict": "SUPPORTED", "issues": []}
                                                                                   for p in w["deck"]["result"]["pages"]],
                                    "coverage": [{"section_id": s["id"], "missing": False, "problem": ""} for s in w["summary"]["sections"]]}}

    def fingerprint(self, w: dict, kind: str, binding: str | None) -> str:
        if kind == "READ_SOURCE":
            return next(s["sha256"] for s in w["sources"] if s["id"] == binding)
        if kind == "SECOND_READ":
            s = next(s for s in w["sources"] if s["id"] == binding)
            return digest({"sha": s["sha256"], "cells": [(u["id"], u["text"]) for u in s["transcriptions"]]})
        return {"SUMMARY": input_hash, "FACTS": facts_input, "DECK": deck_input, "SEMANTIC_REVIEW": semantic_input}[kind](w)

    def queue(self, workflow_id: str, kind: str, page_ids=None):
        require(kind in KINDS, "任务类型无效", 422)
        with self.transaction(workflow_id, "QUEUE_" + kind) as w:
            if kind == "READ_SOURCE":
                require(w["sources"], "请先导入资料")
                bindings = [s["id"] for s in w["sources"] if not all(p["reading"] for p in s["pages"])]
            elif kind == "SECOND_READ":
                bindings = [s["id"] for s in w["sources"] if s["transcriptions"] and any(not u.get("second_read") for u in s["transcriptions"])]
                require(bindings, "没有需要第二次独立转录的资料")
            elif kind == "SUMMARY":
                require(fully_read(w), "请先完成全部资料阅读")
                bindings = [None]
            elif kind == "FACTS":
                require(content_approved(w), "请先完成客户全文内容确认")
                bindings = [None]
            elif kind == "DECK":
                require(facts_current(w), "请先建立当前版本的事实库")
                bindings = [None]
            else:
                require(deck_current(w), "请先完成页面规格")
                bindings = [None]
            for b in bindings:
                fp = self.fingerprint(w, kind, b)
                if any(t["kind"] == kind and t["binding"] == b and t["input_sha256"] == fp and t["status"] in {"PENDING", "RUNNING"} for t in w["tasks"]):
                    continue
                w["tasks"].append({"id": uid("task"), "kind": kind, "binding": b, "input_sha256": fp, "status": "PENDING", "attempts": 0,
                                   "created_at": now(), "worker": None, "lease_token": None, "lease_until": 0, "error": None,
                                   "brief": self.brief(w, kind, b)})
        return self.get(workflow_id)

    def task_current(self, w: dict, t: dict) -> bool:
        try:
            if t["kind"] in {"READ_SOURCE", "SECOND_READ"} and not any(s["id"] == t["binding"] for s in w["sources"]):
                return False
            if t["kind"] == "SUMMARY" and not fully_read(w): return False
            if t["kind"] == "FACTS" and not content_approved(w): return False
            if t["kind"] == "DECK" and not facts_current(w): return False
            if t["kind"] == "SEMANTIC_REVIEW" and not deck_current(w): return False
            return self.fingerprint(w, t["kind"], t["binding"]) == t["input_sha256"]
        except (StopIteration, KeyError, TypeError):
            return False

    def complete(self, workflow_id: str, task_id: str, token: str, result: dict):
        with self.transaction(workflow_id, "TASK_COMPLETE") as w:
            t = self.leased(w, task_id, token)
            {"READ_SOURCE": lambda: self.reading(w, t["binding"], result, t["worker"]),
             "SECOND_READ": lambda: self.second_read(w, t["binding"], result, t["worker"]),
             "SUMMARY": lambda: self.accept_summary(w, result),
             "FACTS": lambda: self.accept_facts(w, result, t["worker"]),
             "DECK": lambda: self.accept_deck(w, result, t["worker"]),
             "SEMANTIC_REVIEW": lambda: self.accept_semantic(w, result, t["worker"])}[t["kind"]]()
            t.update(status="COMPLETE", completed_at=now(), lease_token=None, result_sha256=digest(result))
            t["result_path"] = self.snapshot(w, "task_result", result)
            self.cancel_stale(w)
        return self.get(workflow_id)

    def author(self, workflow_id: str, kind: str, result: dict, operator: str):
        """Operator edits (summary / facts / deck) outside the task queue."""
        require(bool(operator.strip()), "请填写编辑人", 422)
        with self.transaction(workflow_id, kind + "_EDIT") as w:
            who = "operator:" + operator.strip()
            {"SUMMARY": lambda: self.accept_summary(w, result), "FACTS": lambda: self.accept_facts(w, result, who),
             "DECK": lambda: self.accept_deck(w, result, who)}[kind]()
            self.cancel_stale(w)
        return self.get(workflow_id)

    # ---- human decisions
    def approval(self, workflow_id: str, kind: str, record: dict):
        require(kind in {"content", "style"}, "确认类型无效", 422)
        require(all(str(record.get(k, "")).strip() for k in ("customer", "operator", "method")), "需记录客户、操作人和确认方式", 422)
        with self.transaction(workflow_id, f"APPROVE_{kind.upper()}") as w:
            self.source_integrity(w)
            if kind == "content":
                require(fully_read(w) and summary_current(w), "请先完成全文阅读和当前版本总结")
                require(not w["summary"]["pending_issues"], "总结中的待解决问题需先处理")
                expected = digest(w["summary"])
            else:
                require(render_current(w) and all(reviewed(w, p["id"]) for p in w["render"]["pages"][:SAMPLE_PAGES]), "前5页须完成逐页审核后才能确认风格")
                expected = sample_hash(w)
            require(record.get("subject_sha256") == expected, "确认稿已更新，请刷新后重新核对")
            a = {"id": uid("approval"), "kind": kind, "at": now(), "subject_sha256": expected, "customer": record["customer"],
                 "operator": record["operator"], "method": record["method"], "feedback": str(record.get("feedback", "")),
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
            u = next((u for s in w["sources"] for u in s["transcriptions"] if u["id"] == unit_id), None)
            require(u, "转录单元不存在", 404)
            rec = {"decision": "CONFIRM", "text": record["text"], "reviewer": record["reviewer"], "at": now(),
                   "changed": canon(record["text"]) != canon(u["text"]), "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            w["confirmations"]["transcriptions"][unit_id] = rec
            self.snapshot(w, "transcription_confirmation", {"unit_id": unit_id, **rec})
        return self.get(workflow_id)

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
            rec = {"figure_sha256": g["sha256"], "crop_complete": True, "deidentified": record["deidentified"],
                   "reviewer": record["reviewer"], "note": str(record.get("note", ""))[:4000], "at": now(),
                   "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
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
        require(str(record.get("reviewer", "")).strip() and str(record.get("reason", "")).strip(), "需填写审核人和理由", 422)
        with self.transaction(workflow_id, "DISMISS_ISSUE") as w:
            require(semantic_current(w), "没有当前的语义审查")
            require(any(i["id"] == issue_id for i in w["semantic_review"]["issues"]), "问题不存在", 404)
            w["semantic_review"]["dismissed"][issue_id] = {"reviewer": record["reviewer"], "reason": record["reason"], "at": now(),
                                                           "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
        return self.get(workflow_id)

    # ---- render / review / export
    def render(self, workflow_id: str, draft: bool = False):
        """Render with code (no model). A draft may show pending marks and is not reviewable."""
        from factdeck.render import render as do_render
        w = self.get(workflow_id)
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
            report = do_render(w["deck"]["result"], v["facts"], sources, folder, w["theme"], v["terms"], figures=figs)
        except ImportError as e:
            raise WorkflowError(f"渲染环境缺失：{e}；请安装 factdeck/requirements.txt 并执行 playwright install chromium", 503)
        rpages = [{"id": p["id"], "file": f"slide{i:02d}.png", "sha256": sha((folder / f"slide{i:02d}.png").read_bytes())}
                  for i, p in enumerate(w["deck"]["result"]["pages"], 1)]
        record = {"input_sha256": key, "draft": draft, "path": relative, "at": now(), "hard_errors": report["hard_errors"],
                  "summary": report["summary"], "pages": rpages,
                  "files": {n: sha((folder / n).read_bytes()) for n in ("deck.pptx", "deck.pdf", "deck.html", "render_report.json")},
                  "figure_files": sorted(x.name for x in folder.glob("figure_*.png")),
                  "warnings": {"figure_low_dpi": [x for sl in report["slides"] for x in sl.get("figure_low_dpi", [])]}}
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
        with self.transaction(workflow_id, "PAGE_REVIEW") as w:
            require(render_current(w), "没有当前的正式渲染")
            p = next((p for p in w["render"]["pages"] if p["id"] == page_id), None)
            require(p, "页面不存在", 404)
            require(record.get("png_sha256") == p["sha256"], "页面已重新渲染，请刷新后审核")
            require(sha(self.path(w["render"]["path"] + "/" + p["file"]).read_bytes()) == p["sha256"], "页面图片已被修改")
            rec = {"reviewer": record["reviewer"], "at": now(), "png_sha256": p["sha256"], "visual_status": record["visual_status"],
                   "content_status": record["content_status"], "sources_checked": True, "feedback": str(record.get("feedback", "")),
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
            require(stage(w) in {"READY_TO_EXPORT", "DELIVERED"}, "全部页面渲染、逐页审核和两次确认完成后才能交付")
            r = w["render"]
            src = self.path(r["path"])
            for name, digest_ in r["files"].items():
                require(sha((src / name).read_bytes()) == digest_, f"渲染文件 {name} 已被修改")
            for p in r["pages"]:
                require(sha((src / p["file"]).read_bytes()) == p["sha256"], "页面图片已被修改")
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
                                "used": sorted({fid for p in checked(w, v)["pages"] for fid in p["facts"]})},
                      "confirmations": w["confirmations"], "deck": {"author": w["deck"]["author"], "result_sha256": w["deck"]["result_sha256"],
                                                                    "coverage": w["deck"]["coverage"], "warnings": w["deck"]["warnings"]},
                      "semantic_review": w["semantic_review"], "render": {k: r[k] for k in ("input_sha256", "summary", "files", "at")},
                      "pages": [{"id": p["id"], "png_sha256": p["sha256"], "review": w["page_reviews"][p["id"]]} for p in r["pages"]],
                      "figures": figure_inventory(w, v),
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
            files = ("deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json", "delivery.zip")
            w["deliveries"].append({"version": version, "at": now(), "subject_sha256": delivery_subject(w), "path": relative,
                                    "files": [{"name": n, "sha256": sha((folder / n).read_bytes())} for n in files]})
        return self.get(workflow_id)
