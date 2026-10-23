"""Explanatory figures drawn on a composed page (page key `diagram`).

A figure here carries no content of its own: every drawn element is geometry that encodes a
relation the page's own facts state, and every label is a fact reference. What the picture
adds over the sentences is the shape of the relation — where a threshold falls on one scale,
where a course runs over time — which prose states only one word at a time.

Both builders return ordinary composed blocks (line / surface / marker / text), so the page
still passes the same export path: native shapes, native text, native connectors.

  bands   an ordered value axis cut into segments (a grading scale, a threshold), with the
          segments' names and cut-offs as the page's own facts;
  curve   one or more drawn courses on a numeric plane (a volume–time trace).
"""
from __future__ import annotations

from .recipes import line_h, text_px

LINE_H = 1.55
SURFACE_TONES = ("tint", "white", "line", "strong", "accent")


def _tone(t: str) -> str:
    if t not in SURFACE_TONES:
        raise ValueError(f"图的色块 tone 需为 {'、'.join(SURFACE_TONES)} 之一：{t}")
    return t


def _text(x, y, w, h, ref, role="sub", size=13, align="left", tone=None, one=True, valign=None):
    b = {"kind": "text", "refs": [ref], "x": round(x, 1), "y": round(y, 1), "w": round(w, 1),
         "h": round(h, 1), "role": role, "size": size, "align": align}
    if one:
        b["one"] = True
    if tone:
        b["tone"] = tone
    if valign:
        b["valign"] = valign
    return b


def _surface(x, y, w, h, tone, radius=0):
    return {"kind": "surface", "tone": _tone(tone), "x": round(x, 1), "y": round(y, 1),
            "w": round(w, 1), "h": round(h, 1), "radius": radius}


def _line(pts, tone="line", width=1, dash=False, encodes=None):
    """A drawn line: an axis or grid line (no `encodes`), or a course that draws the listed facts."""
    b = {"kind": "line", "points": [[round(x, 1), round(y, 1)] for x, y in pts],
         "tone": tone, "width": width, "dash": dash}
    if encodes:
        b["encodes"] = list(encodes)
    else:
        b["axis"] = True
    return b


def _marker(x, y, d, tone):
    return {"kind": "marker", "tone": _tone(tone), "round": True, "x": round(x - d / 2, 1),
            "y": round(y - d / 2, 1), "w": d, "h": d}


def _text_height(text: str, size: int, width: float) -> int:
    return max(1, round(text_px(text, size) / max(width - 4, 1) + 0.5)) * line_h(size) + 4


# ---------------------------------------------------------------- bands
def bands(spec: dict, texts: dict) -> list[dict]:
    """An ordered value axis cut into segments. `segments` give their upper bound (`to`) on the
    axis range; the last one ends at range[1]. Each segment names its `head` (the level) and
    `label` (the cut-off as the source words it), both facts on this page."""
    x0, y0, w, h = spec["box"]
    lo, hi = spec["range"]
    segs = spec["segments"]
    if hi <= lo or len(segs) < 2:
        raise ValueError("bands：range 须递增，segments 至少两段")
    bounds = [lo] + [s["to"] for s in segs]
    if any(b <= a for a, b in zip(bounds, bounds[1:])) or segs[-1]["to"] != hi:
        raise ValueError("bands：各段 to 须严格递增，末段等于 range 上界")
    head_h = line_h(14) + 2
    label_size = 13
    label_h = line_h(label_size) + 4
    inside = spec.get("label_pos", "below") == "inside"
    bar_h = max(30, h - head_h - (0 if inside else label_h + 4) - 2)
    gap = 4
    out = []
    total = hi - lo
    for i, s in enumerate(segs):
        a, b = bounds[i], bounds[i + 1]
        sx = x0 + (a - lo) / total * w
        ex = x0 + (b - lo) / total * w
        cw = max(ex - sx - gap, 12)
        out.append(_surface(sx, y0 + head_h, cw, bar_h, s.get("tone", "tint"), radius=2))
        if s.get("head"):
            out.append(_text(sx, y0, cw, head_h, s["head"], role="sub", size=14, align="center", tone="primary"))
        if s.get("label"):
            if inside:
                out.append(_text(sx + 6, y0 + head_h, cw - 12, bar_h, s["label"], role="note",
                                 size=label_size, align="center", valign="middle"))
            else:
                out.append(_text(sx, y0 + head_h + bar_h + 4, cw, label_h, s["label"], role="note",
                                 size=label_size, align="center"))
    return out


# ---------------------------------------------------------------- curve
def _map(pt, xr, yr, box):
    x0, y0, w, h = box
    px = x0 + (pt[0] - xr[0]) / (xr[1] - xr[0]) * w
    py = y0 + h - (pt[1] - yr[0]) / (yr[1] - yr[0]) * h
    return round(px, 1), round(py, 1)


def curve(spec: dict, texts: dict) -> list[dict]:
    """A drawn course on a numeric plane: `series` are polylines in data coordinates, `marks`
    sit on the plane, `labels` are facts pinned at a data point."""
    box = spec["box"]
    xr, yr = spec["xr"], spec["yr"]
    if xr[1] <= xr[0] or yr[1] <= yr[0]:
        raise ValueError("curve：xr / yr 须递增")
    x0, y0, w, h = box
    out = []
    axes = spec.get("axes") or {}
    if axes.get("x"):
        out.append(_line([(x0, y0 + h), (x0 + w, y0 + h)], tone="line", width=1.2))
    if axes.get("y"):
        out.append(_line([(x0, y0), (x0, y0 + h)], tone="line", width=1.2))
    for gx in spec.get("grid") or []:
        gxp, _ = _map((gx, yr[0]), xr, yr, box)
        out.append(_line([(gxp, y0), (gxp, y0 + h)], tone="line", width=0.75, dash=True))
    for m in spec.get("marks") or []:
        px, py = _map(m["at"], xr, yr, box)
        out.append(_marker(px, py, m.get("d", 9), m.get("tone", "accent")))
    for s in spec["series"]:
        if not s.get("encodes"):
            raise ValueError("curve：每条 series 须以 encodes 列出它画出的事实")
        pts = [_map(p, xr, yr, box) for p in s["pts"]]
        for a, b in zip(pts, pts[1:]):
            out.append(_line([a, b], tone=s.get("tone", "primary2"), width=s.get("width", 2.2), encodes=s["encodes"]))
    for lb in spec.get("labels") or []:
        px, py = _map(lb["at"], xr, yr, box)
        lw = lb.get("w", 90)
        lh = _text_height(texts.get(lb["ref"]["fact"], ""), lb.get("size", 13), lw)
        align = lb.get("align", "left")
        lx = px + lb.get("dx", 0) if align != "center" else px - lw / 2
        ly = py + lb.get("dy", 0)
        out.append(_text(lx, ly, lw, lh, lb["ref"], role="note", size=lb.get("size", 13), align=align,
                         tone=lb.get("tone")))
    return out


BUILDERS = {"bands": bands, "curve": curve}


def build(spec: dict, texts: dict) -> list[dict]:
    kind = spec.get("kind")
    if kind not in BUILDERS:
        raise ValueError(f"图的 kind 需为 {'、'.join(BUILDERS)} 之一：{kind}")
    return BUILDERS[kind](spec, texts)
