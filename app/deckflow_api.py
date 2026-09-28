"""Local API for the FactDeck mainline (/api/deck). The earlier full-slide image
workflow stays on /api/fact; legacy semantic endpoints stay on the host app."""
import json
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.deckflow import Store, WorkflowError, MAX_UPLOAD, KINDS, digest
from factdeck.render import THEMES

router = APIRouter(prefix="/api/deck", tags=["FactDeck 主线"])
store = Store()
Kind = Literal["READ_SOURCE", "SECOND_READ", "SUMMARY", "FACTS", "DECK", "SEMANTIC_REVIEW"]


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


class Queue(Strict):
    kind: Kind


class Claim(Strict):
    worker: str = Field(min_length=1, max_length=200)
    kind: Kind | None = None


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
            "task_kinds": list(KINDS), "themes": list(THEMES), "projects": len(store.list())}


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


@router.get("/workflows/{workflow_id}/figures/{figure_id}/file")
def figure_file(workflow_id: str, figure_id: str):
    from app.deckflow import figures
    g = figures(call(store.get, workflow_id)).get(figure_id)
    if not g:
        raise HTTPException(404, "图不存在")
    return FileResponse(store.path(g["path"]), media_type="image/png")


@router.post("/workflows/{workflow_id}/tasks")
def queue(workflow_id: str, body: Queue):
    return call(store.queue, workflow_id, body.kind)


@router.post("/workflows/{workflow_id}/tasks/claim")
def claim(workflow_id: str, body: Claim):
    task = call(store.claim, workflow_id, body.worker, body.kind)
    return task if task else Response(status_code=204)


@router.post("/workflows/{workflow_id}/tasks/{task_id}/complete")
def complete(workflow_id: str, task_id: str, body: Complete):
    return call(store.complete, workflow_id, task_id, body.lease_token, body.result)


@router.post("/workflows/{workflow_id}/tasks/{task_id}/fail")
def fail(workflow_id: str, task_id: str, body: Failure):
    return call(store.fail, workflow_id, task_id, body.lease_token, body.error)


@router.post("/workflows/{workflow_id}/tasks/{task_id}/renew")
def renew(workflow_id: str, task_id: str, body: Lease):
    return call(store.renew, workflow_id, task_id, body.lease_token)


@router.put("/workflows/{workflow_id}/summary")
def put_summary(workflow_id: str, body: Authored):
    return call(store.author, workflow_id, "SUMMARY", body.result, body.operator)


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


@router.post("/workflows/{workflow_id}/semantic-review/issues/{issue_id}/dismiss")
def dismiss(workflow_id: str, issue_id: str, body: Dismissal):
    return call(store.dismiss_issue, workflow_id, issue_id, body.model_dump())


@router.post("/workflows/{workflow_id}/render")
def render(workflow_id: str, draft: bool = False):
    return call(store.render, workflow_id, draft)


@router.get("/workflows/{workflow_id}/render/{kind}/{filename}")
def render_file(workflow_id: str, kind: Literal["final", "draft"], filename: str):
    w = call(store.get, workflow_id)
    r = w.get("render") if kind == "final" else w.get("draft_render")
    allowed = {p["file"] for p in (r or {}).get("pages", [])} | set((r or {}).get("figure_files", [])) \
        | {"deck.pptx", "deck.pdf", "deck.html", "render_report.json"}
    if not r or filename not in allowed:
        raise HTTPException(404, "文件不存在")
    return FileResponse(store.path(r["path"] + "/" + filename), headers={"Cache-Control": "no-cache"})


@router.post("/workflows/{workflow_id}/approvals/{kind}")
def approve(workflow_id: str, kind: Literal["content", "style"], body: Approval):
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
    for s in w["summary"]["sections"]:
        lines += ["", "## " + s["title"], s["summary"], "来源：" + "；".join(loc.get(r, r) for r in s["source_page_ids"])]
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
