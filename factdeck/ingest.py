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
* a **figure** is a picture embedded in the original (PDF image, slide picture,
  Word inline image, or a whole image file), taken out by code and normalised to
  PNG without changing its pixels. Figures can be shown on slides as source
  figures; nothing here judges what they show. Tiny images (icons, logos, rules)
  are not registered.

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
MAX_FIGURES = 500
MIN_FIGURE_SIDE = 120            # px; smaller pictures are icons, logos or rules


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


@dataclass
class Figure:
    id: str
    source_id: str
    page_id: str
    location: str
    method: str                   # embedded (phase 1); page_crop is planned
    width: int
    height: int
    original_format: str
    png: bytes = field(repr=False, default=b"")


def to_png(blob: bytes) -> tuple[bytes, int, int, str] | None:
    """Decode an embedded picture and re-encode it losslessly as PNG. None if unreadable."""
    from PIL import Image
    try:
        with Image.open(io.BytesIO(blob)) as im:
            fmt = (im.format or "").lower()
            im.load()
            if im.mode == "CMYK":                   # PNG cannot hold CMYK; the only conversion made
                im = im.convert("RGB")
            elif im.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"}:
                im = im.convert("RGBA")
            out = io.BytesIO()
            im.save(out, "PNG", optimize=False)
            return out.getvalue(), im.width, im.height, fmt
    except Exception:
        return None


class _Builder:
    def __init__(self, source_id: str):
        self.sid = source_id
        self.pages: list[Page] = []
        self.units: list[Unit] = []
        self.figures: list[Figure] = []
        self._seen: set[tuple[str, bytes]] = set()

    def figure(self, page: Page, blob: bytes, label: str = "图"):
        """Register an embedded picture on `page` (same picture twice on one page counts once)."""
        if (page.id, blob) in self._seen or len(self.figures) >= MAX_FIGURES:
            return
        self._seen.add((page.id, blob))
        png = to_png(blob)
        if not png or min(png[1], png[2]) < MIN_FIGURE_SIDE:
            return
        n = sum(1 for f in self.figures if f.page_id == page.id) + 1
        page.requires_visual = True
        self.figures.append(Figure(f"{page.id}:g{n}", self.sid, page.id, f"{re.sub(r'（[^）]*）', '', page.location)} {label}{n}", "embedded",
                                   png[1], png[2], png[3], png[0]))

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
        try:                      # permission-restricted PDFs open with an empty user password
            opened = reader.decrypt("")
        except Exception:
            opened = 0
        if not opened:
            raise IngestError("PDF需要密码才能打开，请提供未加密的版本")
    columns: list[str] = []
    try:                          # second reading: left half, then right half (two-column layouts)
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content), password="") as pdf:
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
        try:
            images = list(page.images)
        except Exception:
            images = []
        for img in images:
            b.figure(p, img.data)


# ------------------------------------------------------------------ PPTX
_SUP = str.maketrans("0123456789+-=()abcdefghijklmnoprstuvwxyzABDEGHIJKLMNOPRTUVW",
                     "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ")
_SUB = str.maketrans("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")


def _tf_text(text_frame) -> str:
    """Text of a PowerPoint text frame as shown: superscript/subscript runs keep their position
    (10⁹, FEV₁, citation marks¹⁻⁸) instead of collapsing into ordinary digits. Otherwise the same as
    python-pptx's `text_frame.text` (paragraphs joined by newline, line breaks as vertical tab)."""
    from pptx.oxml.ns import qn
    paras = []
    for p in text_frame._txBody.iter(qn("a:p")):
        out = []
        for el in p:
            if el.tag == qn("a:br"):
                out.append("\v")
            elif el.tag in (qn("a:r"), qn("a:fld")):
                t = el.findtext(qn("a:t")) or ""
                rpr = el.find(qn("a:rPr"))
                try:
                    base = int(rpr.get("baseline", "0")) if rpr is not None else 0
                except ValueError:
                    base = 0
                out.append(t.translate(_SUP) if base > 0 else t.translate(_SUB) if base < 0 else t)
        paras.append("".join(out))
    return "\n".join(paras)


def _pptx(b: _Builder, content: bytes):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs = Presentation(io.BytesIO(content))
    for n, slide in enumerate(prs.slides, 1):
        visual = False
        items: list[tuple[str, object]] = []
        pictures: list[bytes] = []

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
            if st == MSO_SHAPE_TYPE.PICTURE:
                try:
                    pictures.append(shape.image.blob)
                except Exception:
                    pass
            if getattr(shape, "has_table", False) and shape.has_table:
                items.append(("table", shape.table))
            elif getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                items.append(("text", _tf_text(shape.text_frame)))
            elif type(shape).__name__ == "GraphicFrame" and not getattr(shape, "has_table", False):
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
                        b.unit(p, f"t{tab}r{r}c{c}", f"第{n}页 表格{tab} 第{r}行第{c}列", _tf_text(cell.text_frame), "pptx_table_cell")
        if slide.has_notes_slide:
            b.unit(p, "notes", f"第{n}页 演讲者备注", _tf_text(slide.notes_slide.notes_text_frame), "pptx_notes")
        p.location = f"第{n}页" + ("（含图片/图表）" if visual else "")
        for blob in pictures:
            b.figure(p, blob)


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
                ns_r = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
                for blip in el.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
                    part = doc.part.related_parts.get(blip.get(ns_r + "embed"))
                    if part is not None and hasattr(part, "blob"):
                        b.figure(section, part.blob)
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
    p = b.page("img", "整幅图片", True)
    b.figure(p, content, "图片")


def extract(filename: str, content: bytes, source_id: str) -> tuple[list[Page], list[Unit]]:
    pages, units, _ = extract_all(filename, content, source_id)
    return pages, units


def extract_all(filename: str, content: bytes, source_id: str) -> tuple[list[Page], list[Unit], list[Figure]]:
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
    return b.pages, b.units, b.figures


def transcription_units(page: dict, cells: list[dict], reader: str, figure_ids=frozenset()) -> list[dict]:
    """Units for a reader's transcription of a picture/chart on `page`.

    Each cell: {"id": "c1", "location": "图表 第2个柱 数值标签", "text": "...", "figure": optional figure id}.
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
        fig = str(c.get("figure") or "")
        if fig and fig not in figure_ids:
            raise IngestError(f"转录单元 {cid} 指向的图不在本页：{fig}")
        out.append(asdict(Unit(f"{page['id']}:x.{cid}", page["source_id"], page["id"], f"{page['location']} {loc}",
                               text, "visual_transcription", needs_confirmation=True)) | {"reader": reader, "figure_id": fig})
    return out


def to_dicts(pages: list[Page], units: list[Unit]) -> tuple[list[dict], list[dict]]:
    return [asdict(p) for p in pages], [asdict(u) for u in units]
