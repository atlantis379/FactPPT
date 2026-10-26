"""HTML bodies for the teaching layouts. Slots are measured, then drawn as native shapes."""

from __future__ import annotations

import html
import re

from factdeck.layout_selector import Selection, clean_source, is_metric_item
from factdeck.theme import CSS, MEASURE_JS

PERCENT = re.compile(r"(约?\d+(?:\.\d+)?(?:\s*[-–—]\s*\d+(?:\.\d+)?)?\s*[%％])")
BADGE_YES = frozenset({"是", "有", "Y", "Yes", "YES"})
BADGE_NO = frozenset({"否", "无", "N", "No", "NO"})


def render_html(slide: dict, selection: Selection) -> str:
    renderer = {
        "metric_row": _metric_row,
        "checklist": _checklist,
        "matrix_2x2": _matrix,
        "claim_evidence": _claim_evidence,
        "algorithm_tree": _algorithm,
        "data_table_highlight": _table,
    }.get(selection.layout_id)
    if renderer is None:
        raise KeyError(f"no body template for {selection.layout_id}")
    body = renderer(slide, selection)
    title = html.escape(str(slide.get("title") or ""))
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title><style>{CSS}</style></head><body>{body}{MEASURE_JS}</body></html>"
    )


def _esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _emphasize(text: str) -> str:
    escaped = _esc(text)
    return PERCENT.sub(r"<strong>\1</strong>", escaped)


def _chrome_open(slide: dict, selection: Selection) -> str:
    kicker = _esc(slide.get("kicker") or "")
    title = _esc(slide.get("title") or "")
    figure = slide.get("figure")
    figure_html = (
        f'<div class="fig" data-slot="fig" data-kind="text">{_esc(figure)}</div>' if figure else '<div class="fig"></div>'
    )
    return (
        f'<article class="slide" data-layout="{_esc(selection.layout_id)}" '
        f'data-variant="{_esc(selection.variant)}" data-columns="{selection.columns}">'
        '<header class="top"><div>'
        f'<div class="kicker" data-slot="kicker" data-kind="text">{kicker}</div>'
        f'<h1 data-slot="title" data-kind="text">{title}</h1>'
        '<div class="rule" data-slot="title-rule" data-kind="line"></div>'
        f'</div>{figure_html}</header><main>'
    )


def _chrome_close(slide: dict) -> str:
    page = _esc(slide.get("page") or "")
    source = clean_source(str(slide.get("source") or ""))
    if source and not source.startswith("来源"):
        source = f"来源：{source}"
    return (
        "</main><footer>"
        f'<div class="folio" data-slot="folio" data-kind="text">{page}</div>'
        f'<div class="source" data-slot="source" data-kind="text">{_esc(source)}</div>'
        "</footer></article>"
    )


def _items(slide: dict) -> list[dict]:
    ready = []
    for index, item in enumerate(slide.get("items") or [], start=1):
        copy = dict(item)
        copy.setdefault("id", f"item-{index}")
        ready.append(copy)
    return ready


