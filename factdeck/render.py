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
import shutil
from collections import OrderedDict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .deck import check as deck_check, emph_spans
from . import charts
from . import compose
from . import free
from . import recipes
from .lexicon import lint_text, canon

HERE = Path(__file__).parent
PX = 9525                       # EMU per CSS px at 96 dpi
PPT_FONT = "Microsoft YaHei"
# Body type is fixed by the design and only ever tightens to fit; a sparse page keeps its whitespace
# rather than growing its text towards the title's size (that flattens the hierarchy).
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


NODE_FONT = 15                # px, .node in the template
GRID_SHORT = 24               # characters per tile (heading + items) below which a grid reads across in one row
FLOW_TOP = 24                 # a diagram starts just below the header, like every other body


def flow_geometry(page: dict, width: float, height: float, facts: dict | None = None) -> dict:
    """Place nodes on a col/row grid and route orthogonal arrows between them."""
    nodes = page["nodes"]
    ncol = max(n["col"] for n in nodes) + 1
    nrow = max(n["row"] for n in nodes) + 1
    tagged = any(n.get("tag") for n in nodes)
    labelled = any(len(e) == 4 for e in page["edges"])
    gap_x, gap_y = (76 if labelled else 56), (40 if tagged else 34)
    w = min(220, (width - gap_x * (ncol - 1)) / ncol)
    room = (height - gap_y * (nrow - 1) - (30 if tagged else 0)) / nrow
    # boxes as tall as their text needs (the demo's compact nodes), never taller than the room per row
    text = lambda ref: (ref.get("text") if "text" in ref else ((facts or {}).get(ref.get("fact")) or {}).get("text", "")) or ""
    wide = lambda s: sum(1 if ord(ch) > 0x2E80 else 0.58 for ch in s.replace("\n", "").replace("\v", ""))
    lines = max(math.ceil(wide(text(n["ref"])) * NODE_FONT / max(w - 22, 40)) for n in nodes) if facts else 3
    h = min(84, max(46, room if not facts else lines * 20 + 18), room) if room >= 46 else 46
    total_w = ncol * w + (ncol - 1) * gap_x
    total_h = nrow * h + (nrow - 1) * gap_y
    ox, oy = (width - total_w) / 2, min(max(0, (height - total_h) / 2), FLOW_TOP)
    geo = {}
    placed = []
    for n in nodes:
        x, y = ox + n["col"] * (w + gap_x), oy + n["row"] * (h + gap_y)
        geo[n["id"]] = (x, y)
        placed.append({"x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1), "ref": n["ref"],
                       "cls": {"core": "core", "soft": "soft"}.get(n.get("emphasis", ""), ""),
                       "tag": n.get("tag"), "tag_y": round(y + h + 4, 1)})
    edges = []
    for a, b, support, *label in page["edges"]:
        (ax, ay), (bx, by) = geo[a], geo[b]
        if abs(ay - by) < 1:                                   # same row: side to side
            pts = [(ax + w, ay + h / 2), (bx - 2, by + h / 2)] if bx > ax else [(ax, ay + h / 2), (bx + w + 2, by + h / 2)]
            at = ((pts[0][0] + pts[1][0]) / 2, pts[0][1])
        elif abs(ax - bx) < 1:                                 # same column: top/bottom
            pts = [(ax + w / 2, ay + h), (bx + w / 2, by - 2)] if by > ay else [(ax + w / 2, ay), (bx + w / 2, by + h + 2)]
            at = (pts[0][0], (pts[0][1] + pts[1][1]) / 2)
        else:                                                  # elbow through the gap between columns
            if bx > ax:
                x1, x2 = ax + w, bx - 2
            else:
                x1, x2 = ax, bx + w + 2
            xm = x1 + (x2 - x1) / 2
            pts = [(x1, ay + h / 2), (xm, ay + h / 2), (xm, by + h / 2), (x2, by + h / 2)]
            at = (xm, by + h / 2)                              # at the bend on the target's row: branches keep apart
        e = {"support": support, "points": " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}
        if label:
            lw = label_width(label[0], facts)
            e.update(label=label[0], lx=round(at[0] - lw / 2, 1), ly=round(at[1] - LABEL_H / 2, 1), lw=lw, lh=LABEL_H)
        edges.append(e)
    return {"w": round(width, 1), "h": round(height, 1), "gap_x": gap_x, "nodes": placed, "edges": edges}


LABEL_H = 22                  # an arrow label pill, centred on the line, as narrow as its text so the arrowhead stays visible


def label_width(ref: dict, facts: dict | None) -> float:
    text = ref.get("text") if "text" in ref else ((facts or {}).get(ref.get("fact")) or {}).get("text", "")
    wide = sum(1 if ord(ch) > 0x2E80 else 0.6 for ch in (text or "").strip())
    return round(max(30.0, min(68.0, wide * 13.5 + 16)), 1)


PANEL_CHROME = 5 + 36 + 29 + 12    # compare panel: top border, padding, one-line heading, gap
FIGURE_MIN_DPI = 150          # below this a source figure is flagged for the page reviewer (not blocking)
SLIDE_DPI = 96                # 1280 px = 13.333 in
BODY_BOTTOM = 88             # px between the body and the slide bottom (footer + breathing room); matches .body in the template
FOOTNOTE_BOTTOM = 132        # reserve the 56 px footnote strip plus its 20 px gap above the footer


def body_bottom(page: dict) -> int:
    return FOOTNOTE_BOTTOM if page.get("footnote") else BODY_BOTTOM
BODY_TOP, BODY_TOP_NO_LEAD = 196, 170   # body top under title + lead, and under a title alone (keeps a steady gap)


def body_top(page: dict) -> int:
    return BODY_TOP if page.get("lead") or page.get("headline") else BODY_TOP_NO_LEAD   # a headline takes the lead's room


def figure_geometry(page: dict, fact: dict, figure: dict, box: tuple[float, float] | None = None) -> dict:
    """Fit a source figure into the body (or a given (width, height) box, caption and source
    line included) without cropping or changing its aspect ratio."""
    body_h = 720 - body_top(page) - body_bottom(page)
    width = 1152 - (324 if page.get("side") else 0)
    if box:
        width, body_h = box
    cap_h = 52 if fact.get("caption") else 0
    src_h = 26
    box_h = body_h - cap_h - src_h
    scale = min(width / figure["width"], box_h / figure["height"])
    w, h = figure["width"] * scale, figure["height"] * scale
    return {"w": round(w, 2), "h": round(h, 2), "box_w": width, "box_h": box_h, "cap_h": cap_h, "top": round((box_h - h) / 2, 2),
            "dpi": round(figure["width"] / (w / SLIDE_DPI))}


def chart_geometry_errors(page: dict, facts: dict, drawn: list[dict]) -> list[str]:
    """Recompute every bar from its fact's text and compare with the drawn length (independent of the template)."""
    if page.get("layout") == "free":                       # bars of a free page: length / value equal on each scale
        drawn_bars = [b for b in drawn if b.get("scale")]
        values = compose.bar_values({"blocks": [{"kind": "bar", "value_of": b["fact"]} for b in drawn_bars]}, facts)
        return [f"非图表页出现柱：{b['fact']}" for b in drawn if not b.get("scale")] + free.bar_errors(page, values, drawn_bars)
    if page.get("layout") != "chart":
        return [f"非图表页出现柱：{b['fact']}" for b in drawn]
    m = charts.model(page["chart"], facts)
    want = {b["value"]["fact"]: r for b, r in zip(page["chart"]["bars"], m["ratios"])}
    errors = []
    if sorted(b["fact"] for b in drawn) != sorted(want):
        errors.append("绘制的柱与页面规格不一致")
    for b in drawn:
        exp = want.get(b["fact"], -1) * b["plot"]
        if abs(b["length"] - exp) > 1.0:
            errors.append(f"{b['fact']}：柱长 {b['length']:.1f}px，按数值应为 {exp:.1f}px")
    return errors


def table_widths(page, fview) -> list[float]:
    """Column weights from content length when the spec gives none: a column of short
    names should not take half the table from a column of long source sentences."""
    def length(ref):
        if isinstance(ref, dict) and "fact" in ref:
            return len(fview[ref["fact"]]["text"])
        return len(ref.get("text", "")) if isinstance(ref, dict) else len(str(ref))
    out = []
    for c, head in enumerate(page["columns"]):
        longest = max([length(head)] + [sum(length(r) for r in row[c]) for row in page["rows"]])
        out.append(max(4.0, min(longest, 60)) ** 0.75)
    total = sum(out)
    return [max(x / total, 0.14) for x in out]


def oneline(text: str) -> str:
    """A heading set on one line: the original's line breaks were wrapping, so breaks between CJK characters go away and
    other breaks become a space (the fact text is unchanged; checks compare it without whitespace)."""
    text = re.sub(r"(?<=[\u2E80-\u9FFF\uFF00-\uFFEF])\s*[\n\v]\s*(?=[\u2E80-\u9FFF\uFF00-\uFFEF])", "", text)
    return re.sub(r"\s*[\n\v]\s*", " ", text)


def refs_in(x) -> set:
    """Every fact id referenced inside a page part."""
    if isinstance(x, dict):
        return ({x["fact"]} if "fact" in x else set()) | set().union(*[refs_in(v) for v in x.values()] or [set()])
    if isinstance(x, list):
        return set().union(*[refs_in(v) for v in x] or [set()])
    return set()


def mark_focus(x, focus: str):
    """A copy of a page part in which the reference to the focus fact carries focus=True."""
    if isinstance(x, dict):
        return {**{k: mark_focus(v, focus) for k, v in x.items()}, **({"focus": True} if x.get("fact") == focus else {})}
    if isinstance(x, list):
        return [mark_focus(v, focus) for v in x]
    return x


NOTES_H = 118                 # the auxiliary area under a flow: heading + up to two lines per note


OCCUPANCY_MIN = 0.6           # a content page whose body reaches less than this share of the body height reads as empty
HOLE_MAX = 0.2                # nor may any empty rectangle (no text lines, surfaces or drawing) exceed this share of the body
FULL_BLEED = {"cover", "divider", "agenda"}


def signal_reason(page: dict, signal: str) -> str | None:
    """The page's own reason for a visual signal (design.exceptions), if it gives one."""
    for e in ((page.get("design") or {}).get("exceptions") or []):
        if isinstance(e, dict) and e.get("signal") == signal and str(e.get("reason", "")).strip():
            return str(e["reason"]).strip()
    return None


def whitespace_reason(page: dict) -> str | None:
    return signal_reason(page, "whitespace")


MAX_TYPE_SIZES = 3            # running-text sizes in the body (display sizes excluded), per the visual standard
MAX_STRONG_AREAS = 1          # one dark area per page: more and they compete
MIN_BALANCE = 0.75            # reviewed pilot pages sit at 0.83–0.91 (ink centre of mass against the body centre)
MIN_ALIGNMENT = 0.6           # and at 0.71–1.0 (share of text blocks sharing a left edge)


def metric_signals(slide: dict, page: dict) -> list[dict]:
    """Signals from the composition metrics that the visual standard gives a clear limit for."""
    m, out = slide.get("metrics") or {}, []
    if page.get("layout") in FULL_BLEED or not m:
        return out
    if len(m.get("type_sizes") or []) > MAX_TYPE_SIZES:
        out.append({"signal": "type_sizes", "detail": f"{slide['id']}：正文用了 {len(m['type_sizes'])} 种字号（{'、'.join(map(str, m['type_sizes']))} px），"
                    f"标准为至多 {MAX_TYPE_SIZES} 种（数据大字不计）", "justified": signal_reason(page, "type_sizes")})
    if m.get("balance") is not None and m["balance"] < MIN_BALANCE:
        side = "右" if m["centre"][0] > 0 else "左"
        out.append({"signal": "balance", "detail": f"{slide['id']}：内容重心偏{side}{'下' if m['centre'][1] > 0 else '上'}（平衡 {m['balance']}），版面一侧过空",
                    "justified": signal_reason(page, "balance")})
    if m.get("alignment") is not None and m["alignment"] < MIN_ALIGNMENT:
        out.append({"signal": "alignment", "detail": f"{slide['id']}：只有 {round(m['alignment'] * 100)}% 的文字块与其他块左对齐，版面缺少共同的对齐线",
                    "justified": signal_reason(page, "alignment")})
    if (m.get("strong_areas") or 0) > MAX_STRONG_AREAS:
        out.append({"signal": "strong_areas", "detail": f"{slide['id']}：有 {m['strong_areas']} 处深色区块，会互相争夺注意力（标准为一处）",
                    "justified": signal_reason(page, "strong_areas")})
    return out


def sparse(slide: dict, page: dict) -> bool:
    """A content page with a large empty area: its body stops short, or somewhere in it a rectangle larger than
    HOLE_MAX of the body holds nothing. A signal for the author and page reviewer, not a rule: the page fixes it in
    its own way, or states why the space is intended."""
    if page.get("layout") in FULL_BLEED:
        return False
    return slide.get("occupancy", 1) < OCCUPANCY_MIN or ((slide.get("hole") or {}).get("share") or 0) > HOLE_MAX


def sparse_message(slide: dict) -> str:
    hole = slide.get("hole") or {}
    where = ""
    if hole.get("rect"):
        r = hole["rect"]
        where = f"（版心内 x {r['x']}–{r['x'] + r['w']}，y {r['y']}–{r['y'] + r['h']}）"
    return (f"{slide['id']}：留白过多——主体向下用到版心的 {round(slide.get('occupancy', 1) * 100)}%，最大空白区占版心 "
            f"{round((hole.get('share') or 0) * 100)}%{where}；请合并同一条目的相邻内容、按内容宽度分配栏宽或改用更有分量的版式（不放大文字、不凑内容）")


_WIDE = "[⺀-鿿豈-﫿＀-￯　-〿]"   # CJK, compatibility, full-width forms, CJK punctuation


def unwrap_pdf_lines(text: str) -> str:
    """A PDF's text layer keeps the page's line wraps; a wrap is not part of what the source says. Next to a wide
    (CJK/full-width) character it is dropped ("2030⏎年前" → "2030年前"); between two narrow characters it becomes a
    space. Comparison with the quote ignores whitespace, so the shown text still matches its fact."""
    text = re.sub(rf"(?<={_WIDE})[ \t]*\n[ \t]*|[ \t]*\n[ \t]*(?={_WIDE})", "", text)
    return re.sub(r"[ \t]*\n[ \t]*", " ", text)


def build_models(deck, facts, sources, check, figures=None):
    conflicted = {fid for fid, f in facts.items() if any("来源之间不一致" in p for p in f["problems"])}
    fview = {}
    for fid, f in facts.items():
        text = f["display"] or f["quote"]
        if str((sources.get(f.get("source_id")) or {}).get("filename", "")).lower().endswith(".pdf"):
            text = unwrap_pdf_lines(text)
        fview[fid] = {"id": fid, "text": text, "pending": f["needs_confirmation"], "conflict": fid in conflicted,
                      "figure": f.get("figure", "")}
    def text_len(ref):
        if isinstance(ref, dict) and "fact" in ref:
            return len(fview[ref["fact"]]["text"])
        return len(ref.get("text", "")) if isinstance(ref, dict) else 0

    pages, divider_no = [], 0
    for i, (page, res) in enumerate(zip(deck["pages"], check["pages"])):
        p = dict(page)
        p["pending_count"] = len(res["pending"])
        p["sources_line"] = sources_line(res["facts"], facts, sources)
        if page["layout"] == "composed":
            p.update(compose.model(page, compose.bar_values(page, facts)))
        if page["layout"] == "cover":
            p["art"] = cover_art(7 + i)
            p["chrome_meta"] = f"原始资料 {len(sources)} 份 · 页面中每一条内容均可追溯到原文位置"
        if page["layout"] == "divider":             # the cover's language: number, title, short bar, art
            divider_no += 1
            p["divider_no"] = divider_no
            p["art"] = cover_art(7 + i)
        if page["layout"] in ("bullets", "closing"):
            items = page.get("items") or []
            lens = [text_len(x) for x in items] or [0]
            p["variant"] = "two" if len(items) > 5 and max(lens) <= 40 else "list"
        if page["layout"] == "grid":
            # short tiles (a label and a name) read across in one row; fuller tiles wrap into 2 or 3 columns
            n = len(page["tiles"])
            short = all(text_len(t["heading"]) + sum(text_len(x) for x in t["items"]) <= GRID_SHORT for t in page["tiles"])
            p["grid_cols"] = n if short and n <= 6 else (2 if n in (2, 4) else 3)
        if page["layout"] == "table":
            ws = page.get("widths") or table_widths(page, fview)
            p["col_widths"] = [round(100 * x / sum(ws), 2) for x in ws]
        if page["layout"] == "cards":
            # per card, as in the demo: a short number is set large, a word or phrase one step smaller
            p["cards"] = [{**c, "numeric": "fact" in c["value"] and bool(re.search(r"\d", fview[c["value"]["fact"]]["text"]))
                           and len(fview[c["value"]["fact"]]["text"]) <= 9} for c in page["cards"]]
        if page["layout"] == "flow":
            body_h = 720 - body_top(page) - body_bottom(page) - (NOTES_H + 20 if page.get("notes") else 0)
            p["geo"] = flow_geometry(page, 1152 - (324 if page.get("side") else 0), body_h, fview)
            if page.get("notes"):
                p["notes_top"] = round(max(n["y"] + n["h"] for n in p["geo"]["nodes"]) + 36, 1)
        if page["layout"] == "chart":
            body_h = 720 - body_top(page) - body_bottom(page)
            cm = charts.model(page["chart"], facts)
            p["cg"] = charts.geometry(page["chart"], cm, 1152 - (324 if page.get("side") else 0), body_h - 8)
            p["cg"].update(refs=page["chart"]["bars"], w=1152 - (324 if page.get("side") else 0), h=body_h - 8)
        def fig_model(ref, box=None):
            f = facts[ref["fact"]]
            g = figures[f["figure"]]
            src = sources.get(f["source_id"], {})
            return {"fact": f["id"], "figure": f["figure"], "file": g["file"], "caption": list(f.get("caption") or []),
                    "source": f"{short_title(src.get('title') or src.get('filename') or f['source_id'])} {f['location']}",
                    "pending": f["needs_confirmation"], **figure_geometry(page, f, g, box)}
        if page["layout"] == "figure":
            p["fig"] = fig_model(page["figure"])
        if page["layout"] == "compare" and any("figure" in pn for pn in page["panels"]):
            n = len(page["panels"])
            body_h = 720 - body_top(page) - body_bottom(page) - 8 - (104 if page.get("band") else 0)
            inner = ((1152 - 24 * (n - 1)) / n - 48, body_h - PANEL_CHROME)
            p["panels"] = [{**pn, "fig": fig_model(pn["figure"], inner)} if "figure" in pn else pn for pn in page["panels"]]
            p["fixed_size"] = True           # the figures are sized for body text at k = 1
        # the page's focus. Panels, tiles, cards and side notes are peers: they keep identical surfaces (darkening one
        # would say that peer matters more), and the focus fact itself is marked. Nested levels and flow nodes are not
        # peers: the level or node holding the focus is the page's one strong element.
        focus = (page.get("focus") or {}).get("fact") if isinstance(page.get("focus"), dict) else None
        if focus:
            for key in ("panels", "tiles", "cards", "side"):
                if p.get(key):
                    p[key] = mark_focus(p[key], focus)
            if p.get("levels") and page.get("layout") == "nested":
                p["levels"] = [{**x, "is_focus": focus in refs_in(x)} for x in p["levels"]]
            if p.get("geo"):
                for n in p["geo"]["nodes"]:
                    if focus in refs_in(n["ref"]):
                        n["cls"] = "core"
        if page["layout"] == "nested":
            p["nest_w"] = round((1152 - 44 * (len(page["levels"]) - 1)) / len(page["levels"]) - 44, 1)
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


def _set_font(run, size_px, bold, color, font=PPT_FONT):
    from pptx.util import Pt
    from pptx.oxml.ns import qn
    f = run.font
    f.size = Pt(round(size_px * 0.75 * 2) / 2)
    f.bold = bold
    f.name = font
    rPr = run._r.get_or_add_rPr()
    if re.search(r"[　-鿿＀-￯]", run.text or ""):   # Chinese text: PowerPoint then applies Chinese
        rPr.set("lang", "zh-CN")                                     # line breaking (no line starts with ，。；）
        rPr.set("altLang", "en-US")
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", font)
    if color:
        f.color.rgb = _rgb(color)


def _fill_paras(tf, paras, line_height_px, align="left", font=PPT_FONT):
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN
    al = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
    first = True
    for runs in paras:
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        para.alignment = al
        ppr = para._p.get_or_add_pPr()          # Chinese line breaking: punctuation hangs at the line end, never starts a line
        ppr.set("eaLnBrk", "1")
        ppr.set("hangingPunct", "1")
        if line_height_px:
            para.line_spacing = Pt(line_height_px * 0.75)
        after = max((r.get("after") or 0 for r in runs), default=0)
        if after:
            para.space_after = Pt(after * 0.75)
        for r in runs:
            run = para.add_run()
            run.text = r["text"]
            _set_font(run, r["size"] * (0.62 if r.get("mark") and r["size"] > 14 else 1), r["bold"], r["color"], r.get("font",font))


# theme colour slots: a colour on a slide that equals one of these tokens is written as a reference to the theme, so a
# client who changes the theme (Design → Variants → Colors) recolours the whole deck
THEME_SLOTS = [("dk1", "tx1", "ink"), ("lt1", "bg1", None), ("dk2", "tx2", "primary"), ("lt2", "bg2", "sky"),
               ("accent1", "accent1", "primary"), ("accent2", "accent2", "accent"), ("accent3", "accent3", "primary2"),
               ("accent4", "accent4", "accent2"), ("accent5", "accent5", "muted"), ("accent6", "accent6", "line")]


def _write_theme(prs, tokens: dict, font: str):
    """Colours and fonts of the deck's theme into the presentation theme; slide colours then refer to it."""
    from lxml import etree
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.oxml.ns import qn
    part = prs.slide_master.part.part_related_by(RT.THEME)
    root = etree.fromstring(part.blob)
    scheme = root.find(".//" + qn("a:clrScheme"))
    scheme.set("name", "FactDeck")
    slot_hex = {}
    for slot, ref, token in THEME_SLOTS:
        hexv = "FFFFFF" if token is None else tokens[token].lstrip("#").upper()
        el = scheme.find(qn("a:" + slot))
        for ch in list(el):
            el.remove(ch)
        el.append(el.makeelement(qn("a:srgbClr"), {"val": hexv}))
        slot_hex.setdefault(hexv, ref)
    fonts = root.find(".//" + qn("a:fontScheme"))
    fonts.set("name", "FactDeck")
    for kind in ("a:majorFont", "a:minorFont"):
        f = fonts.find(qn(kind))
        for script in ("a:latin", "a:ea"):
            f.find(qn(script)).set("typeface", font)
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return slot_hex


def _theme_refs(slide, slot_hex: dict):
    """Rewrite every explicit colour that equals a theme colour as a reference to that theme slot."""
    from pptx.oxml.ns import qn
    for el in slide._element.iter(qn("a:srgbClr")):
        ref = slot_hex.get((el.get("val") or "").upper())
        if ref:
            el.tag = qn("a:schemeClr")
            el.attrib.clear()
            el.set("val", ref)


def build_pptx(models: list[dict], raster_png: dict, notes: list[str], out: Path, title: str = "", figure_png: dict | None = None,
               font: str = PPT_FONT, theme: dict | None = None, strict_text_geometry: bool = False,
               icon_png: dict | None = None):
    from pptx import Presentation
    from pptx.util import Emu
    from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
    from pptx.enum.dml import MSO_LINE_DASH_STYLE
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
    from pptx.oxml.ns import qn

    prs = Presentation()
    prs.core_properties.title = title
    prs.slide_width, prs.slide_height = Emu(1280 * PX), Emu(720 * PX)
    title_only = prs.slide_layouts[5]          # the page title goes into a real title placeholder (outline view, accessibility)
    slot_hex = _write_theme(prs, theme, font) if theme else {}
    E = lambda v: Emu(int(round(v * PX)))
    for m, note in zip(models, notes):
        s = prs.slides.add_slide(title_only)
        groups = {}

        def into(group):
            """Where a shape goes: the slide, or the PowerPoint group of its item (created on first use)."""
            if not group:
                return s.shapes
            if group not in groups:
                groups[group] = s.shapes.add_group_shape()
            return groups[group].shapes
        if m.get("background"):
            bg = s.background.fill
            bg.solid()
            bg.fore_color.rgb = _rgb(m["background"])
        for r in m["rasters"]:
            s.shapes.add_picture(str(raster_png[r["id"]]), E(r["x"]), E(r["y"]), E(r["w"]), E(r["h"]))
        for sh in m["shapes"]:
            kind = MSO_SHAPE.ROUNDED_RECTANGLE if sh["radius"] > 0.5 else MSO_SHAPE.RECTANGLE
            target = into(sh.get("group"))
            shape = target.add_shape(kind, E(sh["x"]), E(sh["y"]), E(sh["w"]), E(sh["h"]))
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
                acc = target.add_shape(MSO_SHAPE.RECTANGLE, E(a["x"]), E(a["y"]), E(a["w"]), E(a["h"]))
                acc.fill.solid()
                acc.fill.fore_color.rgb = _rgb(a["color"])
                acc.line.fill.background()
                acc.shadow.inherit = False
        for ln in m["lines"]:
            pts = ln["points"]
            for i in range(len(pts) - 1):
                (x1, y1), (x2, y2) = pts[i], pts[i + 1]
                c = into(ln.get("group")).add_connector(MSO_CONNECTOR.STRAIGHT, E(x1), E(y1), E(x2), E(y2))
                c.line.color.rgb = _rgb({"hex": ln["color"]})
                c.line.width = E(ln["w"])
                if ln.get("dash"):                     # a dashed course stays dashed (it is how two curves are told apart)
                    c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
                if ln["arrow"] and i == len(pts) - 2:
                    lnx = c.line._get_or_add_ln()
                    lnx.append(lnx.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
        for rg in m.get("rings", []):           # free-page rings: a track, then the pale and the solid arc, all native
            side = min(rg["w"], rg["h"])
            x0, y0 = rg["x"] + (rg["w"] - side) / 2, rg["y"] + (rg["h"] - side) / 2
            thick = int(max(1000, min(50000, rg["thick"] * 100000)))
            layers = [(MSO_SHAPE.DONUT, None, rg["track"], 1)]
            for frac, alpha in ((rg["pale"], rg.get("paleOpacity", 1)), (rg["solid"], 1)):
                if frac > 0 and (frac != rg["solid"] or alpha == 1):
                    layers.append((MSO_SHAPE.DONUT if frac >= 99.99 else MSO_SHAPE.BLOCK_ARC, frac, rg["tone"], alpha))
            for kind, frac, col, alpha in layers:
                if not col:
                    continue
                shp = s.shapes.add_shape(kind, E(x0), E(y0), E(side), E(side))
                av = shp._element.spPr.find(qn("a:prstGeom")).get_or_add_avLst()
                for gd in list(av):
                    av.remove(gd)
                if kind == MSO_SHAPE.DONUT:
                    av.append(av.makeelement(qn("a:gd"), {"name": "adj", "fmla": f"val {thick}"}))
                else:                                # PowerPoint angles: 0 = 3 o'clock, clockwise, 60000ths of a degree
                    start, end = 270 * 60000, int((270 + frac * 3.6) % 360 * 60000)
                    for nm, v in (("adj1", start), ("adj2", end), ("adj3", thick)):
                        av.append(av.makeelement(qn("a:gd"), {"name": nm, "fmla": f"val {v}"}))
                shp.fill.solid()
                shp.fill.fore_color.rgb = _rgb(col)
                if alpha < 1:
                    clr = shp.fill._xPr.find(qn("a:solidFill"))[0]
                    clr.append(clr.makeelement(qn("a:alpha"), {"val": str(int(alpha * 100000))}))
                shp.line.fill.background()
                shp.shadow.inherit = False
        for g in m.get("icons", []):           # composed-page icons: above the surfaces they sit on (SVG: native, below)
            if str(icon_png[g["id"]]).lower().endswith(".svg"):
                continue
            s.shapes.add_picture(str(icon_png[g["id"]]), E(g["x"]), E(g["y"]), E(g["w"]), E(g["h"]))
        for g in m.get("figures", []):         # the archived original, not a screenshot
            s.shapes.add_picture(str(figure_png[g["id"]]), E(g["x"]), E(g["y"]), E(g["w"]), E(g["h"]))
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
                    cell.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}.get(cd.get("anchor"), MSO_ANCHOR.TOP if ri else MSO_ANCHOR.MIDDLE)
                    tf = cell.text_frame
                    tf.word_wrap = True
                    _fill_paras(tf, cd["paras"] or [[{"text": "", "size": 14, "bold": False, "color": None}]], cd["lineHeight"], font=font)
                    if cd.get("align"):
                        for para in tf.paragraphs:
                            para.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[cd["align"]]
                    tcPr = cell._tc.get_or_add_tcPr()
                    for index,side in enumerate(("a:lnL", "a:lnR", "a:lnT", "a:lnB")):
                        for existing in list(tcPr.findall(qn(side))): tcPr.remove(existing)
                        ln = tcPr.makeelement(qn(side), {"w": "9525" if side == "a:lnB" and cd["border"] else "0"})
                        if side == "a:lnB" and cd["border"]:
                            sf = ln.makeelement(qn("a:solidFill"), {})
                            sf.append(sf.makeelement(qn("a:srgbClr"), {"val": cd["border"]["hex"].upper()}))
                            ln.append(sf)
                        else:
                            ln.append(ln.makeelement(qn("a:noFill"), {}))
                        # DrawingML requires line children before the cell fill.
                        # Office otherwise falls back to the black Table Grid style.
                        tcPr.insert(index,ln)
        title_ph = s.shapes.title
        for t in m["texts"]:
            if not t["paras"]:
                continue
            w = t["w"] if strict_text_geometry else t["w"] * 1.03 + 2
            geo = (E(t["x"]), E(t["y"]), E(w), E(max(t["h"], t["lineHeight"])))
            if t.get("role") == "title" and title_ph is not None and not title_ph.text_frame.text:
                tb = title_ph
                tb.left, tb.top, tb.width, tb.height = geo
            else:
                tb = into(t.get("group")).add_textbox(*geo)
            tf = tb.text_frame
            tf.word_wrap = not t["nowrap"]
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE if t["anchor"] == "middle" else MSO_ANCHOR.TOP
            tf.auto_size = MSO_AUTO_SIZE.NONE      # explicit: a placeholder would otherwise inherit the layout's autofit
            _fill_paras(tf, t["paras"], t["lineHeight"], t["align"], font)
        if title_ph is not None and not title_ph.text_frame.text:      # a slide without a title keeps no empty placeholder
            title_ph._element.getparent().remove(title_ph._element)
        if slot_hex:
            _theme_refs(s, slot_hex)
        s.notes_slide.notes_text_frame.text = note
    prs.save(str(out))


# ---------------------------------------------------------------- readback
def readback(pptx_path: Path, pages_facts: list[list[str]], fview: dict, pages_figures: list[list[dict]] | None = None) -> list[dict]:
    """Every fact's text is in the slide; every source figure is there byte-identical and undistorted."""
    import hashlib
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs = Presentation(str(pptx_path))

    def flat(shapes):
        """Every shape on the slide, including those inside groups."""
        for sh in shapes:
            if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from flat(sh.shapes)
            else:
                yield sh
    results = []
    for n, (slide, fids) in enumerate(zip(prs.slides, pages_facts)):
        shapes = list(flat(slide.shapes))
        pics = [(hashlib.sha256(sh.image.blob).hexdigest(), sh.width / sh.height) for sh in shapes
                if sh.shape_type == MSO_SHAPE_TYPE.PICTURE]
        missing_figures = []
        for g in (pages_figures or [[]] * len(pages_facts))[n]:
            ratio = g["width"] / g["height"]
            if not any(h == g["sha256"] and abs(r - ratio) / ratio < 0.01 for h, r in pics):
                missing_figures.append(g["id"])
        texts = []
        for sh in shapes:
            if sh.has_text_frame:
                texts.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                texts += [c.text for row in sh.table.rows for c in row.cells]
        # python-pptx exposes DrawingML's escaped control characters literally.
        # Decode once: _x005F_x0001_ represents the literal text _x0001_,
        # while _x0001_ represents the original control character.
        raw_text = "\n".join(texts)
        blob = canon(raw_text)
        decoded_blob = canon(re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), raw_text))
        missing = [fid for fid in fids if not fview[fid].get("figure")
                   and canon(fview[fid]["text"]) not in blob
                   and canon(fview[fid]["text"]) not in decoded_blob]
        notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
        results.append({"facts": len(fids), "missing": missing, "missing_figures": missing_figures, "notes_chars": len(notes)})
    return results


