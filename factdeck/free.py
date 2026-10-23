"""Free pages: the designer writes the page body as HTML/CSS; code decides what is accepted.

A free page (`layout: "free"`) has the usual title/section/focus/design keys plus
  html   the body fragment. The body box is the coordinate space (1152 px wide; 462 px high under a title,
         436 px under a title and a lead or a headline); children may use absolute positioning, flex or grid.
  css    optional rules for this page's body only (selectors are scoped to the page by the renderer).

What the HTML may contain, so that every word stays a verified fact and every mark becomes native PowerPoint:
  * text only inside <span data-fact="id"></span> (left empty: the renderer fills in the fact's shown text) or
    <span data-text>authored label</span> (linted like any authored text); a fact span may carry data-emph="a|b";
  * every text span sits inside exactly one text box: an element marked data-t (becomes one PowerPoint text box,
    its runs keep size, weight and colour); a text box that is an arrow end has an id;
  * every element that paints a fill or a border is marked data-shape (becomes a native shape);
  * tags: div, span, b, br, img, svg, polyline. Styles: the PROPS below; no shadows, gradients, transforms,
    opacity or images (the runtime check rejects what PowerPoint would not show the same way);
  * drawings follow the drawing principle, as on composed pages:
      <svg data-edges style="position:absolute;left:0;top:0;width:…px;height:…px"> holds polylines:
        <polyline points="x,y x,y" data-from="textbox id" data-to="textbox id" data-backed="fact"/>   an arrow
        <polyline points="…" data-encodes="fact fact"/> or <polyline points="…" data-axis/>          a drawn line
      <img data-icon="icon id" data-for="fact">  an icon for the first fact of a text box on the page
      <div data-shape data-value-of="fact" data-scale="name" style="width:…px">  a bar: its length is checked against
        the fact's number on the shared scale (the longest bar of a scale sets the px per unit)
      <div data-ring data-value-of="fact" style="…square…">  a donut whose arc the code draws from the fact's percentage
        (a range or "以上/超过" adds a pale arc to the upper end; "不足/低于" is refused); may hold a centred text box
      <div data-pictogram data-value-of="fact" data-count="10" data-icon="on" data-icon-pale="pale" data-icon-off="off">
        a row of icons, as many filled as the percentage gives (pale for the range or open upper end)
    and a page that draws states its figure layer in design.figure.
"""
from __future__ import annotations

import html as _html
import re
from html.parser import HTMLParser

TAGS = {"div", "span", "b", "br", "img", "svg", "polyline"}
VOID = {"br", "img", "polyline"}
ATTRS = {"class", "id", "style", "points", "width", "height", "viewbox"}
DATA = {"data-fact", "data-text", "data-emph", "data-t", "data-shape", "data-group", "data-edges", "data-from", "data-to",
        "data-backed", "data-encodes", "data-axis", "data-icon", "data-for", "data-value-of", "data-scale",
        "data-ring", "data-pictogram", "data-count", "data-icon-pale", "data-icon-off", "data-tone", "data-size", "data-thick"}
RING_TONES = {"accent": "var(--accent)", "primary": "var(--primary)", "primary2": "var(--primary2)", "muted": "var(--muted)"}
PROPS = {"position", "left", "top", "right", "bottom", "width", "height", "min-width", "min-height", "max-width", "max-height",
         "display", "flex", "flex-direction", "flex-wrap", "flex-grow", "flex-shrink", "flex-basis", "align-items",
         "align-self", "align-content", "justify-content", "justify-items", "justify-self", "gap", "row-gap", "column-gap",
         "grid-template-columns", "grid-template-rows", "grid-column", "grid-row", "grid-area", "grid-template-areas", "order",
         "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
         "margin", "margin-top", "margin-right", "margin-bottom", "margin-left", "box-sizing", "overflow", "z-index",
         "background", "background-color", "border", "border-top", "border-right", "border-bottom", "border-left",
         "border-width", "border-style", "border-color", "border-top-width", "border-right-width", "border-bottom-width",
         "border-left-width", "border-top-color", "border-right-color", "border-bottom-color", "border-left-color",
         "border-radius", "color", "font-size", "font-weight", "line-height", "text-align", "white-space", "vertical-align",
         "word-break", "line-break", "fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin"}
