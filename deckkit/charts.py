# -*- coding: utf-8 -*-
"""
Chart geometry engine.

One deterministic computation drives BOTH the HTML/SVG chart and the PPTX chart,
so the two outputs cannot drift. Every primitive carries its declared value in a
data attribute, which lets `chart_geometry.py` re-derive the drawing from the
deck JSON and compare it against what was actually rendered.

Policy (enforced, not assumed):
  * bar charts must declare an explicit `baseline` (zero-baseline policy)
  * a null / missing value is NEVER drawn as zero — the point is skipped and
    recorded in `missing`
  * y-axis ceiling is a deterministic "nice" number, recorded so the validator
    can recompute the same transform
"""
import math

TICK_COUNT = 4


def nice_max(v):
    """Deterministic ceiling: 1/1.2/1.5/2/2.5/3/4/5/6/8 x 10^k."""
    if v is None or v <= 0:
        return 1.0
    exp = math.floor(math.log10(v))
    base = 10.0 ** exp
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * base + 1e-9:
            return m * base
    return 10.0 * base


def nice_step(span, target=TICK_COUNT):
    """Round tick step from 1/2/2.5/5/10 x 10^k, so axis labels read as whole
    numbers instead of 3.75 / 11.25 style artefacts."""
    if span <= 0:
        return 1.0
    raw = span / max(1, target)
    exp = math.floor(math.log10(raw))
    base = 10.0 ** exp
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * base + 1e-9:
            return m * base
    return 10.0 * base


def nice_axis(vmin, vmax, target=TICK_COUNT):
    """Deterministic rounded axis: (lo, hi, step)."""
    if vmax <= vmin:
        vmax = vmin + 1.0
    step = nice_step(vmax - vmin, target)
    lo = math.floor(vmin / step) * step
    hi = math.ceil(vmax / step) * step
    if hi <= lo:
        hi = lo + step
    return lo, hi, step


def spec_errors(chart):
    """Structural / policy problems that block a chart from being drawn."""
    errs = []
    cats = chart.get("categories") or []
    series = chart.get("series") or []
    if not cats:
        errs.append("no categories")
    if not series:
        errs.append("no series")
    for si, s in enumerate(series):
        vals = s.get("values") or []
        if len(vals) != len(cats):
            errs.append(f"series[{si}] has {len(vals)} values for {len(cats)} categories")
        for v in vals:
            if v is not None and not isinstance(v, (int, float)):
                errs.append(f"series[{si}] non-numeric value {v!r}")
    if (chart.get("kind") or "bar") == "bar" and "baseline" not in chart:
        errs.append("bar chart must declare an explicit baseline (zero-baseline policy)")
    return errs


def _numeric(chart):
    out = []
    for s in chart.get("series") or []:
        for v in s.get("values") or []:
            if isinstance(v, (int, float)):
                out.append(float(v))
    return out


def compute(chart, plot):
    """plot = {'x','y','w','h'} in px. Returns the full drawing description."""
    x0, y0, pw, ph = plot["x"], plot["y"], plot["w"], plot["h"]
    cats = chart.get("categories") or []
    series = chart.get("series") or []
    kind = (chart.get("kind") or "bar").lower()
    baseline = float(chart.get("baseline", 0))

    nums = _numeric(chart)
    vmin_data = min([baseline] + nums) if nums else baseline
    vmax_data = max(nums) if nums else baseline + 1
    if chart.get("y_max"):
        y_max = float(chart["y_max"])
        y_min = math.floor(vmin_data / nice_step(y_max - vmin_data)) * nice_step(y_max - vmin_data)
        step = nice_step(y_max - y_min)
    else:
        y_min, y_max, step = nice_axis(vmin_data, vmax_data)
    if y_max <= y_min:
        y_max = y_min + 1.0

    def fy(v):
        return y0 + ph - (float(v) - y_min) / (y_max - y_min) * ph

    n = max(1, len(cats))
    slot = pw / n
    ns = max(1, len(series))
    bars, points, missing = [], [], []

    if kind == "line":
        for si, s in enumerate(series):
            pts = []
            for ci, v in enumerate(s.get("values") or []):
                if v is None:
                    missing.append({"series": si, "cat": ci})
                    continue
                cx = x0 + slot * (ci + 0.5)
                cy = fy(v)
                pts.append({"series": si, "cat": ci, "value": float(v), "x": cx, "y": cy})
            points.append(pts)
    else:  # bar / bar-grouped
        inner = slot * 0.68
        bw = inner / ns
        for si, s in enumerate(series):
            for ci, v in enumerate(s.get("values") or []):
                if v is None:
                    missing.append({"series": si, "cat": ci})
                    continue
                bx = x0 + slot * ci + (slot - inner) / 2 + bw * si
                yv, yb = fy(v), fy(baseline)
                top, hgt = min(yv, yb), abs(yb - yv)
                bars.append({"series": si, "cat": ci, "value": float(v),
                             "x": bx, "y": top, "w": bw, "h": hgt,
                             "baseline": baseline})

    ticks = []
    steps = int(round((y_max - y_min) / step)) if step else TICK_COUNT
    steps = max(1, min(steps, 10))
    for i in range(steps + 1):
        v = round(y_min + step * i, 10)          # kill float noise (0.6000000000001)
        ticks.append({"value": v, "y": fy(v)})

    return {
        "kind": kind, "plot": dict(plot), "categories": cats,
        "series_names": [s.get("name", f"系列{i+1}") for i, s in enumerate(series)],
        "units": [s.get("unit", "") for s in series],
        "y_min": y_min, "y_max": y_max, "baseline": baseline,
        "bars": bars, "points": points, "missing": missing, "ticks": ticks,
        "slot": slot,
    }


