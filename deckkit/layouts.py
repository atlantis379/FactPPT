# -*- coding: utf-8 -*-
"""
Slide archetypes. Each builder takes a slide dict + deck meta and returns a
complete `<section class="slide">`. No builder contains a literal colour:
everything resolves through CSS variables, so any theme works.
"""
import re
from . import motifs

# canvas geometry (must match css.py)
STRIP_TOP = 168
DOCK_TOP = 570

_BR = re.compile(r"<br\s*/?>", re.I)


def _esc(s):
    """HTML-escape, but allow <br> as an intentional line break."""
    s = _BR.sub("\n", str(s))
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s.replace("\n", "<br/>")


def _esc_rich(text):
    """Escape, but keep the <b> emphasis the page contract allows."""
    out = _esc(text)
    return out.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")


def chip(label):
    if not label:
        return ""
    return f'<div class="chip">{_esc(label)}</div>'


def page_chrome(s, meta, n, with_title=True):
    """Header chrome shared by every teaching page.

    The section chip is the page's ``section_label``; the source line prefers an
    explicit ``source_ref`` so a page can say which textbook page it came from and
    whether it is 原文 or 整理 (the reference deck distinguishes the two).
    """
    label = s.get("section_label") or ""
    sub = s.get("subtitle")
    ref = s.get("source_ref")
    if isinstance(ref, dict):
        page = ref.get("page")
        kind = ref.get("kind", "")
    else:
        page, kind = ref, ""
    if page and not sub:
        sub = f"教材第 {page} 页" + (f"（{kind}）" if kind else "")
    parts = [brand(meta, label), pnum(n)]
    if with_title:
        parts.append(tblock(s.get("title"), sub))
    return "".join(parts)


def keypoint_bar(s):
    """The bottom emphasis bar. Absent keypoint -> no bar (safe to call anywhere)."""
    keypoint = s.get("keypoint")
    if not keypoint:
        return ""
    tone = s.get("keypoint_tone") or "info"
    if isinstance(keypoint, dict):
        tone = keypoint.get("tone", tone)
        text = keypoint.get("text", "")
    else:
        text = str(keypoint)
    if not text:
        return ""
    icon = motifs.get("shield")
    return (f'<div class="kpbar {tone}"><div class="kpi-icon">{icon}</div>'
            f'<div class="kptxt">{_esc_rich(text)}</div></div>')


def brand(meta, label=""):
    # A page that carries a section chip must not also print the brand tagline:
    # both sit in the top-right and they overlapped. The chip is the more useful
    # of the two on a teaching page, so it wins.
    right = "" if label else _esc(meta.get("tagline", ""))
    return (f'<div class="brand"><div class="bl">{_esc(meta.get("brand", ""))}</div>'
            f'<div class="br">{right}</div>{chip(label)}</div>')


def pnum(n):
    return f'<div class="pnum">{n:02d}</div>'


def tblock(title, sub):
    s = f'<div class="sub">{_esc(sub)}</div>' if sub else ""
    return f'<div class="tblock"><h1>{_esc(title)}</h1>{s}</div>'


def foot(meta, src_page, n):
    label = _esc(meta.get("source_label", "Source"))
    name = _esc(meta.get("source", ""))
    left = f"<span><b>{label}:</b> {name}" + (f" p.{src_page}" if src_page else "") + "</span>"
    right = _esc(meta.get("footer_right", ""))
    return f'<div class="foot">{left}<span>{right}</span></div>'


def fig(motif=None, cls="", w=None, h=None):
    svg = motifs.get(motif) if motif else motifs.auto(0)
    style = ""
    if w and h:
        style = f' style="width:{w}px;height:{h}px;"'
    return f'<div class="fig {cls}"{style}>{svg}</div>'


def callout(label, text):
    if not text:
        return ""
    lab = f"<b>{_esc(label)}</b>｜" if label else ""
    return (f'<div class="callout"><div class="ci">{motifs.get("shield")}</div>'
            f'<div class="ct">{lab}{_esc(text)}</div></div>')


def source_page(slide):
    return slide.get("source_page")


# ---------------------------------------------------------------- archetypes
def cover(s, meta, n):
    kick = _esc(s.get("kicker") or meta.get("kicker", ""))
    sub = _esc(s.get("subtitle", ""))
    body = _esc(s.get("body", ""))
    lines = s.get("meta_lines") or [meta.get("author", ""), meta.get("org", "")]
    meta_html = "<br/>".join(_esc(x) for x in lines if x)
    hero = motifs.get(s.get("motif", "layers"))
    body_html = f'<div class="hbody">{body}</div>' if body else ""
    return f'''<section class="slide" id="s{n}">
  <div class="hero">
    <div class="hbg">{hero}</div><div class="hveil"></div>
    <div class="inner">
      <div class="kick">{kick}</div>
      <h1>{_esc(s.get("title", ""))}</h1>
      <div class="rule"></div>
      <div class="sub">{sub}</div>
      {body_html}
      <div class="meta">{meta_html}</div>
    </div>
  </div>
</section>'''


