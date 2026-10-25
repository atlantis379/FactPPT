"""Pharma / academic-congress chart-led families (v1.3.1 pharma batch).

Six chart-led families + the ``key_points/evidence_takeaways`` variant:

  trial_design · forest_plot · endpoint_readout · moa_cascade ·
  data_table_highlight · landscape_swimlane

Every chart is computed here as explicit pixel geometry from the *fill data*
(no images).  Templates only draw SVG/HTML primitives from these numbers, so the
same geometry can later be mapped 1:1 onto native PPTX shapes / charts.

Layout language follows public pharma IR / congress decks (structure only — see
``/workspace/sync/layout-research-pharma/REPORT.md``); no artwork, icons, logos or
brand styling are reused.
"""
from __future__ import annotations

import math
import re
from typing import Any

FAMILIES = (
    "trial_design",
    "forest_plot",
    "endpoint_readout",
    "moa_cascade",
    "data_table_highlight",
    "landscape_swimlane",
)
EVIDENCE_VARIANT = "evidence_takeaways"

DEMO_NOTE = "示例数据，教学示意，非诊疗建议"
STRUCT_NOTE = "版式参考药企学术会议幻灯（仅结构）"

# Canvas geometry shared by all pharma pages (px @ 1280×720).
MAIN_W_RAIL = 896      # main chart width when a right takeaway rail is present
MAIN_W_FULL = 1224     # full body width
BODY_H = 512

_STATUS = ("met", "not_met", "ongoing")


# --------------------------------------------------------------------------- utils

def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _f(v: Any) -> float:
    return float(v)


def fmt(v: float, nd: int = 2) -> str:
    return f"{v:.{nd}f}"


