"""Render a ``presentation.v1`` spec to HTML (one .slide per page), then to native PPTX via the template writer.

The model's decisions arrive as structure + which sentence leads + which number carries the page.  Everything a
reader sees as substance is the sentence's own words (``presentation.check`` resolved them).  Geometry is code's
job and stays parametric: the number of points decides column widths, the length of a line decides its font step.

Kept deliberately close to the template-library pipeline so the same machinery applies: Playwright measures the
page (overflow fails the page, it is never clipped), and ``template_lib.native`` writes real text boxes, tables and
shapes — no whole-slide bitmap, no embedded SVG.
"""
from __future__ import annotations

import html
import re
from jinja2 import Template

from .template_lib.themes import get_theme

W, H = 1280, 720
PAD = 64
FONT = '"Noto Sans CJK SC","Noto Sans SC","Source Han Sans SC","PingFang SC","Microsoft YaHei",sans-serif'

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{margin:0;background:#E4E8ED;font-family:__FONT__;-webkit-font-smoothing:antialiased}
.slide{position:relative;width:1280px;height:720px;overflow:hidden;background:__CANVAS__;color:__INK__}
.kicker{position:absolute;left:__PAD__px;top:38px;font-size:11pt;font-weight:700;letter-spacing:.16em;
  text-transform:uppercase;color:__ACCENT__}
.rule{position:absolute;left:__PAD__px;top:62px;width:56px;height:3px;background:__ACCENT__}
.htitle{position:absolute;left:__PAD__px;top:78px;width:__CONTENTW__px;font-size:30pt;font-weight:700;
  line-height:1.22;letter-spacing:-.01em;color:__HEADLINE__}
.main{position:absolute;left:__PAD__px;top:172px;width:__CONTENTW__px;height:430px}
.take{position:absolute;left:__PAD__px;top:622px;width:__CONTENTW__px;height:52px;background:__TAKEBG__;
  border-left:4px solid __ACCENT__;padding:0 18px;display:flex;align-items:center;font-size:14pt;
  color:__HEADLINE__;overflow:hidden}
.foot{position:absolute;left:__PAD__px;top:686px;width:__CONTENTW__px;height:22px;font-size:9pt;color:__CAPTION__}
.foot .row{float:left;width:820px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.foot .pg{float:right;font-variant-numeric:tabular-nums}

/* stat — one number carries the page */
.stat-num{font-size:104pt;font-weight:700;line-height:1;letter-spacing:-.03em;color:__PRIMARY__}
.stat-label{font-size:15pt;font-weight:600;color:__HEADLINE__;margin-top:14px;line-height:1.35}
.stat-src{font-size:9.5pt;color:__CAPTION__;margin-top:10px}
.points{list-style:none}
.points li b{display:block;color:__HEADLINE__;font-weight:700;margin-bottom:3px}
.points li{position:relative;padding-left:24px;font-size:19pt;line-height:1.55;color:__INK__;margin-bottom:26px}
.points li::before{content:"";position:absolute;left:0;top:12px;width:8px;height:8px;background:__ACCENT__;
  border-radius:50%}
.cols{display:grid;gap:40px}
.col{min-width:0}
.col .hd{font-size:12pt;font-weight:700;letter-spacing:.1em;color:__ACCENT__;text-transform:uppercase;
  padding-bottom:8px;border-bottom:1px solid __LINE__;margin-bottom:16px}
.col .lb{font-weight:700;color:__HEADLINE__;line-height:1.35;margin-top:6px}
.col .n{font-size:11pt;font-weight:700;color:__ACCENT__;font-variant-numeric:tabular-nums;margin-bottom:2px}
.cols .col:not(:last-child){margin-bottom:34px}
.col p{font-size:inherit;line-height:1.55;color:__INK__;margin-top:5px}
.steps{display:grid;gap:22px;align-items:start;position:relative}
.steps::before{content:"";position:absolute;left:0;right:0;top:19px;height:1px;background:__LINE__}
.step{position:relative;min-width:0}
.step .dot{width:38px;height:38px;border-radius:50%;background:__PRIMARY__;color:#fff;font-size:13pt;font-weight:700;
  display:flex;align-items:center;justify-content:center;position:relative;z-index:1}
.step .lb{margin-top:14px;font-weight:700;color:__HEADLINE__;line-height:1.35}
.step p{margin-top:6px;font-size:15pt;line-height:1.45;color:__INK__}
.step .tag{margin-top:8px;font-size:10pt;color:__CAPTION__}

/* threshold — one gauge per indicator.  The track is a solid band split in two at the boundary, the half the
   sentence talks about filled in the accent and the other held back to a light tint, so the split is a shape
   rather than a number with a line under it.  No scale is implied: the band has no ticks, only a division. */
.ths{display:grid;height:100%}
.th{display:grid;grid-template-columns:var(--idw) 1fr;grid-template-areas:"ind ." "val track" ". ends" ". src";
  column-gap:48px;row-gap:4px;align-content:center;min-width:0}
.th-ind{grid-area:ind;font-size:11.5pt;font-weight:700;letter-spacing:.1em;color:__ACCENT2__;line-height:1.3}
.th-val{grid-area:val;align-self:center;font-weight:700;line-height:1;letter-spacing:-.03em;color:__PRIMARY__;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.th-track{grid-area:track;position:relative;display:flex;align-self:center}
.th-half{flex:0 0 50%}
.th-half.hi{background:__ACCENT__}
.th-half.lo{background:__SOFT__}
.th-rule{position:absolute;left:50%;top:-7px;bottom:-7px;width:4px;margin-left:-2px;background:__PRIMARY__}
.th-ends{grid-area:ends;display:flex;justify-content:space-between;gap:24px;margin-top:8px;font-size:10.5pt;
  line-height:1.2;color:__CAPTION__;font-variant-numeric:tabular-nums}
.th-ends .hold{color:__PRIMARY__;font-weight:700}
.th-src{grid-area:src;margin-top:5px;font-size:10pt;line-height:1.4;color:__CAPTION__}
"""

_TMPL = Template("""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<style>{{ CSS }}</style>
<body><div class="slide" data-page="{{ PAGE }}">
  {% if section %}<div class="kicker">{{ section }}</div><div class="rule"></div>{% endif %}
  {% if headline %}<h1 class="htitle">{{ headline }}</h1>{% endif %}
  <div class="main">{{ main|safe }}</div>
  {% if takeaway %}<div class="take">{{ takeaway }}</div>{% endif %}
  <div class="foot"><div class="row">{{ source }}</div><div class="pg">{{ page }} / {{ total }}</div></div>
</div></body></html>""")


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


# PDF extraction leaves a space between characters it could not join ("呼吸困难视 觉 模拟评分").  It is an artefact
# of the extraction, not of the sentence, so it is removed where text is drawn — the words stay the same words.
_CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")


def _txt(s: str) -> str:
    return _CJK_GAP.sub("", s or "")


def _css(theme: str) -> str:
    t = get_theme(theme)
    rep = {"__FONT__": FONT, "__CANVAS__": t["canvas"], "__INK__": t["ink"], "__PAD__": str(PAD),
           "__CONTENTW__": str(W - 2 * PAD), "__ACCENT__": t["accent"], "__ACCENT2__": t["accent2"],
           "__SOFT__": t["soft"], "__HEADLINE__": t["headline"],
           "__PRIMARY__": t["primary"], "__CAPTION__": t["caption"], "__TAKEBG__": t["takeaway-bg"],
           "__LINE__": t["line"]}
    css = _CSS
    for k, v in rep.items():
        css = css.replace(k, v)
    return css


def _body_stat(p) -> str:
    lead = p["lead"]
    pts = "".join(f"<li><b>{_esc(i['label'])}</b>{_esc(_txt(i['quote']))}</li>" for i in p["items"])
    src = ""
    if lead.get("page_id"):
        src = f"<div class=\"stat-src\">{_esc(str(lead.get('source_id') or ''))} · {_esc(str(lead['page_id']))}</div>"
    return (f'<div style="display:grid;grid-template-columns:440px 1fr;gap:56px;height:100%;align-items:center">'
            f'<div><div class="stat-num">{_esc(lead["value"])}</div>'
            f'<div class="stat-label">{_esc(lead["label"])}</div>{src}</div>'
            f'<ul class="points" data-check="fit">{pts}</ul></div>')


def _body_points(p) -> str:
    """Points of equal weight: a single column when there are three or fewer, so each one gets room to breathe."""
    n = len(p["items"])
    cols = 1 if n <= 3 else (2 if n <= 4 else 3)
    rows = -(-n // cols)
    cells = "".join(f'<div class="col" data-check="fit"><div class="n">{k + 1:02d}</div>'
                    f'<div class="lb">{_esc(i["label"])}</div>'
                    f'<p>{_esc(_txt(i["quote"]))}</p></div>' for k, i in enumerate(p["items"]))
    size = "20pt" if cols == 1 else ("18pt" if cols == 2 else "16pt")
    return (f'<div class="cols" style="grid-template-columns:repeat({cols},1fr);'
            f'height:100%;align-content:safe center;font-size:{size}">{cells}</div>')


def _body_compare(p) -> str:
    items = p["items"]
    half = (len(items) + 1) // 2
    sides = (items[:half], items[half:])
    labels = p.get("labels") or ["", ""]

    def side(name: str, rows, offset: int) -> str:
        lis = "".join(f'<p data-check="fit"><span class="n">{offset + k + 1:02d}</span>　'
                      f'<b>{_esc(r["label"])}</b>{_esc(_txt(r["quote"]))}</p>' for k, r in enumerate(rows))
        hd = f'<div class="hd">{_esc(name)}</div>' if name else ""
        return f'<div class="col">{hd}{lis}</div>'
    return (f'<div class="cols" style="grid-template-columns:1fr 1fr;height:100%;align-content:safe center">'
            f'{side(labels[0], sides[0], 0)}{side(labels[1], sides[1], len(sides[0]))}</div>')


def _body_steps(p) -> str:
    n = len(p["items"])
    cells = "".join(f'<div class="step" data-check="fit"><div class="dot">{k + 1}</div>'
                    f'<div class="lb">{_esc(i["label"])}</div>'
                    f'<p>{_esc(_txt(i["quote"]))}</p></div>' for k, i in enumerate(p["items"]))
    return f'<div class="steps" style="grid-template-columns:repeat({n},1fr)">{cells}</div>'


_BODIES = {"stat": _body_stat, "points": _body_points, "compare": _body_compare, "steps": _body_steps}

# A page whose point is a figure names a form; the form picks the body.  One gauge gets the whole page, so its
# number is near-full size and its band is tall; four gauges share the height, so each shrinks.  The number shrinks
# with the row so the band below it keeps enough width to be read as a division rather than a rule.
_TH_GEOM = {1: (96, 104, 300), 2: (64, 68, 300), 3: (44, 52, 300), 4: (32, 38, 280)}


def _th_row(t: dict, size: int, band_h: int) -> str:
    """One gauge: what it measures, the boundary value, the two sides it divides, and the sentence it came from.

    Above the boundary means "on the side the sentence describes" for ≥ and >; for ≤ and < that side is below it,
    so the filled half and the two end labels swap.  Whatever the direction, the labels only restate the boundary
    as the two sides it divides — no number appears that the sentence does not contain.
    """
    floor = t["op"] in (">", "≥")
    halves = ('<div class="th-half lo"></div><div class="th-half hi"></div>' if floor else
              '<div class="th-half hi"></div><div class="th-half lo"></div>')
    left, right = (t["other"], t["holds"]) if floor else (t["holds"], t["other"])
    lcls, rcls = ("" if floor else "hold"), ("hold" if floor else "")
    return (f'<div class="th" data-check="fit">'
            f'<div class="th-ind">{_esc(t["indicator"])}</div>'
            f'<div class="th-val" style="font-size:{size}pt">{_esc(t["token"])}</div>'
            f'<div class="th-track" style="height:{band_h}px">{halves}<div class="th-rule"></div></div>'
            f'<div class="th-ends"><span class="{lcls}">{_esc(left)}</span>'
            f'<span class="{rcls}">{_esc(right)}</span></div>'
            f'<div class="th-src">{_esc(_txt(t["clause"]))}</div></div>')


def _body_threshold(p) -> str:
    """The gauges are the page: one row per boundary, the rows sharing the height between title and footer."""
    rows = p["thresholds"]
    size, band_h, idw = _TH_GEOM[len(rows)]
    cells = "".join(_th_row(t, size, band_h) for t in rows)
    return (f'<div class="ths" style="grid-template-rows:repeat({len(rows)},1fr);--idw:{idw}px">'
            f'{cells}</div>')


_FIGURES = {"threshold": _body_threshold}


def render_page(page: dict, *, page_no: int, total: int, source: str, theme: str = "gold_clinical",
                section: str | None = None) -> str:
    """One resolved presentation page → one HTML document. Content is the sentences' own words."""
    take = page.get("takeaway")
    form = page.get("form") or "text"
    body = _FIGURES[form] if form in _FIGURES else _BODIES[page["structure"]]
    return _TMPL.render(
        CSS=_css(theme), PAGE=page_no, section=section, headline=page.get("headline"),
        main=body(page), takeaway=_esc(_txt(take["quote"])) if take else "",
        source=_esc(source), page=page_no, total=total,
    )


def render_deck(pages: list[dict], *, source: str, theme: str = "gold_clinical",
                sections: list[str | None] | None = None) -> str:
    """Concatenate pages into one document (each page is its own .slide, so one measure pass can read them all)."""
    return "".join(
        render_page(p, page_no=i + 1, total=len(pages), source=source, theme=theme,
                    section=(sections[i] if sections else p.get("section")))
        for i, p in enumerate(pages))