def closing(s, meta, n):
    return cover({**s, "kicker": s.get("kicker", "SUMMARY"), "motif": s.get("motif", "check")},
                 meta, n).replace('class="slide"', 'class="slide" data-kind="closing"')


def statement(s, meta, n):
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="stmt">
    <div class="sk">{_esc(s.get("kicker", "KEY POINT"))}</div>
    <div class="sb">{_esc(s.get("body", ""))}</div>
  </div>
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def steps(s, meta, n):
    items = s.get("steps", [])[:4]
    cards = []
    for i, it in enumerate(items):
        alt = "alt" if i % 2 else ""
        qual = f'<em>{_esc(it.get("qualifier",""))}</em>' if it.get("qualifier") else ""
        cards.append(f'''    <div class="step {alt}">
      <div class="hd"><div class="badge">{i+1:02d}</div><div class="tt">{_esc(it.get("title",""))}{qual}</div></div>
      <div class="tx">{_esc(it.get("body",""))}</div>
      <div class="illobox">{fig(it.get("motif") or motifs.ROTATION[i], "solid")}</div>
    </div>''')
    rail = s.get("rail") or []
    cells = "".join(
        f'<div class="rcell"><div class="rline"></div><div class="rdot"></div>'
        f'<div class="rlab">{_esc(x)}</div></div>' for x in rail)
    dock = ""
    if cells or s.get("callout"):
        dock = (f'<div class="bottomdock">'
                + (f'<div class="rail"><div class="rtrack">{cells}</div></div>' if cells else "")
                + (callout(s.get("callout_label", ""), s.get("callout", "")) if s.get("callout") else "")
                + "</div>")
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="steps">
{chr(10).join(cards)}
  </div>
  {dock}
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def _band(s, top_class, w, h):
    if not s.get("figure"):
        return ""
    return f'<div class="band {top_class}">{fig(s["figure"], "", w, h)}</div>'


def cards(s, meta, n):
    items = s.get("cards", [])
    cols = int(s.get("cols", 3))
    rows = (len(items) + cols - 1) // cols
    body = []
    for it in items:
        tone = it.get("tone", "")
        tc = f" tone-{tone}" if tone else ""
        pv = f'<div class="pv">{_esc(it["tag"])}</div>' if it.get("tag") else ""
        body.append(f'''    <div class="card{tc}">
      <div class="ct"><span class="dot"></span>{_esc(it.get("title",""))}</div>
      <div class="cb">{_esc(it.get("body",""))}</div>
      {pv}
    </div>''')
    band_top = {1: "top-r1", 2: "top-r2", 3: "top-r2"}[min(rows, 3)]
    wh = s.get("figure_size", (470, 235))
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="grid g{cols} rows{min(rows,3)}">
{chr(10).join(body)}
  </div>
  {_band(s, band_top, *wh)}
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def kpi(s, meta, n):
    cells = "".join(
        f'''    <div class="kpi"><span class="tag">{_esc(k.get("tag",""))}</span>
      <div class="num">{_esc(k.get("value",""))}<em>{_esc(k.get("unit",""))}</em></div>
      <div class="lab">{_esc(k.get("label",""))}</div>
    </div>''' for k in s.get("kpis", [])[:4])
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="kpis">
{cells}
  </div>
  {_band(s, "top-kpi", *s.get("figure_size", (470, 200)))}
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def compare(s, meta, n):
    L, R = s.get("left", {}), s.get("right", {})
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="cmp">
    <div class="pnl a"><span class="tagline">{_esc(L.get("tag",""))}</span>
      <div class="ph">{_esc(L.get("heading",""))}</div>
      <div class="pb">{_esc(L.get("body",""))}</div></div>
    <div class="pnl b"><span class="tagline">{_esc(R.get("tag",""))}</span>
      <div class="ph">{_esc(R.get("heading",""))}</div>
      <div class="pb">{_esc(R.get("body",""))}</div></div>
  </div>
  {_band(s, "top-cmp", *s.get("figure_size", (400, 200)))}
  {callout(s.get("callout_label",""), s.get("callout","")) if s.get("callout") else ""}
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def timeline(s, meta, n):
    items = s.get("items", [])[:4]
    body = []
    for i, it in enumerate(items):
        pos = "up" if i % 2 == 0 else "dn"
        body.append(f'''    <div class="ti {pos}">
      <div class="tcard"><div class="tt">{_esc(it.get("title",""))}</div>
        <div class="tb">{_esc(it.get("body",""))}</div></div>
      <div class="tdot"></div>
    </div>''')
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="tl"><div class="tline"></div><div class="titems">
{chr(10).join(body)}
  </div></div>
  {callout(s.get("callout_label",""), s.get("callout","")) if s.get("callout") else ""}
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def table(s, meta, n):
    cols = s.get("columns", [])
    head = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    rows = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>"
                   for r in s.get("rows", []))
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="tblwrap"><table class="dk"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def chart(s, meta, n, theme=None):
    """Native data chart. Geometry comes from charts.compute() so the HTML/SVG
    render and the PPTX render cannot drift, and both can be re-derived."""
    from . import charts as CH
    spec = s.get("chart") or {}
    errs = CH.spec_errors(spec)
    t = theme or {}
    colors = {
        "accent": t.get("accent", "#268B90"), "primary": t.get("primary", "#033E75"),
        "ok": t.get("ok", "#2f7d5b"), "warn": t.get("warn", "#b8791b"),
        "danger": t.get("danger", "#c0453a"), "line": t.get("line", "#bcdcee"),
        "muted": t.get("muted", "#6b8aa3"), "ink2": t.get("ink2", "#2b4a63"),
    }
    plot = {"x": 70, "y": 44, "w": 1120, "h": 316, "vw": 1240, "vh": 420}
    if errs:
        body = (f'<div class="chartfail">图表未通过规范校验：'
                + "；".join(_esc(e) for e in errs) + "</div>")
    else:
        body = CH.svg(spec, plot, colors)
    note = _esc(s.get("note", ""))
    missing = CH.compute(spec, plot)["missing"] if not errs else []
    miss_html = ""
    if missing:
        miss_html = (f'<div class="chartmiss">缺失值（未按 0 绘制）：'
                     + "、".join(f'系列{m["series"]+1}·{_esc((spec.get("categories") or [""])[m["cat"]])}'
                                 for m in missing) + "</div>")
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="chartwrap">{body}</div>
  <div class="chartfoot">{note}{miss_html}</div>
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


