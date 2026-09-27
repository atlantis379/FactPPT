"""Render a checked deck to HTML → PNG/PDF and a native, editable PPTX, then verify.

Pipeline: facts_verified.json + deck.json → HTML (Jinja) → Chromium
  → per-slide PNG, a PDF, DOM checks, and an export model
  → python-pptx builds native text boxes, tables, shapes and connectors
  → the PPTX is read back and every fact on every slide must be found in it.
"""
from __future__ import annotations

import json
import math
import random
import re
from collections import OrderedDict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .deck import check as deck_check, lint_text
from .facts import critical_tokens
from .sources import normalize

HERE = Path(__file__).parent
PX = 9525                       # EMU per CSS px at 96 dpi
PPT_FONT = "Microsoft YaHei"    # font used in the PPTX (Windows); the HTML renders with Noto Sans CJK


# ---------------------------------------------------------------- page models
def short_title(title: str) -> str:
    t = re.sub(r"^\d+\.", "", title)
    t = re.sub(r"[-_ ]*(已修复|V\d.*|\d{6,8}|20\d{2}\d{4})$", "", t).strip(" -")
    t = re.sub(r"\(CN-\d+）?_?.*$", "", t)
    return t if len(t) <= 22 else t[:21] + "…"


def sources_line(fids, facts, sources):
    by_src: "OrderedDict[str, list[str]]" = OrderedDict()
    for fid in fids:
        f = facts[fid]
        m = re.match(r"(第\d+页)", f["location"])
        loc = m.group(1) if m else ("图片表格" if f["location"].startswith("表格") else f["location"])
        by_src.setdefault(f["source_id"], [])
        if loc not in by_src[f["source_id"]]:
            by_src[f["source_id"]].append(loc)
    parts = []
    for sid, locs in by_src.items():
        pages = [l for l in locs if l.startswith("第")]
        other = [l for l in locs if not l.startswith("第")]
        nums = sorted({int(re.search(r"\d+", p).group()) for p in pages})
        loc = ("第" + "、".join(map(str, nums)) + "页") if nums else "、".join(other)
        parts.append(f"{short_title(sources[sid]['title'])} {loc}".strip())
    return "；".join(parts)


def cover_art(seed=7):
    rnd = random.Random(seed)
    branches, dots = [], []

    def grow(x, y, ang, length, width, depth):
        if depth == 0 or length < 8:
            dots.append({"x": round(x, 1), "y": round(y, 1), "r": round(rnd.uniform(2.5, 5.5), 1), "o": round(rnd.uniform(.35, .9), 2)})
            return
        x2, y2 = x + length * math.cos(ang), y - length * math.sin(ang)
        cx, cy = (x + x2) / 2 + rnd.uniform(-8, 8), (y + y2) / 2 + rnd.uniform(-8, 8)
        branches.append({"d": f"M{x:.1f},{y:.1f} Q{cx:.1f},{cy:.1f} {x2:.1f},{y2:.1f}", "w": round(width, 1), "o": round(min(1, .35 + depth * .1), 2)})
        spread = rnd.uniform(.32, .52)
        grow(x2, y2, ang + spread, length * rnd.uniform(.68, .8), width * .72, depth - 1)
        grow(x2, y2, ang - spread, length * rnd.uniform(.68, .8), width * .72, depth - 1)

    grow(330, 760, math.pi / 2, 170, 26, 8)
    return branches, dots


MECH_GEO = {
    "nodes": {
        "trigger": {"x": 0, "y": 30, "w": 120, "cls": "soft"},
        "epi": {"x": 0, "y": 124, "w": 120, "cls": ""},
        "alarmin": {"x": 0, "y": 218, "w": 120, "cls": ""},
        "tslp": {"x": 0, "y": 264, "w": 120, "cls": "core"},
        "th2": {"x": 190, "y": 60, "w": 110, "cls": "core"},
        "il4": {"x": 350, "y": 60, "w": 120, "cls": ""},
        "bige": {"x": 520, "y": 60, "w": 128, "cls": ""},
        "mast": {"x": 690, "y": 20, "w": 100, "cls": "soft"},
        "baso": {"x": 690, "y": 100, "w": 100, "cls": "soft"},
        "ilc2": {"x": 190, "y": 262, "w": 110, "cls": "core"},
        "il5": {"x": 350, "y": 262, "w": 120, "cls": ""},
        "eos": {"x": 520, "y": 262, "w": 128, "cls": ""},
    },
    "drugs": {"tslp": {"x": 0, "y": 330}, "il4": {"x": 326, "y": 118}, "bige": {"x": 526, "y": 160},
              "il5": {"x": 300, "y": 320}, "eos": {"x": 512, "y": 360}},
    "lane_a": {"x": 190, "y": 30}, "lane_b": {"x": 190, "y": 232},
}
NODE_H = 46


