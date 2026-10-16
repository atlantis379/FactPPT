"""Local API for the FactDeck mainline (/api/deck). The earlier full-slide image
workflow stays on /api/fact; legacy semantic endpoints stay on the host app."""
import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.deckflow import (Store, WorkflowError, MAX_UPLOAD, KINDS, all_units, all_claims, claim_origin, claim_text, digest,
                          unsupported_points, message_lines, story_line, summary_review_current, key_point_targets)
from factdeck.render import THEMES
from app.deck_generation import VISUAL_KINDS

router = APIRouter(prefix="/api/deck", tags=["FactDeck 主线"])
# FACTDECK_DATA_ROOT runs a service against another data directory (e.g. a validation copy of a project).
store = Store(Path(os.environ["FACTDECK_DATA_ROOT"]) if os.environ.get("FACTDECK_DATA_ROOT") else None)
Kind = Literal["READ_SOURCE", "SECOND_READ", "CLAIMS", "STRUCTURE", "STRUCTURE_REVIEW", "SUMMARY", "SUMMARY_AMEND", "SUMMARY_REVIEW", "FACTS", "DECK", "SEMANTIC_REVIEW", "VISUAL_CRITIQUE", "VISUAL_DESIGN", "VISUAL_LAYOUT", "VISUAL_CLEAN", "VISUAL_VECTOR", "VISUAL_BLIND_READ"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Requirements(Strict):
    audience: str | None = Field(default=None, max_length=500)
    purpose: str | None = Field(default=None, max_length=2000)
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    target_pages: int | None = Field(default=None, ge=1, le=300)
    emphasis: str | None = Field(default=None, max_length=4000)
    tone: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=10000)


class Create(Strict):
    title: str = Field(min_length=1, max_length=200)
    outline: str = Field(default="", max_length=100000)
    requirements: Requirements = Requirements()
    theme: str = "navy-teal"
    context: dict[str, Any] | None = None


class Settings(Strict):
    title: str | None = None
    outline: str | None = None
    requirements: Requirements | None = None
    theme: str | None = None
    context: dict[str, Any] | None = None
    visual_template: str | None = None
    structure_first: bool | None = None


class Queue(Strict):
    kind: Kind
    sources: list[str] | None = None        # CLAIMS only: redo these sources
    pages: list[str] | None = None          # visual revision only
    checks: list[Literal["COVERAGE", "RELATIONS"]] | None = None   # SEMANTIC_REVIEW only: queue these checklists
    chapters: list[str] | None = None       # SUMMARY / SUMMARY_REVIEW of a chaptered project: these chapters


class VisualRevision(Strict):
    page_id: str
    kind: Literal["VISUAL_DESIGN", "VISUAL_LAYOUT", "VISUAL_CLEAN", "VISUAL_VECTOR", "VISUAL_BLIND_READ"]


class GenerationRequest(Strict):
    first_pages: int | None = Field(default=None, ge=1, le=299, strict=True)
    batch_size: int | None = Field(default=None, ge=1, le=60, strict=True)
    pages: list[str] | None = Field(default=None, max_length=60)


class Claim(Strict):
    worker: str = Field(min_length=1, max_length=200)
    kind: Kind | None = None
    kinds: list[Kind] | None = Field(default=None, min_length=1, max_length=4)
    binding: str | None = Field(default=None, min_length=1, max_length=200)


class Complete(Strict):
    lease_token: str = Field(min_length=1)
    result: dict[str, Any]


class Failure(Strict):
    lease_token: str = Field(min_length=1)
    error: str = Field(min_length=1, max_length=2000)


class Lease(Strict):
    lease_token: str = Field(min_length=1)


class Authored(Strict):
    operator: str = Field(min_length=1, max_length=200)
    result: dict[str, Any]


class Approval(Strict):
    customer: str = Field(min_length=1, max_length=200)
    operator: str = Field(min_length=1, max_length=200)
    method: str = Field(min_length=1, max_length=200)
    feedback: str = Field(default="", max_length=10000)
    subject_sha256: str
    acknowledged_issues: list[str] = Field(default_factory=list, max_length=2000)


