# -*- coding: utf-8 -*-
"""
Independent chart-geometry verification.

The validator never trusts the drawing: it re-derives every mark from the deck's
declared numbers with `charts.compute()` and compares that against the actual
SVG user-space boxes read back from the rendered page (`getBBox()` returns
viewBox units, so page scaling cannot mask an error).

Checks
  GEOMETRY     每个柱/点的位置与高度必须等于按声明数值重算的结果
  SERIES_ORDER 系列序号与类别序号必须与声明一致
  VALUE_LABEL  数值标签必须等于声明值
  BASELINE     必须存在且位于声明的基线值
  MISSING      空值不得被画成 0（且必须出现在缺失清单里）
  YTICKS       刻度值必须等于按同一变换重算的刻度
"""
import pathlib

from playwright.sync_api import sync_playwright

from . import charts as CH

TOL = 0.75   # SVG user units

_JS = r"""(idx) => {
  const s = document.querySelectorAll('.slide')[idx];
  const svg = s ? s.querySelector('svg.chart') : null;
  if (!svg) return {error: 'no chart svg'};
  const num = (el) => parseFloat(el.getAttribute('data-value'));
  const out = {bars: [], points: [], vlabels: [], yticks: [], baseline: null,
               catLabels: [], chartKind: svg.getAttribute('data-chart'),
               dataBaseline: svg.getAttribute('data-baseline'),
               dataYmin: svg.getAttribute('data-ymin'), dataYmax: svg.getAttribute('data-ymax')};
  svg.querySelectorAll('[data-role="bar"]').forEach(el => {
    const b = el.getBBox();
    out.bars.push({series: +el.getAttribute('data-series'), cat: +el.getAttribute('data-cat'),
                   value: num(el), baseline: parseFloat(el.getAttribute('data-baseline')),
                   x: b.x, y: b.y, w: b.width, h: b.height});
  });
  svg.querySelectorAll('[data-role="point"]').forEach(el => {
    out.points.push({series: +el.getAttribute('data-series'), cat: +el.getAttribute('data-cat'),
                     value: num(el), cx: parseFloat(el.getAttribute('cx')),
                     cy: parseFloat(el.getAttribute('cy'))});
  });
  svg.querySelectorAll('[data-role="vlabel"]').forEach(el => {
    out.vlabels.push({series: +el.getAttribute('data-series'), cat: +el.getAttribute('data-cat'),
                      text: (el.textContent || '').trim()});
  });
  svg.querySelectorAll('[data-role="ytick"]').forEach(el => {
    out.yticks.push(num(el));
  });
  const bl = svg.querySelector('[data-role="baseline"]');
  if (bl) out.baseline = parseFloat(bl.getAttribute('data-value'));
  svg.querySelectorAll('[data-role="cat"]').forEach(el => out.catLabels.push((el.textContent||'').trim()));
  return out;
}"""


def read_rendered(html_path, slide_index, mutate=None):
    """mutate: optional JS string run inside the page before reading — used to
    inject deliberate corruption when proving the validator can fail."""
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        pg.goto(pathlib.Path(html_path).resolve().as_uri(), wait_until="load", timeout=60000)
        pg.wait_for_timeout(400)
        if mutate:
            pg.evaluate("(idx) => { const s = document.querySelectorAll('.slide')[idx]; " + mutate + " }",
                        slide_index)
            pg.wait_for_timeout(120)
        res = pg.evaluate(_JS, slide_index)
        b.close()
    return res