DRIFT_MAX = 0.06              # mean per-pixel difference (0–1) between PowerPoint-side and browser renders of a slide


def soffice_path() -> str | None:
    for c in (shutil.which("soffice"), shutil.which("libreoffice"),
              r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        if c and Path(c).exists():
            return c
    return None


def appearance_check(out: Path, n_slides: int) -> dict:
    """Does the exported PPTX look like the browser render? LibreOffice renders the PPTX (an independent office
    renderer), each page is compared with slideNN.png. Skipped, with a notice, where LibreOffice is not installed."""
    import subprocess
    import tempfile
    soffice = soffice_path()
    if not soffice:
        return {"status": "skipped", "reason": "未安装 LibreOffice，未比对 PPTX 与浏览器画面（安装后自动启用）"}
    try:
        import pypdfium2 as pdfium
        from PIL import Image, ImageChops, ImageStat
    except ImportError as e:
        return {"status": "skipped", "reason": f"缺少比对组件：{e}"}
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(out / "deck.pptx")],
                       check=True, capture_output=True, timeout=300)
        pdf = pdfium.PdfDocument(str(Path(tmp) / "deck.pdf"))
        slides = []
        for i in range(min(len(pdf), n_slides)):
            office = pdf[i].render(scale=1280 / pdf[i].get_width()).to_pil().convert("L").resize((640, 360))
            browser = Image.open(out / f"slide{i + 1:02d}.png").convert("L").resize((640, 360))
            diff = ImageStat.Stat(ImageChops.difference(office, browser)).mean[0] / 255
            slides.append({"slide": i + 1, "drift": round(diff, 3)})
    return {"status": "checked", "slides": slides, "drifted": [x["slide"] for x in slides if x["drift"] > DRIFT_MAX]}