def edge_points(a, b, geo):
    A, B = geo["nodes"][a], geo["nodes"][b]
    if abs(A["x"] - B["x"]) < 5:                            # vertical
        x = A["x"] + A["w"] / 2
        return [(x, A["y"] + NODE_H), (x, B["y"] - 2)]
    x1, y1 = A["x"] + A["w"], A["y"] + NODE_H / 2
    if a == "alarmin":                                      # leave from the alarmin/TSLP pair
        y1 = A["y"] + NODE_H
    x2, y2 = B["x"] - 2, B["y"] + NODE_H / 2
    if abs(y1 - y2) < 2:
        return [(x1, y1), (x2, y2)]
    xm = x1 + (x2 - x1) / 2
    return [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]


def build_models(deck, facts, sources, check):
    conflicted = {fid for f in facts.values() for fid in [f["id"]] if any("来源之间不一致" in p for p in f["problems"])}
    fview = {}
    for fid, f in facts.items():
        text = f["display"] or f["quote"]
        fview[fid] = {"id": fid, "text": text, "pending": f["needs_confirmation"], "conflict": fid in conflicted,
                      "numeric": bool(re.search(r"\d", text))}
    pages = []
    for page, res in zip(deck["pages"], check["pages"]):
        p = dict(page)
        p["pending_count"] = len(res["pending"])
        p["sources_line"] = sources_line(res["facts"], facts, sources)
        if page["layout"] == "cover":
            p["chrome_meta"] = f"原始资料 {len(sources)} 份 · 页面中每一条医学内容均可追溯到原文位置"
        if page["layout"] == "mechanism":
            p["geo"] = MECH_GEO
            edges = list(page["edges"]) + [["bige", "baso", "mech.path.allergic"]]
            p["edge_paths"] = [{"support": s, "points": " ".join(f"{x:.1f},{y:.1f}" for x, y in edge_points(a, b, MECH_GEO))}
                               for a, b, s in edges]
        pages.append(p)
    return pages, fview


# ---------------------------------------------------------------- PPTX writer
def _rgb(c):
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(c["hex"].upper())


def _alpha(shape_fill_elm, a):
    if a >= 0.999:
        return
    from lxml import etree
    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    srgb = shape_fill_elm.find(f".//{{{ns}}}srgbClr")
    if srgb is not None:
        el = etree.SubElement(srgb, f"{{{ns}}}alpha")
        el.set("val", str(int(a * 100000)))


def _set_font(run, size_px, bold, color):
    from pptx.util import Pt
    from pptx.oxml.ns import qn
    f = run.font
    f.size = Pt(round(size_px * 0.75 * 2) / 2)
    f.bold = bold
    f.name = PPT_FONT
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", PPT_FONT)
    if color:
        f.color.rgb = _rgb(color)


def _fill_paras(tf, paras, line_height_px, align="left"):
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN
    al = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
    first = True
    for runs in paras:
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        para.alignment = al
        if line_height_px:
            para.line_spacing = Pt(line_height_px * 0.75)
        for r in runs:
            run = para.add_run()
            run.text = r["text"]
            _set_font(run, r["size"] * (0.62 if r.get("mark") and r["size"] > 14 else 1), r["bold"], r["color"])


