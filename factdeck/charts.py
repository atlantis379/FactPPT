"""Bar charts drawn by code from facts.

A chart never carries a number of its own. Each bar's value label *is* a fact
(shown verbatim), and the bar length is computed by code from the number inside
that fact's text — the author cannot type a value. Rules:

* each value fact contains exactly one plain number (no comparison operator, no
  range, no negative sign); all bars use the same unit;
* the scale starts at zero and ends at a rounded ceiling above the largest value,
  so bar lengths are proportional to the values;
* no axis tick numbers are drawn (they would be numbers without a source);
* values taken from different sources are allowed but flagged, because putting
  them side by side suggests they are comparable — the semantic review decides.

The same geometry is recomputed after rendering and compared with the drawn bars.
"""
from __future__ import annotations

import math
import re

from .lexicon import canon, _num_re

ORIENTATIONS = ("vertical", "horizontal")
BARS = (2, 8)


class ChartError(ValueError):
    pass


def chart_value(text: str) -> tuple[float, str]:
    """(number, unit) from a fact's display text, or ChartError with the reason."""
    t = canon(text)
    found = [m for m in _num_re().finditer(t) if m.group(2)]
    if len(found) != 1:
        raise ChartError(f"需恰好含一个数字（现有 {len(found)} 个）")
    m = found[0]
    op, a, sep, b, unit = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5) or ""
    if op:
        raise ChartError("含比较符号的数值不能画成柱")
    if sep and b:
        raise ChartError("区间数值不能画成柱")
    if m.start() > 0 and t[m.start() - 1] in "-−":
        raise ChartError("数字前有负号或连字符（负数或编号），不能画成柱")
    if "," in a and not re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", a):
        raise ChartError("数字格式不明确")
    return float(a.replace(",", "")), unit.lower()


def nice_max(v: float) -> float:
    """Rounded ceiling (1/1.2/1.5/2/2.5/3/4/5/6/8 × 10^k) at or above v."""
    if v <= 0:
        return 1.0
    base = 10.0 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * base + 1e-9:
            return m * base
    return 10.0 * base


def model(chart: dict, facts: dict[str, dict]) -> dict:
    """Values, unit and scale for a chart spec; raises ChartError."""
    bars = chart.get("bars") or []
    values, units, sources = [], set(), set()
    for i, b in enumerate(bars, 1):
        f = facts[b["value"]["fact"]]
        try:
            v, u = chart_value(f["display"] or f["quote"])
        except ChartError as e:
            raise ChartError(f"第{i}根柱的数值 {f['id']}：{e}") from None
        values.append(v)
        units.add(u)
        sources.add(f.get("source_id"))
    if len(units) > 1:
        raise ChartError("各柱单位不一致：" + "、".join(sorted(u or "（无单位）" for u in units)))
    top = nice_max(max(values))
    return {"values": values, "unit": units.pop() if units else "", "max": top,
            "ratios": [v / top for v in values], "sources": sorted(s for s in sources if s)}


def geometry(chart: dict, m: dict, width: float, height: float) -> dict:
    """Pixel boxes for bars, value labels and category labels inside a width × height area."""
    n = len(m["values"])
    horizontal = chart.get("orientation") == "horizontal"
    bars = []
    if horizontal:
        label_w, value_w, gap = 230, 120, 14
        plot = width - label_w - gap - value_w
        slot = height / n
        bh = min(46, slot * 0.62)
        for i, r in enumerate(m["ratios"]):
            y = i * slot + (slot - bh) / 2
            L = r * plot
            bars.append({"bar": (label_w + gap, y, L, bh), "value": (label_w + gap + L + 10, y, value_w - 10, bh),
                         "label": (0, y - 8, label_w, bh + 16), "length": L})
        base = (label_w + gap - 2, 0, 2, height)
    else:
        label_h, value_h = 58, 34
        plot = height - label_h - value_h - 10
        slot = width / n
        bw = min(118, slot * 0.56)
        for i, r in enumerate(m["ratios"]):
            x = i * slot + (slot - bw) / 2
            L = r * plot
            top = value_h + (plot - L)
            bars.append({"bar": (x, top, bw, L), "value": (i * slot, top - value_h, slot, value_h - 4),
                         "label": (i * slot + 4, value_h + plot + 10, slot - 8, label_h), "length": L})
        base = (0, value_h + plot, width, 2)
    rnd = lambda box: [round(v, 2) for v in box]
    return {"horizontal": horizontal, "plot": round(plot, 2), "baseline": rnd(base),
            "bars": [{k: (rnd(v) if isinstance(v, tuple) else round(v, 2)) for k, v in b.items()} for b in bars]}


def structure_errors(chart) -> list[str]:
    if not isinstance(chart, dict):
        return ["chart 需为对象"]
    errors = []
    if chart.get("orientation", "vertical") not in ORIENTATIONS:
        errors.append("orientation 需为 vertical 或 horizontal")
    bars = chart.get("bars")
    if not (isinstance(bars, list) and BARS[0] <= len(bars) <= BARS[1]):
        errors.append(f"bars 数量需为 {BARS[0]}–{BARS[1]}")
        return errors
    for i, b in enumerate(bars, 1):
        if not (isinstance(b, dict) and b.get("label") and isinstance(b.get("value"), dict) and set(b["value"]) == {"fact"}):
            errors.append(f"第{i}根柱需有 label，value 须为单纯的事实引用 {{\"fact\": id}}")
    return errors
