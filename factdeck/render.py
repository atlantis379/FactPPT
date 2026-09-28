"""Render a checked deck to HTML → PNG/PDF and a native, editable PPTX, then verify.

Pipeline: verified facts + deck spec → HTML (Jinja) → Chromium
  → per page: fit density (shrink body type in small steps until nothing overflows)
  → per-slide PNG, a PDF, DOM checks, and an export model
  → python-pptx builds native text boxes, tables, shapes and connectors
  → the PPTX is read back and every fact on every slide must be found in it.

Nothing here knows about a particular subject: layouts are generic, diagram
geometry is computed from a node grid, and colours come from a named theme.
"""
from __future__ import annotations

import json
import math
import random
import re
from collections import OrderedDict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .deck import check as deck_check
from .lexicon import lint_text, canon

HERE = Path(__file__).parent
PX = 9525                       # EMU per CSS px at 96 dpi
PPT_FONT = "Microsoft YaHei"
DENSITY = (1, .92, .85, .78, .72)

THEMES = {
    "navy-teal": {"ink": "#0E1B2C", "primary": "#0B2447", "primary2": "#19376D", "accent": "#0F8B8D", "accent2": "#12A5A7",
                  "accent-on-dark": "#7FD6D0", "soft": "#E4F3F2", "sky": "#F1F5F9", "line": "#D8E0E8", "muted": "#5A6B7E"},
    "clinical-blue": {"ink": "#10202F", "primary": "#0A3D62", "primary2": "#1E5AA8", "accent": "#1F74C9", "accent2": "#54A0FF",
                      "accent-on-dark": "#9CC8FF", "soft": "#E8F1FC", "sky": "#F2F6FB", "line": "#D6E0EC", "muted": "#566779"},
    "graphite-amber": {"ink": "#1D2126", "primary": "#22272E", "primary2": "#3A424D", "accent": "#A8690A", "accent2": "#E0A526",
                       "accent-on-dark": "#F2C66B", "soft": "#FBF3E4", "sky": "#F5F5F4", "line": "#E1DED8", "muted": "#61666D"},
    "forest": {"ink": "#14231C", "primary": "#1B3A2F", "primary2": "#2D5A47", "accent": "#2F7D4F", "accent2": "#56B37A",
               "accent-on-dark": "#9FDAB5", "soft": "#E7F4EC", "sky": "#F3F7F4", "line": "#D7E3DB", "muted": "#58695F"},
    "plum": {"ink": "#221526", "primary": "#3B1F4A", "primary2": "#5B3470", "accent": "#A13D73", "accent2": "#D0679E",
             "accent-on-dark": "#EDB1D1", "soft": "#F7E9F1", "sky": "#F7F4F8", "line": "#E3D9E6", "muted": "#675A6C"},
}


# ---------------------------------------------------------------- page models
def short_title(title: str) -> str:
    t = re.sub(r"\.(pptx|pdf|docx|xlsx|txt|md|png|jpe?g|webp)$", "", title, flags=re.I)
    t = re.sub(r"^\d+[.、]\s*", "", t).strip(" -_")
    return t if len(t) <= 22 else t[:21] + "…"


def sources_line(fids, facts, sources):
    by_src: "OrderedDict[str, list[str]]" = OrderedDict()
    for fid in fids:
        f = facts[fid]
        m = re.match(r"(第\d+页|第\d+部分|工作表「[^」]+」|整幅图片|页眉页脚)", f["location"])
        loc = m.group(1) if m else f["location"].split(" ")[0]
        by_src.setdefault(f["source_id"], [])
        if loc not in by_src[f["source_id"]]:
            by_src[f["source_id"]].append(loc)
    parts = []
    for sid, locs in by_src.items():
        pages = sorted({int(re.search(r"\d+", l).group()) for l in locs if re.fullmatch(r"第\d+页", l)})
        other = [l for l in locs if not re.fullmatch(r"第\d+页", l)]
        loc = "、".join((["第" + "、".join(map(str, pages)) + "页"] if pages else []) + other)
        src = sources.get(sid, {})
        parts.append(f"{short_title(src.get('title') or src.get('filename') or sid)} {loc}".strip())
    return "；".join(parts)


def cover_art(seed: int):
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
    return {"branches": branches, "dots": dots}