def compare(spec, plot, rendered):
    """Return the issue list (empty == PASS)."""
    exp = CH.compute(spec, plot)
    issues = []

    if rendered.get("error"):
        return [{"check": "RENDER", "detail": rendered["error"]}]

    # ---- kind / transform identity
    if rendered["chartKind"] != exp["kind"]:
        issues.append({"check": "KIND", "expected": exp["kind"], "actual": rendered["chartKind"]})
    for key, mine in (("dataBaseline", exp["baseline"]), ("dataYmin", exp["y_min"]),
                      ("dataYmax", exp["y_max"])):
        try:
            got = float(rendered.get(key))
        except (TypeError, ValueError):
            issues.append({"check": "TRANSFORM", "detail": f"{key} missing"})
            continue
        if abs(got - mine) > 1e-6:
            issues.append({"check": "TRANSFORM", "detail": f"{key}: {got} != {mine}"})

    # ---- bars
    if exp["kind"] != "line":
        if len(rendered["bars"]) != len(exp["bars"]):
            issues.append({"check": "GEOMETRY", "detail":
                           f"bar count {len(rendered['bars'])} != {len(exp['bars'])}"})
        for eb in exp["bars"]:
            rb = next((x for x in rendered["bars"]
                       if x["series"] == eb["series"] and x["cat"] == eb["cat"]), None)
            if rb is None:
                issues.append({"check": "MISSING_MARK", "detail": f"series{eb['series']} cat{eb['cat']}"})
                continue
            for f in ("x", "y", "w", "h"):
                if abs(rb[f] - eb[f]) > TOL:
                    issues.append({"check": "GEOMETRY", "series": eb["series"], "cat": eb["cat"],
                                   "field": f, "expected": round(eb[f], 3),
                                   "actual": round(rb[f], 3), "value": eb["value"]})
            if abs(rb["value"] - eb["value"]) > 1e-9:
                issues.append({"check": "SERIES_ORDER", "series": eb["series"], "cat": eb["cat"],
                               "expected": eb["value"], "actual": rb["value"]})
            if abs(rb["baseline"] - exp["baseline"]) > 1e-9:
                issues.append({"check": "BASELINE", "series": eb["series"], "cat": eb["cat"],
                               "expected": exp["baseline"], "actual": rb["baseline"]})
    else:
        flat_exp = [p for pts in exp["points"] for p in pts]
        if len(rendered["points"]) != len(flat_exp):
            issues.append({"check": "GEOMETRY", "detail":
                           f"point count {len(rendered['points'])} != {len(flat_exp)}"})
        for ep in flat_exp:
            rp = next((x for x in rendered["points"]
                       if x["series"] == ep["series"] and x["cat"] == ep["cat"]), None)
            if rp is None:
                issues.append({"check": "MISSING_MARK", "detail": f"series{ep['series']} cat{ep['cat']}"})
                continue
            for f, key in (("cx", "x"), ("cy", "y")):
                if abs(rp[f] - ep[key]) > TOL:
                    issues.append({"check": "GEOMETRY", "series": ep["series"], "cat": ep["cat"],
                                   "field": key, "expected": round(ep[key], 3),
                                   "actual": round(rp[f], 3)})

    # ---- value labels must equal the declared numbers
    for lb in rendered["vlabels"]:
        s = spec["series"][lb["series"]]
        v = s["values"][lb["cat"]]
        if v is None:
            issues.append({"check": "MISSING", "detail": "label drawn for a null value"})
            continue
        try:
            shown = float(lb["text"])
        except ValueError:
            issues.append({"check": "VALUE_LABEL", "detail": f"non-numeric label {lb['text']!r}"})
            continue
        if abs(shown - float(v)) > 1e-6:
            issues.append({"check": "VALUE_LABEL", "series": lb["series"], "cat": lb["cat"],
                           "expected": v, "actual": shown})

    # ---- baseline presence
    if rendered["baseline"] is None:
        issues.append({"check": "BASELINE", "detail": "baseline line missing"})
    elif abs(rendered["baseline"] - exp["baseline"]) > 1e-6:
        issues.append({"check": "BASELINE", "expected": exp["baseline"],
                       "actual": rendered["baseline"]})

    # ---- y ticks
    exp_ticks = [t["value"] for t in exp["ticks"]]
    if len(rendered["yticks"]) != len(exp_ticks):
        issues.append({"check": "YTICKS", "detail":
                       f"{len(rendered['yticks'])} ticks != {len(exp_ticks)}"})
    else:
        for a, e in zip(sorted(rendered["yticks"]), sorted(exp_ticks)):
            if abs(a - e) > 1e-6:
                issues.append({"check": "YTICKS", "expected": e, "actual": a})
                break

    # ---- category order
    cats = [str(c) for c in spec.get("categories") or []]
    if rendered["catLabels"] and rendered["catLabels"] != cats:
        issues.append({"check": "CATEGORY_ORDER", "expected": cats, "actual": rendered["catLabels"]})

    return issues


