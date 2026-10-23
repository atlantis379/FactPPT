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
* a **page crop** is a region of a PDF page chosen by a reader (vector charts,
  composite figures that are not one embedded picture). Code renders the page and
  cuts the region; the reader only gives the box, never pixels.

Supported: PDF, PPTX, DOCX, XLSX, TXT/MD, PNG/JPG/JPEG/WEBP.
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

SUPPORTED = {".pdf", ".pptx", ".docx", ".xlsx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}
MAX_UNITS = 20000
MAX_TEXT = 3_000_000
MAX_FIGURES = 500
MIN_FIGURE_SIDE = 120            # px; smaller pictures are icons, logos or rules
CROP_DPI = 200                   # page crops are cut from the page rendered at this resolution
CROP_AGREE_IOU = 0.9             # two independent boxes closer than this count as the same region


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
    arrow: dict | None = None     # pptx_arrow units: {from, to, label} unit ids, recovered from the diagram's geometry
    signals: dict | None = None   # what the original's author marked: {"title": [...], "emphasis": [...]} fragments of `text`


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
    method: str                   # embedded; page crops are registered by the workflow (see crop_pdf_page)
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
PDF_EMPHASIS = 1.2            # a line set at least this many times the page's usual size is marked


def _pdf_marks(page) -> dict:
    """Lines the author set apart on a PDF page: the largest line in the top zone is the title; lines in a
    bold face or at least PDF_EMPHASIS times the usual size are emphasis."""
    words = page.extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=True) or []
    lines: dict[int, list] = {}
    for wd in words:
        lines.setdefault(round(wd["top"] / 3), []).append(wd)
    rows = []
    for _, ws in sorted(lines.items()):
        ws.sort(key=lambda wd: wd["x0"])
        text = "".join(wd["text"] for wd in ws).strip()
        if len(text) >= 2:
            rows.append((text, max(wd["size"] for wd in ws), any("bold" in wd["fontname"].lower() for wd in ws), ws[0]["top"]))
    if not rows:
        return {"title": [], "emphasis": []}
    sizes = sorted(r[1] for r in rows)
    usual = sizes[len(sizes) // 2]
    top = [r for r in rows if r[3] <= TITLE_ZONE * page.height and r[1] >= PDF_EMPHASIS * usual]
    title = [max(top, key=lambda r: r[1])[0]] if top else []
    emphasis = [r[0] for r in rows if (r[2] or r[1] >= PDF_EMPHASIS * usual) and r[0] not in title]
    return {"title": title, "emphasis": emphasis[:12]}


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
    marks: list[dict] = []
    try:                          # second reading: left half, then right half (two-column layouts)
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content), password="") as pdf:
            for page in pdf.pages:
                w, h = page.width, page.height
                columns.append((page.crop((0, 0, w / 2, h)).extract_text() or "") + "\n" +
                               (page.crop((w / 2, 0, w, h)).extract_text() or ""))
                marks.append(_pdf_marks(page))
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
        if i <= len(marks) and b.units and b.units[-1].id == p.id:
            from .lexicon import canon
            whole = canon(text)                          # keep only lines the page's own text contains
            m = {k: [x for x in v if canon(x) in whole] for k, v in marks[i - 1].items()}
            if m["title"] or m["emphasis"]:
                b.units[-1].signals = m
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


def _run_text(el, qn) -> str:
    t = el.findtext(qn("a:t")) or ""
    rpr = el.find(qn("a:rPr"))
    try:
        base = int(rpr.get("baseline", "0")) if rpr is not None else 0
    except ValueError:
        base = 0
    return t.translate(_SUP) if base > 0 else t.translate(_SUB) if base < 0 else t