class PendingAnswer(Strict):
    index: int = Field(ge=0)
    answer: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    note: str = Field(default="", max_length=4000)


class PendingResponses(Strict):
    operator: str = Field(min_length=1, max_length=200)
    subject_sha256: str
    answers: list[PendingAnswer]


class Decision(Strict):
    reviewer: str = Field(min_length=1, max_length=200)
    decision: Literal["CONFIRM", "REJECT"]
    note: str = Field(default="", max_length=4000)


class Resolution(Strict):
    reviewer: str = Field(min_length=1, max_length=200)
    entity: str
    attribute: str
    fact_id: str
    note: str = Field(default="", max_length=4000)


class TranscriptionCheck(Strict):
    reviewer: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=20000)
    original_checked: bool


class FigureReview(Strict):
    reviewer: str = Field(min_length=1, max_length=200)
    crop_complete: bool
    deidentified: Literal["NO_PATIENT_CONTENT", "DEIDENTIFIED", "IDENTIFIABLE"]
    note: str = Field(default="", max_length=4000)


class FigureLicence(Strict):
    customer: str = Field(min_length=1, max_length=200)
    operator: str = Field(min_length=1, max_length=200)
    method: str = Field(min_length=1, max_length=200)
    permitted: bool
    scope: str = Field(default="", max_length=1000)


class Dismissal(Strict):
    reviewer: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)


class Review(Strict):
    reviewer: str = Field(min_length=1, max_length=200)
    png_sha256: str
    sources_checked: bool
    visual_status: Literal["PASS", "REVISE"]
    content_status: Literal["PASS", "REVISE"]
    feedback: str = Field(default="", max_length=10000)


def call(method, *args, **kwargs):
    try:
        return method(*args, **kwargs)
    except WorkflowError as error:
        raise HTTPException(error.status, str(error)) from error
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        raise HTTPException(422, f"文件或结果格式无效：{error}") from error


@router.get("/health")
def health():
    return {"product": "FactPPTv2", "workflow": "factdeck.v1", "mainline": True, "execution": "WORKER_COLLABORATION",
            "visual_generation": {"default_route": "A_NATIVE_VECTOR", "executor": "CODEX_ADOBE_WORKER", "server_vendor_calls": False},
            "task_kinds": list(KINDS), "themes": list(THEMES), "theme_palettes": THEMES,
            "projects": len(store.list())}


@router.get("/templates")
def academic_template_list():
    from app.academic_templates import list_templates
    return list_templates()


@router.get("/templates/{template_id}/{filename}")
def academic_template_asset(template_id: str, filename: str):
    from app.academic_templates import asset
    return FileResponse(call(asset,template_id,filename))


@router.get("/workflows/{workflow_id}/visual-template")
def selected_visual_template(workflow_id: str):
    selected=call(store.get,workflow_id).get('visual_template')
    if not selected:raise HTTPException(404,'尚未选择学术模板')
    return FileResponse(store.path(selected['design_path']),media_type='image/png')


@router.get("/workflows")
def workflows():
    return store.list()


@router.post("/workflows", status_code=201)
def create(body: Create):
    return call(store.create, body.title, body.outline, body.requirements.model_dump(exclude_none=True), body.context, body.theme)


@router.get("/workflows/{workflow_id}")
def workflow(workflow_id: str):
    return call(store.get, workflow_id)


@router.patch("/workflows/{workflow_id}")
def settings(workflow_id: str, body: Settings):
    changes = body.model_dump(exclude_none=True)
    if body.requirements is not None:
        changes["requirements"] = body.requirements.model_dump(exclude_none=True)
    return call(store.settings, workflow_id, changes)


@router.get("/workflows/{workflow_id}/progress")
def workbench_progress(workflow_id: str):
    w = call(store.get, workflow_id)
    return {"id": w["id"], "stage": w["stage"], "updated_at": w["updated_at"],
            "tasks": [{k: t[k] for k in ("id", "status", "attempts")} for t in w["tasks"]]}