def text_w(s: str, pt: float) -> float:
    """Rough rendered width (px) of *s* at *pt* — CJK ≈ 1em, latin ≈ 0.56em."""
    px = pt * 96 / 72
    w = 0.0
    for ch in str(s):
        if ord(ch) > 0x2E80:
            w += 1.0
        elif ch in " .,:;'|!()[]":
            w += 0.3
        else:
            w += 0.56
    return w * px


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / max(n - 1, 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    start = math.floor(lo / step + 1e-9) * step
    ticks = [round(start, 10)]
    while ticks[-1] < hi - step * 1e-6:
        ticks.append(round(ticks[-1] + step, 10))
    return ticks


def _has_digit(s: str) -> bool:
    return bool(re.search(r"\d", s or ""))


# --------------------------------------------------------------------------- common

def _refs(fill: dict) -> list[dict[str, str]]:
    out = []
    for i, r in enumerate(fill.get("refs") or []):
        if isinstance(r, str):
            out.append({"id": str(i + 1), "text": r.strip()})
        elif isinstance(r, dict):
            out.append({"id": _s(r.get("id")) or str(i + 1), "text": _s(r.get("text"))})
    return out


def _takeaways(raw: list | None) -> list[dict[str, Any]]:
    out = []
    for i, t in enumerate(raw or []):
        if not isinstance(t, dict):
            continue
        refs = t.get("refs")
        if refs is None and t.get("ref") is not None:
            refs = [t.get("ref")]
        out.append({
            "value": _s(t.get("value")),
            "unit": _s(t.get("unit")),
            "text": _s(t.get("text")),
            "refs": [_s(r) for r in (refs or []) if _s(r)],
            "index": i + 1,
        })
    return out


def common(fill: dict) -> dict[str, Any]:
    return {
        "section": _s(fill.get("section")),
        "title": _s(fill.get("title")),
        "subtitle": _s(fill.get("subtitle")),
        "figure": _s(fill.get("figure")),
        "abbrev": _s(fill.get("abbrev")),
        "footnote": _s(fill.get("footnote")),
        "data_note": _s(fill.get("data_note")) or DEMO_NOTE,
        "source": _s(fill.get("source")) or STRUCT_NOTE,
        "page": _s(fill.get("page")),
        "refs": _refs(fill),
        "takeaways": _takeaways(fill.get("takeaways")),
        "rail_label": _s(fill.get("rail_label")) or "关键要点",
    }


# --------------------------------------------------------------------------- 1 trial design

def trial_geometry(fill: dict, width: float = MAIN_W_FULL) -> dict[str, Any]:
    tps = sorted(
        ({"week": _f(t["week"]), "label": _s(t.get("label")), "tag": _s(t.get("tag"))}
         for t in fill.get("timepoints") or []),
        key=lambda t: t["week"],
    )
    weeks = [t["week"] for t in tps]
    x0, x1 = 64.0, width - 70.0
    gaps = [b - a for a, b in zip(weeks, weeks[1:])]
    total = sum(gaps) or 1.0
    weights = [max(g, 0.22 * total) for g in gaps]
    wsum = sum(weights)
    xs = [x0]
    for w in weights:
        xs.append(xs[-1] + w / wsum * (x1 - x0))

    def xw(week: float) -> float:
        if week <= weeks[0]:
            return xs[0]
        for i in range(len(weeks) - 1):
            a, b = weeks[i], weeks[i + 1]
            if a <= week <= b:
                return xs[i] + (week - a) / (b - a) * (xs[i + 1] - xs[i])
        return xs[-1]

    axis_y = 62.0
    for t, x in zip(tps, xs):
        t["x"] = round(x, 1)
    phases = []
    for p in fill.get("phases") or []:
        a, b = xw(_f(p["from"])), xw(_f(p["to"]))
        phases.append({"label": _s(p.get("label")), "x0": round(a + 6, 1),
                       "x1": round(b - 6, 1), "cx": round((a + b) / 2, 1)})
    rand_week = _f((fill.get("randomisation") or {}).get("week", 0))
    end_week = _f(fill.get("treatment_end_week", weeks[-2] if len(weeks) > 2 else weeks[-1]))
    rx = xw(rand_week)
    arm_h, arm_gap, arm_top = 44.0, 16.0, 106.0
    arms = []
    raw_arms = fill.get("arms") or []
    ax0 = rx + 92
    ax1 = xw(end_week)
    for i, a in enumerate(raw_arms):
        y = arm_top + i * (arm_h + arm_gap)
        arms.append({
            "name": _s(a.get("name")), "detail": _s(a.get("detail")),
            "n": _s(a.get("n")), "role": _s(a.get("role")) or ("active" if i == 0 else "control"),
            "x": round(ax0, 1), "y": round(y, 1), "w": round(ax1 - ax0, 1), "h": arm_h,
            "cy": round(y + arm_h / 2, 1),
            "fu_x0": round(ax1, 1), "fu_x1": round(xs[-1], 1),
        })
    block_top = arm_top
    block_bot = arm_top + len(arms) * arm_h + max(len(arms) - 1, 0) * arm_gap
    r_h = min(block_bot - block_top, 76.0)
    r_box = {"x": round(rx - 46, 1), "y": round((block_top + block_bot - r_h) / 2, 1),
             "w": 92.0, "h": r_h, "cx": round(rx, 1), "cy": round((block_top + block_bot) / 2, 1)}
    elbow_x = round(r_box["x"] + r_box["w"] + (ax0 - r_box["x"] - r_box["w"]) / 2, 1)
    height = block_bot + 34
    screen = None
    if len(xs) > 1 and fill.get("screen_note"):
        lines = fill.get("screen_note")
        lines = lines if isinstance(lines, list) else [lines]
        screen = {"x": round((xs[0] + rx - 46) / 2 - 6, 1), "y": block_top + 8,
                  "lines": [_s(s) for s in lines]}
    return {
        "width": width, "height": round(height, 1), "axis_y": axis_y,
        "axis_x0": xs[0], "axis_x1": xs[-1],
        "timepoints": tps, "phases": phases, "arms": arms, "r_box": r_box,
        "elbow_x": elbow_x, "endpoint_x": round(ax1, 1), "screen": screen,
        "endpoint_label": _s(fill.get("endpoint_marker")) or "主要终点评估",
    }


def _trial(fill: dict) -> dict[str, Any]:
    rnd = fill.get("randomisation") or {}
    return {
        "design_label": _s(fill.get("design_label")),
        "population": _s(fill.get("population")),
        "rand_label": _s(rnd.get("label")) or "随机化",
        "rand_ratio": _s(rnd.get("ratio")) or "1:1",
        "rand_n": _s(rnd.get("n")),
        "inclusion": [_s(x) for x in fill.get("inclusion") or []],
        "endpoints": [{"tier": _s(e.get("tier")), "text": _s(e.get("text"))}
                      for e in fill.get("endpoints") or []],
        "geo": trial_geometry(fill),
    }


# --------------------------------------------------------------------------- 2 forest plot

def forest_geometry(fill: dict, width: float = MAIN_W_RAIL) -> dict[str, Any]:
    ax = fill.get("axis") or {}
    lo_v, hi_v = _f(ax.get("min", 0.25)), _f(ax.get("max", 2.0))
    ticks = [float(t) for t in ax.get("ticks") or [0.25, 0.5, 1, 2]]
    px0, px1 = 600.0, width - 20.0
    l0, l1 = math.log(lo_v), math.log(hi_v)

    def xv(v: float) -> float:
        v = min(max(v, lo_v), hi_v)
        return px0 + (math.log(v) - l0) / (l1 - l0) * (px1 - px0)

    rows_in = fill.get("rows") or []
    head_h = 40.0
    row_h = min(34.0, 404.0 / max(len(rows_in), 1))
    rows = []
    for i, r in enumerate(rows_in):
        y = head_h + i * row_h
        kind = "group" if _s(r.get("kind")) == "group" else ("overall" if r.get("overall") else "row")
        row = {"label": _s(r.get("label")), "kind": kind, "y": round(y, 1),
               "cy": round(y + row_h / 2, 1), "h": round(row_h, 1),
               "highlight": bool(r.get("highlight")), "zebra": i % 2 == 1}
        if kind != "group":
            est, lo, hi = _f(r["est"]), _f(r["lo"]), _f(r["hi"])
            row.update({
                "n_a": _s(r.get("n_a")), "n_c": _s(r.get("n_c")),
                "est_txt": fmt(est), "ci_txt": f"{fmt(lo)}–{fmt(hi)}",
                "xe": round(xv(est), 1), "xl": round(xv(lo), 1), "xh": round(xv(hi), 1),
                "clip_l": lo < lo_v, "clip_h": hi > hi_v,
            })
        rows.append(row)
    body_bot = head_h + len(rows_in) * row_h
    axis_y = body_bot + 6
    return {
        "width": width, "height": round(axis_y + 52, 1), "head_h": head_h,
        "rows": rows, "row_h": row_h, "axis_y": round(axis_y, 1),
        "px0": px0, "px1": px1, "x_ref": round(xv(1.0), 1),
        "ticks": [{"v": t, "x": round(xv(t), 1), "txt": (f"{t:g}")} for t in ticks],
        "cols": {"label": 8, "label_in": 24, "n_a": 318, "n_c": 392, "est": 456, "ci": 578},
    }


def _forest(fill: dict) -> dict[str, Any]:
    return {
        "effect_label": _s(fill.get("effect_label")) or "率比（95% CI）",
        "col_a": _s(fill.get("col_a")) or "研究药",
        "col_c": _s(fill.get("col_c")) or "对照",
        "est_head": _s(fill.get("est_head")) or "RR",
        "favours_left": _s(fill.get("favours_left")),
        "favours_right": _s(fill.get("favours_right")),
        "geo": forest_geometry(fill),
    }


# --------------------------------------------------------------------------- 3 endpoint readout

def _series(fill: dict) -> list[dict[str, Any]]:
    out = []
    for i, s in enumerate(fill.get("series") or []):
        out.append({
            "name": _s(s.get("name")), "role": _s(s.get("role")) or ("control" if i == 0 else "active"),
            "values": [_f(v) for v in s.get("values") or []],
            "lo": [_f(v) for v in s.get("lo") or s.get("values") or []],
            "hi": [_f(v) for v in s.get("hi") or s.get("values") or []],
            "n": [_s(v) for v in s.get("n") or []],
            "short": _s(s.get("short")) or _s(s.get("name")),
        })
    return out


def bar_geometry(fill: dict, width: float = MAIN_W_RAIL, height: float = 424.0) -> dict[str, Any]:
    cats = [_s(c) for c in fill.get("categories") or []]
    series = _series(fill)
    pl, pr, pt, pb = 76.0, width - 24.0, 18.0, height - 52.0
    vmax = max(max(s["hi"]) for s in series)
    ticks = nice_ticks(0, vmax * 1.3, 6)
    ymax = ticks[-1]

    def yv(v: float) -> float:
        return pb - v / ymax * (pb - pt)

    gw = (pr - pl) / max(len(cats), 1)
    ns = len(series)
    bw = min(92.0, gw * 0.56 / ns)
    gap = 14.0
    annots = fill.get("annotations") or []
    groups = []
    for ci, c in enumerate(cats):
        cx = pl + gw * (ci + 0.5)
        total = ns * bw + (ns - 1) * gap
        bars = []
        for si, s in enumerate(series):
            x = cx - total / 2 + si * (bw + gap)
            v = s["values"][ci]
            bars.append({
                "x": round(x, 1), "w": round(bw, 1), "y": round(yv(v), 1),
                "h": round(pb - yv(v), 1), "cx": round(x + bw / 2, 1),
                "ylo": round(yv(s["lo"][ci]), 1), "yhi": round(yv(s["hi"][ci]), 1),
                "label": fmt(v), "role": s["role"],
                "n": s["n"][ci] if ci < len(s["n"]) else "",
            })
        top = min(b["yhi"] for b in bars)
        ann = annots[ci] if ci < len(annots) else None
        groups.append({
            "label": c, "cx": round(cx, 1), "bars": bars,
            "bracket_y": round(top - 40, 1),
            "annot": _s(ann.get("text")) if isinstance(ann, dict) else _s(ann),
            "annot_sub": _s(ann.get("sub")) if isinstance(ann, dict) else "",
        })
    return {
        "kind": "bar", "width": width, "height": height,
        "pl": pl, "pr": pr, "pt": pt, "pb": pb,
        "ticks": [{"v": t, "y": round(yv(t), 1), "txt": f"{t:g}"} for t in ticks],
        "groups": groups, "series": series,
    }


def line_geometry(fill: dict, width: float = MAIN_W_RAIL, height: float = 340.0) -> dict[str, Any]:
    weeks = [_f(w) for w in fill.get("x") or []]
    series = _series(fill)
    pl, pr, pt, pb = 100.0, width - 24.0, 14.0, height - 40.0
    lo = min(min(s["lo"]) for s in series)
    hi = max(max(s["hi"]) for s in series)
    pad = (hi - lo) * 0.08
    ticks = nice_ticks(min(lo - pad, 0) if lo < 0 else 0, hi + pad, 6)
    y0, y1 = ticks[0], ticks[-1]
    xmax = weeks[-1] or 1.0

    xpad = 14.0  # keep week-0 markers off the y axis

    def xv(w: float) -> float:
        return pl + xpad + w / xmax * (pr - pl - xpad)

    def yv(v: float) -> float:
        return pb - (v - y0) / (y1 - y0) * (pb - pt)

    out = []
    off = [-4.0, 4.0, 0.0]
    for si, s in enumerate(series):
        pts = []
        for wi, w in enumerate(weeks):
            x = xv(w) + off[si % 3]
            pts.append({"x": round(x, 1), "y": round(yv(s["values"][wi]), 1),
                        "ylo": round(yv(s["lo"][wi]), 1), "yhi": round(yv(s["hi"][wi]), 1)})
        out.append({"name": s["name"], "role": s["role"], "pts": pts,
                    "path": " ".join(f"{'M' if i == 0 else 'L'}{p['x']},{p['y']}" for i, p in enumerate(pts)),
                    "n": s["n"]})
    n_top = height + 8
    n_rows = [{"name": s["short"], "role": s["role"], "y": round(n_top + 18 + 18 * si, 1),
               "cells": [{"x": round(xv(w), 1), "txt": s["n"][wi] if wi < len(s["n"]) else ""}
                         for wi, w in enumerate(weeks)]}
              for si, s in enumerate(series)]
    return {
        "kind": "line", "width": width, "height": round(n_top + 26 + 18 * len(series), 1),
        "plot_h": height, "n_top": n_top, "n_rows": n_rows,
        "pl": pl, "pr": pr, "pt": pt, "pb": pb, "y_zero": round(yv(0), 1),
        "ticks": [{"v": t, "y": round(yv(t), 1), "txt": f"{t:g}"} for t in ticks],
        "xticks": [{"v": w, "x": round(xv(w), 1), "txt": f"{w:g}"} for w in weeks],
        "series": out,
    }


def _endpoint(fill: dict, variant: str) -> dict[str, Any]:
    stats = fill.get("stats") or {}
    geo = line_geometry(fill) if variant == "line" else bar_geometry(fill)
    return {
        "chart_title": _s(fill.get("chart_title")),
        "y_label": _s(fill.get("y_label")),
        "x_label": _s(fill.get("x_label")),
        "stats": {"title": _s(stats.get("title")), "lines": [_s(x) for x in stats.get("lines") or []]},
        "geo": geo,
    }


# --------------------------------------------------------------------------- 4 MoA cascade

def moa_geometry(fill: dict, width: float = MAIN_W_RAIL) -> dict[str, Any]:
    stages = fill.get("stages") or []
    n = max(len(stages), 1)
    left_pad, gutter = 12.0, 30.0
    col_w = (width - left_pad - gutter * (n - 1)) / n
    head_h, item_h, item_gap, items_top = 40.0, 50.0, 10.0, 54.0
    cols, index = [], {}
    max_items = 0
    for ci, st in enumerate(stages):
        x = left_pad + ci * (col_w + gutter)
        items = []
        for ii, it in enumerate(st.get("items") or []):
            it = it if isinstance(it, dict) else {"label": it}
            y = items_top + ii * (item_h + item_gap)
            item = {"id": _s(it.get("id")) or f"s{ci}i{ii}", "label": _s(it.get("label")),
                    "sub": _s(it.get("sub")), "x": round(x, 1), "y": round(y, 1),
                    "w": round(col_w, 1), "h": item_h, "cy": round(y + item_h / 2, 1),
                    "target": False}
            index[item["id"]] = (ci, item)
            items.append(item)
        max_items = max(max_items, len(items))
        cols.append({"label": _s(st.get("label")), "num": ci + 1, "x": round(x, 1),
                     "w": round(col_w, 1), "items": items})
    items_bot = items_top + max_items * (item_h + item_gap) - item_gap
    arrows = []
    for ci in range(len(cols) - 1):
        a = cols[ci]["x"] + col_w
        arrows.append({"x0": round(a + 4, 1), "x1": round(a + gutter - 4, 1), "y": head_h / 2})
    # Callouts: stacked in a band below the item stacks, inside the target column;
    # connectors run in the target column's left gutter with nested lanes (no crossings).
    band_top = items_bot + 26
    co_h, co_gap = 44.0, 8.0
    by_col: dict[int, list] = {}
    for k, c in enumerate(fill.get("callouts") or []):
        tid = _s(c.get("target"))
        if tid not in index:
            continue
        ci, item = index[tid]
        item["target"] = True
        by_col.setdefault(ci, []).append({"key": _s(c.get("key")) or chr(65 + k),
                                          "label": _s(c.get("label")), "sub": _s(c.get("sub")),
                                          "item": item})
    callouts, max_stack = [], 0
    for ci, lst in by_col.items():
        lst.sort(key=lambda c: -c["item"]["cy"])  # lowest target first → inner lane
        max_stack = max(max_stack, len(lst))
        col = cols[ci]
        for k, c in enumerate(lst):
            y = band_top + k * (co_h + co_gap)
            lane_x = col["x"] - 7 - 6 * k
            cy = y + co_h / 2
            ty = c["item"]["cy"]
            path = (f"M{col['x']},{cy} L{lane_x},{cy} L{lane_x},{ty} "
                    f"L{col['x'] - 3},{ty}")
            callouts.append({
                "key": c["key"], "label": c["label"], "sub": c["sub"],
                "x": col["x"], "y": round(y, 1), "w": col["w"], "h": co_h,
                "path": path, "tbar_x": round(col["x"] - 3, 1), "tbar_y": ty,
                "target_label": c["item"]["label"],
            })
    band_bot = band_top + max_stack * (co_h + co_gap) - co_gap if max_stack else items_bot
    return {
        "width": width, "height": round(band_bot + 6, 1), "col_w": round(col_w, 1),
        "head_h": head_h, "cols": cols, "arrows": arrows, "callouts": callouts,
        "band_top": round(band_top, 1),
    }


def _moa(fill: dict) -> dict[str, Any]:
    return {"phenotype_note": _s(fill.get("phenotype_note")),
            "geo": moa_geometry(fill)}


# --------------------------------------------------------------------------- 5 data table

def _table(fill: dict) -> dict[str, Any]:
    cols = [{"label": _s(c.get("label")) if isinstance(c, dict) else _s(c),
             "sub": _s(c.get("sub")) if isinstance(c, dict) else ""}
            for c in fill.get("columns") or []]
    rows, z = [], 0
    for r in fill.get("rows") or []:
        kind = "group" if _s(r.get("kind")) == "group" else "row"
        if kind == "row":
            z += 1
        else:
            z = 0
        rows.append({"label": _s(r.get("label")), "kind": kind,
                     "cells": [_s(c) for c in r.get("cells") or []],
                     "highlight": bool(r.get("highlight")), "zebra": kind == "row" and z % 2 == 0,
                     "mark": _s(r.get("mark"))})
    # wording cells (a teaching table: target, dosing, indication) wrap and align left; numbers stay right-aligned
    text_cells = any(re.search(r"[一-鿿]", c) or len(c) > 14 for r in rows for c in r["cells"])
    return {"columns": cols, "rows": rows, "stub_head": _s(fill.get("stub_head")) or "特征",
            "footnotes": [_s(x) for x in fill.get("footnotes") or []], "text_cells": text_cells}


# --------------------------------------------------------------------------- 6 swimlane

def swimlane_geometry(fill: dict, width: float = MAIN_W_RAIL) -> dict[str, Any]:
    y0, y1 = _f(fill.get("year_start")), _f(fill.get("year_end"))
    tx0, tx1 = 178.0, width - 8.0
    axis_h = 30.0

    def xy(y: float) -> float:
        return tx0 + (y - y0) / (y1 - y0) * (tx1 - tx0)

    years = [{"y": int(y), "x": round(xy(y), 1), "cx": round(xy(y + 0.5), 1)}
             for y in range(int(y0), int(y1))]
    bar_h, bar_pitch, lane_pad = 20.0, 38.0, 6.0
    lanes, top = [], axis_h + 6
    for li, ln in enumerate(fill.get("lanes") or []):
        studies = ln.get("studies") or []
        h = lane_pad * 2 + bar_pitch * max(len(studies), 1) - (bar_pitch - bar_h - 14)
        bars = []
        for si, st in enumerate(studies):
            xs, xe = xy(_f(st["start"])), xy(_f(st["end"]))
            by = top + lane_pad + si * bar_pitch
            status = _s(st.get("status")) or "ongoing"
            res = _s(st.get("result"))
            mx = xe + 11
            res_w = text_w(res, 9)
            res_inline = mx + 10 + res_w <= width - 2
            bars.append({
                "name": _s(st.get("name")), "note": _s(st.get("note")), "status": status,
                "result": res, "x": round(xs, 1), "w": round(xe - xs, 1), "y": round(by, 1),
                "h": bar_h, "cy": round(by + bar_h / 2, 1), "xe": round(xe, 1),
                "mx": round(mx, 1), "res_inline": res_inline,
                "name_fits": text_w(_s(st.get("name")), 9.5) + 12 <= xe - xs,
            })
        lanes.append({"label": _s(ln.get("label")), "sub": _s(ln.get("sub")),
                      "focus": bool(ln.get("focus")), "y": round(top, 1), "h": round(h, 1),
                      "cy": round(top + h / 2, 1), "zebra": li % 2 == 1, "bars": bars})
        top += h
    today = fill.get("today")
    return {
        "width": width, "height": round(top + 4, 1), "axis_h": axis_h,
        "tx0": tx0, "tx1": tx1, "years": years, "lanes": lanes,
        "today_x": round(xy(_f(today)), 1) if today is not None else None,
        "today_label": _s(fill.get("today_label")),
    }


def _swimlane(fill: dict) -> dict[str, Any]:
    return {"geo": swimlane_geometry(fill), "legend": {
        "met": _s((fill.get("legend") or {}).get("met")) or "达到主要终点",
        "not_met": _s((fill.get("legend") or {}).get("not_met")) or "未达到主要终点",
        "ongoing": _s((fill.get("legend") or {}).get("ongoing")) or "进行中（预计读出）",
    }}


# --------------------------------------------------------------------------- evidence takeaways

def _evidence(fill: dict) -> dict[str, Any]:
    items = []
    for i, it in enumerate(fill.get("items") or []):
        refs = it.get("refs") or ([it["ref"]] if it.get("ref") else [])
        items.append({"value": _s(it.get("value")), "unit": _s(it.get("unit")),
                      "text": _s(it.get("text")), "refs": [_s(r) for r in refs],
                      "quote": _s(it.get("quote")), "loc": _s(it.get("loc")), "index": i + 1})
    return {"ev_items": items, "head_value": _s(fill.get("head_value")) or "数字",
            "head_text": _s(fill.get("head_text")) or "结论",
            "head_quote": _s(fill.get("head_quote")) or "逐字证据（源文档 · 页码）"}


# --------------------------------------------------------------------------- dispatch

def normalize(family: str, fill: dict, variant: str | None = None) -> dict[str, Any]:
    page = common(fill)
    if family == "trial_design":
        page.update(_trial(fill))
    elif family == "forest_plot":
        page.update(_forest(fill))
    elif family == "endpoint_readout":
        page.update(_endpoint(fill, variant or "bar"))
    elif family == "moa_cascade":
        page.update(_moa(fill))
    elif family == "data_table_highlight":
        page.update(_table(fill))
    elif family == "landscape_swimlane":
        page.update(_swimlane(fill))
    elif family == EVIDENCE_VARIANT:
        page.update(_evidence(fill))
    else:
        raise KeyError(family)
    return page


def validate(family: str, fill: dict, errors: list[str], warnings: list[str],
             variant: str | None = None) -> None:
    """Structural contract checks for chart-led families (data, not just text length)."""
    if not _s(fill.get("figure")):
        errors.append("figure：必填（图/表编号）")
    ref_ids = {r["id"] for r in _refs(fill)}

    def _check_refs(where: str, refs: list[str]) -> None:
        for r in refs:
            if r not in ref_ids:
                errors.append(f"{where}：证据号 {r} 未在 refs 中定义")

    if family == EVIDENCE_VARIANT:
        items = fill.get("items") or []
        if not 3 <= len(items) <= 4:
            errors.append(f"items：evidence_takeaways 需要 3–4 条，收到 {len(items)} 条")
        for i, it in enumerate(items):
            if not _has_digit(_s(it.get("value"))):
                errors.append(f"items[{i}].value：须以数字开头（数字化结论）")
            refs = it.get("refs") or ([it["ref"]] if it.get("ref") else [])
            if not refs:
                errors.append(f"items[{i}].refs：每条结论必须带证据号")
            _check_refs(f"items[{i}]", [_s(r) for r in refs])
            if not _s(it.get("quote")) or not _s(it.get("loc")):
                errors.append(f"items[{i}]：须给出逐字摘录 quote 与源位置 loc")
        return

    tks = _takeaways(fill.get("takeaways"))
    if family == "data_table_highlight" and not tks:
        pass                                      # no rail: the table takes the full body width
    elif not 3 <= len(tks) <= 4:
        errors.append(f"takeaways：需要 3–4 条数字化要点，收到 {len(tks)} 条")
    for i, t in enumerate(tks):
        if not _has_digit(t["value"]):
            errors.append(f"takeaways[{i}].value：须为数字（number-led）")
        if len(t["text"]) > 56:
            errors.append(f"takeaways[{i}].text：{len(t['text'])} 字超过容量 56")
        _check_refs(f"takeaways[{i}]", t["refs"])

    try:
        if family == "trial_design":
            tps = fill.get("timepoints") or []
            if len(tps) < 3:
                errors.append("timepoints：至少 3 个时间点")
            arms = fill.get("arms") or []
            if not 2 <= len(arms) <= 3:
                errors.append("arms：需要 2–3 个治疗臂")
            if len(fill.get("inclusion") or []) > 6:
                errors.append("inclusion：容量 6 条")
            if len(fill.get("endpoints") or []) > 5:
                errors.append("endpoints：容量 5 条")
        elif family == "forest_plot":
            rows = fill.get("rows") or []
            if not rows or len(rows) > 13:
                errors.append(f"rows：1–13 行，收到 {len(rows)} 行")
            ax = fill.get("axis") or {}
            amin, amax = _f(ax.get("min", 0.25)), _f(ax.get("max", 2))
            if not 0 < amin < 1 < amax:
                errors.append("axis：对数轴须满足 0 < min < 1 < max")
            hl = 0
            for i, r in enumerate(rows):
                if _s(r.get("kind")) == "group":
                    continue
                est, lo, hi = _f(r["est"]), _f(r["lo"]), _f(r["hi"])
                if not (0 < lo <= est <= hi):
                    errors.append(f"rows[{i}]：须满足 0 < lo ≤ est ≤ hi")
                hl += bool(r.get("highlight"))
            if hl > 1:
                errors.append("rows：最多高亮 1 行")
        elif family == "endpoint_readout":
            series = fill.get("series") or []
            if not 2 <= len(series) <= 3:
                errors.append("series：需要 2–3 组")
            n = len(fill.get("x") or []) if variant == "line" else len(fill.get("categories") or [])
            if n == 0:
                errors.append("x/categories：必填")
            for i, s in enumerate(series):
                vals = s.get("values") or []
                if len(vals) != n:
                    errors.append(f"series[{i}].values：长度 {len(vals)} ≠ {n}")
                for k, (v, lo, hi) in enumerate(zip(vals, s.get("lo") or vals, s.get("hi") or vals)):
                    if not (_f(lo) <= _f(v) <= _f(hi)):
                        errors.append(f"series[{i}][{k}]：须满足 lo ≤ value ≤ hi")
            if variant == "line":
                xs = [_f(x) for x in fill.get("x") or []]
                if xs != sorted(xs):
                    errors.append("x：时间点须递增")
            if not (fill.get("stats") or {}).get("lines"):
                errors.append("stats：须提供统计框（差值 / 95% CI / P）")
        elif family == "moa_cascade":
            stages = fill.get("stages") or []
            if not 3 <= len(stages) <= 6:
                errors.append("stages：3–6 个阶段")
            ids = set()
            for ci, st in enumerate(stages):
                its = st.get("items") or []
                if len(its) > 4:
                    errors.append(f"stages[{ci}].items：容量 4")
                for ii, it in enumerate(its):
                    ids.add(_s((it if isinstance(it, dict) else {}).get("id")) or f"s{ci}i{ii}")
            for k, c in enumerate(fill.get("callouts") or []):
                if _s(c.get("target")) not in ids:
                    errors.append(f"callouts[{k}].target：{c.get('target')} 不存在")
            per = {}
            for c in fill.get("callouts") or []:
                per[_s(c.get("target"))[:2]] = per.get(_s(c.get("target"))[:2], 0) + 1
        elif family == "data_table_highlight":
            cols = fill.get("columns") or []
            rows = fill.get("rows") or []
            body = [r for r in rows if _s(r.get("kind")) != "group"]
            if not 3 <= len(rows) <= 18:
                errors.append(f"rows：需要 3–18 行，收到 {len(rows)} 行")
            if not 1 <= len(cols) <= 4:
                errors.append("columns：1–4 个数据列")
            for i, r in enumerate(body):
                if len(r.get("cells") or []) != len(cols):
                    errors.append(f"rows[{r.get('label')}]：单元格数 ≠ 列数 {len(cols)}")
            if sum(bool(r.get("highlight")) for r in rows) > 1:
                errors.append("rows：至多高亮 1 行")
        elif family == "landscape_swimlane":
            y0, y1 = _f(fill.get("year_start")), _f(fill.get("year_end"))
            if y1 <= y0:
                errors.append("year_end 须大于 year_start")
            lanes = fill.get("lanes") or []
            if not 2 <= len(lanes) <= 6:
                errors.append("lanes：2–6 条泳道")
            for li, ln in enumerate(lanes):
                for si, st in enumerate(ln.get("studies") or []):
                    a, b = _f(st["start"]), _f(st["end"])
                    if not (y0 <= a < b <= y1):
                        errors.append(f"lanes[{li}].studies[{si}]：时间须在轴范围内且 start < end")
                    if _s(st.get("status")) not in _STATUS:
                        errors.append(f"lanes[{li}].studies[{si}].status：须为 {'/'.join(_STATUS)}")
                if len(ln.get("studies") or []) > 3:
                    errors.append(f"lanes[{li}]：每泳道最多 3 项研究")
    except (KeyError, TypeError, ValueError) as e:  # missing / non-numeric data
        errors.append(f"数据字段缺失或非数值：{e}")