BANNED_VALUE = re.compile(r"url\(|gradient|expression|@import|image-set|attr\(|calc\(.*var\(--k", re.I)
SELECTOR = re.compile(r"^[A-Za-z0-9_\-.#\s>+~:*(),]+$")


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, attrs, parent, []

    def has(self, a):
        return a in self.attrs

    def walk(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.walk()

    def text(self):
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def up(self, attr):
        n = self.parent
        while n is not None and n.tag != "#root":
            if n.has(attr):
                return n
            n = n.parent
        return None


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.cur, self.errors = self.root, []

    def handle_starttag(self, tag, attrs):
        n = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is self.root:
            self.errors.append(f"多余的结束标签 </{tag}>")
        else:
            self.cur = n.parent

    def handle_data(self, data):
        if data:
            self.cur.children.append(data)

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        self.errors.append("不允许 <!…> 声明")

    def unknown_decl(self, data):
        self.errors.append("不允许 CDATA 等声明")


def parse(markup: str) -> tuple[Node, list[str]]:
    p = _Parser()
    p.feed(markup or "")
    p.close()
    if p.cur is not p.root:
        p.errors.append(f"标签 <{p.cur.tag}> 未闭合")
    return p.root, p.errors


def _decls(style: str) -> list[tuple[str, str]]:
    out = []
    for part in (style or "").split(";"):
        if part.strip():
            k, _, v = part.partition(":")
            out.append((k.strip().lower(), v.strip()))
    return out


def _decl_errors(where: str, decls) -> list[str]:
    errors = []
    for k, v in decls:
        if k.startswith("--"):
            errors.append(f"{where}：不能定义 CSS 变量 {k}（用主题变量 var(--…)）")
        elif k not in PROPS:
            errors.append(f"{where}：不支持样式 {k}（PowerPoint 无法同样呈现；可用：位置尺寸、flex/grid、内外边距、纯色填充与边框、圆角、文字颜色/字号/字重/行高/对齐）")
        elif BANNED_VALUE.search(v) or (k == "background" and re.search(r"\b(url|gradient|no-repeat|cover)\b", v, re.I)):
            errors.append(f"{where}：样式 {k}: {v} 不可用（渐变、图片、表达式无法转成原生形状）")
    return errors


def css_rules(css: str) -> tuple[list[tuple[str, list[tuple[str, str]]]], list[str]]:
    rules, errors = [], []
    text = re.sub(r"/\*.*?\*/", "", css or "", flags=re.S)
    if "@" in text:
        errors.append("css 不能含 @ 规则（@media、@import、@font-face…）")
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        sel, body = m.group(1).strip(), m.group(2)
        if not SELECTOR.match(sel) or "::" in sel or re.search(r":(?:before|after)\b", sel):
            errors.append(f"css 选择器“{sel}”不可用：只用类、id、标签与组合，不用属性选择器和伪元素")
        rules.append((sel, _decls(body)))
        errors += _decl_errors(f"css {sel}", _decls(body))
    if re.sub(r"([^{}]+)\{([^{}]*)\}", "", text).strip():
        errors.append("css 有无法解析的内容")
    return rules, errors


def structure_errors(page: dict) -> list[str]:
    """Shape of a free page's HTML: allowed tags, attributes and styles; every word in a fact or authored span inside
    one text box; drawings named after the facts they draw; a page that draws states its figure layer."""
    root, errors = parse(page.get("html") or "")
    if not (page.get("html") or "").strip():
        return ["free 页需有 html（本页正文）"]
    _, css_errors = css_rules(page.get("css") or "")
    errors += css_errors
    nodes = list(root.walk())
    ids = [n.attrs["id"] for n in nodes if n.attrs.get("id")]
    if len(set(ids)) != len(ids):
        errors.append("html 中 id 重复")
    boxes = {n.attrs["id"]: n for n in nodes if n.has("data-t") and n.attrs.get("id")}
    first = {first_fact(n) for n in nodes if n.has("data-t")} - {None}   # an icon names the first fact of any text box
    drawn = False
    for c in root.children:
        if isinstance(c, str) and c.strip():
            errors.append(f"文字“{c.strip()[:20]}”须放在 data-fact 或 data-text 的 span 里")
    for n in nodes:
        where = f"<{n.tag}{(' id=' + n.attrs['id']) if n.attrs.get('id') else ''}>"
        if n.tag not in TAGS:
            errors.append(f"{where} 不可用：标签只能是 {'、'.join(sorted(TAGS))}")
            continue
        for a in n.attrs:
            if a.startswith("on") or (a not in ATTRS and a not in DATA):
                errors.append(f"{where} 的属性 {a} 不可用")
        errors += _decl_errors(where, _decls(n.attrs.get("style", "")))
        for c in n.children:
            if isinstance(c, str) and c.strip() and not (n.tag == "span" and n.has("data-text")):
                errors.append(f"文字“{c.strip()[:20]}”须放在 data-fact 或 data-text 的 span 里")
        if n.has("data-fact") or n.has("data-text"):
            if n.tag != "span":
                errors.append(f"{where}：data-fact / data-text 只用在 span 上")
            if n.has("data-fact") and n.children:
                errors.append(f"{where}：data-fact 的 span 须留空（由程序填入事实的显示文字）")
            if n.has("data-text") and (any(isinstance(c, Node) for c in n.children) or not n.text().strip()):
                errors.append(f"{where}：data-text 的 span 只含作者文字")
            if not n.has("data-t") and not n.up("data-t"):
                errors.append(f"{where}：文字须放在一个 data-t 文本框里（它会成为一个 PowerPoint 文本框）")
        if n.has("data-t") and n.up("data-t"):
            errors.append(f"{where}：data-t 文本框不能嵌套")
        if n.has("data-t") and n.tag not in ("div", "span"):
            errors.append(f"{where}：data-t 只用在 div 或 span 上")
        if n.tag in ("svg", "polyline", "img"):
            drawn = True
        if n.tag == "svg" and not n.has("data-edges"):
            errors.append(f"{where}：svg 只用来画箭头和线（data-edges）")
        if n.tag == "svg" and any(isinstance(c, Node) and c.tag != "polyline" for c in n.children):
            errors.append(f"{where}：svg 里只能放 polyline")
        if n.tag == "polyline":
            if not (n.parent and n.parent.tag == "svg"):
                errors.append("polyline 须在 svg data-edges 里")
            pts = re.findall(r"-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?", n.attrs.get("points", ""))
            if len(pts) < 2:
                errors.append("polyline 需有至少两个点：points=\"x,y x,y\"")
            arrow = n.has("data-from") or n.has("data-to") or n.has("data-backed")
            if arrow:
                if not (n.attrs.get("data-from") in boxes and n.attrs.get("data-to") in boxes):
                    errors.append("箭头需以 data-from / data-to 指明两端文本框（data-t 元素）的 id")
                if not n.attrs.get("data-backed"):
                    errors.append("箭头需以 data-backed 给出支持事实")
            elif not (n.attrs.get("data-encodes", "").split() or n.has("data-axis")):
                errors.append("线条需以 data-encodes 写明它画出的事实，或标为 data-axis（坐标轴、刻度）")
        if n.tag == "img":
            if not n.attrs.get("data-icon"):
                errors.append("图标需以 data-icon 指明图标文件")
            if n.attrs.get("data-for") not in first:
                errors.append("图标需以 data-for 指明它代表的事实：本页某个文本框的第一条事实")
        if n.has("data-ring") or n.has("data-pictogram"):
            drawn = True
            if not n.attrs.get("data-value-of"):
                errors.append(f"{where}：环形图/象形图需以 data-value-of 指明它画出的百分数事实")
            if n.attrs.get("data-tone", "accent") not in RING_TONES:
                errors.append(f"{where}：data-tone 只能是 {'、'.join(RING_TONES)}")
            if n.has("data-pictogram"):
                if not (n.attrs.get("data-count", "").isdigit() and 4 <= int(n.attrs["data-count"]) <= 30):
                    errors.append(f"{where}：象形图需以 data-count 给出 4–30 个图标")
                if not n.attrs.get("data-icon"):
                    errors.append(f"{where}：象形图需以 data-icon 指明图标")
        elif n.has("data-value-of"):
            drawn = True
            if not n.has("data-shape") or not n.attrs.get("data-scale"):
                errors.append(f"{where}：条形需有 data-shape 和 data-scale（同一刻度的条形共用一个名字）")
    if drawn and not str((page.get("design") or {}).get("figure") or "").strip():
        errors.append("本页画了图（线、箭头、图标或条形）：须在 design.figure 写明它承担了哪一层文字讲不了的内容"
                      "（数值在刻度上的位置、过程的走向、部分之间的连接）；说不出来就不画")
    return errors


def icon_ids(markup: str) -> set[str]:
    """Every icon file a free page needs (its own img icons and its pictograms' icons)."""
    root, _ = parse(markup)
    out = set()
    for n in root.walk():
        for a in ("data-icon", "data-icon-pale", "data-icon-off"):
            if n.attrs.get(a) and (n.tag == "img" or n.has("data-pictogram")):
                out.add(n.attrs[a])
    return out


def first_fact(n: Node) -> str | None:
    for m in n.walk():
        if m.has("data-fact"):
            return m.attrs["data-fact"]
    return None


def view(page: dict) -> list[dict]:
    """The page as composed-page blocks, for the checks that do not depend on geometry (facts shown, arrows backed,
    lines and bars bound to facts, icons standing for a shown term)."""
    root, _ = parse(page.get("html") or "")
    blocks, auto = [], 0
    for n in root.walk():
        if n.has("data-t"):
            refs = []
            for m in ([n] if (n.has("data-fact") or n.has("data-text")) else []) + list(n.walk()):
                if m.has("data-fact"):
                    ref = {"fact": m.attrs["data-fact"]}
                    if m.attrs.get("data-emph"):
                        ref["emph"] = [x for x in m.attrs["data-emph"].split("|") if x]
                    refs.append(ref)
                elif m.has("data-text"):
                    refs.append({"text": m.text().strip()})
            auto += 1
            blocks.append({"kind": "text", "id": n.attrs.get("id") or f"_t{auto}", "refs": refs})
        elif n.tag == "polyline" and (n.has("data-from") or n.has("data-backed")):
            blocks.append({"kind": "arrow", "from": n.attrs.get("data-from"), "to": n.attrs.get("data-to"),
                           "backed_by": n.attrs.get("data-backed")})
        elif n.tag == "polyline":
            blocks.append({"kind": "line", **({"axis": True} if n.has("data-axis") else {"encodes": n.attrs.get("data-encodes", "").split()})})
        elif n.tag == "img":
            blocks.append({"kind": "icon", "icon": n.attrs.get("data-icon"), "for": n.attrs.get("data-for")})
        if n.has("data-ring") or n.has("data-pictogram"):
            blocks.append({"kind": "ring", "value_of": n.attrs.get("data-value-of")})
        elif n.has("data-value-of"):
            blocks.append({"kind": "bar", "value_of": n.attrs["data-value-of"], "scale": n.attrs.get("data-scale")})
    return blocks


def ring_spec(text: str) -> tuple[float, float]:
    """(solid, pale) percentages a ring or pictogram draws for a fact's shown text: one number fills to it; a range fills
    to the lower end and pales to the upper; an open upper end ("以上", "超过", "more than") pales to 100. An upper bound
    ("不足", "低于") is refused: drawing it at the number would overstate it."""
    if re.search(r"不足|低于|少于|小于|less than|<|≤", text, re.I):
        raise ValueError(f"“{text}”是一个上限，按数值画会夸大，不画")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    if "%" not in text or not 1 <= len(nums) <= 2 or any(v > 100 for v in nums):
        raise ValueError(f"“{text}”须是一个百分数或一个百分数区间")
    solid = nums[0]
    pale = nums[1] if len(nums) == 2 else (100.0 if re.search(r"以上|超过|至少|more than|over|>", text, re.I) else solid)
    return solid, max(pale, solid)


def _arc(frac: float, r: float) -> str:
    """SVG path of an arc from 12 o'clock clockwise over `frac` of the circle (viewBox 0 0 100 100)."""
    import math
    frac = min(frac, 0.99999)
    a = 2 * math.pi * frac
    x, y = 50 + r * math.sin(a), 50 - r * math.cos(a)
    return f"M50,{50 - r:.3f} A{r:.3f},{r:.3f} 0 {1 if frac > 0.5 else 0} 1 {x:.3f},{y:.3f}"


ARROW_DEFS = ('<defs><marker id="farr-{pid}-{i}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
              'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" style="fill:var(--primary2)"/></marker></defs>')


def render(page: dict, fview: dict, icon_files: dict, emph_spans) -> tuple[str, str]:
    """The page's body HTML (fact spans filled, authored spans marked, arrows given heads) and its scoped CSS."""
    root, _ = parse(page.get("html") or "")
    pid = page["id"]
    svg_no = [0]

    def attrs(n, extra=None):
        a = dict(n.attrs)
        a.update(extra or {})
        return "".join(f' {k}' if v == "" and k.startswith("data-") else f' {k}="{_html.escape(str(v), quote=True)}"'
                       for k, v in a.items())

    def out(n) -> str:
        if isinstance(n, str):
            return _html.escape(n)
        if n.tag == "#root":
            return "".join(out(c) for c in n.children)
        if n.has("data-fact"):
            f = fview[n.attrs["data-fact"]]
            emph = [x for x in n.attrs.get("data-emph", "").split("|") if x]
            body = "".join(f'<b class="em">{_html.escape(t)}</b>' if on else _html.escape(t) for t, on in emph_spans(f["text"], emph)) \
                if emph else _html.escape(f["text"])
            a = {k: v for k, v in n.attrs.items() if k != "data-emph"}
            a["class"] = ("f " + a.get("class", "")).strip()
            mark = '<span class="mark" data-mark="pending" title="待人工确认">●</span>' if f["pending"] else ""
            return f"<span{attrs(Node('span', a))}>{body}</span>{mark}"
        if n.has("data-text"):
            a = {k: v for k, v in n.attrs.items() if k != "data-text"}
            a["data-authored"] = ""
            return f"<span{attrs(Node('span', a))}>{_html.escape(n.text().strip())}</span>"
        if n.tag == "svg":
            svg_no[0] += 1
            inner = ARROW_DEFS.format(pid=pid, i=svg_no[0]) + "".join(out(c) for c in n.children)
            return f"<svg{attrs(n)}>{inner}</svg>"
        if n.tag == "polyline":
            arrow = n.has("data-from") or n.has("data-backed")
            style = "fill:none;stroke:var(--primary2);stroke-width:2;" + n.attrs.get("style", "")
            extra = {"style": style, "fill": "none"}
            if arrow:
                extra.update({"data-edge": n.attrs.get("data-backed", ""), "marker-end": f"url(#farr-{pid}-{svg_no[0]})"})
            else:
                extra["data-plain"] = "1"
            return f"<polyline{attrs(n, extra)}/>"
        if n.has("data-ring"):
            solid, pale = ring_spec(fview[n.attrs["data-value-of"]]["text"])
            thick = float(n.attrs.get("data-thick") or 14)
            r = 50 - thick / 2
            tone = RING_TONES[n.attrs.get("data-tone", "accent")]
            svg = (f'<svg class="ring" viewBox="0 0 100 100" style="position:absolute;left:0;top:0;width:100%;height:100%">'
                   f'<circle class="ring-track" cx="50" cy="50" r="{r}" style="fill:none;stroke:var(--sky);stroke-width:{thick}"/>'
                   + (f'<path class="ring-pale" d="{_arc(pale / 100, r)}" style="fill:none;stroke:{tone};stroke-opacity:.3;stroke-width:{thick}"/>' if pale > solid else "")
                   + (f'<path class="ring-solid" d="{_arc(solid / 100, r)}" style="fill:none;stroke:{tone};stroke-width:{thick}"/>' if solid > 0 else "")
                   + '</svg>')
            extra = {"data-solid": solid, "data-pale": pale, "data-thick": thick / 100}
            return f"<div{attrs(n, extra)}>{svg}{''.join(out(c) for c in n.children)}</div>"
        if n.has("data-pictogram"):
            solid, pale = ring_spec(fview[n.attrs["data-value-of"]]["text"])
            count, size = int(n.attrs["data-count"]), float(n.attrs.get("data-size") or 28)
            k_solid = int(solid / 100 * count + 1e-9)
            k_pale = max(0, -int(-(pale / 100 * count - 1e-9)) - k_solid)
            ids = [n.attrs["data-icon"]] * k_solid + [n.attrs.get("data-icon-pale") or n.attrs["data-icon"]] * k_pale
            ids += [n.attrs.get("data-icon-off") or n.attrs.get("data-icon-pale") or n.attrs["data-icon"]] * (count - len(ids))
            imgs = "".join(f'<img data-icon="{i}" src="{_html.escape(icon_files.get(i, ""))}" alt="" '
                           f'style="width:{size}px;height:{size}px;object-fit:contain">' for i in ids)
            return f"<div{attrs(n)}>{imgs}</div>"
        if n.tag == "img":
            src = icon_files.get(n.attrs.get("data-icon"), "")
            return f'<img{attrs(n, {"src": src, "alt": ""})}>'
        if n.tag in VOID:
            return f"<{n.tag}{attrs(n)}>"
        return f"<{n.tag}{attrs(n)}>{''.join(out(c) for c in n.children)}</{n.tag}>"

    rules, _ = css_rules(page.get("css") or "")
    css = "\n".join(",".join(f"#{pid} .body {s.strip()}" for s in sel.split(",")) + "{" + ";".join(f"{k}:{v}" for k, v in decls) + "}"
                    for sel, decls in rules)
    return out(root), css


def bar_errors(page: dict, values: dict[str, float], drawn: list[dict]) -> list[str]:
    """A bar's drawn length against its fact's number: on one scale, length / value is the same for every bar."""
    errors, by_scale = [], {}
    for b in drawn:
        by_scale.setdefault(b["scale"], []).append(b)
    for scale, bars in by_scale.items():
        top = max(bars, key=lambda b: abs(values.get(b["fact"], 0)))
        unit = top["length"] / (abs(values.get(top["fact"], 0)) or 1)
        for b in bars:
            want = abs(values.get(b["fact"], 0)) * unit
            if abs(b["length"] - want) > 1.0:
                errors.append(f"条形 {b['fact']}（刻度 {scale}）长 {b['length']:.1f}px，按数值应为 {want:.1f}px")
    return errors