@router.post("/workflows/{workflow_id}/sources")
async def source(workflow_id: str, file: UploadFile = File(...)):
    content = await file.read(MAX_UPLOAD + 1)
    return call(store.add_source, workflow_id, file.filename or "source.txt", content)


@router.delete("/workflows/{workflow_id}/sources/{source_id}")
def remove_source(workflow_id: str, source_id: str):
    return call(store.remove_source, workflow_id, source_id)


@router.get("/workflows/{workflow_id}/sources/{source_id}/file")
def source_file(workflow_id: str, source_id: str):
    w = call(store.get, workflow_id)
    s = next((s for s in w["sources"] if s["id"] == source_id), None)
    if not s:
        raise HTTPException(404, "资料不存在")
    return FileResponse(store.path(s["path"]), filename=s["filename"])


@router.get("/workflows/{workflow_id}/sources/{source_id}/pages/{page_id}/image")
def page_image(workflow_id: str, source_id: str, page_id: str):
    return Response(call(store.page_image, workflow_id, source_id, page_id), media_type="image/png")


@router.post("/workflows/{workflow_id}/brand/template")
async def brand_template(workflow_id: str, file: UploadFile = File(...)):
    content = await file.read(MAX_UPLOAD + 1)
    return call(store.brand_template, workflow_id, file.filename or "template.pptx", content)


@router.post("/workflows/{workflow_id}/brand/logo")
async def brand_logo(workflow_id: str, file: UploadFile = File(...)):
    content = await file.read(5 * 1024 * 1024 + 1)
    return call(store.brand_logo, workflow_id, file.filename or "logo.png", content)


@router.delete("/workflows/{workflow_id}/brand")
def remove_brand(workflow_id: str):
    return call(store.remove_brand, workflow_id)


@router.get("/workflows/{workflow_id}/brand/logo")
def brand_logo_file(workflow_id: str):
    b = call(store.get, workflow_id).get("brand") or {}
    if not b.get("logo"):
        raise HTTPException(404, "没有标志")
    return FileResponse(store.path(b["logo"]["path"]))


@router.get("/workflows/{workflow_id}/figures/{figure_id}/file")
def figure_file(workflow_id: str, figure_id: str):
    from app.deckflow import figures
    g = figures(call(store.get, workflow_id)).get(figure_id)
    if not g:
        raise HTTPException(404, "图不存在")
    return FileResponse(store.path(g["path"]), media_type="image/png")


class RulesAdoption(Strict):
    operator: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=4, max_length=2000)


class ChapterPlan(Strict):
    chapters: Literal["by_source"] | list[dict]
    operator: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=4, max_length=2000)


@router.post("/workflows/{workflow_id}/chapters")
def set_chapters(workflow_id: str, body: ChapterPlan):
    """Write and review the summary one chapter at a time (each task carries only its chapter's sources)."""
    result = call(store.set_chapters, workflow_id, body.chapters, body.operator, body.reason)
    return {k: result.get(k) for k in ("id", "stage", "open_items", "chapters", "chapter_status")}


@router.post("/workflows/{workflow_id}/rules/adopt")
def adopt_rules(workflow_id: str, body: RulesAdoption):
    result = call(store.adopt_rules, workflow_id, body.operator, body.reason)
    return {k: result.get(k) for k in ("id", "rules_version", "rules_history")}


@router.post("/workflows/{workflow_id}/tasks")
def queue(workflow_id: str, body: Queue, compact: bool = False):
    if sum(bool(x) for x in (body.sources, body.pages, body.checks, body.chapters)) > 1: raise HTTPException(422, "sources、pages、checks、chapters 只能提交其一")
    result = call(store.queue, workflow_id, body.kind, body.pages or body.sources or body.checks or body.chapters)
    return workflow_ack(result, body.kind) if compact else result