def _tick_label(v, step):
    """Decimals follow the tick step: 5 -> '5', 0.2 -> '0.2', 0.05 -> '0.05'."""
    if step >= 1:
        return f"{v:.0f}"
    if step >= 0.1:
        return f"{v:.1f}"
    if step >= 0.01:
        return f"{v:.2f}"
    return f"{v:.3f}"


# --------------------------------------------------------------------- SVG
def svg(chart, plot, colors):
    """Render the chart as an SVG whose primitives expose their declared value."""
    g = compute(chart, plot)
    x0, y0, pw, ph = g["plot"]["x"], g["plot"]["y"], g["plot"]["w"], g["plot"]["h"]
    pal = [colors.get("accent"), colors.get("primary"), colors.get("ok"),
           colors.get("warn"), colors.get("danger")]
    out = [f'<svg class="chart" viewBox="0 0 {plot["vw"]} {plot["vh"]}" '
           f'xmlns="http://www.w3.org/2000/svg" data-chart="{g["kind"]}" '
           f'data-baseline="{g["baseline"]}" data-ymin="{g["y_min"]:.6f}" '
           f'data-ymax="{g["y_max"]:.6f}">']

    # grid + y ticks
    for t in g["ticks"]:
        out.append(f'<line x1="{x0:.2f}" y1="{t["y"]:.2f}" x2="{x0+pw:.2f}" y2="{t["y"]:.2f}" '
                   f'stroke="{colors.get("line")}" stroke-width="1" '
                   f'data-role="gridline" data-value="{t["value"]:.6f}"/>')
        lab = _tick_label(t["value"], g.get("step", 1.0))
        out.append(f'<text x="{x0-12:.2f}" y="{t["y"]+4:.2f}" text-anchor="end" '
                   f'font-size="12" fill="{colors.get("muted")}" '
                   f'data-role="ytick" data-value="{t["value"]:.6f}">{lab}</text>')

    # baseline emphasis
    by = [t for t in g["ticks"] if abs(t["value"] - g["baseline"]) < 1e-9]
    out.append(f'<line x1="{x0:.2f}" y1="{g["plot"]["y"]+ph - (g["baseline"]-g["y_min"])/(g["y_max"]-g["y_min"])*ph:.2f}" '
               f'x2="{x0+pw:.2f}" y2="{g["plot"]["y"]+ph - (g["baseline"]-g["y_min"])/(g["y_max"]-g["y_min"])*ph:.2f}" '
               f'stroke="{colors.get("ink2")}" stroke-width="2" data-role="baseline" '
               f'data-value="{g["baseline"]:.6f}"/>')

    # categories
    for ci, c in enumerate(g["categories"]):
        cx = x0 + g["slot"] * (ci + 0.5)
        out.append(f'<text x="{cx:.2f}" y="{y0+ph+24:.2f}" text-anchor="middle" '
                   f'font-size="13" fill="{colors.get("ink2")}" data-role="cat">{_esc(c)}</text>')

    # marks
    if g["kind"] == "line":
        for si, pts in enumerate(g["points"]):
            if len(pts) > 1:
                d = " ".join(f'{p["x"]:.2f},{p["y"]:.2f}' for p in pts)
                out.append(f'<polyline points="{d}" fill="none" stroke="{pal[si%len(pal)]}" '
                           f'stroke-width="3" data-role="line" data-series="{si}"/>')
            for p in pts:
                out.append(f'<circle cx="{p["x"]:.2f}" cy="{p["y"]:.2f}" r="5" '
                           f'fill="{pal[si%len(pal)]}" data-role="point" data-series="{p["series"]}" '
                           f'data-cat="{p["cat"]}" data-value="{p["value"]:.6f}"/>')
                out.append(f'<text x="{p["x"]:.2f}" y="{p["y"]-12:.2f}" text-anchor="middle" '
                           f'font-size="12" fill="{colors.get("ink2")}" data-role="vlabel" '
                           f'data-series="{p["series"]}" data-cat="{p["cat"]}">{p["value"]:g}</text>')
    else:
        for b in g["bars"]:
            out.append(f'<rect x="{b["x"]:.2f}" y="{b["y"]:.2f}" width="{b["w"]:.2f}" '
                       f'height="{b["h"]:.2f}" rx="3" fill="{pal[b["series"]%len(pal)]}" '
                       f'data-role="bar" data-series="{b["series"]}" data-cat="{b["cat"]}" '
                       f'data-value="{b["value"]:.6f}" data-baseline="{b["baseline"]:.6f}"/>')
            out.append(f'<text x="{b["x"]+b["w"]/2:.2f}" y="{b["y"]-7:.2f}" text-anchor="middle" '
                       f'font-size="12" fill="{colors.get("ink2")}" data-role="vlabel" '
                       f'data-series="{b["series"]}" data-cat="{b["cat"]}">{b["value"]:g}</text>')

    # legend
    if len(g["series_names"]) > 1:
        lx = x0
        for si, name in enumerate(g["series_names"]):
            out.append(f'<rect x="{lx:.2f}" y="{y0-26:.2f}" width="12" height="12" rx="2" '
                       f'fill="{pal[si%len(pal)]}" data-role="legend"/>')
            out.append(f'<text x="{lx+18:.2f}" y="{y0-16:.2f}" font-size="13" '
                       f'fill="{colors.get("ink2")}" data-role="legend-label">{_esc(name)}</text>')
            lx += 34 + 14 * len(name)
    out.append("</svg>")
    return "".join(out)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