def _metric_row(slide: dict, selection: Selection) -> str:
    items = _items(slide)
    if selection.variant == "band":
        cells = []
        for index, item in enumerate(items[:3], start=1):
            cells.append(
                '<div class="cell">'
                f'<div class="label" data-slot="m{index}-label" data-kind="text">{_esc(item.get("title"))}</div>'
                f'<div class="value" data-slot="m{index}-value" data-kind="text">{_esc(item.get("value") or item.get("body"))}</div>'
                "</div>"
            )
        main = f'<div class="metric-band" data-slot="metric-band" data-kind="shape">{"".join(cells)}</div>'
        return _chrome_open(slide, selection) + main + _chrome_close(slide)

    anchor = selection.anchor
    hero_id = anchor.get("source_item_id")
    statement_id = anchor.get("statement_item_id")
    notes = [item for item in items if item.get("id") not in {hero_id, statement_id}]
    hero = (
        '<div class="hero" data-slot="hero" data-kind="shape">'
        f'<div class="label" data-slot="hero-label" data-kind="text">{_esc(anchor.get("label"))}</div>'
        f'<div class="value" data-slot="hero-value" data-kind="text">{_esc(anchor.get("value"))}</div>'
        "</div>"
    )
    label = anchor.get("statement_label") or ""
    label_html = ""
    if label and label != slide.get("title"):
        label_html = f'<div class="label" data-slot="take-label" data-kind="text">{_esc(label)}</div>'
    takeaway = (
        '<div class="takeaway">'
        f"{label_html}"
        f'<div class="text" data-slot="take-text" data-kind="text">{_esc(anchor.get("statement"))}</div>'
        "</div>"
    )
    note_html = []
    for index, item in enumerate(notes, start=1):
        note_html.append(
            '<div class="note">'
            f'<div class="idx" data-slot="n{index}-idx" data-kind="text">{index:02d}</div>'
            f'<h3 data-slot="n{index}-title" data-kind="text">{_esc(item.get("title"))}</h3>'
            f'<p data-slot="n{index}-body" data-kind="text">{_esc(item.get("body") if not is_metric_item(item) else item.get("body"))}</p>'
            "</div>"
        )
    columns = "cols-1" if selection.columns <= 1 or len(notes) <= 1 else "cols-2"
    main = (
        f'<div class="hero-row">{hero}{takeaway}</div>'
        f'<div class="notes {columns}">{"".join(note_html)}</div>'
    )
    return _chrome_open(slide, selection) + main + _chrome_close(slide)


def _checklist(slide: dict, selection: Selection) -> str:
    items = _items(slide)
    anchor = selection.anchor
    panel = (
        '<aside class="anchor-panel" data-slot="anchor" data-kind="shape">'
        f'<div class="label" data-slot="anchor-label" data-kind="text">{_esc(anchor.get("label"))}</div>'
        f'<div class="value" data-slot="anchor-value" data-kind="text">{_esc(anchor.get("value"))}</div>'
        f'<div class="text" data-slot="anchor-text" data-kind="text">{_esc(anchor.get("statement"))}</div>'
        "</aside>"
    )
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            '<div class="check">'
            f'<div class="idx" data-slot="c{index}-idx" data-kind="text">{index:02d}</div>'
            f'<h3 data-slot="c{index}-title" data-kind="text">{_esc(item.get("title"))}</h3>'
            f'<p data-slot="c{index}-body" data-kind="text">{_esc(item.get("body"))}</p>'
            "</div>"
        )
    columns = "cols-1" if selection.columns <= 1 else "cols-2"
    main = f'<div class="check-wrap">{panel}<div class="checks {columns}">{"".join(rows)}</div></div>'
    return _chrome_open(slide, selection) + main + _chrome_close(slide)


def _claim_evidence(slide: dict, selection: Selection) -> str:
    items = _items(slide)
    anchor = selection.anchor
    claim_id = anchor.get("source_item_id")
    evidence_rows = []
    primary_done = False
    index = 0
    for item in items:
        chunks = []
        if item.get("id") == claim_id and item.get("evidence"):
            chunks.append((item.get("title") or "依据", item.get("evidence")))
            primary_done = True
        elif item.get("id") != claim_id:
            text = item.get("evidence") or item.get("body") or item.get("value") or ""
            if text:
                chunks.append((item.get("title") or "", text))
        elif item.get("id") == claim_id and not item.get("evidence"):
            primary_done = True
        for title, text in chunks:
            index += 1
            evidence_rows.append(
                '<div class="ev-item">'
                f'<h3 data-slot="e{index}-title" data-kind="text">{_esc(title)}</h3>'
                f'<p data-slot="e{index}-body" data-kind="text">{_emphasize(text)}</p>'
                "</div>"
            )
    if not primary_done and anchor.get("statement"):
        evidence_rows.insert(
            0,
            '<div class="ev-item">'
            f'<h3 data-slot="e0-title" data-kind="text">{_esc(anchor.get("statement_label"))}</h3>'
            f'<p data-slot="e0-body" data-kind="text">{_emphasize(anchor.get("statement"))}</p>'
            "</div>",
        )
    main = (
        '<div class="ce">'
        '<section class="claim">'
        f'<div class="label" data-slot="claim-label" data-kind="text">{_esc(anchor.get("label"))}</div>'
        f'<h2 data-slot="claim-text" data-kind="text">{_esc(anchor.get("value"))}</h2>'
        "</section>"
        '<section class="ev">'
        '<div class="label" data-slot="ev-label" data-kind="text">依据</div>'
        f'{"".join(evidence_rows)}'
        "</section></div>"
    )
    return _chrome_open(slide, selection) + main + _chrome_close(slide)