FIT_JS = """(id) => {
  const s = document.getElementById(id); const S = s.getBoundingClientRect();
  const foot = s.querySelector('.foot'), body = s.querySelector('.body');
  const limit = Math.min(foot ? foot.getBoundingClientRect().top : S.bottom, body ? body.getBoundingClientRect().bottom : S.bottom);
  let bad = 0;
  s.querySelectorAll('[data-t], td, th').forEach((el) => {
    if (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1) bad++;
  });
  s.querySelectorAll('.body [data-t], .body table, .body [data-shape]').forEach((el) => {
    const r = el.getBoundingClientRect(); if (r.height > 0 && r.bottom > limit + 0.5) bad++;
  });
  return bad;
}"""


MEASURE_JS = r"""(id) => {
  // natural height of every composed text block, keyed like recipes.mkey: size | width | text without whitespace
  const out = {};
  document.querySelectorAll('#' + id + ' .cb[data-t]').forEach((el) => {
    const cs = getComputedStyle(el), h0 = el.style.height;
    el.style.height = 'auto';
    const h = Math.ceil(el.getBoundingClientRect().height);
    el.style.height = h0;
    const text = [...el.querySelectorAll('[data-fact],[data-authored]')].map((x) => x.textContent).join('　').replace(/\s+/g, '');
    const key = Math.round(parseFloat(cs.fontSize)) + '|' + Math.round(el.getBoundingClientRect().width) + '|' + text;
    out[key] = Math.max(out[key] || 0, h);
  });
  return out;
}"""