def build_pptx(models: list[dict], raster_png: dict, notes: list[str], out: Path):
    from pptx import Presentation
    from pptx.util import Emu
    from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
    from pptx.enum.text import MSO_ANCHOR
    from pptx.oxml.ns import qn

    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(1280 * PX), Emu(720 * PX)
    blank = prs.slide_layouts[6]
    E = lambda v: Emu(int(round(v * PX)))
    for m, note in zip(models, notes):
        s = prs.slides.add_slide(blank)
        if m.get("background"):
            bg = s.background.fill
            bg.solid()
            bg.fore_color.rgb = _rgb(m["background"])
        for r in m["rasters"]:
            s.shapes.add_picture(str(raster_png[r["id"]]), E(r["x"]), E(r["y"]), E(r["w"]), E(r["h"]))
        for sh in m["shapes"]:
            kind = MSO_SHAPE.ROUNDED_RECTANGLE if sh["radius"] > 0.5 else MSO_SHAPE.RECTANGLE
            shape = s.shapes.add_shape(kind, E(sh["x"]), E(sh["y"]), E(sh["w"]), E(sh["h"]))
            if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
                shape.adjustments[0] = min(0.5, sh["radius"] / max(1, min(sh["w"], sh["h"])))
            if sh["fill"]:
                shape.fill.solid()
                shape.fill.fore_color.rgb = _rgb(sh["fill"])
                _alpha(shape.fill._xPr, sh["fill"]["a"])
            else:
                shape.fill.background()
            if sh["line"] and sh["line"]["color"]:
                shape.line.color.rgb = _rgb(sh["line"]["color"])
                shape.line.width = E(sh["line"]["w"])
            else:
                shape.line.fill.background()
            shape.shadow.inherit = False
            shape.text_frame.text = ""
            for a in sh["accents"]:
                acc = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, E(a["x"]), E(a["y"]), E(a["w"]), E(a["h"]))
                acc.fill.solid()
                acc.fill.fore_color.rgb = _rgb(a["color"])
                acc.line.fill.background()
                acc.shadow.inherit = False
        for ln in m["lines"]:
            pts = ln["points"]
            for i in range(len(pts) - 1):
                (x1, y1), (x2, y2) = pts[i], pts[i + 1]
                c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, E(x1), E(y1), E(x2), E(y2))
                c.line.color.rgb = _rgb({"hex": ln["color"]})
                c.line.width = E(ln["w"])
                if ln["arrow"] and i == len(pts) - 2:
                    lnx = c.line._get_or_add_ln()
                    tail = lnx.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
                    lnx.append(tail)
        for t in m["tables"]:
            nrows, ncols = len(t["rows"]), len(t["rows"][0]["cells"])
            gf = s.shapes.add_table(nrows, ncols, E(t["x"]), E(t["y"]), E(t["w"]), E(t["h"]))
            tbl = gf.table
            tblPr = tbl._tbl.tblPr
            for attr in ("bandRow", "firstRow"):
                tblPr.set(attr, "0")
            style = tblPr.find(qn("a:tableStyleId"))
            if style is not None:
                style.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"   # "No Style, Table Grid" → we paint cells ourselves
            for ci, cell in enumerate(t["rows"][0]["cells"]):
                tbl.columns[ci].width = E(cell["w"])
            for ri, row in enumerate(t["rows"]):
                tbl.rows[ri].height = E(row["h"])
                for ci, cd in enumerate(row["cells"]):
                    cell = tbl.cell(ri, ci)
                    if cd["fill"]:
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = _rgb(cd["fill"])
                    else:
                        cell.fill.background()
                    pt, pr, pb, pl = cd["pad"]
                    cell.margin_top, cell.margin_right, cell.margin_bottom, cell.margin_left = E(pt), E(pr), E(pb), E(pl)
                    cell.vertical_anchor = MSO_ANCHOR.TOP if ri else MSO_ANCHOR.MIDDLE
                    tf = cell.text_frame
                    tf.word_wrap = True
                    _fill_paras(tf, cd["paras"] or [[{"text": "", "size": 14, "bold": False, "color": None}]], cd["lineHeight"])
                    # borders: thin bottom rule only
                    tcPr = cell._tc.get_or_add_tcPr()
                    for side in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
                        ln = tcPr.makeelement(qn(side), {"w": "9525" if side == "a:lnB" and cd["border"] else "0"})
                        if side == "a:lnB" and cd["border"]:
                            sf = ln.makeelement(qn("a:solidFill"), {})
                            clr = sf.makeelement(qn("a:srgbClr"), {"val": cd["border"]["hex"].upper()})
                            sf.append(clr)
                            ln.append(sf)
                        else:
                            ln.append(ln.makeelement(qn("a:noFill"), {}))
                        tcPr.append(ln)
        for t in m["texts"]:
            if not t["paras"]:
                continue
            w = t["w"] * 1.03 + 2        # small allowance: PowerPoint CJK metrics differ from the browser's
            tb = s.shapes.add_textbox(E(t["x"]), E(t["y"]), E(w), E(max(t["h"], t["lineHeight"])))
            tf = tb.text_frame
            tf.word_wrap = not t["nowrap"]
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE if t["anchor"] == "middle" else MSO_ANCHOR.TOP
            tf.auto_size = None
            _fill_paras(tf, t["paras"], t["lineHeight"], t["align"])
        s.notes_slide.notes_text_frame.text = note
    prs.save(str(out))


# ---------------------------------------------------------------- readback
def readback(pptx_path: Path, pages_facts: list[list[str]], fview: dict) -> list[dict]:
    from pptx import Presentation
    prs = Presentation(str(pptx_path))
    results = []
    for slide, fids in zip(prs.slides, pages_facts):
        texts = []
        for sh in slide.shapes:
            if sh.has_text_frame:
                texts.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                texts += [c.text for row in sh.table.rows for c in row.cells]
        blob = normalize("\n".join(texts))
        missing = [fid for fid in fids if normalize(fview[fid]["text"]) not in blob]
        notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
        results.append({"facts": len(fids), "missing": missing, "notes_chars": len(notes)})
    return results