def _tf_emphasis(text_frame) -> tuple[list[str], float]:
    """Fragments the author set apart inside a text frame (bold, an explicit colour other than the frame's usual one,
    or a size at least 1.2 times the frame's usual size), and the frame's largest explicit size in points.
    Consecutive marked runs join into one fragment; the fragments are substrings of `_tf_text`."""
    from pptx.oxml.ns import qn
    runs = []                                  # (text, bold, colour, size)
    for p in text_frame._txBody.iter(qn("a:p")):
        for el in p:
            if el.tag in (qn("a:r"), qn("a:fld")):
                rpr = el.find(qn("a:rPr"))
                fill = rpr.find(qn("a:solidFill")) if rpr is not None else None
                clr = None
                if fill is not None and len(fill):
                    clr = fill[0].get("val")
                size = int(rpr.get("sz")) / 100 if rpr is not None and rpr.get("sz", "").isdigit() else None
                runs.append((_run_text(el, qn), rpr is not None and rpr.get("b") == "1", clr, size))
            elif el.tag == qn("a:br"):
                runs.append(("\v", False, None, None))
        runs.append(("\n", False, None, None))
    colours = [c for _, _, c, _ in runs if c]
    usual_colour = max(set(colours), key=colours.count) if colours and len(set(colours)) > 1 else None
    sizes = sorted(s for _, _, _, s in runs if s)
    usual_size = sizes[len(sizes) // 2] if sizes else None
    out, cur = [], ""
    for t, bold, clr, size in runs:
        marked = t.strip() and (bold or (usual_colour and clr and clr != usual_colour) or (usual_size and size and size >= 1.2 * usual_size))
        if marked:
            cur += t
        else:
            if len(cur.strip()) >= 2:
                out.append(cur.strip())
            cur = ""
    if len(cur.strip()) >= 2:
        out.append(cur.strip())
    return out, (sizes[-1] if sizes else 0.0)


_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_BLOCK = {"rightArrow": "right", "leftArrow": "left", "upArrow": "up", "downArrow": "down",
          "notchedRightArrow": "right", "stripedRightArrow": "right"}
_TURN = {"right": "down", "down": "left", "left": "up", "up": "right"}       # a quarter turn clockwise


def _plain_text(shape) -> bool:
    """A text box with no fill or outline: how diagrams write arrow labels such as 是/否 (filled shapes are nodes)."""
    el = shape._element
    c = el.find("./{*}nvSpPr/{*}cNvSpPr")
    if c is not None and c.get("txBox") == "1":
        return True
    sp = el.find("./{*}spPr")
    if sp is None or sp.find("./" + _A + "prstGeom") is None:
        return False
    filled = any(sp.find("./" + _A + k) is not None for k in ("solidFill", "gradFill", "pattFill", "blipFill"))
    ln = sp.find("./" + _A + "ln")
    outlined = ln is not None and ln.find("./" + _A + "noFill") is None
    return not filled and not outlined and el.find("./{*}style") is None


def _xfrm(shape):
    el = shape._element
    for path in ("./{*}grpSpPr/" + _A + "xfrm", "./{*}spPr/" + _A + "xfrm"):
        x = el.find(path)
        if x is not None and x.find(_A + "off") is not None and x.find(_A + "ext") is not None:
            return x
    return None


def _box(x, T):
    """Absolute (x, y, w, h) of an xfrm under the group transform T (scale x, scale y, offset x, offset y)."""
    sx, sy, ox, oy = T
    off, ext = x.find(_A + "off"), x.find(_A + "ext")
    return (ox + int(off.get("x")) * sx, oy + int(off.get("y")) * sy, int(ext.get("cx")) * sx, int(ext.get("cy")) * sy)


def _connector_path(el, x, T):
    """The connector's drawn path as absolute points: elbow connectors follow their bends (adj values),
    then flip and rotation are applied about the centre as DrawingML does."""
    bx, by, w, h = _box(x, T)
    prst = el.find(".//" + _A + "prstGeom")
    kind = prst.get("prst", "") if prst is not None else ""
    adj = {g.get("name"): int(g.get("fmla", "val 50000").split()[-1]) / 100000 for g in el.iter(_A + "gd")}
    a1, a2, a3 = adj.get("adj1", .5), adj.get("adj2", .5), adj.get("adj3", .5)
    local = {"bentConnector2": [(0, 0), (w, 0), (w, h)], "curvedConnector2": [(0, 0), (w, 0), (w, h)],
             "bentConnector3": [(0, 0), (a1 * w, 0), (a1 * w, h), (w, h)], "curvedConnector3": [(0, 0), (a1 * w, 0), (a1 * w, h), (w, h)],
             "bentConnector4": [(0, 0), (a1 * w, 0), (a1 * w, a2 * h), (w, a2 * h), (w, h)],
             "bentConnector5": [(0, 0), (a1 * w, 0), (a1 * w, a2 * h), (a3 * w, a2 * h), (a3 * w, h), (w, h)],
             }.get(kind, [(0, 0), (w, h)])
    fh, fv = x.get("flipH") == "1", x.get("flipV") == "1"
    t = math.radians(int(x.get("rot", "0")) / 60000)
    cx, cy = w / 2, h / 2

    def place(p):
        px, py = (w - p[0] if fh else p[0]), (h - p[1] if fv else p[1])
        return (bx + cx + (px - cx) * math.cos(t) - (py - cy) * math.sin(t),
                by + cy + (px - cx) * math.sin(t) + (py - cy) * math.cos(t))
    return [place(p) for p in local]


TITLE_ZONE = 0.2              # share of the slide height from the top where a title box sits
FOOT_ZONE = 0.85              # boxes starting below this share of the height are footnotes and references: no marks


def _headline(text: str) -> bool:
    """Worth reading as a title: at least two characters that are not digits or punctuation (not a page number)."""
    return sum(ch.isalpha() for ch in text) >= 2


def _mark_slide(text_unit: dict, sig: dict, slide_height: int) -> None:
    """Attach each text box's marks to its unit. Emphasis is a fragment set apart inside a box (a whole box in bold is
    the box's style, not a mark). The slide title is the title placeholder; failing that, the box
    in the top zone set in the slide's largest explicit type size (a headline written as an ordinary text box)."""
    titles = [i for i in text_unit if sig.get(i, {}).get("title") and _headline(text_unit[i].text)]
    if not titles:                         # a headline in the top zone: a placeholder first, then the largest type, then the highest
        top = [i for i in text_unit if sig.get(i, {}).get("top") is not None and sig[i]["top"] <= TITLE_ZONE * slide_height
               and _headline(text_unit[i].text)]
        if top:
            titles = [min(top, key=lambda i: (not sig[i].get("placeholder"), -(sig[i]["size"] or 0), sig[i]["top"]))]
    for i, u in text_unit.items():
        s = sig.get(i) or {}
        if s.get("top") is not None and s["top"] >= FOOT_ZONE * slide_height:
            s = {}
        marks = {"title": [u.text.strip()] if i in titles else [],
                 "emphasis": [e for e in s.get("emphasis", []) if e in u.text and e != u.text.strip() and _headline(e)]}
        if marks["title"] or marks["emphasis"]:
            u.signals = marks


def _pptx(b: _Builder, content: bytes):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from .diagram import arrows as find_arrows
    prs = Presentation(io.BytesIO(content))
    for n, slide in enumerate(prs.slides, 1):
        visual = False
        items: list[tuple[str, object]] = []
        pictures: list[bytes] = []
        geo = {"text": {}, "segments": [], "blocks": []}     # text item index → box; connector lines; block arrows
        sig: dict[int, dict] = {}                             # text item index → the author's marks

        def walk(shape, T=(1.0, 1.0, 0.0, 0.0)):
            nonlocal visual
            st = shape.shape_type
            x = _xfrm(shape)
            if st == MSO_SHAPE_TYPE.GROUP:
                if x is not None and x.find(_A + "chOff") is not None:
                    off, ext, cho, che = (x.find(_A + k) for k in ("off", "ext", "chOff", "chExt"))
                    gx = int(ext.get("cx")) / max(1, int(che.get("cx")))
                    gy = int(ext.get("cy")) / max(1, int(che.get("cy")))
                    sx, sy, ox, oy = T
                    T = (sx * gx, sy * gy, ox + (int(off.get("x")) - int(cho.get("x")) * gx) * sx,
                         oy + (int(off.get("y")) - int(cho.get("y")) * gy) * sy)
                for child in shape.shapes:
                    walk(child, T)
                return
            tag = shape._element.tag.rsplit("}", 1)[-1]
            if tag == "cxnSp" and x is not None:
                ln = shape._element.find(".//" + _A + "ln")
                head = lambda k: ln is not None and ln.find(_A + k) is not None and ln.find(_A + k).get("type", "none") != "none"
                st_c, en_c = shape._element.find(".//" + _A + "stCxn"), shape._element.find(".//" + _A + "endCxn")
                geo["segments"].append((_connector_path(shape._element, x, T), head("headEnd"), head("tailEnd"),
                                        st_c.get("id") if st_c is not None else None, en_c.get("id") if en_c is not None else None))
                return
            prst = shape._element.find(".//" + _A + "prstGeom")
            if prst is not None and prst.get("prst") in _BLOCK and x is not None \
                    and not (getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip()):
                d = _BLOCK[prst.get("prst")]
                for _ in range(round(int(x.get("rot", "0")) / 5400000) % 4):
                    d = _TURN[d]
                if x.get("flipH") == "1" and d in ("left", "right") or x.get("flipV") == "1" and d in ("up", "down"):
                    d = {"left": "right", "right": "left", "up": "down", "down": "up"}[d]
                geo["blocks"].append((*_box(x, T), d))
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
                if x is not None:
                    geo["text"][len(items)] = (_box(x, T), str(shape.shape_id), _plain_text(shape))
                emph, size = _tf_emphasis(shape.text_frame)
                ph = shape.placeholder_format.type if getattr(shape, "is_placeholder", False) else None
                sig[len(items)] = {"title": ph in (1, 3), "emphasis": emph, "size": size,     # 1 TITLE, 3 CENTER_TITLE
                                   "placeholder": ph is not None and ph not in (13, 15, 16),     # not slide number/footer/date
                                   "top": _box(x, T)[1] if x is not None else (0 if ph is not None else None)}
                items.append(("text", _tf_text(shape.text_frame)))
            elif type(shape).__name__ == "GraphicFrame" and not getattr(shape, "has_table", False):
                visual = True       # SmartArt and other diagrams

        for shape in slide.shapes:
            walk(shape)
        p = b.page(f"s{n}", f"第{n}页", True)   # slides always need a look at the original
        p.requires_visual = True
        box = tab = 0
        boxes, labels, by_shape, units, text_unit = {}, {}, {}, {}, {}
        for i, (kind, obj) in enumerate(items):
            if kind == "text":
                box += 1
                b.unit(p, f"b{box}", f"第{n}页 文本框{box}", obj, "pptx_text")
                if b.units and b.units[-1].id == f"{p.id}:b{box}":
                    text_unit[i] = b.units[-1]
                if i in geo["text"] and b.units and b.units[-1].id == f"{p.id}:b{box}":
                    key = f"b{box}"
                    boxes[key], units[key] = geo["text"][i][0], b.units[-1]
                    by_shape[geo["text"][i][1]] = key
                    if geo["text"][i][2]:
                        labels[key] = obj
            else:
                tab += 1
                for r, row in enumerate(obj.rows, 1):
                    for c, cell in enumerate(row.cells, 1):
                        b.unit(p, f"t{tab}r{r}c{c}", f"第{n}页 表格{tab} 第{r}行第{c}列", _tf_text(cell.text_frame), "pptx_table_cell")
        if boxes and (geo["segments"] or geo["blocks"]):
            segs = [(path, h0, h1, by_shape.get(g0), by_shape.get(g1)) for path, h0, h1, g0, g1 in geo["segments"]]
            for k, a in enumerate(find_arrows(boxes, segs, geo["blocks"], labels, prs.slide_width or 12192000), 1):
                src, dst = units[a["from"]], units[a["to"]]
                lab = units[a["label"]] if a["label"] else None
                how = {"connector": "连接线", "connector_geometry": "连接线，按图形位置推断", "block_arrow": "箭头图形，按位置推断"}[a["method"]]
                text = f"{src.text.strip()}→{dst.text.strip()}" + (f"（{lab.text.strip()}）" if lab else "")
                b.unit(p, f"a{k}", f"第{n}页 箭头{k}（文本框{a['from'][1:]}→文本框{a['to'][1:]}，{how}）", text, "pptx_arrow")
                b.units[-1].arrow = {"from": src.id, "to": dst.id, "label": lab.id if lab else None, "method": a["method"]}
        _mark_slide(text_unit, sig, prs.slide_height or 6858000)
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
                bold, cur = [], ""
                for run in para.runs:                  # consecutive bold runs form one emphasised fragment
                    if run.bold and run.text.strip():
                        cur += run.text
                    else:
                        if len(cur.strip()) >= 2:
                            bold.append(cur.strip())
                        cur = ""
                if len(cur.strip()) >= 2:
                    bold.append(cur.strip())
                marks = {"title": [text.strip()] if heading else [], "emphasis": [x for x in bold if x in text and x != text.strip()]}
                if marks["title"] or marks["emphasis"]:
                    b.units[-1].signals = marks
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


def check_bbox(bbox) -> list[float]:
    """A crop box in normalised page coordinates [x0, y0, x1, y1] (origin top left)."""
    if not (isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox)):
        raise IngestError("截取区域 bbox 需为 [x0, y0, x1, y1] 四个数（页面归一化坐标，左上角为原点）")
    x0, y0, x1, y1 = (float(v) for v in bbox)
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise IngestError(f"截取区域超出页面或方向颠倒：{bbox}")
    if x1 - x0 < 0.05 or y1 - y0 < 0.05:
        raise IngestError(f"截取区域过小：{bbox}")
    return [round(v, 4) for v in (x0, y0, x1, y1)]


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return round(inter / union, 4) if union > 0 else 0.0