SET_K_JS = """([id, k]) => {
  const s = document.getElementById(id); const b = s.querySelector('.body');
  s.style.setProperty('--k', Math.min(k, 1));
  if (b) b.style.setProperty('--k', k);
}"""


FONT_JS = """(face) => {
  const c = document.createElement('canvas').getContext('2d'); const s = '测试字体宽度Ag123';
  const w = (ff) => { c.font = '40px ' + ff; return c.measureText(s).width; };
  return ['monospace', 'serif', 'sans-serif'].some((b) => w('"' + face + '",' + b) !== w(b));
}"""


def resolve_theme(theme) -> tuple[dict, str | None, str | None, str]:
    """(tokens, brand font, logo path, name) for a built-in theme name or a brand dict {tokens, font, logo}."""
    if isinstance(theme, dict):
        missing = set(THEMES["navy-teal"]) - set(theme.get("tokens", {}))
        if missing:
            raise ValueError("品牌配色缺少：" + "、".join(sorted(missing)))
        return dict(theme["tokens"]), theme.get("font"), theme.get("logo"), "brand"
    return THEMES.get(theme, THEMES["navy-teal"]), None, None, theme


# ---------------------------------------------------------------- main
def render(deck: dict, facts: dict[str, dict], sources: dict[str, dict], out: Path,
           theme: str = "navy-teal", terms: list[str] | tuple[str, ...] = (), pages_only: list[str] | None = None,
           figures: dict[str, dict] | None = None, teaching_notes: dict[str, str] | None = None,
           generated_illustrations: dict[str, list[dict] | dict] | None = None,
           icons: dict[str, str | Path] | None = None) -> dict:
    """Render `deck` into `out`. `facts` are verified facts by id; `sources` by id ({title|filename});
    `figures` by figure id ({path, sha256, width, height}) for every figure fact on a page;
    `teaching_notes` by page id: the summary text the presenter speaks to, placed before the provenance list;
    `icons` by icon id: the PNG files that composed pages' icon blocks name."""
    import hashlib
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    chk = deck_check(deck, facts, terms)
    if chk["errors"]:
        raise ValueError(f"页面规格检查未通过：{chk['errors']} 处错误")
    figview = {}
    for fid, g in (figures or {}).items():
        data = Path(g["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != g["sha256"]:
            raise ValueError(f"图文件已被修改：{fid}")
        name = f"figure_{g['sha256'][:24]}.png"
        (out / name).write_bytes(data)
        figview[fid] = {**g, "file": name, "path": out / name}
    # Generated, text-free explanatory diagrams are optional supporting art. Their labels
    # remain native locked facts; the image itself never supplies page wording or data.
    illustration_view = {}
    for page_id, raw_layers in (generated_illustrations or {}).items():
        layers = raw_layers if isinstance(raw_layers, list) else [raw_layers]
        for index, layer in enumerate(layers):
            path = Path(layer["path"])
            if not path.is_file():
                raise ValueError(f"找不到生成插图：{path}")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            name = f"illustration_{digest[:24]}.png"
            (out / name).write_bytes(data)
            illustration_view.setdefault(page_id, []).append({"id": f"{page_id}-{index}", "file": name,
                "x": float(layer["x"]), "y": float(layer["y"]), "w": float(layer["w"]), "h": float(layer["h"])})

    iconview = {}
    for icon_id, path in (icons or {}).items():
        data = Path(path).read_bytes()
        name = f"icon_{hashlib.sha256(data).hexdigest()[:24]}{Path(path).suffix.lower()}"
        (out / name).write_bytes(data)
        iconview[icon_id] = {"file": name, "path": out / name}

    def add_illustrations(models):
        for model in models:
            model["generated_illustrations"] = illustration_view.get(model["id"], [])
            if model["layout"] == "free":
                missing = sorted(i for i in free.icon_ids(model["html"]) if i not in iconview)
                if missing:
                    raise ValueError(f"找不到图标文件：{'、'.join(map(str, missing))}（页面 {model['id']}）")
                model["free_html"], model["free_css"] = free.render(model, fview, {k: v["file"] for k, v in iconview.items()}, emph_spans)
            for b in model.get("blocks") or []:
                if b.get("kind") == "icon":
                    if b["icon"] not in iconview:
                        raise ValueError(f"找不到图标文件：{b['icon']}（页面 {model['id']}）")
                    b["file"] = iconview[b["icon"]]["file"]
        return models

    source_deck = deck
    deck, _ = recipes.expand_deck(deck, facts)                  # recipe pages placed as the check saw them (estimates)
    pages, fview = build_models(deck, facts, sources, chk, figview)
    add_illustrations(pages)
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True)
    env.globals["emph_spans"] = emph_spans
    env.filters["oneline"] = oneline
    tokens, font, logo, theme_name = resolve_theme(theme)
    if logo:
        logo_name = "logo" + Path(logo).suffix.lower()
        shutil.copyfile(logo, out / logo_name)
        logo = logo_name
    html_path = out / "deck.html"
    write = lambda f: html_path.write_text(env.get_template("deck.html.j2").render(
        deck=deck, pages=pages, facts=fview, theme=tokens, brand_font=f, logo=logo,
        body_top=BODY_TOP, body_top_no_lead=BODY_TOP_NO_LEAD), encoding="utf-8")
    write(font)

    js = (HERE / "extract.js").read_text(encoding="utf-8")
    expected = {k: v["text"] for k, v in fview.items()}
    glossary = [x["text"] for x in deck.get("glossary", deck.get("terms", []))]
    models, raster_png, report, density = [], {}, {"slides": []}, {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        page.goto(html_path.resolve().as_uri())
        page.evaluate("document.fonts.ready")
        font_warning = None
        if font and not page.evaluate(FONT_JS, font):     # browser and PowerPoint must measure the same face
            font_warning = f"品牌字体“{font}”未安装在渲染机上，已改用{PPT_FONT}；如需使用请先安装该字体"
            font = None
            write(None)
            page.goto(html_path.resolve().as_uri())
            page.evaluate("document.fonts.ready")
        # recipe pages: measure every text block's real height, then place the page again from real sizes
        recipe_ids = [p["id"] for p in source_deck["pages"] if p.get("recipe")]
        if recipe_ids:
            measured = {pid: page.evaluate(MEASURE_JS, pid) for pid in recipe_ids}
            deck, _ = recipes.expand_deck(source_deck, facts, measured)
            pages, fview = build_models(deck, facts, sources, chk, figview)
            add_illustrations(pages)
            write(font)
            page.goto(html_path.resolve().as_uri())
            page.evaluate("document.fonts.ready")
        for i, p in enumerate(pages, 1):
            for k in (DENSITY if p["layout"] != "free" else DENSITY[:1]):   # largest body size at which nothing overflows
                # (a free page's HTML sets its own sizes: an overflow there is the designer's to fix, not shrunk away)
                page.evaluate(SET_K_JS, [p["id"], k])
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
            m["checks"]["chart_geometry"] = chart_geometry_errors(p, facts, m.pop("chart_bars"))
            m["checks"]["figure_low_dpi"] = []
            for g in m["figures"]:
                src = figview[facts[g["id"]]["figure"]]
                ratio, shown = src["width"] / src["height"], g["w"] / max(g["h"], 1e-6)
                if abs(shown - ratio) / ratio >= 0.01 or g["nw"] != src["width"] or g["nh"] != src["height"]:
                    m["checks"]["figure_distortion"].append(g["id"])
                dpi = round(src["width"] / (g["w"] / SLIDE_DPI))
                if dpi < FIGURE_MIN_DPI:
                    m["checks"]["figure_low_dpi"].append({"fact": g["id"], "dpi": dpi})
            report["slides"].append({"id": p["id"], "density": k, "occupancy": m.pop("occupancy", 1), "hole": m.pop("hole", None), "metrics": m.pop("metrics", None), **m["checks"]})
            models.append(m)
        html_path.write_text(page.content(), encoding="utf-8")      # keep the fitted densities
        page.emulate_media(media="print")
        page.pdf(path=str(out / "deck.pdf"), width="1280px", height="720px", print_background=True)
        browser.close()

    notes = []
    for p, res in zip(pages, chk["pages"]):
        script = (teaching_notes or {}).get(p.get("id"), "")
        lines = ["【来源追溯】本页每条内容对应的原文位置："]
        for fid in res["facts"]:
            f = facts[fid]
            flag = "（待人工确认）" if f["needs_confirmation"] else ""
            src = sources.get(f["source_id"], {})
            shown = f"〔原件图片，未作修改〕{f['figure']}" if f.get("figure") else fview[fid]["text"]
            lines.append(f"· {shown} ← {src.get('filename') or src.get('title', '')} {f['location']}{flag}")
        trace = "\n".join(lines) if res["facts"] else ""
        notes.append("\n\n".join(x for x in ("【讲稿】\n" + script if script else "", trace) if x))
    pptx_path = out / "deck.pptx"
    figure_png = {fid: figview[f["figure"]]["path"] for fid, f in facts.items() if f.get("figure") in figview}
    build_pptx(models, raster_png, notes, pptx_path, deck.get("title", ""), figure_png, font or PPT_FONT, tokens,
               icon_png={k: v["path"] for k, v in iconview.items()})
    svg_icons = [[g for g in m.get("icons", []) if iconview[g["id"]]["file"].endswith(".svg")] for m in models]
    if any(svg_icons):                         # code-drawn icons become editable PowerPoint shapes, not pictures
        from .native_vectors import add_native_vectors, trace_svg
        per_slide = []
        for icons_here in svg_icons:
            vectors = []
            for g in icons_here:
                traced, _ = trace_svg(iconview[g["id"]]["path"].read_bytes(), preserve_order=True, target_size=(g["w"], g["h"]))
                for v in traced:
                    v["group"] = v["name"] = f"图标 {g['id']}"
                    v["commands"] = [[c[0], *[n + (g["x"] if k % 2 == 0 else g["y"]) for k, n in enumerate(c[1:])]] for c in v["commands"]]
                vectors += traced
            per_slide.append(vectors)
        add_native_vectors(pptx_path, per_slide, on_top=True)
    # Immutable preparation input for the image → native-vector route. Content,
    # tables and supported connectors are locked before a visual worker sees them.
    (out / "native_model.json").write_text(json.dumps({"models": models, "notes": notes, "font": font or PPT_FONT}, ensure_ascii=False), encoding="utf-8")
    pages_figures = [[{"id": g["id"], **{k: figview[facts[g["id"]]["figure"]][k] for k in ("sha256", "width", "height")}}
                      for g in m["figures"]] for m in models]
    rb = readback(pptx_path, [r["facts"] for r in chk["pages"]], fview, pages_figures)
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
        "hierarchy": sum(len(s.get("hierarchy", [])) for s in report["slides"]),
        "unsupported": sum(len(s.get("unsupported", [])) for s in report["slides"]),
        "authored_lint": sum(len(s["authored_lint"]) for s in report["slides"]),
        "pptx_missing_facts": sum(len(r["missing"]) for r in rb),
        "chart_geometry": sum(len(s["chart_geometry"]) for s in report["slides"]),
        "figures": sum(len(m["figures"]) for m in models),
        "figure_distortion": sum(len(s["figure_distortion"]) for s in report["slides"]),
        "figure_low_dpi": sum(len(s["figure_low_dpi"]) for s in report["slides"]),
        "pptx_missing_figures": sum(len(r["missing_figures"]) for r in rb),
        "sparse": sum(1 for sl, p in zip(report["slides"], pages) if sparse(sl, p) and not whitespace_reason(p)),
    }
    s = report["summary"]
    report["hard_errors"] = s["untracked_text"] + s["fact_text_mismatch"] + s["overflow"] + s["out_of_bounds"] + s["overlap"] + s["hierarchy"] + s["authored_lint"] + s["pptx_missing_facts"] \
        + s["figure_distortion"] + s["pptx_missing_figures"] + s["chart_geometry"] + s["unsupported"]
    report["theme"] = theme_name
    report["font"] = font or PPT_FONT
    # per page: the design note, the signals (fixed or justified by the page itself) and the semantic review list
    for sl, p, res in zip(report["slides"], pages, chk["pages"]):
        sl["design"], sl["review"], sl["signals"] = res.get("design") or {}, res.get("review") or [], list(res.get("signals") or [])
        if sparse(sl, p):
            sl["signals"].append({"signal": "whitespace", "detail": sparse_message(sl), "justified": whitespace_reason(p)})
        sl["signals"] += metric_signals(sl, p)
    report["appearance"] = appearance_check(out, len(pages))
    report["warnings"] = ([font_warning] if font_warning else []) + (
        [f"PPTX 画面与浏览器渲染差异较大的页：{'、'.join(map(str, report['appearance']['drifted']))}（请在 PowerPoint 中检查）"]
        if report["appearance"].get("drifted") else []) + [
        s["detail"] for sl in report["slides"] for s in sl["signals"] if s["signal"] != "repetition" and not s["justified"]]
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