def flow_geometry(page: dict, width: float, height: float) -> dict:
    """Place nodes on a col/row grid and route orthogonal arrows between them."""
    nodes = page["nodes"]
    ncol = max(n["col"] for n in nodes) + 1
    nrow = max(n["row"] for n in nodes) + 1
    tagged = any(n.get("tag") for n in nodes)
    gap_x, gap_y = 56, (40 if tagged else 34)
    w = min(220, (width - gap_x * (ncol - 1)) / ncol)
    h = min(84, max(46, (height - gap_y * (nrow - 1) - (30 if tagged else 0)) / nrow))
    total_w = ncol * w + (ncol - 1) * gap_x
    total_h = nrow * h + (nrow - 1) * gap_y
    ox, oy = (width - total_w) / 2, max(0, (height - total_h) / 2)
    geo = {}
    placed = []
    for n in nodes:
        x, y = ox + n["col"] * (w + gap_x), oy + n["row"] * (h + gap_y)
        geo[n["id"]] = (x, y)
        placed.append({"x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1), "ref": n["ref"],
                       "cls": {"core": "core", "soft": "soft"}.get(n.get("emphasis", ""), ""),
                       "tag": n.get("tag"), "tag_y": round(y + h + 4, 1)})
    edges = []
    for a, b, support in page["edges"]:
        (ax, ay), (bx, by) = geo[a], geo[b]
        if abs(ay - by) < 1:                                   # same row: side to side
            pts = [(ax + w, ay + h / 2), (bx - 2, by + h / 2)] if bx > ax else [(ax, ay + h / 2), (bx + w + 2, by + h / 2)]
        elif abs(ax - bx) < 1:                                 # same column: top/bottom
            pts = [(ax + w / 2, ay + h), (bx + w / 2, by - 2)] if by > ay else [(ax + w / 2, ay), (bx + w / 2, by + h + 2)]
        else:                                                  # elbow through the gap between columns
            if bx > ax:
                x1, x2 = ax + w, bx - 2
            else:
                x1, x2 = ax, bx + w + 2
            xm = x1 + (x2 - x1) / 2
            pts = [(x1, ay + h / 2), (xm, ay + h / 2), (xm, by + h / 2), (x2, by + h / 2)]
        edges.append({"support": support, "points": " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)})
    return {"w": round(width, 1), "h": round(height, 1), "gap_x": gap_x, "nodes": placed, "edges": edges}


def build_models(deck, facts, sources, check):
    conflicted = {fid for fid, f in facts.items() if any("来源之间不一致" in p for p in f["problems"])}
    fview = {}
    for fid, f in facts.items():
        text = f["display"] or f["quote"]
        fview[fid] = {"id": fid, "text": text, "pending": f["needs_confirmation"], "conflict": fid in conflicted}
    pages, divider_no = [], 0
    for i, (page, res) in enumerate(zip(deck["pages"], check["pages"])):
        p = dict(page)
        p["pending_count"] = len(res["pending"])
        p["sources_line"] = sources_line(res["facts"], facts, sources)
        if page["layout"] in ("cover", "divider"):
            p["art"] = cover_art(7 + i)
        if page["layout"] == "cover":
            p["chrome_meta"] = f"原始资料 {len(sources)} 份 · 页面中每一条内容均可追溯到原文位置"
        if page["layout"] == "divider":
            divider_no += 1
            p["divider_no"] = divider_no
        if page["layout"] == "table":
            ws = page.get("widths") or [1] * len(page["columns"])
            p["col_widths"] = [round(100 * x / sum(ws), 2) for x in ws]
        if page["layout"] == "cards":
            p["cards"] = [{**c, "numeric": "fact" in c["value"] and bool(re.search(r"\d", fview[c["value"]["fact"]]["text"]))
                           and len(fview[c["value"]["fact"]]["text"]) <= 14} for c in page["cards"]]
        if page["layout"] == "flow":
            body_h = 720 - (150 if not page.get("lead") else 196) - 72
            p["geo"] = flow_geometry(page, 1152 - (324 if page.get("side") else 0), body_h)
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


def build_pptx(models: list[dict], raster_png: dict, notes: list[str], out: Path, title: str = ""):
    from pptx import Presentation
    from pptx.util import Emu
    from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
    from pptx.enum.text import MSO_ANCHOR
    from pptx.oxml.ns import qn

    prs = Presentation()
    prs.core_properties.title = title
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
                    lnx.append(lnx.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
        for t in m["tables"]:
            nrows, ncols = len(t["rows"]), len(t["rows"][0]["cells"])
            gf = s.shapes.add_table(nrows, ncols, E(t["x"]), E(t["y"]), E(t["w"]), E(t["h"]))
            tbl = gf.table
            tblPr = tbl._tbl.tblPr
            for attr in ("bandRow", "firstRow"):
                tblPr.set(attr, "0")
            style = tblPr.find(qn("a:tableStyleId"))
            if style is not None:
                style.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"   # "No Style, Table Grid" → cells painted explicitly
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
                    tcPr = cell._tc.get_or_add_tcPr()
                    for side in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
                        ln = tcPr.makeelement(qn(side), {"w": "9525" if side == "a:lnB" and cd["border"] else "0"})
                        if side == "a:lnB" and cd["border"]:
                            sf = ln.makeelement(qn("a:solidFill"), {})
                            sf.append(sf.makeelement(qn("a:srgbClr"), {"val": cd["border"]["hex"].upper()}))
                            ln.append(sf)
                        else:
                            ln.append(ln.makeelement(qn("a:noFill"), {}))
                        tcPr.append(ln)
        for t in m["texts"]:
            if not t["paras"]:
                continue
            w = t["w"] * 1.03 + 2        # PowerPoint CJK metrics differ slightly from the browser's
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
        blob = canon("\n".join(texts))
        missing = [fid for fid in fids if canon(fview[fid]["text"]) not in blob]
        notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
        results.append({"facts": len(fids), "missing": missing, "notes_chars": len(notes)})
    return results


FIT_JS = """(id) => {
  const s = document.getElementById(id); const S = s.getBoundingClientRect();
  const foot = s.querySelector('.foot'); const limit = foot ? foot.getBoundingClientRect().top : S.bottom;
  let bad = 0;
  s.querySelectorAll('[data-t], td, th').forEach((el) => {
    if (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1) bad++;
  });
  s.querySelectorAll('.body [data-t], .body table, .body [data-shape]').forEach((el) => {
    const r = el.getBoundingClientRect(); if (r.height > 0 && r.bottom > limit + 0.5) bad++;
  });
  return bad;
}"""


# ---------------------------------------------------------------- main
def render(deck: dict, facts: dict[str, dict], sources: dict[str, dict], out: Path,
           theme: str = "navy-teal", terms: list[str] | tuple[str, ...] = (), pages_only: list[str] | None = None) -> dict:
    """Render `deck` into `out`. `facts` are verified facts by id; `sources` by id ({title|filename})."""
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    chk = deck_check(deck, facts, terms)
    if chk["errors"]:
        raise ValueError(f"页面规格检查未通过：{chk['errors']} 处错误")
    pages, fview = build_models(deck, facts, sources, chk)
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True)
    html = env.get_template("deck.html.j2").render(deck=deck, pages=pages, facts=fview, theme=THEMES.get(theme, THEMES["navy-teal"]))
    html_path = out / "deck.html"
    html_path.write_text(html, encoding="utf-8")

    js = (HERE / "extract.js").read_text(encoding="utf-8")
    expected = {k: v["text"] for k, v in fview.items()}
    glossary = [x["text"] for x in deck.get("glossary", deck.get("terms", []))]
    models, raster_png, report, density = [], {}, {"slides": []}, {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        page.goto(html_path.resolve().as_uri())
        page.evaluate("document.fonts.ready")
        for i, p in enumerate(pages, 1):
            for k in DENSITY:                          # tighten the page until nothing overflows
                page.evaluate("([id, k]) => document.getElementById(id).style.setProperty('--k', k)", [p["id"], k])
                if page.evaluate(FIT_JS, p["id"]) == 0:
                    break
            density[p["id"]] = k
            el = page.locator(f"#{p['id']}")
            el.screenshot(path=str(out / f"slide{i:02d}.png"))
            m = page.evaluate(js, {"slideId": p["id"], "expected": expected})
            for r in m["rasters"]:
                png = out / f"raster_{r['id']}.png"
                page.locator(f"#{p['id']} [data-raster='{r['id']}']").screenshot(path=str(png), omit_background=True)
                raster_png[r["id"]] = png
            lint = [f"“{t}”：{'；'.join(lint_text(t, glossary, terms))}" for t in m.pop("authored") if lint_text(t, glossary, terms)]
            m["checks"]["authored_lint"] = lint
            report["slides"].append({"id": p["id"], "density": k, **m["checks"]})
            models.append(m)
        html_path.write_text(page.content(), encoding="utf-8")      # keep the fitted densities
        page.emulate_media(media="print")
        page.pdf(path=str(out / "deck.pdf"), width="1280px", height="720px", print_background=True)
        browser.close()

    notes = []
    for p, res in zip(pages, chk["pages"]):
        lines = ["【来源追溯】本页每条内容对应的原文位置："]
        for fid in res["facts"]:
            f = facts[fid]
            flag = "（待人工确认）" if f["needs_confirmation"] else ""
            src = sources.get(f["source_id"], {})
            lines.append(f"· {fview[fid]['text']} ← {src.get('filename') or src.get('title', '')} {f['location']}{flag}")
        notes.append("\n".join(lines) if res["facts"] else "")
    pptx_path = out / "deck.pptx"
    build_pptx(models, raster_png, notes, pptx_path, deck.get("title", ""))
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
    s = report["summary"]
    report["hard_errors"] = s["untracked_text"] + s["fact_text_mismatch"] + s["overflow"] + s["out_of_bounds"] + s["overlap"] + s["authored_lint"] + s["pptx_missing_facts"]
    report["theme"] = theme
    (out / "render_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def run(project: Path, out: Path):
    """CLI: a project folder with deck.json, facts_verified.json and sources.json."""
    deck = json.loads((project / "deck.json").read_text(encoding="utf-8"))
    fv = json.loads((project / "facts_verified.json").read_text(encoding="utf-8"))
    src = json.loads((project / "sources.json").read_text(encoding="utf-8"))
    return render(deck, {f["id"]: f for f in fv["facts"]}, {s["id"]: s for s in src["sources"]}, out,
                  deck.get("theme", "navy-teal"), fv.get("terms", []))


if __name__ == "__main__":
    import sys
    rep = run(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(rep["summary"], ensure_ascii=False, indent=1))
