"""Transactional, source-bound 57098 workflow. No model calls or fake approvals."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import secrets
import sqlite3
import subprocess
import time
import uuid
import zipfile
import posixpath
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = "57098-full-slide.v1"
BASELINE = "57098ca072fe05ec8e6ad54e9f13753754862fd4"
DEFAULT_STYLE = "16:9，白底，深海军蓝标题、湖蓝与青绿色强调；中文清晰可读；根据内容选择图表、机制图或流程图；简洁医学授课风格。"
MAX_UPLOAD = 40 * 1024 * 1024
MAX_UNITS = 6000
MAX_TEXT = 3_000_000
LEASE_SECONDS = 900


class WorkflowError(ValueError):
    def __init__(self, message: str, status: int = 409):
        self.status = status
        super().__init__(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def require(condition: Any, message: str, status: int = 409):
    if not condition:
        raise WorkflowError(message, status)


def uid(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex[:20]


def parse_outline(text: str) -> list[dict]:
    return [{"id": f"outline_{i}", "text": line.strip()} for i, line in
            enumerate((line for line in text.splitlines() if line.strip()), 1)]


def extract_document(filename: str, content: bytes, source_id: str) -> list[dict]:
    """Extract all units; require a reading receipt even for text-only units."""
    suffix = Path(filename).suffix.lower()
    require(0 < len(content) <= MAX_UPLOAD, "资料为空或超过40MB", 422)
    pages: list[tuple[str, str, bool]] = []
    if suffix == ".pdf":
        from pypdf import PdfReader
        from pypdf.generic import ContentStream
        reader = PdfReader(io.BytesIO(content))
        require(not reader.is_encrypted, "请先提供未加密PDF", 422)
        for i, page in enumerate(reader.pages, 1):
            visual = False
            stream = page.get_contents()
            if stream:
                visual = any(op in {b"Do", b"BI", b"S", b"s", b"f", b"f*", b"B", b"sh"}
                             for _, op in ContentStream(stream, reader).operations)
            text = page.extract_text() or ""
            pages.append((f"第{i}页", text, visual or not text.strip()))
    elif suffix == ".pptx":
        from pptx import Presentation
        prs = Presentation(io.BytesIO(content))
        def shape_text(shape):
            result = []
            if shape.shape_type == 6:
                for child in shape.shapes:
                    result.extend(shape_text(child))
            elif shape.has_table:
                result.extend(" | ".join(cell.text for cell in row.cells) for row in shape.table.rows)
            elif shape.has_text_frame:
                result.append(shape.text)
            return result
        for i, slide in enumerate(prs.slides, 1):
            text = "\n".join(t for shape in slide.shapes for t in shape_text(shape) if t.strip())
            if slide.has_notes_slide:
                text += "\n[演讲备注]\n" + slide.notes_slide.notes_text_frame.text
            # Every PPTX slide needs visual inspection (charts/images/textboxes).
            pages.append((f"第{i}张幻灯片", text, True))
    elif suffix == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(content))
        text = [p.text for p in doc.paragraphs]
        text.extend(" | ".join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows)
        for section in doc.sections:
            text.extend(p.text for part in (section.header, section.footer) for p in part.paragraphs)
        pages.append(("全文（含正文、表格、页眉页脚；需核对脚注与图形）", "\n".join(text), True))
    elif suffix == ".xlsx":
        from openpyxl import load_workbook
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        try:
            for sheet in book:
                lines = [f"{cell.coordinate}: {cell.value}" for row in sheet for cell in row if cell.value is not None]
                pages.append((f"工作表 {sheet.title}（需核对图表与批注）", "\n".join(lines), True))
        finally:
            book.close()
    elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        pages.append(("图片全文", "", True))
    elif suffix in {".txt", ".md"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("gb18030")
        pages.append(("全文", text, False))
    else:
        raise WorkflowError("支持PDF、PPTX、DOCX、XLSX、PNG/JPG/WEBP和TXT/MD", 422)
    require(0 < len(pages) <= MAX_UNITS, "资料页数为空或超过容量限制", 422)
    require(sum(len(t) for _, t, _ in pages) <= MAX_TEXT, "资料文字超出容量；请拆分导入，不能截断", 422)
    return [{"id": f"{source_id}:unit:{i}", "number": i, "location": label,
             "extracted_text": text, "text": text, "requires_visual": visual,
             "reading": None} for i, (label, text, visual) in enumerate(pages, 1)]


def input_hash(w: dict) -> str:
    return digest({"sources": [{"sha256": s["sha256"], "units": s["units"]} for s in w["sources"]],
                   "outline": w["outline"], "context": w["context"]})


def units(w: dict) -> dict[str, dict]:
    return {p["id"]: p for s in w["sources"] for p in s["units"]}


def fully_read(w: dict) -> bool:
    return bool(w["sources"]) and all(p["reading"] for p in units(w).values())


def summary_current(w: dict) -> bool:
    return bool(w["summary"]) and w["summary"]["input_sha256"] == input_hash(w)


def content_approved(w: dict) -> bool:
    approval = w["content_approval"]
    return summary_current(w) and bool(approval) and approval["subject_sha256"] == digest(w["summary"])


def page_hash(w: dict, page: dict, number: int, total: int) -> str:
    return digest({"template": TEMPLATE, "summary": digest(w["summary"]), "style": w["style"],
                   "number": number, "total": total, "page": {k: v for k, v in page.items()
                   if k not in {"image", "review", "contract_sha256", "generation_history", "prompt"}}})


def sample_hash(w: dict) -> str:
    return digest({"style": w["style"], "plan": w["plan_sha256"], "pages": [
        {"id": p["id"], "contract": p["contract_sha256"], "image": p["image"]["sha256"] if p["image"] else None,
         "review": p["review"]} for p in w["pages"][:5]]})


def style_approved(w: dict) -> bool:
    return content_approved(w) and bool(w["style_approval"]) and w["style_approval"]["subject_sha256"] == sample_hash(w)


def reviewed(page: dict) -> bool:
    return bool(page["image"] and page["review"]) and page["review"]["image_sha256"] == page["image"]["sha256"] and \
        page["review"]["visual_status"] == "PASS" and page["review"]["medical_status"] == "PASS"


def stage(w: dict) -> str:
    if not fully_read(w): return "READING_REQUIRED"
    if not summary_current(w): return "SUMMARY_REQUIRED"
    if not content_approved(w): return "CONTENT_CONFIRMATION"
    if not w["pages"]: return "PAGE_PLAN_REQUIRED"
    if any(not p["image"] for p in w["pages"][:5]): return "SAMPLES_GENERATION"
    if any(not reviewed(p) for p in w["pages"][:5]): return "SAMPLES_REVIEW"
    if not style_approved(w): return "STYLE_CONFIRMATION"
    if any(not p["image"] for p in w["pages"]): return "FULL_GENERATION"
    if any(not reviewed(p) for p in w["pages"]): return "PAGE_REVIEW"
    return "DELIVERED" if w["deliveries"] and w["deliveries"][-1]["subject_sha256"] == sample_all_hash(w) else "READY_TO_EXPORT"


def sample_all_hash(w: dict) -> str:
    return digest({"plan": w["plan_sha256"], "content_approval": w["content_approval"], "style_approval": w["style_approval"],
                   "pages": [{"id": p["id"], "image": p["image"], "review": p["review"]} for p in w["pages"]]})


def compile_prompt(w: dict, page: dict, number: int) -> str:
    return "\n\n".join([
        "STYLE_LOCK\n生成一张完整的16:9医学授课幻灯片图片，包含以下全部文字与图形，不能只生成背景。\n" + w["style"],
        "CONTENT_LOCK\n以下标题及正文逐字保留，保留数字、单位、比较符号、适用人群、时间和限制条件：\n" +
        page["title"] + "\n" + page["locked_text"],
        f"LAYOUT\n第{number}/{len(w['pages'])}页。" + page["layout"],
        "VISUAL_METAPHOR\n" + page["visual_strategy"] + "\n所有视觉关系必须来自内容；不得暗示未获来源支持的因果、优越性或强制顺序。",
        "NEGATIVE_CONSTRAINTS\n禁止遗漏、改写或新增医学事实；禁止新增宣传口号；禁止用原PPT渲染图替代生成；禁止把提示词写入幻灯片；禁止不可读的小字、文字遮挡、乱码或裁切。图像审核失败时重新生成。"
    ])


class Store:
    def __init__(self, data_root: Path | None = None):
        self.root = (data_root or ROOT / "data" / "factppt").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "workflow.sqlite3"
        with self.connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL,
                  created_at TEXT NOT NULL, event TEXT NOT NULL, details TEXT NOT NULL);
            """)

    def connect(self):
        db = sqlite3.connect(self.database, timeout=45)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=45000")
        return db

    @contextmanager
    def transaction(self, workflow_id: str, event: str):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision,state FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            require(row, "项目不存在", 404)
            state = json.loads(row[1])
            yield state
            state["updated_at"] = now()
            state["revision"] = row[0] + 1
            db.execute("UPDATE workflows SET revision=?,state=? WHERE id=?", (state["revision"], json.dumps(state, ensure_ascii=False), workflow_id))
            db.execute("INSERT INTO events(workflow_id,created_at,event,details) VALUES(?,?,?,?)",
                       (workflow_id, now(), event, json.dumps({"revision": state["revision"], "state_sha256": digest(state)}, ensure_ascii=False)))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def path(self, relative: str) -> Path:
        target = (self.root / relative).resolve()
        require(target.is_relative_to(self.root), "非法文件路径", 422)
        return target

    def immutable(self, workflow_id: str, folder: str, content: bytes, suffix: str) -> str:
        relative = f"{workflow_id}/{folder}/{sha(content)}{suffix}"
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(content)
        require(sha(target.read_bytes()) == sha(content), "不可变文件校验失败")
        return relative

    def snapshot(self, w: dict, name: str, value: Any) -> str:
        return self.immutable(w["id"], "snapshots", json.dumps({"kind": name, "value": value}, ensure_ascii=False, indent=2).encode(), ".json")

    def source_integrity(self, w: dict):
        for s in w["sources"]:
            file = self.path(s["path"])
            require(file.is_file() and sha(file.read_bytes()) == s["sha256"], "来源文件缺失或已被修改，请重新导入")

    def create(self, title: str, outline: str, context: dict | None = None) -> dict:
        require(bool(title.strip()), "请填写项目名称", 422)
        w = {"id": uid("flow"), "title": title.strip(), "revision": 1, "created_at": now(), "updated_at": now(),
             "template": TEMPLATE, "baseline": BASELINE, "context": context or {"language": "zh-CN", "external_research_allowed": False, "synthetic_case": False},
             "outline": parse_outline(outline), "style": DEFAULT_STYLE, "sources": [], "summary": None,
             "content_approval": None, "style_approval": None, "approvals": [], "pages": [], "plan_sha256": None,
             "tasks": [], "deliveries": []}
        with self.connect() as db:
            db.execute("INSERT INTO workflows VALUES(?,?,?)", (w["id"], 1, json.dumps(w, ensure_ascii=False)))
            db.execute("INSERT INTO events(workflow_id,created_at,event,details) VALUES(?,?,?,?)", (w["id"], now(), "CREATE", digest(w)))
        return self.get(w["id"])

    def get(self, workflow_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT state FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        require(row, "项目不存在", 404)
        result = json.loads(row[0])
        result["stage"] = stage(result)
        result["approval_subjects"] = {"content": digest(result["summary"]) if summary_current(result) else None,
                                       "style": sample_hash(result) if result["pages"] else None}
        # Leases are returned only from the claim endpoint.
        for task in result["tasks"]:
            task.pop("lease_token", None)
        return result

    def list(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT state FROM workflows ORDER BY rowid DESC").fetchall()
        return [{"id": w["id"], "title": w["title"], "stage": stage(w), "pages": len(w["pages"]), "updated_at": w["updated_at"]}
                for w in (json.loads(row[0]) for row in rows)]

    def cancel(self, w: dict, kinds: set[str] | None = None):
        for task in w["tasks"]:
            if task["status"] in {"PENDING", "RUNNING", "FAILED"} and (kinds is None or task["kind"] in kinds):
                task["status"] = "CANCELLED"
                task["lease_token"] = None

    def invalidate_content(self, w: dict, keep_reading: bool = False):
        self.cancel(w, {"SUMMARY", "PAGE_PLAN", "IMAGE"} if keep_reading else None)
        if w["pages"]:
            self.snapshot(w, "superseded_pages", w["pages"])
        w.update(summary=None, content_approval=None, style_approval=None, pages=[], plan_sha256=None)

    def settings(self, workflow_id: str, changes: dict):
        with self.transaction(workflow_id, "SETTINGS") as w:
            if "outline" in changes or "context" in changes:
                outline = parse_outline(changes.get("outline", "")) if "outline" in changes else w["outline"]
                context = changes.get("context", w["context"])
                if outline != w["outline"] or context != w["context"]:
                    self.invalidate_content(w)
                    w.update(outline=outline, context=context)
            if "title" in changes:
                require(bool(changes["title"].strip()), "名称不能为空", 422)
                w["title"] = changes["title"].strip()
            if "style" in changes and changes["style"] != w["style"]:
                require(bool(changes["style"].strip()), "风格不能为空", 422)
                self.cancel(w, {"IMAGE"})
                self.snapshot(w, "superseded_style_pages", w["pages"])
                w["style"] = changes["style"].strip()
                w["style_approval"] = None
                for i, p in enumerate(w["pages"], 1):
                    p["image"] = p["review"] = None
                    p["contract_sha256"] = page_hash(w, p, i, len(w["pages"]))
                    p["prompt"] = compile_prompt(w, p, i)
                w["plan_sha256"] = digest([p["contract_sha256"] for p in w["pages"]]) if w["pages"] else None
        return self.get(workflow_id)

    def add_source(self, workflow_id: str, filename: str, content: bytes):
        source_id = uid("source")
        extracted = extract_document(filename, content, source_id)
        with self.transaction(workflow_id, "SOURCE_IMPORT") as w:
            require(not any(s["sha256"] == sha(content) for s in w["sources"]), "相同资料已导入", 422)
            self.invalidate_content(w)
            path = self.immutable(workflow_id, "sources", content, Path(filename).suffix.lower())
            w["sources"].append({"id": source_id, "filename": Path(filename.replace("\\", "/")).name,
                                 "sha256": sha(content), "path": path, "units": extracted})
        return self.get(workflow_id)

    def remove_source(self, workflow_id: str, source_id: str):
        with self.transaction(workflow_id, "SOURCE_REMOVE") as w:
            require(any(s["id"] == source_id for s in w["sources"]), "资料不存在", 404)
            self.invalidate_content(w)
            w["sources"] = [s for s in w["sources"] if s["id"] != source_id]
        return self.get(workflow_id)

    def reading(self, w: dict, source_id: str, result: dict, reader: str):
        source = next((s for s in w["sources"] if s["id"] == source_id), None)
        require(source, "资料不存在", 404)
        require(result.get("source_sha256") == source["sha256"], "阅读结果来源已变更")
        rows = result.get("units")
        require(isinstance(rows, list) and len(rows) == len(source["units"]), "需提交资料全部单元的阅读记录", 422)
        require({r.get("id") for r in rows} == {p["id"] for p in source["units"]}, "阅读单元缺失或重复", 422)
        by_id = {r["id"]: r for r in rows}
        for unit in source["units"]:
            row = by_id[unit["id"]]
            text = str(row.get("text", ""))
            category = row.get("classification")
            require(category in {"SUBSTANTIVE", "REFERENCE", "EMPTY"}, "需标记正文、参考文献或空白单元", 422)
            require(category == "EMPTY" or bool(text.strip()), "非空白单元需提供完整阅读文字", 422)
            require(category != "EMPTY" or bool(str(row.get("reason", "")).strip()), "空白单元需说明原因", 422)
            require(category != "EMPTY" or not unit["extracted_text"].strip(), "已有提取文字的单元不能标记为空白", 422)
            require(not unit["requires_visual"] or row.get("visual_inspected") is True, "此单元必须核对原始视觉内容", 422)
            # Raw text remains retained for comparison; receipt author owns semantic reading.
            unit["text"] = text
            unit["reading"] = {"reader": reader, "at": now(), "classification": category,
                               "visual_inspected": row.get("visual_inspected") is True,
                               "reason": str(row.get("reason", "")), "text_sha256": sha(text.encode())}
        require(sum(len(p["text"]) for p in source["units"]) <= MAX_TEXT, "阅读文字超出容量", 422)

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
        known = units(w)
        covered = set()
        for s in sections:
            require(bool(str(s.get("title", "")).strip()) and len(str(s.get("summary", "")).strip()) >= 20, "章节标题及总结不能为空", 422)
            refs = s.get("source_unit_ids")
            require(isinstance(refs, list) and refs and set(refs) <= set(known), "章节需引用有效资料位置", 422)
            covered.update(refs)
        require(set(known) <= covered, "全文总结未覆盖全部资料单元（含参考文献与空白说明）", 422)
        mapping = result.get("outline_coverage", [])
        outline_ids = {o["id"] for o in w["outline"]}
        require(isinstance(mapping, list) and len(mapping) == len(outline_ids) and
                {m.get("outline_id") for m in mapping} == outline_ids, "总结需覆盖全部教学提纲条目", 422)
        for m in mapping:
            require(m.get("section_ids") and set(m["section_ids"]) <= set(ids), "提纲映射需指向有效章节", 422)
        require(isinstance(result.get("pending_issues"), list), "需列出待解决问题；无问题时为空列表", 422)
        self.snapshot(w, "summary", result)
        w["summary"] = copy.deepcopy(result)
        w["content_approval"] = w["style_approval"] = None
        if w["pages"]:
            self.snapshot(w, "superseded_pages", w["pages"])
        w["pages"] = []
        w["plan_sha256"] = None
        self.cancel(w, {"PAGE_PLAN", "IMAGE"})

    def accept_plan(self, w: dict, result: dict):
        require(content_approved(w), "请先完成客户全文内容确认")
        require(result.get("summary_sha256") == digest(w["summary"]), "分页方案对应的总结已过期")
        pages = result.get("pages")
        require(isinstance(pages, list) and 0 < len(pages) <= 500, "分页数量需为1至500", 422)
        known = units(w)
        outline = {o["id"] for o in w["outline"]}
        seen = set()
        mapped = set()
        new_pages = []
        for i, raw in enumerate(pages, 1):
            p = {k: raw.get(k) for k in ("id", "title", "locked_text", "source_unit_ids", "outline_ids", "layout", "visual_strategy", "placement", "critical_terms")}
            p["id"] = p["id"] or f"page_{i}"
            require(isinstance(p["id"], str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", p["id"]) and p["id"] not in seen, "页面ID非法或重复", 422)
            seen.add(p["id"])
            require(all(isinstance(p[k], str) and p[k].strip() for k in ("title", "locked_text", "layout", "visual_strategy")), "每页需提供标题、锁定正文、布局和视觉方案", 422)
            require(p["placement"] in {"BODY", "APPENDIX"}, "页面位置需为BODY或APPENDIX", 422)
            require(isinstance(p["source_unit_ids"], list) and p["source_unit_ids"] and set(p["source_unit_ids"]) <= set(known), "每页需引用有效来源", 422)
            require(isinstance(p["outline_ids"], list) and set(p["outline_ids"]) <= outline, "提纲映射无效", 422)
            require(isinstance(p["critical_terms"], list) and all(isinstance(t, str) and t in p["title"] + "\n" + p["locked_text"] for t in p["critical_terms"]), "重点词需出现在锁定正文中", 422)
            require(not re.search(r"STYLE_LOCK|CONTENT_LOCK|NEGATIVE_CONSTRAINTS", p["locked_text"] + p["title"]), "提示词不能进入教学正文", 422)
            mapped.update(p["outline_ids"])
            p.update(image=None, review=None, generation_history=[])
            p["contract_sha256"] = page_hash(w, p, i, len(pages))
            new_pages.append(p)
        require(mapped == outline, "分页未覆盖全部教学提纲", 422)
        if w["pages"]:
            self.snapshot(w, "superseded_pages", w["pages"])
        self.cancel(w, {"IMAGE"})
        w["pages"] = new_pages
        for i, p in enumerate(w["pages"], 1):
            p["prompt"] = compile_prompt(w, p, i)
        w["plan_sha256"] = digest([p["contract_sha256"] for p in w["pages"]])
        w["style_approval"] = None
        self.snapshot(w, "page_plan", result)

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
                require(content_approved(w) and w["pages"] and all(reviewed(p) for p in w["pages"][:5]), "前5页须完成图片与医学内容审核后才能确认风格")
                expected = sample_hash(w)
            require(record.get("subject_sha256") == expected, "确认稿已更新，请刷新后重新核对")
            approval = {"id": uid("approval"), "kind": kind, "at": now(), "subject_sha256": expected,
                        "customer": record["customer"], "operator": record["operator"], "method": record["method"], "feedback": str(record.get("feedback", "")),
                        "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            w[kind + "_approval"] = approval
            w["approvals"].append(approval)
            self.snapshot(w, kind + "_approval", approval)
        return self.get(workflow_id)

    def brief(self, w: dict, kind: str, source_id: str | None = None, page_id: str | None = None) -> dict:
        if kind == "READ_SOURCE":
            s = next(s for s in w["sources"] if s["id"] == source_id)
            return {"kind": kind, "source": s, "source_url": f"/api/fact/workflows/{w['id']}/sources/{s['id']}/file",
                    "rules": ["阅读每个单元；所有图、表、算法和非正文内容必须核对原件，不得截断。", "保留数字、单位、限定条件与冲突；参考文献和空白单元也要登记。"],
                    "result_contract": {"source_sha256": s["sha256"], "units": [{"id": p["id"], "text": p["text"], "classification": "SUBSTANTIVE", "visual_inspected": False, "reason": ""} for p in s["units"]]}}
        if kind == "SUMMARY":
            return {"kind": kind, "schema_version": "full_source_summary.v2", "input_sha256": input_hash(w), "context": w["context"], "outline": w["outline"], "sources": w["sources"],
                    "rules": ["全文综合总结；不得新增外部医学事实。", "全部资料单元都要引用；教学提纲全部覆盖，指令性提示词不得写入教学内容。", "不确定事项列入pending_issues；保留人群、剂量、时间、证据和限制。"],
                    "result_contract": {"schema_version": "full_source_summary.v2", "input_sha256": input_hash(w), "overall_summary": "", "sections": [{"id": "section_1", "title": "", "summary": "", "source_unit_ids": []}], "outline_coverage": [{"outline_id": o["id"], "section_ids": []} for o in w["outline"]], "pending_issues": []}}
        if kind == "PAGE_PLAN":
            return {"kind": kind, "summary_sha256": digest(w["summary"]), "summary": w["summary"], "sources": w["sources"], "outline": w["outline"], "context": w["context"], "style": w["style"],
                    "rules": ["一页一个认知单元；不能预设55页。", "全部教学提纲映射到正文或附录；源事实、剂量、阈值、限制必须保留。", "不在教学正文中包含提示词；精确数字和医学关键词列入critical_terms。"],
                    "result_contract": {"summary_sha256": digest(w["summary"]), "pages": [{"id": "page_1", "title": "", "locked_text": "", "source_unit_ids": [], "outline_ids": [], "layout": "", "visual_strategy": "", "placement": "BODY", "critical_terms": []}]}}
        p = next(p for p in w["pages"] if p["id"] == page_id)
        return {"kind": "IMAGE", "template": TEMPLATE, "page_id": p["id"], "contract_sha256": p["contract_sha256"], "prompt": p["prompt"],
                "source_unit_ids": p["source_unit_ids"], "reference_images": [w["pages"][0]["image"]["path"]] if style_approved(w) and w["pages"][0]["image"] else [],
                "reference_image_urls": [f"/api/fact/workflows/{w['id']}/pages/{w['pages'][0]['id']}/image"] if style_approved(w) and w["pages"][0]["image"] else [],
                "rules": ["必须调用内置image_gen工具生成整页图片；不能使用PPT渲染、背景图或程序绘制冒充。", "实际调用标识与PNG校验值需写入生成记录。", "结果需人工逐页审核，不能自动宣称医学通过。"],
                "receipt_contract": {"provider": "OpenAI", "engine": "image_gen", "tool_call_id": "actual-tool-call-reference", "generated_at": "ISO8601", "image_sha256": "PNG-sha256", "preliminary_qa": {"status": "NEEDS_HUMAN_REVIEW", "issues": []}}}

    def queue(self, workflow_id: str, kind: str, page_ids: list[str] | None = None):
        require(kind in {"READ_SOURCE", "SUMMARY", "PAGE_PLAN", "IMAGE"}, "任务类型无效", 422)
        with self.transaction(workflow_id, "QUEUE_" + kind) as w:
            bindings = []
            if kind == "READ_SOURCE":
                require(w["sources"], "请先导入资料")
                bindings = [(s["id"], s["sha256"]) for s in w["sources"] if not all(p["reading"] for p in s["units"])]
            elif kind == "SUMMARY":
                require(fully_read(w), "请先完成全部资料阅读")
                bindings = [(None, input_hash(w))]
            elif kind == "PAGE_PLAN":
                require(content_approved(w), "请先完成客户全文内容确认")
                bindings = [(None, digest(w["summary"]))]
            else:
                require(content_approved(w) and w["pages"], "请先确认内容并完成分页")
                allowed = w["pages"] if style_approved(w) else w["pages"][:5]
                if page_ids:
                    require(len(page_ids) <= 5, "一次最多请求5页", 422)
                    require(set(page_ids) <= {p["id"] for p in allowed}, "风格确认前只能生成前5页；页面ID需有效")
                selected = [p for p in allowed if (p["id"] in page_ids if page_ids else not p["image"])]
                # Batch size five, including explicit page requests.
                selected = selected[:5]
                bindings = [(p["id"], p["contract_sha256"]) for p in selected]
                for p in selected:
                    if p["image"]:
                        if p in w["pages"][:5]:
                            w["style_approval"] = None
                            self.cancel(w, {"IMAGE"})
                        p["generation_history"].append({"image": p["image"], "review": p["review"]})
                        p["image"] = p["review"] = None
            for binding, fingerprint in bindings:
                if any(t["kind"] == kind and t["binding"] == binding and t["input_sha256"] == fingerprint and t["status"] in {"PENDING", "RUNNING"} for t in w["tasks"]):
                    continue
                task = {"id": uid("task"), "kind": kind, "binding": binding, "input_sha256": fingerprint, "status": "PENDING", "attempts": 0, "created_at": now(), "worker": None, "lease_token": None, "lease_until": 0, "error": None,
                        "brief": self.brief(w, kind, source_id=binding if kind == "READ_SOURCE" else None, page_id=binding if kind == "IMAGE" else None)}
                w["tasks"].append(task)
        return self.get(workflow_id)

    def task_current(self, w: dict, t: dict) -> bool:
        if t["kind"] == "READ_SOURCE":
            return any(s["id"] == t["binding"] and s["sha256"] == t["input_sha256"] for s in w["sources"])
        if t["kind"] == "SUMMARY": return fully_read(w) and input_hash(w) == t["input_sha256"]
        if t["kind"] == "PAGE_PLAN": return content_approved(w) and digest(w["summary"]) == t["input_sha256"]
        p = next((p for p in w["pages"] if p["id"] == t["binding"]), None)
        return bool(p) and content_approved(w) and p["contract_sha256"] == t["input_sha256"] and (p in w["pages"][:5] or style_approved(w))

    def claim(self, workflow_id: str, worker: str, kind: str | None = None):
        require(bool(worker.strip()), "请填写执行端标识", 422)
        claimed = None
        with self.transaction(workflow_id, "TASK_CLAIM") as w:
            for t in w["tasks"]:
                if t["status"] == "RUNNING" and t["lease_until"] < time.time():
                    t["status"] = "PENDING" if t["attempts"] < 3 else "FAILED"
                    t["lease_token"] = None
                    t["error"] = "执行租约超时"
                if t["status"] != "PENDING" or (kind and t["kind"] != kind): continue
                if not self.task_current(w, t):
                    t["status"] = "CANCELLED"
                    continue
                if t["attempts"] >= 3:
                    t["status"] = "FAILED"
                    continue
                t.update(status="RUNNING", worker=worker, lease_token=secrets.token_urlsafe(32), lease_until=time.time() + LEASE_SECONDS, attempts=t["attempts"] + 1, error=None)
                claimed = copy.deepcopy(t)
                break
        return claimed

    def leased(self, w: dict, task_id: str, token: str) -> dict:
        t = next((t for t in w["tasks"] if t["id"] == task_id), None)
        require(t, "任务不存在", 404)
        require(t["status"] == "RUNNING" and secrets.compare_digest(t["lease_token"] or "", token) and t["lease_until"] >= time.time(), "任务租约无效或已过期")
        require(self.task_current(w, t), "任务对应的内容或审批已变更")
        return t

    def complete(self, workflow_id: str, task_id: str, token: str, result: dict):
        with self.transaction(workflow_id, "TASK_COMPLETE") as w:
            t = self.leased(w, task_id, token)
            require(t["kind"] != "IMAGE", "图片任务需提交PNG与生成凭据", 422)
            if t["kind"] == "READ_SOURCE":
                self.invalidate_content(w, keep_reading=True)
                self.reading(w, t["binding"], result, t["worker"])
            elif t["kind"] == "SUMMARY": self.accept_summary(w, result)
            else: self.accept_plan(w, result)
            t.update(status="COMPLETE", completed_at=now(), lease_token=None, result_sha256=digest(result))
            t["result_path"] = self.snapshot(w, "task_result", result)
        return self.get(workflow_id)

    def fail(self, workflow_id: str, task_id: str, token: str, error: str):
        with self.transaction(workflow_id, "TASK_FAIL") as w:
            t = self.leased(w, task_id, token)
            t.update(status="PENDING" if t["attempts"] < 3 else "FAILED", lease_token=None, error=error[:2000])
        return self.get(workflow_id)

    def renew(self, workflow_id: str, task_id: str, token: str):
        deadline = 0
        with self.transaction(workflow_id, "TASK_RENEW") as w:
            t = self.leased(w, task_id, token)
            deadline = time.time() + LEASE_SECONDS
            t["lease_until"] = deadline
        return {"task_id": task_id, "lease_until": deadline}

    def image_result(self, workflow_id: str, task_id: str, token: str, content: bytes, receipt: dict):
        require(isinstance(receipt, dict), "生成凭据需为JSON对象", 422)
        require(0 < len(content) <= MAX_UPLOAD, "图片为空或超过40MB", 422)
        require(receipt.get("engine") == "image_gen" and receipt.get("provider") == "OpenAI", "此模式只接受Codex内置ImageGen生成记录", 422)
        require(bool(str(receipt.get("tool_call_id", "")).strip()), "需提供真实工具调用标识", 422)
        try:
            datetime.fromisoformat(receipt.get("generated_at", "").replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise WorkflowError("生成时间需为ISO8601", 422)
        require(receipt.get("image_sha256") == sha(content), "生成凭据与图片校验值不一致", 422)
        require(isinstance(receipt.get("preliminary_qa"), dict), "需提供初步复核记录", 422)
        with Image.open(io.BytesIO(content)) as image:
            require(image.format == "PNG", "交付图片需为PNG", 422)
            width, height = image.size
            require(width >= 1280 and height >= 720 and abs(width / height - 16 / 9) < .02, "图片需为至少1280×720的16:9完整页面", 422)
            image.verify()
        with self.transaction(workflow_id, "IMAGE_COMPLETE") as w:
            t = self.leased(w, task_id, token)
            require(t["kind"] == "IMAGE", "任务不是图片生成任务", 422)
            require(not any(s["sha256"] == sha(content) for s in w["sources"]), "不能用原始资料图片替代模型生成页面", 422)
            require(not any(p["image"] and p["image"]["sha256"] == sha(content) for p in w["pages"] if p["id"] != t["binding"]), "不同页面不能复用同一张整页图", 422)
            p = next(p for p in w["pages"] if p["id"] == t["binding"])
            require(receipt.get("contract_sha256") == p["contract_sha256"], "图片生成凭据对应的页面合同已过期")
            path = self.immutable(workflow_id, "images", content, ".png")
            p["image"] = {"path": path, "sha256": sha(content), "width": width, "height": height,
                          "contract_sha256": p["contract_sha256"], "receipt": {**receipt, "worker": t["worker"], "received_at": now()}, "task_id": t["id"]}
            p["review"] = None
            if p in w["pages"][:5]: w["style_approval"] = None
            t.update(status="COMPLETE", completed_at=now(), lease_token=None, result_sha256=sha(content))
            self.snapshot(w, "generation_receipt", p["image"])
        return self.get(workflow_id)

    def review(self, workflow_id: str, page_id: str, record: dict):
        require(bool(str(record.get("reviewer", "")).strip()), "请填写审核人", 422)
        require(record.get("visual_status") in {"PASS", "REVISE"} and record.get("medical_status") in {"PASS", "REVISE"}, "请分别记录视觉和医学审核结论", 422)
        require(record.get("exact_text_checked") is True, "请核对标题、全文、数字、单位和限定条件", 422)
        with self.transaction(workflow_id, "PAGE_REVIEW") as w:
            p = next((p for p in w["pages"] if p["id"] == page_id), None)
            require(p and p["image"], "页面尚无生成图片")
            require(record.get("image_sha256") == p["image"]["sha256"], "图片已更新，请重新审核")
            require(sha(self.path(p["image"]["path"]).read_bytes()) == p["image"]["sha256"], "图片文件已被修改")
            new = {"reviewer": record["reviewer"], "at": now(), "image_sha256": record["image_sha256"],
                   "visual_status": record["visual_status"], "medical_status": record["medical_status"],
                   "exact_text_checked": True, "feedback": str(record.get("feedback", "")), "identity_assurance": "LOCAL_RECORDED_NOT_AUTHENTICATED"}
            if p in w["pages"][:5]:
                w["style_approval"] = None
                for task in w["tasks"]:
                    if task["kind"] == "IMAGE" and task["binding"] not in {x["id"] for x in w["pages"][:5]} and task["status"] in {"RUNNING", "PENDING"}:
                        task.update(status="CANCELLED", lease_token=None)
            p["review"] = new
            self.snapshot(w, "page_review", new)
        return self.get(workflow_id)

    def export(self, workflow_id: str):
        from app.packager import _pptxgenjs_runtime_paths
        with self.transaction(workflow_id, "EXPORT") as w:
            self.source_integrity(w)
            require(stage(w) in {"READY_TO_EXPORT", "DELIVERED"}, "全部页面生成、逐页审核和两次确认完成后才能交付")
            require(fully_read(w) and content_approved(w) and style_approved(w), "来源或确认已过期")
            for i, p in enumerate(w["pages"], 1):
                require(p["contract_sha256"] == page_hash(w, p, i, len(w["pages"])), "页面合同已变更")
                require(reviewed(p) and p["image"]["contract_sha256"] == p["contract_sha256"], "页面审核或生成合同已过期")
                file = self.path(p["image"]["path"])
                require(file.is_file() and sha(file.read_bytes()) == p["image"]["sha256"], "缺失图片或图片校验不符")
                receipt = p["image"]["receipt"]
                require(receipt["engine"] == "image_gen" and receipt["tool_call_id"] and receipt["image_sha256"] == p["image"]["sha256"], "缺失有效生成凭据")
                t = next((t for t in w["tasks"] if t["id"] == p["image"]["task_id"]), None)
                require(t and t["status"] == "COMPLETE" and t["result_sha256"] == p["image"]["sha256"], "缺失已完成的真实生成任务记录")
            node, _ = _pptxgenjs_runtime_paths()
            version = len(w["deliveries"]) + 1
            relative = f"{workflow_id}/deliveries/v{version:03d}"
            folder = self.path(relative)
            folder.mkdir(parents=True, exist_ok=True)
            report = {"schema_version": "factppt.delivery.v1", "template": TEMPLATE, "baseline": BASELINE,
                      "project": w["title"], "at": now(), "version": version, "page_count": len(w["pages"]),
                      "content_approval": w["content_approval"], "style_approval": w["style_approval"],
                      "source_inventory": [{k: s[k] for k in ("id", "filename", "sha256")} for s in w["sources"]],
                      "pages": [{"id": p["id"], "image_sha256": p["image"]["sha256"], "receipt": p["image"]["receipt"], "review": p["review"], "source_unit_ids": p["source_unit_ids"]} for p in w["pages"]],
                      "verification_limits": "结构检查不验证图片中文字；医学与文字结论来自所列本地人工审核。工具凭据为执行端回传记录，不是供应商签名证明。"}
            report_path = folder / "verification_report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            plan = {"title": w["title"], "pages": [{**p, "image_path": str(self.path(p["image"]["path"])), "source_locations": [
                {"filename": s["filename"], "location": u["location"], "source_sha256": s["sha256"]} for s in w["sources"] for u in s["units"] if u["id"] in p["source_unit_ids"]]} for p in w["pages"]]}
            planfile = folder / "delivery_contract.json"
            planfile.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            result = subprocess.run([str(node), str(ROOT / "app" / "fact57098_writer.mjs"), str(planfile), str(folder)], capture_output=True, text=True, encoding="utf-8", timeout=120)
            require(result.returncode == 0, "PPT打包失败：" + result.stderr[-1500:], 503)
            for name in ("editable.pptx", "image_pages.pptx"):
                with zipfile.ZipFile(folder / name) as archive:
                    slides = [n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
                    require(archive.testzip() is None and len(slides) == len(w["pages"]), "PPT结构校验失败", 503)
                    if name == "image_pages.pptx":
                        require(len([n for n in archive.namelist() if n.startswith("ppt/media/") and not n.endswith("/")]) == len(w["pages"]), "PPT嵌入图片数量不符", 503)
                        for i, p in enumerate(w["pages"], 1):
                            slide = ET.fromstring(archive.read(f"ppt/slides/slide{i}.xml"))
                            require(len(slide.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}pic")) == 1 and
                                    not slide.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}t"), "图片版页面必须仅含一张整页图", 503)
                            blip = slide.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
                            rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                            rels = ET.fromstring(archive.read(f"ppt/slides/_rels/slide{i}.xml.rels"))
                            rel = next(r for r in rels if r.get("Id") == rid)
                            media = posixpath.normpath("ppt/slides/" + rel.get("Target"))
                            require(sha(archive.read(media)) == p["image"]["sha256"], "PPT嵌入图片与已审核图片不一致", 503)
            archive_path = folder / "delivery.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for name in ("editable.pptx", "image_pages.pptx", "verification_report.json"):
                    archive.write(folder / name, name)
                for i, p in enumerate(w["pages"], 1):
                    archive.write(self.path(p["image"]["path"]), f"image_pages/slide-{i:03d}.png")
            delivery = {"version": version, "at": now(), "subject_sha256": sample_all_hash(w), "path": relative,
                        "files": [{"name": n, "sha256": sha((folder / n).read_bytes())} for n in ("editable.pptx", "image_pages.pptx", "verification_report.json", "delivery.zip")]}
            w["deliveries"].append(delivery)
        return self.get(workflow_id)