# ------------------------------------------------------------------ images
def _img_src(sl, base_note=None):
    return sl.get("src") or ""


def _img_tag(src, focal, slot, extra=""):
    """An <img> sized and cropped exactly as images.GEOM declares. The crop is
    also described in data attributes so the page can be audited against the
    independently re-derived crop plan."""
    fx, fy = (focal or [0.5, 0.5])[:2]
    style = (f'width:{slot["w"]}px;height:{slot["h"]}px;'
             f'object-position:{round(fx*100,2)}% {round(fy*100,2)}%')
    return (f'<img class="ph-img" src="{_esc(src)}" alt="" '
            f'data-slot-w="{slot["w"]}" data-slot-h="{slot["h"]}" '
            f'data-focal-x="{fx}" data-focal-y="{fy}" '
            f'style="{style}" {extra}/>')


def _img_placeholder(src, label):
    return (f'<div class="img-missing"><div class="im-t">{_esc(label)}</div>'
            f'<div class="im-s">{_esc(src)}</div></div>')


IMG_ERR = {}


def build_image_check(sl, base_dir):
    """Filled by the CLI before rendering so layouts can show real diagnostics."""
    from . import images as IM
    return IM.spec_errors(sl)


def image_hero(s, meta, n, base_dir=None):
    from . import images as IM
    boxes = IM.slot_boxes(s)
    fx, fy = (s.get("focal") or [0.5, 0.42])[:2]
    img = _img_tag(s.get("src", ""), s.get("focal"), boxes[0])
    kick = _esc(s.get("kicker", ""))
    body = _esc(s.get("body", ""))
    return f'''<section class="slide" id="s{n}">
  <div class="imghero">
    {img}
    <div class="ihscrim"></div>
    <div class="ihinner">
      <div class="kick">{kick}</div>
      <h1>{_esc(s.get("title",""))}</h1>
      <div class="sub">{_esc(s.get("subtitle",""))}</div>
      {f'<div class="body">{body}</div>' if body else ''}
    </div>
  </div>
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def image_split(s, meta, n, base_dir=None):
    from . import images as IM
    boxes = IM.slot_boxes(s)
    side = (s.get("side") or "left").lower()
    box = boxes[0]
    img = _img_tag(s.get("src", ""), s.get("focal"), box)
    fig = f'<figure class="imgsplit-fig" style="grid-column:{1 if side=="left" else 2};grid-row:1;">{img}</figure>'
    pts = s.get("points") or []
    bullets = "".join(f'<li>{_esc(p)}</li>' for p in pts)
    txt = (f'<div class="imgsplit-tx" style="grid-column:{2 if side=="left" else 1};grid-row:1;">'
           f'<h2>{_esc(s.get("title",""))}</h2>'
           f'<div class="sb">{_esc(s.get("subtitle",""))}</div>'
           + (f'<ul>{bullets}</ul>' if bullets else "")
           + (f'<div class="nb">{_esc(s.get("note",""))}</div>' if s.get("note") else "")
           + "</div>")
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n, with_title=False)}
  <div class="imgsplit">
    {fig}
    {txt}
  </div>
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def image_grid(s, meta, n, base_dir=None):
    from . import images as IM
    boxes = IM.slot_boxes(s)
    items = (s.get("images") or [])[:4]
    cells = []
    for i, it in enumerate(items):
        box = boxes[min(i, len(boxes) - 1)]
        img = _img_tag(it.get("src", ""), it.get("focal"), box)
        cap = _esc(it.get("caption", ""))
        cap_html = f'<figcaption>{cap}</figcaption>' if cap else ""
        cells.append(f'<figure class="imggrid-cell" style="left:{box["x"]}px;top:{box["y"]}px;'
                     f'width:{box["w"]}px;">{img}{cap_html}</figure>')
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="imggrid">
{chr(10).join(cells)}
  </div>
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


# ------------------------------------------------------------ teaching carriers
def matrix(s, meta, n):
    """Multi-column comparison table: the reference deck's 对照 page."""
    columns = s.get("columns") or []
    rows = s.get("rows") or []
    head = "".join(f"<th>{_esc(c)}</th>" for c in columns)
    body = ""
    for row in rows:
        first = f'<td class="rowhead">{_esc(row[0])}</td>' if row else ""
        rest = "".join(f"<td>{_esc_rich(cell)}</td>" for cell in row[1:])
        body += f"<tr>{first}{rest}</tr>"
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="mxwrap"><table class="mx"><thead><tr>{head}</tr></thead>
  <tbody>{body}</tbody></table></div>
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def quickref(s, meta, n):
    """Compact multi-card quick reference, 2-3 columns."""
    items = s.get("items") or []
    cols = int(s.get("cols", 3))
    cards = "".join(
        f'<div class="qrcard"><div class="qt">{_esc(item.get("title", ""))}</div>'
        f'<div class="qb">{_esc_rich(item.get("body", ""))}</div></div>'
        for item in items)
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="qrwrap" style="grid-template-columns:repeat({cols},1fr)">{cards}</div>
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


def flow(s, meta, n):
    """Branch flow chart drawn with native boxes and arrows.

    ``flow`` is a list of ROWS; each row is a list of boxes, so branches are
    expressed by the row structure instead of by absolute coordinates.
    """
    rows = s.get("flow") or []
    html = []
    for row in rows:
        if isinstance(row, dict):
            row = [row]
        pieces = []
        for index, box in enumerate(row):
            kind = box.get("kind", "box")
            cls = "flowbox decision" if kind == "decision" else "flowbox"
            pieces.append(f'<div class="{cls}">{_esc_rich(box.get("text", ""))}</div>')
            if index < len(row) - 1:
                label = box.get("arrow", "")
                arrow = '<div class="flowarrow">→</div>'
                if label:
                    arrow = (f'<div class="flowarrow">→<div class="flowlabel">'
                             f'{_esc(label)}</div></div>')
                pieces.append(arrow)
        html.append(f'<div class="flowrow">{"".join(pieces)}</div>')
    return f'''<section class="slide" id="s{n}">
  {page_chrome(s, meta, n)}
  <div class="flowwrap">{"".join(html)}</div>
  {keypoint_bar(s)}{foot(meta, source_page(s), n)}
</section>'''


BUILDERS = {
    "cover": cover, "closing": closing, "statement": statement, "steps": steps,
    "cards": cards, "kpi": kpi, "compare": compare, "timeline": timeline, "table": table,
    "chart": chart,
    "matrix": matrix,
    "quickref": quickref,
    "flow": flow,
    "image-hero": image_hero,
    "image-split": image_split,
    "image-grid": image_grid,
}


def render(slide, meta, n, theme=None):
    kind = (slide.get("type") or "cards").lower()
    if kind not in BUILDERS:
        raise KeyError(f"unknown slide type {kind!r}; available: {', '.join(BUILDERS)}")
    fn = BUILDERS[kind]
    if kind == "chart":
        return fn(slide, meta, n, theme)
    if kind.startswith("image-"):
        return fn(slide, meta, n, None)
    return fn(slide, meta, n)