def render_pdf_page(content: bytes, number: int, dpi: int = CROP_DPI):
    """PIL image of PDF page `number` (1-based), rendered by code (pypdfium2) on a white background."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(content)
    try:
        if not 1 <= number <= len(pdf):
            raise IngestError(f"PDF没有第{number}页")
        page = pdf[number - 1]
        try:
            return page.render(scale=dpi / 72, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
        finally:
            page.close()
    finally:
        pdf.close()


def crop_pdf_page(content: bytes, number: int, bbox: list[float], dpi: int = CROP_DPI) -> tuple[bytes, int, int]:
    """Cut `bbox` out of the rendered page; PNG bytes and size. Same input, same bytes."""
    im = render_pdf_page(content, number, dpi)
    W, H = im.size
    box = (round(bbox[0] * W), round(bbox[1] * H), round(bbox[2] * W), round(bbox[3] * H))
    part = im.crop(box)
    if min(part.size) < MIN_FIGURE_SIDE:
        raise IngestError(f"截取区域在 {dpi} dpi 下只有 {part.size[0]}×{part.size[1]} 像素，过小")
    out = io.BytesIO()
    part.save(out, "PNG", optimize=False)
    return out.getvalue(), part.size[0], part.size[1]


def transcription_units(page: dict, cells: list[dict], reader: str, figure_ids=frozenset()) -> list[dict]:
    """Units for a reader's transcription of a picture/chart on `page`.

    Each cell: {"id": "c1", "location": "图表 第2个柱 数值标签", "text": "...", "figure": optional figure id,
    "parent": optional id of an earlier cell on this page that this one sits under (a table sub-row, a subtype)}.
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
        parent = str(c.get("parent") or "").strip()
        if parent and (parent == cid or parent not in seen):
            raise IngestError(f"转录单元 {cid} 的 parent 须是本页在它之前转录的另一格：{parent}")
        out.append(asdict(Unit(f"{page['id']}:x.{cid}", page["source_id"], page["id"], f"{page['location']} {loc}",
                               text, "visual_transcription", needs_confirmation=True)) | {"reader": reader, "figure_id": fig}
                   | ({"parent": f"{page['id']}:x.{parent}"} if parent else {}))
    return out


def to_dicts(pages: list[Page], units: list[Unit]) -> tuple[list[dict], list[dict]]:
    return [asdict(p) for p in pages], [asdict(u) for u in units]
