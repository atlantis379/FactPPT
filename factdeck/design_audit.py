"""The design rules a page has to pass, borrowed from the PPT skill's ``design-principle.md``.

That document states its rules as numbers (smallest type on the page, how many type styles a page may use, how far
apart two levels have to be, where the footer sits).  Numbers can be read off a rendered page, so the rules stop
being advice and become a gate: the same Playwright pass that already catches overflow measures type as well, and a
page that breaks a rule is reported before anything is written to PowerPoint.

What is kept here is only the mechanically checkable part.  "Data must land on a judgement", "no equal-column
grids", "no AI-flavoured titles" stay out: they are judgements about content, not measurements.
"""
from __future__ import annotations

# (role, minimum px, rule text) — thresholds from design-principle.md §1.6
MIN_PX = {
    "title": 32,
    "figure": 48,        # an anchor number is by definition large; anything smaller is not an anchor
    "label": 16,         # card headings and chart labels
    "body": 18,
    "note": 14,          # footnote / source / page number
    "kicker": 14,
    "unit": 14,          # a unit is sized relative to its number, so only the floor applies
    "take": 16,
}

MAX_STYLES = 4           # §1.6: distinct (size, weight) combinations on one page
SOFT_MAX_STYLES = 5      # a page built on one big number needs label + body beside it; reported, not refused
MIN_STEP_PX = 4          # §1.6: adjacent levels differ by at least 4px
MIN_LINE_HEIGHT = 1.2    # §1.7
FOOTER_TOP = 670         # §1.1: the footer band starts at y=670 on a 720-high canvas
FOOTER_TOLERANCE = 3
CONTENT_BOTTOM = 660     # §1.1: the content area ends here; the footer band is 670-700
MIN_FILL = 0.5           # §1.3: below this the page is too thin to stand on its own

DESIGN_JS = """(index) => {
  const slide = document.querySelectorAll('.slide')[index || 0];
  if (!slide) return null;
  const S = slide.getBoundingClientRect();
  const ROLE = [
    ['.htitle', 'title'], ['.stat-num', 'figure'], ['.th-unit', 'unit'], ['.th-val', 'figure'],
    ['.take', 'take'], ['.kicker', 'kicker'],
    ['.points li b', 'label'], ['.points li', 'body'], ['.col p', 'body'], ['.step p', 'body'],
    ['.th-ind', 'label'], ['.th-ends', 'label'], ['.col .lb', 'label'], ['.step .lb', 'label'],
    ['.stat-label', 'label'], ['.col .n', 'label'], ['.step .dot', 'label'],
    ['.foot', 'note'], ['.stat-src', 'note'], ['.th-src', 'note'],
  ];
  const roleOf = (el) => {
    for (const [sel, role] of ROLE) {
      const hit = el.closest(sel);
      if (hit && slide.contains(hit)) return role;
    }
    return 'body';
  };
  const out = [];
  const seen = new Set();
  for (const el of slide.querySelectorAll('*')) {
    if (el.closest('svg, style, script')) continue;
    // the element that owns the visible text: no element child carries text of its own
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own || seen.has(el)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    seen.add(el);
    out.push({
      role: roleOf(el),
      text: el.textContent.trim().slice(0, 24),
      size: parseFloat(cs.fontSize),
      weight: parseInt(cs.fontWeight) >= 600 ? 'bold' : 'normal',
      lineHeight: parseFloat(cs.lineHeight) / parseFloat(cs.fontSize),
      inMain: !!el.closest('.main'),
      top: Math.round(r.top - S.top),
      bottom: Math.round(r.bottom - S.top),
    });
  }
  const foot = slide.querySelector('.foot');
  const main = slide.querySelector('.main');
  return {
    ink: out,
    footerTop: foot ? Math.round(foot.getBoundingClientRect().top - S.top) : null,
    contentTop: main ? Math.min(...[...main.querySelectorAll('*')]
      .map((e) => e.getBoundingClientRect().top - S.top).concat([1e9])) : null,
    // the lowest point of anything above the footer: how much of the 600px content area is actually used
    contentBottom: main ? Math.max(...[...main.querySelectorAll('*')]
      .map((e) => e.getBoundingClientRect().bottom - S.top).concat([0])) : null,
  };
}"""