def _matrix(slide: dict, selection: Selection) -> str:
    items = _items(slide)
    if len(items) != 4:
        raise ValueError("matrix_2x2 requires 4 items")
    axes = slide.get("axes") or {}
    rows = list(axes.get("rows") or ["", ""])
    cols = list(axes.get("cols") or ["", ""])
    cells = []
    for index, item in enumerate(items):
        cells.append(
            '<div class="cell">'
            f'<h3 data-slot="x{index}-title" data-kind="text">{_esc(item.get("title"))}</h3>'
            f'<p data-slot="x{index}-body" data-kind="text">{_esc(item.get("body"))}</p>'
            "</div>"
        )
    main = (
        '<div class="matrix"><div class="grid">'
        '<div class="corner" data-slot="mx-corner" data-kind="shape"></div>'
        f'<div class="gh" data-slot="mx-c0" data-kind="shape"><span data-slot="mx-c0t" data-kind="text">{_esc(cols[0])}</span></div>'
        f'<div class="gh" data-slot="mx-c1" data-kind="shape"><span data-slot="mx-c1t" data-kind="text">{_esc(cols[1])}</span></div>'
        f'<div class="rh" data-slot="mx-r0" data-kind="shape"><span data-slot="mx-r0t" data-kind="text">{_esc(rows[0])}</span></div>'
        f'{cells[0]}{cells[1]}'
        f'<div class="rh" data-slot="mx-r1" data-kind="shape"><span data-slot="mx-r1t" data-kind="text">{_esc(rows[1])}</span></div>'
        f'{cells[2]}{cells[3]}'
        "</div></div>"
    )
    return _chrome_open(slide, selection) + main + _chrome_close(slide)


def _node_html(node: dict) -> str:
    kind = node.get("type") or "action"
    slot = _esc(node.get("id"))
    chip = {"start": "起始", "decision": "判定", "action": "处置", "exclude": "排除"}.get(kind, "处置")
    css = {"start": "node-start", "decision": "node-decision", "action": "node-action", "exclude": "node-exclude"}.get(kind, "node-action")
    title = (
        f'<div class="ntitle" data-slot="{slot}-title" data-kind="text">{_esc(node.get("title"))}</div>'
    )
    chip_html = f'<div class="chip" data-slot="{slot}-chip" data-kind="text">{chip}</div>'
    body = node.get("body") or ""
    body_html = f'<div class="nbody" data-slot="{slot}-body" data-kind="text">{_esc(body)}</div>' if body else ""
    lines = []
    for index, line in enumerate(node.get("lines") or [], start=1):
        css_line = "threshold" if kind == "decision" else "subline"
        lines.append(f'<div class="{css_line}" data-slot="{slot}-line{index}" data-kind="text">{_esc(line)}</div>')
    return (
        f'<div class="node {css}" data-slot="{slot}" data-kind="shape" data-node-type="{_esc(kind)}">'
        f"{chip_html}{title}{body_html}{''.join(lines)}</div>"
    )


def _chain(start_id: str, edges: list[dict], nodes: dict[str, dict], skip: set[str]) -> list[dict]:
    ordered = []
    seen = set()
    current = start_id
    while current and current not in seen and current in nodes:
        seen.add(current)
        if current not in skip:
            ordered.append(nodes[current])
        nxt = next((edge.get("to") for edge in edges if edge.get("from") == current), None)
        current = nxt
    return ordered