@router.post("/workflows/{workflow_id}/tasks/claim")
def claim(workflow_id: str, body: Claim):
    if body.kind and body.kinds: raise HTTPException(422, "kind 与 kinds 只能提交其一")
    task = call(store.claim, workflow_id, body.worker, tuple(body.kinds) if body.kinds else body.kind, body.binding)
    return task if task else Response(status_code=204)


def chained(ack, workflow_id, task_id, chain, chain_kinds):
    """Lease the same page's next visual stage to the same worker right after a submit."""
    if not chain: return ack
    w = call(store.get, workflow_id)
    done = next(t for t in w["tasks"] if t["id"] == task_id)
    kinds = tuple(chain_kinds) if chain_kinds else VISUAL_KINDS
    ack["next"] = call(store.claim, workflow_id, done["worker"], kinds, done["binding"]) if done["status"] == "COMPLETE" else None
    return ack


@router.post("/workflows/{workflow_id}/tasks/{task_id}/complete")
def complete(workflow_id: str, task_id: str, body: Complete, background_tasks: BackgroundTasks, compact: bool = False,
             chain: bool = False, chain_kinds: list[Kind] | None = Query(default=None)):
    result = call(store.complete, workflow_id, task_id, body.lease_token, body.result)
    if chain: return chained(completion_ack(result, task_id), workflow_id, task_id, chain, chain_kinds)
    return completion_ack(result, task_id) if compact else result


def completion_ack(result, task_id):
    task = next(t for t in result["tasks"] if t["id"] == task_id)
    return {"workflow_id": result["id"], "task_id": task_id,
            "status": task["status"], "result_sha256": task.get("result_sha256"),
            "stage": result.get("stage"),
            "render_status": ((result.get("generation") or {}).get("render") or {}).get("status")}


def workflow_ack(result, kind=None):
    return {"workflow_id": result["id"], "stage": result.get("stage"),
            "tasks": [{k: t.get(k) for k in ("id", "kind", "binding", "status")}
                      for t in result.get("tasks", []) if t.get("status") in {"PENDING", "RUNNING", "FAILED"}
                      and (kind is None or t.get("kind") == kind)]}


@router.post("/workflows/{workflow_id}/tasks/{task_id}/fail")
def fail(workflow_id: str, task_id: str, body: Failure, compact: bool = False):
    result = call(store.fail, workflow_id, task_id, body.lease_token, body.error)
    return completion_ack(result, task_id) if compact else result


@router.post("/workflows/{workflow_id}/tasks/{task_id}/renew")
def renew(workflow_id: str, task_id: str, body: Lease):
    return call(store.renew, workflow_id, task_id, body.lease_token)


@router.post("/workflows/{workflow_id}/tasks/{task_id}/summary-draft")
def summary_draft(workflow_id: str, task_id: str, body: Complete):
    """Checkpoint a chunked SUMMARY or SUMMARY_REVIEW; the task stays open and a later session continues from the draft."""
    return call(store.save_summary_draft, workflow_id, task_id, body.lease_token, body.result)


@router.put("/workflows/{workflow_id}/summary")
def put_summary(workflow_id: str, body: Authored):
    return call(store.author, workflow_id, "SUMMARY", body.result, body.operator)


@router.post("/workflows/{workflow_id}/summary/pending-responses")
def pending_responses(workflow_id: str, body: PendingResponses):
    return call(store.record_summary_responses, workflow_id, body.model_dump())


@router.put("/workflows/{workflow_id}/facts")
def put_facts(workflow_id: str, body: Authored):
    return call(store.author, workflow_id, "FACTS", body.result, body.operator)


@router.put("/workflows/{workflow_id}/deck")
def put_deck(workflow_id: str, body: Authored):
    return call(store.author, workflow_id, "DECK", body.result, body.operator)


@router.get("/workflows/{workflow_id}/facts/report")
def facts_report(workflow_id: str):
    return Response(call(store.facts_report, workflow_id), media_type="text/markdown; charset=utf-8")


