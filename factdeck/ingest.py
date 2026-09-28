"""Turn any supported source file into reading pages and quotable units.

Two granularities:

* a **page** is what a reader records as read: a PDF page, a slide, a worksheet
  block, a section of a Word/text document, or a whole image. Pages that contain
  pictures, charts or no extractable text are marked `requires_visual`.
* a **unit** is the smallest piece of text a fact may quote, with a precise
  location: a PDF page, a slide text box / table cell / speaker notes, a document
  paragraph / table cell, a worksheet row, a text paragraph. Units carry the text
  extracted by code, never text written by a model. Transcriptions of images and
  charts are added later as separate units that need confirmation.

Supported: PDF, PPTX, DOCX, XLSX, TXT/MD, PNG/JPG/JPEG/WEBP.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

SUPPORTED = {".pdf", ".pptx", ".docx", ".xlsx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}
MAX_UNITS = 20000
MAX_TEXT = 3_000_000


class IngestError(ValueError):
    pass


@dataclass
class Unit:
    id: str
    source_id: str
    page_id: str
    location: str
    text: str
    method: str
    needs_confirmation: bool = False
    alt_text: str = ""


@dataclass
class Page:
    id: str
    source_id: str
    number: int
    location: str
    text: str                     # all extracted text of the page, for the reader's convenience
    requires_visual: bool
    unit_ids: list[str] = field(default_factory=list)


class _Builder:
    def __init__(self, source_id: str):
        self.sid = source_id
        self.pages: list[Page] = []
        self.units: list[Unit] = []

    def page(self, key: str, location: str, visual: bool) -> Page:
        p = Page(f"{self.sid}:{key}", self.sid, len(self.pages) + 1, location, "", visual)
        self.pages.append(p)
        return p

    def unit(self, page: Page, key: str, location: str, text: str, method: str, alt: str = ""):
        if not text.strip():
            return
        u = Unit(f"{page.id}:{key}" if key else page.id, self.sid, page.id, location, text, method, alt_text=alt)
        self.units.append(u)
        page.unit_ids.append(u.id)
        page.text = (page.text + "\n" + text).strip() if page.text else text


# ------------------------------------------------------------------ PDF
def _pdf(b: _Builder, content: bytes):
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        raise IngestError("请先提供未加密的PDF")
    columns: list[str] = []
    try:                          # second reading: left half, then right half (two-column layouts)
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                w, h = page.width, page.height
                columns.append((page.crop((0, 0, w / 2, h)).extract_text() or "") + "\n" +
                               (page.crop((w / 2, 0, w, h)).extract_text() or ""))
    except Exception:
        columns = []
    for i, page in enumerate(reader.pages, 1):
        visual = False
        try:
            stream = page.get_contents()
            if stream:
                visual = any(op in {b"Do", b"BI", b"sh"} for _, op in ContentStream(stream, reader).operations)
        except Exception:
            visual = True
        text = page.extract_text() or ""
        p = b.page(f"p{i}", f"第{i}页", visual or not text.strip())
        b.unit(p, "", f"第{i}页", text, "pdf_page", alt=columns[i - 1] if i <= len(columns) else "")


# ------------------------------------------------------------------ PPTX
def _pptx(b: _Builder, content: bytes):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs = Presentation(io.BytesIO(content))
    for n, slide in enumerate(prs.slides, 1):
        visual = False
        items: list[tuple[str, object]] = []

        def walk(shape):
            nonlocal visual
            st = shape.shape_type
            if st == MSO_SHAPE_TYPE.GROUP:
                for child in shape.shapes:
                    walk(child)
                return
            if st in (MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.CHART, MSO_SHAPE_TYPE.MEDIA, MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT) \
                    or getattr(shape, "has_chart", False):
                visual = True
            if getattr(shape, "has_table", False) and shape.has_table:
                items.append(("table", shape.table))
            elif getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                items.append(("text", shape.text_frame.text))
            elif st == MSO_SHAPE_TYPE.GRAPHIC_FRAME and not getattr(shape, "has_table", False):
                visual = True       # SmartArt and other diagrams

        for shape in slide.shapes:
            walk(shape)
        p = b.page(f"s{n}", f"第{n}页", True)   # slides always need a look at the original
        p.requires_visual = True
        box = tab = 0
        for kind, obj in items:
            if kind == "text":
                box += 1
                b.unit(p, f"b{box}", f"第{n}页 文本框{box}", obj, "pptx_text")
            else:
                tab += 1
                for r, row in enumerate(obj.rows, 1):
                    for c, cell in enumerate(row.cells, 1):
                        b.unit(p, f"t{tab}r{r}c{c}", f"第{n}页 表格{tab} 第{r}行第{c}列", cell.text, "pptx_table_cell")
        if slide.has_notes_slide:
            b.unit(p, "notes", f"第{n}页 演讲者备注", slide.notes_slide.notes_text_frame.text, "pptx_notes")
        p.location = f"第{n}页" + ("（含图片/图表）" if visual else "")


# ------------------------------------------------------------------ DOCX
def _docx(b: _Builder, content: bytes):
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(io.BytesIO(content))
    ns_w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    section, para_no, tab_no, count = None, 0, 0, 0

    def new_section(title: str):
        nonlocal section, count
        label = f"第{len(b.pages) + 1}部分" + (f"「{title[:30]}」" if title else "")
        section = b.page(f"d{len(b.pages) + 1}", label, False)
        count = 0

    for el in doc.element.body.iterchildren():
        if el.tag == ns_w + "p":
            para = Paragraph(el, doc)
            text = para.text
            style = (para.style.name if para.style is not None else "") or ""
            heading = style.lower().startswith(("heading", "title")) or style.startswith(("标题",))
            if section is None or (heading and count) or count >= 40:
                new_section(text.strip() if heading else "")
            if el.findall(f".//{ns_w}drawing") or el.findall(".//{urn:schemas-microsoft-com:vml}imagedata"):
                section.requires_visual = True
            if text.strip():
                para_no += 1
                count += 1
                b.unit(section, f"para{para_no}", f"{section.location} 第{para_no}段", text, "docx_paragraph")
        elif el.tag == ns_w + "tbl":
            if section is None:
                new_section("")
            tab_no += 1
            table = Table(el, doc)
            for r, row in enumerate(table.rows, 1):
                for c, cell in enumerate(row.cells, 1):
                    b.unit(section, f"t{tab_no}r{r}c{c}", f"{section.location} 表格{tab_no} 第{r}行第{c}列", cell.text, "docx_table_cell")
            count += len(table.rows)
    extra = [p.text for s in doc.sections for part in (s.header, s.footer) for p in part.paragraphs if p.text.strip()]
    if extra:
        p = b.page("hf", "页眉页脚", False)
        for i, t in enumerate(extra, 1):
            b.unit(p, f"hf{i}", f"页眉页脚 第{i}条", t, "docx_header_footer")
    if not b.pages:
        b.page("d1", "全文", True)


# ------------------------------------------------------------------ XLSX
def _xlsx(b: _Builder, content: bytes):
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(content), data_only=False)
    for sheet in book.worksheets:
        visual = bool(getattr(sheet, "_charts", None) or getattr(sheet, "_images", None))
        rows = [row for row in sheet.iter_rows() if any(c.value is not None for c in row)]
        for start in range(0, max(len(rows), 1), 200):
            chunk = rows[start:start + 200]
            label = f"工作表「{sheet.title}」" + (f" 第{start // 200 + 1}块" if len(rows) > 200 else "")
            p = b.page(f"x{len(b.pages) + 1}", label + ("（含图表）" if visual else ""), visual or not chunk)
            for row in chunk:
                r = row[0].row
                text = " | ".join(f"{c.coordinate}: {c.value}" for c in row if c.value is not None)
                b.unit(p, f"r{r}", f"工作表「{sheet.title}」第{r}行", text, "xlsx_row")


# ------------------------------------------------------------------ TXT / MD
def _text(b: _Builder, content: bytes):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("gb18030")
    blocks = [x for x in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if x.strip()]
    page, n = None, 0
    for block in blocks:
        heading = re.match(r"\s*#{1,3}\s+(.+)", block)
        if page is None or (heading and page.unit_ids) or len(page.unit_ids) >= 30:
            title = heading.group(1).strip()[:30] if heading else ""
            page = b.page(f"t{len(b.pages) + 1}", f"第{len(b.pages) + 1}部分" + (f"「{title}」" if title else ""), False)
        n += 1
        b.unit(page, f"para{n}", f"{page.location} 第{n}段", block.strip("\n"), "text_paragraph")
    if not b.pages:
        b.page("t1", "全文", True)


def _image(b: _Builder, content: bytes):
    from PIL import Image
    with Image.open(io.BytesIO(content)) as image:
        image.verify()
    b.page("img", "整幅图片", True)


def extract(filename: str, content: bytes, source_id: str) -> tuple[list[Page], list[Unit]]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise IngestError("支持PDF、PPTX、DOCX、XLSX、TXT/MD和PNG/JPG/WEBP")
    if not content:
        raise IngestError("资料为空")
    b = _Builder(source_id)
    {".pdf": _pdf, ".pptx": _pptx, ".docx": _docx, ".xlsx": _xlsx, ".txt": _text, ".md": _text}.get(suffix, _image)(b, content)
    if not b.pages:
        raise IngestError("资料中没有可登记的页面")
    if len(b.units) > MAX_UNITS or sum(len(u.text) for u in b.units) > MAX_TEXT:
        raise IngestError("资料超出容量；请拆分导入，不能截断")
    return b.pages, b.units


def transcription_units(page: dict, cells: list[dict], reader: str) -> list[dict]:
    """Units for a reader's transcription of a picture/chart on `page`.

    Each cell: {"id": "c1", "location": "图表 第2个柱 数值标签", "text": "..."}.
    They need confirmation until a second, independent read agrees.
    """
    out, seen = [], set()
    for c in cells:
        cid = str(c.get("id", "")).strip()
        if not re.fullmatch(r"[\w.\-一-鿿]{1,60}", cid) or cid in seen:
            raise IngestError(f"转录单元编号非法或重复：{cid!r}")
        seen.add(cid)
        text, loc = str(c.get("text", "")), str(c.get("location", "")).strip()
        if not text.strip() or not loc:
            raise IngestError("转录单元需提供位置和文字")
        out.append(asdict(Unit(f"{page['id']}:x.{cid}", page["source_id"], page["id"], f"{page['location']} {loc}",
                               text, "visual_transcription", needs_confirmation=True)) | {"reader": reader})
    return out


def to_dicts(pages: list[Page], units: list[Unit]) -> tuple[list[dict], list[dict]]:
    return [asdict(p) for p in pages], [asdict(u) for u in units]