def audit(measured: dict) -> list[dict]:
    """Every rule the page breaks, with the numbers that broke it. Empty means the page may be drawn."""
    if not measured:
        return [{"rule": "measure", "detail": "页面没有量到任何文字"}]
    bad: list[dict] = []
    ink = measured["ink"]

    for t in ink:
        floor = MIN_PX.get(t["role"])
        if floor and t["size"] < floor - 0.6:
            bad.append({"rule": "min-size", "detail":
                        f'{t["role"]}「{t["text"]}」只有 {t["size"]:.1f}px，下限 {floor}px'})
        # A single-line figure is set solid on purpose (line-height 1); the rule is about paragraphs, where a
        # tight leading collides with ascenders and descenders.
        if t["role"] not in ("figure", "unit") and t["lineHeight"] and t["lineHeight"] < MIN_LINE_HEIGHT - 0.02:
            bad.append({"rule": "line-height", "detail":
                        f'「{t["text"]}」行高 {t["lineHeight"]:.2f}，下限 {MIN_LINE_HEIGHT}'})

    # A unit is part of its number, not a level of its own (§1.6), so it does not spend one of the four styles.
    styles = sorted({(round(t["size"], 1), t["weight"]) for t in ink if t["role"] != "unit"}, reverse=True)
    if len(styles) > SOFT_MAX_STYLES:
        bad.append({"level": "warn", "rule": "type-styles", "detail":
                    f"本页有 {len(styles)} 种字号/字重组合（上限 {MAX_STYLES}）："
                    + "、".join(f"{s}px/{w}" for s, w in styles)})
    elif len(styles) > MAX_STYLES:
        bad.append({"level": "warn", "rule": "type-styles", "detail":
                    f"本页有 {len(styles)} 种字号/字重组合，超出上限 {MAX_STYLES} 一种："
                    + "、".join(f"{s}px/{w}" for s, w in styles)})

    # §1.6 asks neighbouring *levels* to differ by 4px.  The small-print tier is exempt: the same table sets
    # chart labels at 16px and footnotes at 14px, so a 2px gap there is the rule's own arrangement, not a break.
    levels = sorted({round(t["size"], 1) for t in ink if t["size"] >= 18}, reverse=True)
    for a, b in zip(levels, levels[1:]):
        if 0 < a - b < MIN_STEP_PX:
            bad.append({"rule": "type-step", "detail": f"{a}px 与 {b}px 只差 {a - b:.1f}px，相邻层级需 ≥{MIN_STEP_PX}px"})

    body_ink = [t for t in ink if t.get("inMain")] or ink
    top = min((t["top"] for t in body_ink), default=None)
    bottom = max((t["bottom"] for t in body_ink), default=None)
    if bottom is not None and bottom > CONTENT_BOTTOM:
        bad.append({"rule": "content-height", "detail":
                    f"内容最低点 y={bottom:.0f}，越过内容区底线 {CONTENT_BOTTOM}（会压到页脚）"})

    # §1.3: a content page has to carry its area.  Measured as how much of the band between the title and the
    # footer the content actually spans — a page whose content floats in the middle with voids above and below
    # is a page with too little material, and the fix is to merge it, not to stretch it.
    if top is not None and bottom is not None:
        span = (bottom - top) / float(CONTENT_BOTTOM - 172)
        if span < MIN_FILL:
            bad.append({"level": "warn", "rule": "content-fill", "detail":
                        f"内容只占内容区高度的 {span:.0%}（下限 {MIN_FILL:.0%}）：这页材料撑不满，考虑合并或补内容"})

    if measured.get("footerTop") is not None and abs(measured["footerTop"] - FOOTER_TOP) > FOOTER_TOLERANCE:
        bad.append({"rule": "footer", "detail": f'页脚顶边在 y={measured["footerTop"]}，应固定为 {FOOTER_TOP}'})
    return bad