@router.get("/workflows/{workflow_id}/facts")
def facts(workflow_id: str):
    from app.deckflow import verified, facts_current
    w = call(store.get, workflow_id)
    if not w["facts"]:
        raise HTTPException(409, "尚无事实库")
    v = verified(w)
    return {"author": w["facts"]["author"], "at": w["facts"]["at"], "current": facts_current(w),
            "facts": list(v["facts"].values()), "derivations": v["derivations"], "conflicts": v["conflicts"], "terms": v["terms"]}


@router.get("/workflows/{workflow_id}/deck/check")
def deck_check(workflow_id: str):
    from app.deckflow import checked, deck_current
    w = call(store.get, workflow_id)
    if not w["deck"]:
        raise HTTPException(409, "尚无页面规格")
    result = checked(w)
    result["current"] = deck_current(w)
    result["layouts"] = [{"id": p.get("id"), "layout": p.get("layout"), "outline_ids": p.get("outline_ids", []),
                          "section_ids": p.get("section_ids", [])} for p in w["deck"]["result"]["pages"]]
    return result


@router.get("/workflows/{workflow_id}/confirmations")
def confirmations(workflow_id: str):
    from app.deckflow import verified, checked, pending_items, deck_current
    w = call(store.get, workflow_id)
    if not deck_current(w):
        raise HTTPException(409, "尚无当前版本的页面规格")
    v = verified(w)
    return {"pending": pending_items(w, v, checked(w, v)), "decisions": w["confirmations"]}


@router.post("/workflows/{workflow_id}/confirmations/derivations/{der_id}")
def confirm_derivation(workflow_id: str, der_id: str, body: Decision):
    return call(store.confirm_derivation, workflow_id, der_id, body.model_dump())


@router.post("/workflows/{workflow_id}/confirmations/conflicts")
def resolve_conflict(workflow_id: str, body: Resolution):
    return call(store.resolve_conflict, workflow_id, body.model_dump())


@router.post("/workflows/{workflow_id}/confirmations/transcriptions/{unit_id}")
def confirm_transcription(workflow_id: str, unit_id: str, body: TranscriptionCheck):
    return call(store.confirm_transcription, workflow_id, unit_id, body.model_dump())


@router.post("/workflows/{workflow_id}/confirmations/figures/{figure_id}/review")
def confirm_figure(workflow_id: str, figure_id: str, body: FigureReview):
    return call(store.confirm_figure, workflow_id, figure_id, body.model_dump())


@router.post("/workflows/{workflow_id}/confirmations/figures/{figure_id}/licence")
def license_figure(workflow_id: str, figure_id: str, body: FigureLicence):
    return call(store.license_figure, workflow_id, figure_id, body.model_dump())


@router.post("/workflows/{workflow_id}/summary-review/issues/{issue_id}/dismiss")
def dismiss_summary(workflow_id: str, issue_id: str, body: Dismissal):
    return call(store.dismiss_summary_issue, workflow_id, issue_id, body.model_dump())


@router.post("/workflows/{workflow_id}/semantic-review/issues/{issue_id}/dismiss")
def dismiss(workflow_id: str, issue_id: str, body: Dismissal):
    return call(store.dismiss_issue, workflow_id, issue_id, body.model_dump())


@router.post("/workflows/{workflow_id}/render")
def render(workflow_id: str, background_tasks: BackgroundTasks, draft: bool = False):
    result = call(store.render, workflow_id, draft)
    if not draft and result.get("generation"): background_tasks.add_task(store.run_generation, workflow_id)
    return result


@router.post("/workflows/{workflow_id}/generation")
def generate(workflow_id: str, background_tasks: BackgroundTasks, body: GenerationRequest | None = None):
    result = call(store.start_generation, workflow_id, body.first_pages if body else None, body.batch_size if body else None, body.pages if body else None)
    background_tasks.add_task(store.run_generation, workflow_id)
    return result


@router.get("/workflows/{workflow_id}/generation")
def generation(workflow_id: str):
    return call(store.generation_view, workflow_id)


@router.post("/workflows/{workflow_id}/generation/revise")
def revise_generation(workflow_id: str, body: VisualRevision):
    return call(store.revise_generation, workflow_id, body.page_id, body.kind)


