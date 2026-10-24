"""Native PPTX writer for template-library pages (T_TEMPLATE_NATIVE).

Pipeline: Jinja HTML (html_render) → Playwright renders + measures every element (native_extract.js) →
python-pptx writes native objects at the measured geometry:

* HTML text  → text boxes with real, editable runs (font, size, bold, colour, letter-spacing, super/subscript)
* <table>    → native PowerPoint tables (cell spans, fills, per-side borders, padding, runs)
* boxes      → rectangles / rounded rectangles / ovals with solid or linear-gradient fill, borders, outer shadow
* SVG        → native lines (connectors), freeforms (polylines, polygons, paths), rectangles, ovals and text
               boxes, mapped through each element's screen CTM, so chart geometry computed in pharma.py
               (bars, CI whiskers, markers, axes, ticks, tree connectors) lands 1:1.

No whole-slide bitmap, no embedded SVG, no picture object of any kind is written.  Slide size = the HTML slide
(1280×720 px = 13.333 in × 7.5 in, 16:9).
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
EXTRACT_JS = (HERE / "native_extract.js").read_text(encoding="utf-8")
PX = 9525                                    # EMU per CSS px at 96 dpi
DEFAULT_FONT = "Noto Sans CJK SC"            # the face the browser measured with (OFL; installable on Windows/macOS)
TEXT_SLACK = 0.03                            # wrapping text boxes get 3 % (+2 px) extra width against metric drift
VERSION = "template-native.1"


def E(v: float) -> int:
    return int(round(v * PX))


def extract_slide(page, selector: str = ".slide") -> dict:
    """Run the extractor on the current Playwright page (slide already rendered)."""
    return page.evaluate(EXTRACT_JS, {"selector": selector})


# ------------------------------------------------------------------ low-level helpers

def _rgb(hexv: str):
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(hexv.upper())


def _qn(tag: str):
    from pptx.oxml.ns import qn
    return qn(tag)


def _set_alpha(parent_el, a: float) -> None:
    """Add <a:alpha> to the first colour element under parent_el."""
    if a is None or a >= 0.999:
        return
    for clr in parent_el.iter(_qn("a:srgbClr"), _qn("a:schemeClr")):
        for old in clr.findall(_qn("a:alpha")):
            clr.remove(old)
        el = clr.makeelement(_qn("a:alpha"), {"val": str(max(0, int(a * 100000)))})
        clr.append(el)
        return


def _solid(fill_fmt, color: dict | None) -> None:
    if not color:
        fill_fmt.background()
        return
    fill_fmt.solid()
    fill_fmt.fore_color.rgb = _rgb(color["hex"])
    _set_alpha(fill_fmt._xPr.find(_qn("a:solidFill")), color.get("a", 1))


def _blend(hexv: str, a: float, under: str) -> str:
    c = [int(hexv[i:i + 2], 16) for i in (0, 2, 4)]
    u = [int(under[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(x * a + y * (1 - a)):02X}" for x, y in zip(c, u))


def _gradient(shape, grad: dict, under: str | None = None) -> None:
    """CSS linear-gradient → DrawingML gradFill (angle: CSS 0deg = to top, clockwise; OOXML 0 = to right).
    Translucent stops are pre-blended onto the slide background (`under`): renderers disagree on per-stop alpha."""
    if under:
        grad = {**grad, "stops": [dict(st, hex=_blend(st["hex"], st.get("a", 1), under), a=1) if st.get("a", 1) < 0.999
                                  else st for st in grad["stops"]]}
    spPr = shape._element.spPr
    for tag in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill"):
        for old in spPr.findall(_qn(tag)):
            spPr.remove(old)
    gf = spPr.makeelement(_qn("a:gradFill"), {"rotWithShape": "1"})
    lst = gf.makeelement(_qn("a:gsLst"), {})
    for st in grad["stops"]:
        gs = lst.makeelement(_qn("a:gs"), {"pos": str(int(max(0, min(1, st["pos"])) * 100000))})
        c = gs.makeelement(_qn("a:srgbClr"), {"val": st["hex"].upper()})
        if st.get("a", 1) < 0.999:
            c.append(c.makeelement(_qn("a:alpha"), {"val": str(int(st["a"] * 100000))}))
        gs.append(c)
        lst.append(gs)
    gf.append(lst)
    ang = (grad.get("angle", 180) - 90) % 360
    gf.append(gf.makeelement(_qn("a:lin"), {"ang": str(int(ang * 60000)), "scaled": "0"}))
    # gradFill goes right after the geometry (prstGeom/custGeom), before <a:ln>
    geom = spPr.find(_qn("a:prstGeom"))
    if geom is None:
        geom = spPr.find(_qn("a:custGeom"))
    geom.addnext(gf)


def _line(line_fmt, color: dict | None, width_px: float, dash: bool = False) -> None:
    from pptx.enum.dml import MSO_LINE_DASH_STYLE
    if not color or width_px <= 0:
        line_fmt.fill.background()
        return
    line_fmt.color.rgb = _rgb(color["hex"])
    line_fmt.width = E(width_px)
    _set_alpha(line_fmt._get_or_add_ln().find(_qn("a:solidFill")), color.get("a", 1))
    if dash:
        line_fmt.dash_style = MSO_LINE_DASH_STYLE.DASH


def _no_shadow(shape) -> Any:
    """Explicit, theme-free look: drop <p:style> (its effectRef/fillRef/fontRef would pull theme shadows and
    white text in some renderers) and write an empty <a:effectLst/>."""
    style = shape._element.find(_qn("p:style"))
    if style is not None:
        shape._element.remove(style)
    shape.shadow.inherit = False
    return shape._element.spPr.find(_qn("a:effectLst"))


def _shadow(shape, sh: dict | None) -> None:
    eff = _no_shadow(shape)
    if not sh or eff is None or sh["blur"] < 4 or sh["color"].get("a", 1) < 0.03:
        return                              # hairline / near-invisible CSS shadows are not worth a native effect
    dist = math.hypot(sh["dx"], sh["dy"])
    ang = (math.degrees(math.atan2(sh["dy"], sh["dx"])) % 360) if dist else 90
    el = eff.makeelement(_qn("a:outerShdw"), {"blurRad": str(E(sh["blur"])), "dist": str(E(dist)),
                                              "dir": str(int(ang * 60000)), "algn": "t", "rotWithShape": "0"})
    c = el.makeelement(_qn("a:srgbClr"), {"val": sh["color"]["hex"].upper()})
    c.append(c.makeelement(_qn("a:alpha"), {"val": str(int(sh["color"].get("a", 1) * 100000))}))
    el.append(c)
    eff.append(el)


def _font_run(run, r: dict, font: str) -> None:
    from pptx.util import Pt
    f = run.font
    f.size = Pt(round(r["size"] * 0.75 * 2) / 2)
    f.bold = bool(r.get("bold"))
    if r.get("italic"):
        f.italic = True
    f.name = font
    rPr = run._r.get_or_add_rPr()
    if re.search(r"[\u3000-\u9fff\uff00-\uffef]", run.text or ""):
        rPr.set("lang", "zh-CN")
        rPr.set("altLang", "en-US")
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(_qn(tag))
        if el is None:
            el = rPr.makeelement(_qn(tag), {})
            rPr.append(el)
        el.set("typeface", font)
    if r.get("spacing"):
        rPr.set("spc", str(int(round(r["spacing"] * 0.75 * 100))))
    if r.get("sup"):
        rPr.set("baseline", "30000" if r["sup"] > 0 else "-25000")
    if r.get("color"):
        f.color.rgb = _rgb(r["color"]["hex"])
        _set_alpha(rPr.find(_qn("a:solidFill")), r["color"].get("a", 1))


def _fill_text(tf, paras: list[list[dict]], *, align: str, line_px: float | None, font: str) -> None:
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Pt
    al = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}.get(align, PP_ALIGN.LEFT)
    first = True
    for runs in paras or [[]]:
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        para.alignment = al
        ppr = para._p.get_or_add_pPr()
        ppr.set("eaLnBrk", "1")
        ppr.set("hangingPunct", "1")
        if line_px:
            para.line_spacing = Pt(line_px * 0.75)
        body = max((r["size"] for r in runs if not r.get("sup")), default=0)
        for r in runs:
            run = para.add_run()
            run.text = r["text"]
            if r.get("sup"):      # renderers shrink super/subscript runs again (~60 %); give back the CSS size
                r = dict(r, size=min(r["size"] / 0.62, max(body, r["size"])))
            _font_run(run, r, font)


# ------------------------------------------------------------------ item writers

def _shape_kind(it: dict):
    from pptx.enum.shapes import MSO_SHAPE
    w, h, rad = it["w"], it["h"], it.get("radius") or 0
    radii = it.get("radii") or [rad] * 4
    if rad >= min(w, h) / 2 - 0.75 and abs(w - h) < 1.5 and min(radii) >= rad - 0.5:
        return MSO_SHAPE.OVAL, None
    if rad > 0.75 and max(radii) - min(radii) < 0.75:
        return MSO_SHAPE.ROUNDED_RECTANGLE, min(0.5, rad / max(1.0, min(w, h)))
    tl, tr, br, bl = radii
    if rad > 0.75 and abs(tl - tr) < 0.75 and max(br, bl) < 0.75 and tl > 0.75:
        return MSO_SHAPE.ROUND_2_SAME_RECTANGLE, min(0.5, tl / max(1.0, min(w, h)))          # top corners
    if rad > 0.75 and abs(br - bl) < 0.75 and max(tl, tr) < 0.75 and br > 0.75:
        return "ROUND_BOTTOM", min(0.5, br / max(1.0, min(w, h)))                             # bottom corners
    return MSO_SHAPE.RECTANGLE, None


def _write_box(shapes, it: dict, under: str | None = None) -> int:
    from pptx.enum.shapes import MSO_SHAPE
    kind, adj = _shape_kind(it)
    n = 0
    if it.get("fill") or it.get("grad") or it.get("line"):
        flip = kind == "ROUND_BOTTOM"
        if flip:
            kind = MSO_SHAPE.ROUND_2_SAME_RECTANGLE
        sp = shapes.add_shape(kind, E(it["x"]), E(it["y"]), E(it["w"]), E(it["h"]))
        if adj is not None:
            sp.adjustments[0] = adj
            if kind == MSO_SHAPE.ROUND_2_SAME_RECTANGLE:
                sp.adjustments[1] = 0.0
        if flip:                               # same geometry mirrored: rounded corners at the bottom
            sp._element.spPr.find(_qn("a:xfrm")).set("flipV", "1")
            if it.get("grad"):
                it = {**it, "grad": {**it["grad"], "angle": (180 - it["grad"].get("angle", 180)) % 360}}
        if it.get("grad"):
            _gradient(sp, it["grad"], under)
        else:
            _solid(sp.fill, it.get("fill"))
        ln = it.get("line")
        _line(sp.line, (ln or {}).get("color"), (ln or {}).get("w", 0), (ln or {}).get("dash") in ("dashed", "dotted"))
        _shadow(sp, it.get("shadow"))
        sp.name = f"box {it.get('cls', '')}"[:60]
        n += 1
    for e in it.get("edges") or []:          # non-uniform borders: each visible side is a thin native bar
        x, y, w, h = it["x"], it["y"], it["w"], it["h"]
        geo = {"top": (x, y, w, e["w"]), "bottom": (x, y + h - e["w"], w, e["w"]),
               "left": (x, y, e["w"], h), "right": (x + w - e["w"], y, e["w"], h)}[e["side"]]
        bar = shapes.add_shape(MSO_SHAPE.RECTANGLE, *(E(v) for v in geo))
        _solid(bar.fill, e["color"])
        bar.line.fill.background()
        _no_shadow(bar)
        bar.name = f"border-{e['side']}"
        n += 1
    return n


def _write_svg_rect(shapes, it: dict, oval: bool = False) -> int:
    from pptx.enum.shapes import MSO_SHAPE
    kind = MSO_SHAPE.OVAL if oval else (MSO_SHAPE.ROUNDED_RECTANGLE if (it.get("radius") or 0) > 0.75 else MSO_SHAPE.RECTANGLE)
    sp = shapes.add_shape(kind, E(it["x"]), E(it["y"]), E(max(it["w"], 0.5)), E(max(it["h"], 0.5)))
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        sp.adjustments[0] = min(0.5, it["radius"] / max(1.0, min(it["w"], it["h"])))
    _solid(sp.fill, it.get("fill"))
    st = it.get("stroke")
    _line(sp.line, st, (st or {}).get("w", 0), (st or {}).get("dash", False))
    _no_shadow(sp)
    sp.name = f"{'oval' if oval else 'rect'} {it.get('shape') or it.get('svgClass') or ''}".strip()[:60]
    return 1


def _write_line(shapes, it: dict, pts=None) -> int:
    from pptx.enum.shapes import MSO_CONNECTOR
    (x1, y1), (x2, y2) = pts or it["points"]
    c = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, E(x1), E(y1), E(x2), E(y2))
    style = c._element.find(_qn("p:style"))
    if style is not None:
        c._element.remove(style)
    st = it.get("stroke") or ({"hex": it["fill"]["hex"], "a": it["fill"].get("a", 1), "w": 1} if it.get("fill") else None)
    _line(c.line, st, (st or {}).get("w", 1), (st or {}).get("dash", False))
    c.name = f"line {it.get('shape') or it.get('svgClass') or ''}".strip()[:60]
    return 1


def _write_poly(shapes, it: dict) -> int:
    n = 0
    paths = it["paths"]
    simple = all(len(p["points"]) == 2 and not p["closed"] for p in paths)
    if simple and not it.get("fill"):
        for p in paths:
            n += _write_line(shapes, it, p["points"])
        return n
    first = paths[0]["points"][0]
    fb = shapes.build_freeform(E(first[0]), E(first[1]), scale=1.0)
    for k, p in enumerate(paths):
        if k:
            fb.move_to(E(p["points"][0][0]), E(p["points"][0][1]))
        fb.add_line_segments([(E(x), E(y)) for x, y in p["points"][1:]], close=bool(p["closed"]))
    sp = fb.convert_to_shape()
    closed = any(p["closed"] for p in paths)
    _solid(sp.fill, it.get("fill") if closed or it.get("fill") else None)
    st = it.get("stroke")
    _line(sp.line, st, (st or {}).get("w", 0), (st or {}).get("dash", False))
    _no_shadow(sp)
    sp.name = f"path {it.get('shape') or it.get('svgClass') or ''}".strip()[:60]
    return 1


def _write_text(shapes, it: dict, font: str) -> int:
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE
    if it.get("svg"):
        size = it["paras"][0][0]["size"]
        h = max(it["h"], size * 1.3)
        if it.get("rotation"):
            w = it["textLen"] + 6
            x, y = it["cx"] - w / 2, it["cy"] - h / 2
        else:
            w = it["w"] + 6
            x = {"left": it["x"] - 1, "center": it["cx"] - w / 2, "right": it["x"] + it["w"] + 1 - w}[it["align"]]
            y = it["cy"] - h / 2
        tb = shapes.add_textbox(E(x), E(y), E(w), E(h))
        if it.get("rotation"):
            tb.rotation = it["rotation"]
        tf = tb.text_frame
        tf.word_wrap = False
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        line_px = None
    else:
        x, w = it["x"], it["w"]
        if not it.get("nowrap"):
            extra = w * TEXT_SLACK + 2
            x = {"left": x, "center": x - extra / 2, "right": x - extra}.get(it["align"], x)
            w = w + extra
        tb = shapes.add_textbox(E(x), E(it["y"]), E(max(w, 1)), E(max(it["h"], it["lineHeight"])))
        tf = tb.text_frame
        tf.word_wrap = not it.get("nowrap")
        tf.vertical_anchor = MSO_ANCHOR.TOP
        line_px = it.get("lineHeight")
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.auto_size = MSO_AUTO_SIZE.NONE
    _fill_text(tf, it["paras"], align=it.get("align", "left"), line_px=line_px, font=font)
    tb.name = f"text {it.get('cls', '')}"[:60]
    return 1


def _cell_border(tcPr, side: str, b: dict | None) -> None:
    tag = {"left": "a:lnL", "right": "a:lnR", "top": "a:lnT", "bottom": "a:lnB"}[side]
    for old in tcPr.findall(_qn(tag)):
        tcPr.remove(old)
    w = b["w"] if b and b.get("color") else 0
    ln = tcPr.makeelement(_qn(tag), {"w": str(E(w))})
    if w > 0:
        sf = ln.makeelement(_qn("a:solidFill"), {})
        sf.append(sf.makeelement(_qn("a:srgbClr"), {"val": b["color"]["hex"].upper()}))
        ln.append(sf)
    else:
        ln.append(ln.makeelement(_qn("a:noFill"), {}))
    return ln


def _write_table(shapes, it: dict, font: str) -> int:
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    cols = it["cols"]
    widths = [cols[i + 1] - cols[i] for i in range(len(cols) - 1)]
    rows = it["rows"]
    gf = shapes.add_table(len(rows), len(widths), E(it["x"]), E(it["y"]), E(it["w"]), E(it["h"]))
    tbl = gf.table
    tblPr = tbl._tbl.tblPr
    for attr in ("bandRow", "firstRow"):
        tblPr.set(attr, "0")
    style = tblPr.find(_qn("a:tableStyleId"))
    if style is not None:
        style.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"     # No Style, Table Grid → cells painted explicitly
    for i, w in enumerate(widths):
        tbl.columns[i].width = E(w)
    for ri, row in enumerate(rows):
        tbl.rows[ri].height = E(row["h"])
        for cd in row["cells"]:
            c0, c1 = cd["c0"], max(cd["c1"], cd["c0"] + 1)
            cell = tbl.cell(ri, c0)
            if c1 - c0 > 1:
                cell.merge(tbl.cell(ri, c1 - 1))
            _solid(cell.fill, cd.get("fill"))
            pt, pr, pb, pl = cd["pad"]
            cell.margin_top, cell.margin_right, cell.margin_bottom, cell.margin_left = E(pt), E(pr), E(pb), E(pl)
            cell.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[cd["anchor"]]
            tf = cell.text_frame
            tf.word_wrap = True
            _fill_text(tf, cd["paras"] or [[]], align=cd["align"], line_px=cd.get("lineHeight"), font=font)
            tcPr = cell._tc.get_or_add_tcPr()
            lns = [_cell_border(tcPr, s, cd["borders"].get(s)) for s in ("left", "right", "top", "bottom")]
            for k, ln in enumerate(lns):        # DrawingML: line children come before the cell fill
                tcPr.insert(k, ln)
    gf.name = "table"
    return 1


# ------------------------------------------------------------------ deck

def _theme_fonts(prs, font: str) -> None:
    from lxml import etree
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    part = prs.slide_master.part.part_related_by(RT.THEME)
    root = etree.fromstring(part.blob)
    fonts = root.find(".//" + _qn("a:fontScheme"))
    for kind in ("a:majorFont", "a:minorFont"):
        f = fonts.find(_qn(kind))
        for script in ("a:latin", "a:ea"):
            f.find(_qn(script)).set("typeface", font)
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def build_pptx(models: list[dict], out: Path | str, *, title: str = "", font: str = DEFAULT_FONT,
               notes: list[str] | None = None) -> dict:
    """Write one native slide per extracted model.  Returns {slides: [{written counts}], path}."""
    from pptx import Presentation
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    prs.core_properties.title = title
    w = models[0]["width"] if models else 1280
    h = models[0]["height"] if models else 720
    prs.slide_width, prs.slide_height = E(w), E(h)
    _theme_fonts(prs, font)
    blank = prs.slide_layouts[6]
    report = []
    for i, m in enumerate(models):
        s = prs.slides.add_slide(blank)
        if m.get("background"):
            s.background.fill.solid()
            s.background.fill.fore_color.rgb = _rgb(m["background"]["hex"])
        counts: dict[str, int] = {}
        for it in m["items"]:
            t = it["type"]
            if t == "box":
                k = _write_box(s.shapes, it, (m.get("background") or {}).get("hex"))
            elif t == "text":
                k = _write_text(s.shapes, it, font)
            elif t == "table":
                k = _write_table(s.shapes, it, font)
            elif t == "rect":
                k = _write_svg_rect(s.shapes, it)
            elif t == "ellipse":
                k = _write_svg_rect(s.shapes, it, oval=True)
            elif t == "line":
                k = _write_line(s.shapes, it)
            elif t == "poly":
                k = _write_poly(s.shapes, it)
            else:
                k = 0
            counts[t] = counts.get(t, 0) + k
        if notes and i < len(notes) and notes[i]:
            s.notes_slide.notes_text_frame.text = notes[i]
        report.append({"slide": i + 1, "written": counts, "unsupported": m.get("unsupported") or []})
    prs.save(str(out))
    return {"path": str(out), "slides": report, "font": font, "version": VERSION}


# ------------------------------------------------------------------ verification (re-open with python-pptx)

def inspect_pptx(path: Path | str) -> dict:
    """Re-open a PPTX: per slide shape counts by kind, pictures, text frames with text, table cells."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs = Presentation(str(path))
    slides = []

    def walk(shapes):
        for sh in shapes:
            yield sh
            if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from walk(sh.shapes)

    for i, s in enumerate(prs.slides, 1):
        kinds: dict[str, int] = {}
        pics = text_frames = tables = cells = 0
        texts = []
        for sh in walk(s.shapes):
            st = sh.shape_type
            if st == MSO_SHAPE_TYPE.PICTURE or sh._element.tag.endswith("}pic"):
                pics += 1
                kinds["picture"] = kinds.get("picture", 0) + 1
                continue
            if getattr(sh, "has_table", False) and sh.has_table:
                tables += 1
                kinds["table"] = kinds.get("table", 0) + 1
                for row in sh.table.rows:
                    for c in row.cells:
                        if c.text_frame.text.strip():
                            cells += 1
                            texts.append(c.text_frame.text)
                continue
            tag = sh._element.tag.split("}")[-1]
            if tag == "cxnSp":
                k = "connector"
            elif st == MSO_SHAPE_TYPE.FREEFORM:
                k = "freeform"
            elif st == MSO_SHAPE_TYPE.TEXT_BOX:
                k = "textbox"
            elif st == MSO_SHAPE_TYPE.AUTO_SHAPE:
                k = "autoshape"
            else:
                k = str(st)
            kinds[k] = kinds.get(k, 0) + 1
            if getattr(sh, "has_text_frame", False) and sh.has_text_frame and sh.text_frame.text.strip():
                text_frames += 1
                texts.append(sh.text_frame.text)
        blob = s.part.blob.decode("utf-8", "ignore")
        slides.append({"slide": i, "shapes": sum(kinds.values()), "kinds": kinds, "pictures": pics,
                       "text_frames": text_frames, "tables": tables, "table_cells_with_text": cells,
                       "svg_embedded": "svgBlip" in blob, "texts": texts})
    return {"slide_width_emu": prs.slide_width, "slide_height_emu": prs.slide_height,
            "aspect": round(prs.slide_width / prs.slide_height, 4), "slides": slides}