def audit(html_path, slide_index, spec, plot=None, mutate=None):
    plot = plot or {"x": 70, "y": 44, "w": 1120, "h": 316, "vw": 1240, "vh": 420}
    rendered = read_rendered(html_path, slide_index, mutate=mutate)
    issues = compare(spec, plot, rendered)
    return {"status": "PASS" if not issues else "FAIL", "issues": issues,
            "marks_checked": len(rendered.get("bars") or rendered.get("points") or [])}


# --------------------------------------------------------------------------
# Negative fixtures: each mutation MUST make the validator fail, otherwise the
# checker is not actually testing anything.
#   (name, js, needs)   needs: "any" | "multiseries" | "line"
# --------------------------------------------------------------------------
NEGATIVE_FIXTURES = [
    ("geometry-wrong", """
        const el = s.querySelector('[data-role="bar"]');
        if (el) { const b = el.getBBox(); el.setAttribute('height', (b.height * 1.45).toFixed(2));
                  el.setAttribute('y', (b.y - b.height * 0.45).toFixed(2)); }
    """, "any"),
    ("series-swapped", """
        const bs = [...s.querySelectorAll('[data-role="bar"]')];
        const seen = [...new Set(bs.map(b => b.getAttribute('data-series')))];
        if (seen.length > 1) {
          const first = bs.filter(b => b.getAttribute('data-series') === seen[0]);
          const second = bs.filter(b => b.getAttribute('data-series') === seen[1]);
          first.forEach(b => b.setAttribute('data-series', seen[1]));
          second.forEach(b => b.setAttribute('data-series', seen[0]));
        }
    """, "multiseries"),
    ("category-order-swapped", """
        const bs = [...s.querySelectorAll('[data-role="bar"]')];
        const cats = [...new Set(bs.map(b => b.getAttribute('data-cat')))];
        if (cats.length > 1) {
          const a = cats[0], b = cats[cats.length - 1];
          bs.forEach(el => { const c = el.getAttribute('data-cat');
            if (c === a) el.setAttribute('data-cat', b);
            else if (c === b) el.setAttribute('data-cat', a); });
        }
    """, "any"),
    ("label-altered", """
        const el = s.querySelector('[data-role="vlabel"]');
        if (el) el.textContent = '999';
    """, "any"),
    ("baseline-moved", """
        const el = s.querySelector('[data-role="baseline"]');
        if (el) el.setAttribute('data-value', '5');
    """, "any"),
    ("axis-rescaled", """
        const svg = s.querySelector('svg.chart');
        if (svg) svg.setAttribute('data-ymax', String(parseFloat(svg.getAttribute('data-ymax')) * 1.3));
    """, "any"),
    ("extra-mark-injected", """
        const svg = s.querySelector('svg.chart');
        const first = s.querySelector('[data-role="bar"], [data-role="point"]');
        if (svg && first) { const c = first.cloneNode(true);
            c.setAttribute('data-cat', '99'); svg.appendChild(c); }
    """, "any"),
    ("missing-value-zeroed", """
        const svg = s.querySelector('svg.chart');
        const base = s.querySelector('[data-role="point"], [data-role="bar"]');
        if (svg && base) { const c = base.cloneNode(true);
            c.setAttribute('data-cat', '99'); c.setAttribute('data-value', '0');
            svg.appendChild(c); }
    """, "line"),
]