@router.post("/workflows/{workflow_id}/tasks/{task_id}/asset")
def visual_asset(workflow_id: str, task_id: str, background_tasks: BackgroundTasks,
                 lease_token: str = Form(...), receipt: str = Form(...), file: UploadFile = File(...), compact: bool = False,
                 chain: bool = False, chain_kinds: list[Kind] | None = Query(default=None)):
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD: raise HTTPException(422, "文件超过40MB")
    result = call(store.visual_asset, workflow_id, task_id, lease_token, content, call(json.loads, receipt))
    task = next(t for t in result["tasks"] if t["id"] == task_id)
    if task["kind"] == "VISUAL_VECTOR": background_tasks.add_task(store.run_page_preview, workflow_id, task["binding"])
    background_tasks.add_task(store.run_generation, workflow_id)
    if chain: return chained(completion_ack(result, task_id), workflow_id, task_id, chain, chain_kinds)
    return completion_ack(result, task_id) if compact else result


@router.get("/workflows/{workflow_id}/visual-standard/{name}")
def visual_standard_reference(workflow_id: str, name: str):
    from app.deck_generation import content_references
    ref = next((r for r in call(content_references, call(store.get, workflow_id)) if r["name"] == name), None)
    if not ref: raise HTTPException(404, "该项目没有这张标准参考图")
    return FileResponse(ref["path"], media_type="image/png")


@router.get("/workflows/{workflow_id}/generation/assets/{page_id}/{kind}")
def visual_asset_file(workflow_id: str, page_id: str, kind: Literal["design", "clean", "vector"]):
    w = call(store.get, workflow_id)
    page = next((p for p in (w.get("generation") or {}).get("pages", []) if p["id"] == page_id), None)
    asset = (page or {}).get("assets", {}).get(kind)
    if not asset: raise HTTPException(404, "资产不存在")
    path = store.path(asset["path"])
    from app.fact57098 import sha
    if sha(path.read_bytes()) != asset["sha256"]: raise HTTPException(409, "资产校验失败")
    return FileResponse(path, media_type="image/svg+xml" if kind == "vector" else "image/png")


@router.post("/workflows/{workflow_id}/generation/previews/{page_id}")
def page_preview(workflow_id: str, page_id: str):
    result = call(store.run_page_preview, workflow_id, page_id)
    if result is None: raise HTTPException(409, "该页素材未齐或生成已过期")
    return {k: result.get(k) for k in ("status", "error", "issues", "seconds", "summary", "office")}


@router.get("/workflows/{workflow_id}/generation/previews/{page_id}")
def page_preview_file(workflow_id: str, page_id: str):
    w = call(store.get, workflow_id)
    page = next((p for p in (w.get("generation") or {}).get("pages", []) if p["id"] == page_id), None)
    slide = ((page or {}).get("preview") or {}).get("slide")
    if not slide: raise HTTPException(404, "暂无单页预览")
    return FileResponse(store.path(slide), media_type="image/png")


def recover_generation_jobs(stop):
    """Persistent code jobs survive restart; leases serialize multiple app workers."""
    import time
    while not stop.is_set():
        try:
            with store.connect() as db:
                states = [json.loads(row[0]) for row in db.execute("SELECT state FROM workflows")]
            for w in states:
                if stop.is_set(): break
                job = (w.get("generation") or {}).get("render", {})
                if job.get("status") in {"PENDING", "WAITING_APPROVAL"} or (job.get("status") == "RUNNING" and job.get("lease_until", 0) < time.time()):
                    store.run_generation(w["id"])
        except Exception:
            import logging
            logging.getLogger(__name__).exception("A route render recovery failed")
        stop.wait(15)


@router.post("/workflows/{workflow_id}/backfill-structure")
@router.post("/workflows/{workflow_id}/backfill-arrows")
def backfill_structure(workflow_id: str):
    return call(store.backfill_structure, workflow_id)