# ---------------------------------------------------------------- main
def run(project: Path, out: Path):
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    deck = json.loads((project / "deck.json").read_text(encoding="utf-8"))
    fv = json.loads((project / "facts_verified.json").read_text(encoding="utf-8"))
    facts = {f["id"]: f for f in fv["facts"]}
    src = json.loads((project / "sources.json").read_text(encoding="utf-8"))
    sources = {s["id"]: s for s in src["sources"]}
    chk = deck_check(deck, facts)
    if chk["errors"]:
        raise SystemExit(f"页面规格检查未通过：{chk['errors']} 处错误，见 deck_check.json")

    pages, fview = build_models(deck, facts, sources, chk)
    branches, dots = cover_art()
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True)
    html = env.get_template("deck.html.j2").render(deck=deck, pages=pages, facts=fview,
                                                    cover_branches=branches, cover_dots=dots)
    html_path = out / "deck.html"
    html_path.write_text(html, encoding="utf-8")

    js = (HERE / "extract.js").read_text(encoding="utf-8")
    expected = {k: v["text"] for k, v in fview.items()}
    models, raster_png, report = [], {}, {"slides": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        page.goto(html_path.resolve().as_uri())
        page.evaluate("document.fonts.ready")
        for i, p in enumerate(pages, 1):
            el = page.locator(f"#{p['id']}")
            el.screenshot(path=str(out / f"slide{i:02d}.png"))
            m = page.evaluate(js, {"slideId": p["id"], "expected": expected})
            for r in m["rasters"]:
                png = out / f"raster_{r['id']}.png"
                page.locator(f"#{p['id']} [data-raster='{r['id']}']").screenshot(path=str(png), omit_background=True)
                raster_png[r["id"]] = png
            lint = [f"“{t}”：{'；'.join(lint_text(t, [x['text'] for x in deck.get('terms', [])]))}"
                    for t in m.pop("authored") if lint_text(t, [x["text"] for x in deck.get("terms", [])])]
            m["checks"]["authored_lint"] = lint
            report["slides"].append({"id": p["id"], **m["checks"]})
            models.append(m)
        pdf_page = browser.new_page()
        pdf_page.goto(html_path.resolve().as_uri())
        pdf_page.evaluate("document.fonts.ready")
        pdf_page.pdf(path=str(out / "deck.pdf"), width="1280px", height="720px", print_background=True)
        browser.close()

    notes = []
    for p, res in zip(pages, chk["pages"]):
        lines = ["【来源追溯】本页每条内容对应的原文位置："]
        for fid in res["facts"]:
            f = facts[fid]
            flag = "（待人工确认）" if f["needs_confirmation"] else ""
            lines.append(f"· {fview[fid]['text']} ← {sources[f['source_id']]['title']} {f['location']}{flag}")
        notes.append("\n".join(lines) if res["facts"] else "")
    pptx_path = out / "deck.pptx"
    build_pptx(models, raster_png, notes, pptx_path)
    rb = readback(pptx_path, [r["facts"] for r in chk["pages"]], fview)
    for s, r in zip(report["slides"], rb):
        s["pptx_readback"] = r
    report["summary"] = {
        "slides": len(pages),
        "facts_on_slides": sum(len(r["facts"]) for r in chk["pages"]),
        "pending_confirmation": sum(len(r["pending"]) for r in chk["pages"]),
        "untracked_text": sum(len(s["untracked"]) for s in report["slides"]),
        "fact_text_mismatch": sum(len(s["mismatch"]) for s in report["slides"]),
        "overflow": sum(len(s["overflow"]) for s in report["slides"]),
        "out_of_bounds": sum(len(s["bounds"]) for s in report["slides"]),
        "overlap": sum(len(s["overlap"]) for s in report["slides"]),
        "authored_lint": sum(len(s["authored_lint"]) for s in report["slides"]),
        "pptx_missing_facts": sum(len(r["missing"]) for r in rb),
    }
    (out / "render_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys
    rep = run(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(rep["summary"], ensure_ascii=False, indent=1))
    for s in rep["slides"]:
        issues = {k: v for k, v in s.items() if k not in ("id", "pptx_readback") and v}
        if issues or s["pptx_readback"]["missing"]:
            print(s["id"], json.dumps(issues, ensure_ascii=False)[:600], s["pptx_readback"]["missing"])