def _algorithm(slide: dict, selection: Selection) -> str:
    nodes = {node["id"]: node for node in slide.get("nodes") or []}
    edges = list(slide.get("edges") or [])
    decision = next((node for node in nodes.values() if node.get("type") == "decision"), None)
    start = next((node for node in nodes.values() if node.get("type") == "start"), None)
    yes_edge = next((edge for edge in edges if edge.get("from") == (decision or {}).get("id") and edge.get("label") == "是"), None)
    no_edge = next((edge for edge in edges if edge.get("from") == (decision or {}).get("id") and edge.get("label") == "否"), None)
    if decision and yes_edge and no_edge:
        skip = {start["id"]} if start else set()
        skip.add(decision["id"])
        yes_nodes = _chain(yes_edge["to"], edges, nodes, skip=set())
        no_nodes = _chain(no_edge["to"], edges, nodes, skip=set())
        main = '<div class="tree">'
        if start:
            main += _node_html(start)
            main += '<div class="stem" data-slot="stem-start" data-kind="line"></div>'
        main += _node_html(decision)
        main += '<div class="stem" data-slot="stem-decision" data-kind="line"></div>'
        main += '<div class="split"><div class="bridge" data-slot="bridge" data-kind="line"></div>'
        main += _arm("yes", "是", yes_nodes)
        main += _arm("no", "否", no_nodes)
        main += "</div></div>"
        return _chrome_open(slide, selection) + main + _chrome_close(slide)

    stacked = []
    for index, node in enumerate(slide.get("nodes") or []):
        if index:
            stacked.append(f'<div class="stem" data-slot="stem-{index}" data-kind="line"></div>')
        stacked.append(_node_html(node))
    main = f'<div class="tree tree-stack">{"".join(stacked)}</div>'
    return _chrome_open(slide, selection) + main + _chrome_close(slide)


def _arm(name: str, label: str, nodes: list[dict]) -> str:
    body = [
        f'<div class="stem-label"><div class="stem" data-slot="stem-{name}" data-kind="line"></div>'
        f'<div class="edge-label" data-slot="label-{name}" data-kind="text">{_esc(label)}</div></div>'
    ]
    for index, node in enumerate(nodes):
        if index:
            body.append(f'<div class="stem" data-slot="stem-{name}-{index}" data-kind="line"></div>')
        body.append(_node_html(node))
    return f'<div class="arm arm-{name}">{"".join(body)}</div>'


def _badge(text: str) -> str | None:
    stripped = text.strip()
    if stripped in BADGE_YES:
        return f'<span class="badge badge-yes">{_esc(stripped)}</span>'
    if stripped in BADGE_NO:
        return f'<span class="badge badge-no">{_esc(stripped)}</span>'
    return None


def _table(slide: dict, selection: Selection) -> str:
    table = slide.get("table") or {}
    columns = list(table.get("columns") or [])
    rows = list(table.get("rows") or [])
    highlight_cols = set(table.get("highlight_columns") or [])
    highlight_rows = set(table.get("highlight_rows") or [])
    header = []
    for index, name in enumerate(columns):
        klass = "hi" if index in highlight_cols else ""
        header.append(
            f'<th class="{klass}" data-slot="th-{index}" data-kind="text">{_esc(name)}</th>'
        )
    body = []
    for r_index, row in enumerate(rows):
        label = row.get("label")
        values = list(row.get("cells") or [])
        cells = [
            f'<td class="rowhead" data-slot="r{r_index}-h" data-kind="text">{_esc(label)}</td>'
        ]
        for c_index, value in enumerate(values, start=1):
            classes = []
            if c_index in highlight_cols or r_index in highlight_rows:
                classes.append("hi")
            badge = _badge(str(value))
            inner = badge if badge else _esc(value)
            cells.append(
                f'<td class="{" ".join(classes)}" data-slot="r{r_index}-c{c_index}" data-kind="text">{inner}</td>'
            )
        body.append(f"<tr>{''.join(cells)}</tr>")
    caption = table.get("caption") or ""
    caption_html = f"<caption data-slot=\"caption\" data-kind=\"text\">{_esc(caption)}</caption>" if caption else ""
    colgroup = []
    widths = table.get("widths") or []
    for index, _name in enumerate(columns):
        width = widths[index] if index < len(widths) else ""
        colgroup.append(f'<col style="width:{_esc(width)}">' if width else "<col>")
    main = (
        '<div class="table-wrap"><table class="clinical" data-slot="table" data-kind="shape">'
        f"<colgroup>{''.join(colgroup)}</colgroup>"
        f"<thead><tr>{''.join(header)}</tr></thead><tbody>{''.join(body)}</tbody>{caption_html}</table></div>"
    )
    return _chrome_open(slide, selection) + main + _chrome_close(slide)