@router.get("/workflows/{workflow_id}/render/{kind}/{filename}")
def render_file(workflow_id: str, kind: Literal["final", "draft"], filename: str):
    w = call(store.get, workflow_id)
    r = w.get("render") if kind == "final" else w.get("draft_render")
    allowed = {p["file"] for p in (r or {}).get("pages", [])} | set((r or {}).get("figure_files", [])) \
        | {(r or {}).get("logo_file"), "deck.pptx", "deck.pdf", "deck.html", "render_report.json"}
    if not r or filename not in allowed:
        raise HTTPException(404, "文件不存在")
    return FileResponse(store.path(r["path"] + "/" + filename), headers={"Cache-Control": "no-cache"})


@router.post("/workflows/{workflow_id}/approvals/{kind}")
def approve(workflow_id: str, kind: Literal["structure", "content", "style"], body: Approval):
    return call(store.approval, workflow_id, kind, body.model_dump())


@router.post("/workflows/{workflow_id}/pages/{page_id}/review")
def review(workflow_id: str, page_id: str, body: Review):
    return call(store.review, workflow_id, page_id, body.model_dump())


@router.get("/workflows/{workflow_id}/confirmation-draft")
def draft(workflow_id: str):
    w = call(store.get, workflow_id)
    if not w["summary"]:
        raise HTTPException(409, "尚无全文总结")
    loc = {p["id"]: f"{s['filename']} · {p['location']}" for s in w["sources"] for p in s["pages"]}
    lines = [f"# {w['title']}：内容确认稿", f"版本校验值：{digest(w['summary'])}", "", w["summary"]["overall_summary"]]
    units = {u["id"]: u for u in all_units(w)}
    claims = all_claims(w)
    review = w.get("summary_review") if summary_review_current(w) else None
    verdict = {p["point_id"]: p for r in (review or {}).get("sections", []) for p in r.get("points") or []}
    key_verdict = {p["target_id"]: p for r in (review or {}).get("sections", []) for p in r.get("key_points") or []}
    MARK = {"ENTAILED": "", "PARTIAL": "（审查：部分支持）", "NOT_ENTAILED": "（审查：原文不支持）", "CONTRADICTED": "（审查：与原文矛盾）"}
    for s in w["summary"]["sections"]:
        lines += ["", "## " + s["title"], s["summary"], "来源：" + "；".join(loc.get(r, r) for r in s["source_page_ids"])]
        lines += message_lines(w, s)                       # the storyboard: core sentence, logic, support and limits
        for k in key_point_targets(w, s):                 # each generalisation with its own review
            v = key_verdict.get(k["target_id"]) or {}
            lines += ["", f"- 要点：{k['point']}{MARK.get(v.get('verdict'), '')}"]
            if v.get("issue"):
                lines.append("  - 审查意见：" + v["issue"])
            if k.get("claim_ids"):
                claims = all_claims(w)
                lines += [f"  - 原文（{claims[c]['page_id']} {c.split('#')[1]}）：" + " ｜ ".join(" ".join(sp["quote"].split()) for sp in claims[c]["spans"])
                          for c in k["claim_ids"] if c in claims]
                continue
            for uid_ in k["unit_ids"]:
                u = units.get(uid_)
                if u:
                    flag = "（转录待确认）" if u.get("needs_confirmation") else ""
                    lines.append(f"  - 原文{flag}（{u['source_id']} {u['location']}）：{' '.join(u['text'].split())}")
        if s.get("point_coverage"):                        # the outline's points for this item, each with its source or its gap
            lines += ["", "提纲要点："]
            for r in s["point_coverage"]:
                if r.get("unsupported") is not None:
                    lines.append(f"- ✗ {r['point_id']} {r.get('point', '')}（无资料支撑：{r['unsupported']}）")
                else:
                    v = verdict.get(r["point_id"]) or {}
                    if r.get("claim_ids"):               # the point with the original text it rests on, source by source
                        if r.get("statement"):
                            lines.append(f"- ✓ {r['point_id']} 提纲：{r.get('point', '')}{MARK.get(v.get('verdict'), '')}")
                            lines.append(f"  - **资料实际说**：{r['statement']}")
                        else:
                            lines.append(f"- ✓ {r['point_id']} {r.get('point', '')}{MARK.get(v.get('verdict'), '')}")
                        lines += [f"  - 原文（{claim_origin(w, claims[c])}）：{claim_text(claims[c])}" for c in r["claim_ids"] if c in claims]
                    else:
                        locs = "；".join(f"{units[x]['source_id']} {units[x]['location']}" for x in r["unit_ids"] if x in units)
                        lines.append(f"- ✓ {r['point_id']} {r.get('point', '')}（{locs}）{MARK.get(v.get('verdict'), '')}")
                    if v.get("issue"):
                        lines.append(f"  - 审查意见：{v['issue']}")
    differ = [(r["point_id"], r.get("point", ""), r["statement"]) for s in w["summary"]["sections"]
              for r in s.get("point_coverage") or [] if r.get("statement")]
    if differ:
        lines += ["", "## 提纲措辞与资料不一致（请确认按资料讲述，或修改提纲）"]
        lines += [f"- {pid}　提纲：{p}\n  - 资料：{st}" for pid, p, st in differ]
    gaps = unsupported_points(w)
    if gaps:
        lines += ["", "## 无资料支撑的提纲要点（不上页，请确认）", *[f"- {k}：{v}" for k, v in gaps.items()]]
    if review:
        from app.review_ledger import STATUS_NAMES
        human = [i for i in review["issues"] if i["status"] == "NEEDS_HUMAN"]
        if human:
            lines += ["", "## ⚠ 须由您裁定的事项（审核无法通过修订解决）"]
            lines += [f"- {i['id']} {i['ref']}：{i['problem']}" for i in human]
        lines += ["", f"## 独立总结审查（{review['reviewer']}，问题台账共 {len(review['issues'])} 条，含历次审查）"]
        lines += [f"- {i['id']} {'阻断' if i['severity'] == 'BLOCKER' else '提示'} [{STATUS_NAMES[i['status']]}] {i['ref']}：{i['problem']}"
                  + (f"（裁定：{review['dismissed'][i['id']]['reason']}）" if i["id"] in review["dismissed"] else "")
                  for i in review["issues"]] or ["- 未报告问题"]
    else:
        lines += ["", "## 独立总结审查", "- 当前总结尚未经独立审查"]
    story = story_line(w)
    if any("「" in x for x in story):
        lines += ["", "## 故事线（各提纲条目的核心句，按讲述顺序）", *story]
    lines += ["", "## 教学提纲覆盖", *[f"- {o['id']}：{o['text']}" for o in w["outline"]], "", "## 需求",
              json.dumps(w["requirements"], ensure_ascii=False), "", "## 待解决问题", json.dumps(w["summary"]["pending_issues"], ensure_ascii=False),
              "", "客户：____  操作人：____  确认方式：____  日期：____", "反馈：____"]
    return Response("\n".join(lines), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="confirmation.md"'})


@router.get("/workflows/{workflow_id}/audit")
def audit(workflow_id: str):
    call(store.get, workflow_id)
    with store.connect() as db:
        rows = db.execute("SELECT seq,created_at,event,details FROM events WHERE workflow_id=? ORDER BY seq", (workflow_id,)).fetchall()
    return [{"sequence": r[0], "at": r[1], "event": r[2], "details": r[3]} for r in rows]


@router.post("/workflows/{workflow_id}/export")
def export(workflow_id: str):
    return call(store.export, workflow_id)


@router.get("/workflows/{workflow_id}/deliveries/{version}/{filename}")
def download(workflow_id: str, version: int, filename: Literal["deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json", "delivery.zip"]):
    w = call(store.get, workflow_id)
    d = next((d for d in w["deliveries"] if d["version"] == version), None)
    if not d:
        raise HTTPException(404, "交付版本不存在")
    return FileResponse(store.path(d["path"] + "/" + filename), filename=f"FactDeck-v{version:03d}-{filename}")
