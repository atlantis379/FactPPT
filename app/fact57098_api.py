"""Local API for FactPPT 57098. Legacy endpoints remain on the host app."""
import json
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.fact57098 import Store, WorkflowError, MAX_UPLOAD, digest, stage

router = APIRouter(prefix="/api/fact", tags=["FactPPT 57098"])
store = Store()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Create(Strict):
    title: str = Field(min_length=1, max_length=200)
    outline: str = Field(default="", max_length=100000)
    context: dict[str, Any] | None = None


class Settings(Strict):
    title: str | None = None
    outline: str | None = None
    context: dict[str, Any] | None = None
    style: str | None = None


class Queue(Strict):
    kind: Literal["READ_SOURCE", "SUMMARY", "PAGE_PLAN", "IMAGE"]
    page_ids: list[str] | None = None


class Claim(Strict):
    worker: str = Field(min_length=1, max_length=200)
    kind: Literal["READ_SOURCE", "SUMMARY", "PAGE_PLAN", "IMAGE"] | None = None


class Complete(Strict):
    lease_token: str = Field(min_length=1)
    result: dict[str, Any]


class Failure(Strict):
    lease_token: str = Field(min_length=1)
    error: str = Field(min_length=1, max_length=2000)


class Lease(Strict):
    lease_token: str = Field(min_length=1)


class Approval(Strict):
    customer: str = Field(min_length=1, max_length=200)
    operator: str = Field(min_length=1, max_length=200)
    method: str = Field(min_length=1, max_length=200)
    feedback: str = Field(default="", max_length=10000)
    subject_sha256: str


class Review(Strict):
    reviewer: str = Field(min_length=1, max_length=200)
    image_sha256: str
    exact_text_checked: bool
    visual_status: Literal["PASS", "REVISE"]
    medical_status: Literal["PASS", "REVISE"]
    feedback: str = Field(default="", max_length=10000)


class Authored(Strict):
    result: dict[str, Any]


def call(method, *args, **kwargs):
    try:
        return method(*args, **kwargs)
    except WorkflowError as error:
        raise HTTPException(error.status, str(error)) from error
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        raise HTTPException(422, f"文件或结果格式无效：{error}") from error


@router.get("/health")
def health():
    return {"product": "FactPPTv2", "version": "2.0.0", "workflow": "57098-full-slide.v1", "execution": "CODEX_COLLABORATION", "projects": len(store.list())}


@router.get("/workflows")
def workflows():
    return store.list()


@router.post("/workflows", status_code=201)
def create(body: Create):
    return call(store.create, body.title, body.outline, body.context)


@router.get("/workflows/{workflow_id}")
def workflow(workflow_id: str):
    return call(store.get, workflow_id)


@router.patch("/workflows/{workflow_id}")
def settings(workflow_id: str, body: Settings):
    return call(store.settings, workflow_id, body.model_dump(exclude_none=True))


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


@router.post("/workflows/{workflow_id}/tasks")
def queue(workflow_id: str, body: Queue):
    return call(store.queue, workflow_id, body.kind, body.page_ids)


@router.put("/workflows/{workflow_id}/summary")
def save_summary(workflow_id: str, body: Authored):
    def save():
        with store.transaction(workflow_id, "SUMMARY_EDIT") as w:
            store.cancel(w, {"SUMMARY"})
            store.accept_summary(w, body.result)
        return store.get(workflow_id)
    return call(save)


@router.put("/workflows/{workflow_id}/page-plan")
def save_plan(workflow_id: str, body: Authored):
    def save():
        with store.transaction(workflow_id, "PAGE_PLAN_EDIT") as w:
            store.cancel(w, {"PAGE_PLAN"})
            store.accept_plan(w, body.result)
        return store.get(workflow_id)
    return call(save)


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


@router.post("/workflows/{workflow_id}/tasks/{task_id}/image")
async def image(workflow_id: str, task_id: str, lease_token: str = Form(...), receipt: str = Form(...), file: UploadFile = File(...)):
    try:
        record = json.loads(receipt)
    except json.JSONDecodeError:
        raise HTTPException(422, "生成凭据必须是JSON")
    content = await file.read(MAX_UPLOAD + 1)
    return call(store.image_result, workflow_id, task_id, lease_token, content, record)


@router.post("/workflows/{workflow_id}/approvals/{kind}")
def approve(workflow_id: str, kind: Literal["content", "style"], body: Approval):
    return call(store.approval, workflow_id, kind, body.model_dump())


@router.post("/workflows/{workflow_id}/pages/{page_id}/review")
def review(workflow_id: str, page_id: str, body: Review):
    return call(store.review, workflow_id, page_id, body.model_dump())


@router.get("/workflows/{workflow_id}/pages/{page_id}/image")
def page_image(workflow_id: str, page_id: str):
    w = call(store.get, workflow_id)
    p = next((p for p in w["pages"] if p["id"] == page_id), None)
    if not p or not p["image"]:
        raise HTTPException(404, "页面尚无图片")
    return FileResponse(store.path(p["image"]["path"]), media_type="image/png", headers={"Cache-Control": "no-cache"})


@router.get("/workflows/{workflow_id}/confirmation-draft")
def draft(workflow_id: str):
    w = call(store.get, workflow_id)
    if not w["summary"]:
        raise HTTPException(409, "尚无全文总结")
    lines = [f"# {w['title']}：内容确认稿", f"版本校验值：{digest(w['summary'])}", "", w["summary"]["overall_summary"]]
    locators = {u["id"]: f"{s['filename']} · {u['location']}" for s in w["sources"] for u in s["units"]}
    for s in w["summary"]["sections"]:
        lines.extend(["", "## " + s["title"], s["summary"], "来源：" + "；".join(locators[r] for r in s["source_unit_ids"])])
    lines.extend(["", "## 教学提纲覆盖", *[f"- {o['id']}：{o['text']}" for o in w["outline"]], "", "## 待解决问题", json.dumps(w["summary"]["pending_issues"], ensure_ascii=False), "", "客户：____  操作人：____  确认方式：____  日期：____", "反馈：____"])
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
def download(workflow_id: str, version: int, filename: Literal["editable.pptx", "image_pages.pptx", "verification_report.json", "delivery.zip"]):
    w = call(store.get, workflow_id)
    d = next((d for d in w["deliveries"] if d["version"] == version), None)
    if not d:
        raise HTTPException(404, "交付版本不存在")
    return FileResponse(store.path(d["path"] + "/" + filename), filename=f"FactPPT-v{version:03d}-{filename}")
