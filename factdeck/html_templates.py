"""HTML bodies for the teaching layouts.

``render_html`` traces every slot and draws fact text only through
``emit_on_screen``. A fill the fact gate rejected or held for review is
not in the HTML. Slots that remain are measured, then drawn as native shapes.
"""

from __future__ import annotations

import html
import json
import re

from factdeck.layout_selector import Selection, refuse_equal_card_wall
from factdeck.slots import SlideTrace, SlotVerdict, emit_on_screen, trace_slide
from factdeck.theme import CSS, MEASURE_JS

PERCENT = re.compile(r"(约?\d+(?:\.\d+)?(?:\s*[-–—]\s*\d+(?:\.\d+)?)?\s*[%％])")
BADGE_YES = frozenset({"是", "有", "Y", "Yes", "YES"})
BADGE_NO = frozenset({"否", "无", "N", "No", "NO"})


def render_html(slide: dict, selection: Selection) -> str:
    refuse_equal_card_wall(slide, selection)
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
    trace = trace_slide(slide, selection)
    body = renderer(slide, selection, trace)
    title = html.escape(str(slide.get("title") or ""))
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title><style>{CSS}</style></head><body>{body}{MEASURE_JS}</body></html>"
    )


def _esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _attr(verdict: SlotVerdict) -> str:
    parts = [
        f'data-slot="{_esc(verdict.slot_id)}"',
        f'data-kind="{_esc(verdict.kind)}"',
        f'data-role="{_esc(verdict.role)}"',
        f'data-fact="{"1" if verdict.fact_bearing else "0"}"',
        f'data-status="{_esc(verdict.status)}"',
    ]
    if verdict.source_id:
        parts.append(f'data-source-id="{_esc(verdict.source_id)}"')
    if verdict.source_field:
        parts.append(f'data-source-field="{_esc(verdict.source_field)}"')
    if verdict.pair_id:
        parts.append(f'data-pair="{_esc(verdict.pair_id)}"')
    if verdict.provenance:
        parts.append(f'data-provenance="{_esc(verdict.provenance)}"')
    if verdict.admitted_slices:
        payload = json.dumps([item.to_dict() for item in verdict.admitted_slices], ensure_ascii=False)
        parts.append(f'data-slices="{_esc(payload)}"')
    return " ".join(parts)


def _el(trace: SlideTrace, slot_id: str, *, tag: str = "div", class_name: str = "", inner: str | None = None, extra: str = "") -> str:
    verdict = trace.by_id()[slot_id]
    if not emit_on_screen(verdict):
        return ""
    content = _esc(verdict.display_text) if inner is None else inner
    class_attr = f' class="{class_name}"' if class_name else ""
    extra_attr = f" {extra}" if extra else ""
    return f"<{tag}{class_attr} {_attr(verdict)}{extra_attr}>{content}</{tag}>"


def _emphasize(text: str) -> str:
    escaped = _esc(text)
    return PERCENT.sub(r"<strong>\1</strong>", escaped)


def _chrome_open(slide: dict, selection: Selection, trace: SlideTrace) -> str:
    figure = slide.get("figure")
    figure_html = _el(trace, "fig", class_name="fig") if figure else '<div class="fig"></div>'
    return (
        f'<article class="slide" data-layout="{_esc(selection.layout_id)}" '
        f'data-variant="{_esc(selection.variant)}" data-columns="{selection.columns}">'
        '<header class="top"><div>'
        f'{_el(trace, "kicker", class_name="kicker")}'
        f'{_el(trace, "title", tag="h1")}'
        f'{_el(trace, "title-rule", class_name="rule")}'
        f'</div>{figure_html}</header><main>'
    )


def _chrome_close(trace: SlideTrace) -> str:
    return (
        "</main><footer>"
        f'{_el(trace, "folio", class_name="folio")}'
        f'{_el(trace, "source", class_name="source")}'
        "</footer></article>"
    )


def _items(slide: dict) -> list[dict]:
    ready = []
    for index, item in enumerate(slide.get("items") or [], start=1):
        copy = dict(item)
        copy.setdefault("id", f"item-{index}")
        ready.append(copy)
    return ready


def _metric_row(slide: dict, selection: Selection, trace: SlideTrace) -> str:
    items = _items(slide)
    if selection.variant == "band":
        cells = []
        for index, _item in enumerate(items[:3], start=1):
            cells.append(
                '<div class="cell">'
                f'{_el(trace, f"m{index}-label", class_name="label")}'
                f'{_el(trace, f"m{index}-value", class_name="value")}'
                "</div>"
            )
        main = f'{_el(trace, "metric-band", class_name="metric-band", inner="".join(cells))}'
        return _chrome_open(slide, selection, trace) + main + _chrome_close(trace)

    anchor = selection.anchor
    hero_id = anchor.get("source_item_id")
    statement_id = anchor.get("statement_item_id")
    notes = [item for item in items if item.get("id") not in {hero_id, statement_id}]
    hero = _el(
        trace,
        "hero",
        class_name="hero",
        inner=_el(trace, "hero-label", class_name="label") + _el(trace, "hero-value", class_name="value"),
    )
    label = anchor.get("statement_label") or ""
    label_html = _el(trace, "take-label", class_name="label") if label and label != slide.get("title") else ""
    takeaway = (
        '<div class="takeaway">'
        f"{label_html}"
        f'{_el(trace, "take-text", class_name="text")}'
        "</div>"
    )
    note_html = []
    for index, _item in enumerate(notes, start=1):
        note_html.append(
            '<div class="note">'
            f'{_el(trace, f"n{index}-idx", class_name="idx")}'
            f'{_el(trace, f"n{index}-title", tag="h3")}'
            f'{_el(trace, f"n{index}-body", tag="p")}'
            "</div>"
        )
    columns = "cols-1" if selection.columns <= 1 or len(notes) <= 1 else "cols-2"
    main = (
        f'<div class="hero-row">{hero}{takeaway}</div>'
        f'<div class="notes {columns}">{"".join(note_html)}</div>'
    )
    return _chrome_open(slide, selection, trace) + main + _chrome_close(trace)


def _checklist(slide: dict, selection: Selection, trace: SlideTrace) -> str:
    items = _items(slide)
    index = trace.by_id()
    value_html = _el(trace, "anchor-value", class_name="value") if "anchor-value" in index else ""
    panel = _el(
        trace,
        "anchor",
        tag="aside",
        class_name="anchor-panel",
        inner=(
            f'{_el(trace, "anchor-label", class_name="label")}'
            f"{value_html}"
            f'{_el(trace, "anchor-text", class_name="text")}'
        ),
    )
    rows = []
    for number, _item in enumerate(items, start=1):
        rows.append(
            '<div class="check">'
            f'{_el(trace, f"c{number}-idx", class_name="idx")}'
            f'{_el(trace, f"c{number}-title", tag="h3")}'
            f'{_el(trace, f"c{number}-body", tag="p")}'
            "</div>"
        )
    columns = "cols-1" if selection.columns <= 1 else "cols-2"
    main = f'<div class="check-wrap">{panel}<div class="checks {columns}">{"".join(rows)}</div></div>'
    return _chrome_open(slide, selection, trace) + main + _chrome_close(trace)


def _claim_evidence(slide: dict, selection: Selection, trace: SlideTrace) -> str:
    items = _items(slide)
    anchor = selection.anchor
    claim_id = anchor.get("source_item_id")
    evidence_rows = []
    primary_done = False
    index = 0
    for item in items:
        chunk = False
        if item.get("id") == claim_id and item.get("evidence"):
            chunk = True
            primary_done = True
        elif item.get("id") != claim_id:
            text = item.get("evidence") or item.get("body") or item.get("value") or ""
            chunk = bool(text)
        elif item.get("id") == claim_id and not item.get("evidence"):
            primary_done = True
        if not chunk:
            continue
        index += 1
        evidence_rows.append(
            '<div class="ev-item">'
            f'{_el(trace, f"e{index}-title", tag="h3")}'
            f'{_el(trace, f"e{index}-body", tag="p", inner=_emphasize(trace.by_id()[f"e{index}-body"].display_text))}'
            "</div>"
        )
    if not primary_done and anchor.get("statement"):
        evidence_rows.insert(
            0,
            '<div class="ev-item">'
            f'{_el(trace, "e0-title", tag="h3")}'
            f'{_el(trace, "e0-body", tag="p", inner=_emphasize(trace.by_id()["e0-body"].display_text))}'
            "</div>",
        )
    main = (
        '<div class="ce">'
        '<section class="claim">'
        f'{_el(trace, "claim-label", class_name="label")}'
        f'{_el(trace, "claim-text", tag="h2")}'
        "</section>"
        '<section class="ev">'
        f'{_el(trace, "ev-label", class_name="label")}'
        f'{"".join(evidence_rows)}'
        "</section></div>"
    )
    return _chrome_open(slide, selection, trace) + main + _chrome_close(trace)


def _matrix(slide: dict, selection: Selection, trace: SlideTrace) -> str:
    items = _items(slide)
    if len(items) != 4:
        raise ValueError("matrix_2x2 requires 4 items")
    cells = []
    for index, _item in enumerate(items):
        cells.append(
            '<div class="cell">'
            f'{_el(trace, f"x{index}-title", tag="h3")}'
            f'{_el(trace, f"x{index}-body", tag="p")}'
            "</div>"
        )
    main = (
        '<div class="matrix"><div class="grid">'
        f'{_el(trace, "mx-corner", class_name="corner")}'
        f'{_el(trace, "mx-c0", class_name="gh", inner=_el(trace, "mx-c0t", tag="span"))}'
        f'{_el(trace, "mx-c1", class_name="gh", inner=_el(trace, "mx-c1t", tag="span"))}'
        f'{_el(trace, "mx-r0", class_name="rh", inner=_el(trace, "mx-r0t", tag="span"))}'
        f'{cells[0]}{cells[1]}'
        f'{_el(trace, "mx-r1", class_name="rh", inner=_el(trace, "mx-r1t", tag="span"))}'
        f'{cells[2]}{cells[3]}'
        "</div></div>"
    )
    return _chrome_open(slide, selection, trace) + main + _chrome_close(trace)


def _node_html(node: dict, trace: SlideTrace) -> str:
    kind = node.get("type") or "action"
    slot = str(node.get("id"))
    css = {"start": "node-start", "decision": "node-decision", "action": "node-action", "exclude": "node-exclude"}.get(kind, "node-action")
    title = _el(trace, f"{slot}-title", class_name="ntitle")
    chip_html = _el(trace, f"{slot}-chip", class_name="chip")
    body_html = _el(trace, f"{slot}-body", class_name="nbody") if f"{slot}-body" in trace.by_id() else ""
    lines = []
    index = 1
    while f"{slot}-line{index}" in trace.by_id():
        css_line = "threshold" if kind == "decision" else "subline"
        lines.append(_el(trace, f"{slot}-line{index}", class_name=css_line))
        index += 1
    return _el(
        trace,
        slot,
        class_name=f"node {css}",
        extra=f'data-node-type="{_esc(kind)}"',
        inner=f"{chip_html}{title}{body_html}{''.join(lines)}",
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


def _algorithm(slide: dict, selection: Selection, trace: SlideTrace) -> str:
    nodes = {node["id"]: node for node in slide.get("nodes") or []}
    edges = list(slide.get("edges") or [])
    decision = next((node for node in nodes.values() if node.get("type") == "decision"), None)
    start = next((node for node in nodes.values() if node.get("type") == "start"), None)
    yes_edge = next((edge for edge in edges if edge.get("from") == (decision or {}).get("id") and edge.get("label") == "是"), None)
    no_edge = next((edge for edge in edges if edge.get("from") == (decision or {}).get("id") and edge.get("label") == "否"), None)
    if decision and yes_edge and no_edge:
        yes_nodes = _chain(yes_edge["to"], edges, nodes, skip=set())
        no_nodes = _chain(no_edge["to"], edges, nodes, skip=set())
        main = '<div class="tree">'
        if start:
            main += _node_html(start, trace)
            main += _el(trace, "stem-start", class_name="stem")
        main += _node_html(decision, trace)
        main += _el(trace, "stem-decision", class_name="stem")
        main += f'<div class="split">{_el(trace, "bridge", class_name="bridge")}'
        main += _arm("yes", yes_nodes, trace)
        main += _arm("no", no_nodes, trace)
        main += "</div></div>"
        return _chrome_open(slide, selection, trace) + main + _chrome_close(trace)

    stacked = []
    for index, node in enumerate(slide.get("nodes") or []):
        if index:
            stacked.append(_el(trace, f"stem-{index}", class_name="stem"))
        stacked.append(_node_html(node, trace))
    main = f'<div class="tree tree-stack">{"".join(stacked)}</div>'
    return _chrome_open(slide, selection, trace) + main + _chrome_close(trace)


def _arm(name: str, nodes: list[dict], trace: SlideTrace) -> str:
    body = [
        '<div class="stem-label">'
        f'{_el(trace, f"stem-{name}", class_name="stem")}'
        f'{_el(trace, f"label-{name}", class_name="edge-label")}'
        "</div>"
    ]
    for index, node in enumerate(nodes):
        if index:
            body.append(_el(trace, f"stem-{name}-{index}", class_name="stem"))
        body.append(_node_html(node, trace))
    return f'<div class="arm arm-{name}">{"".join(body)}</div>'


def _badge(text: str) -> str | None:
    stripped = text.strip()
    if stripped in BADGE_YES:
        return f'<span class="badge badge-yes">{_esc(stripped)}</span>'
    if stripped in BADGE_NO:
        return f'<span class="badge badge-no">{_esc(stripped)}</span>'
    return None


def _table(slide: dict, selection: Selection, trace: SlideTrace) -> str:
    table = slide.get("table") or {}
    columns = list(table.get("columns") or [])
    rows = list(table.get("rows") or [])
    highlight_cols = set(table.get("highlight_columns") or [])
    highlight_rows = set(table.get("highlight_rows") or [])
    header = []
    for index, _name in enumerate(columns):
        klass = "hi" if index in highlight_cols else ""
        header.append(_el(trace, f"th-{index}", tag="th", class_name=klass))
    body = []
    for r_index, row in enumerate(rows):
        values = list(row.get("cells") or [])
        cells = [_el(trace, f"r{r_index}-h", tag="td", class_name="rowhead")]
        for c_index, value in enumerate(values, start=1):
            classes = []
            if c_index in highlight_cols or r_index in highlight_rows:
                classes.append("hi")
            badge = _badge(str(value))
            cells.append(
                _el(
                    trace,
                    f"r{r_index}-c{c_index}",
                    tag="td",
                    class_name=" ".join(classes),
                    inner=badge,
                )
            )
        body.append(f"<tr>{''.join(cells)}</tr>")
    caption = table.get("caption") or ""
    caption_html = _el(trace, "caption", tag="caption") if caption else ""
    colgroup = []
    widths = table.get("widths") or []
    for index, _name in enumerate(columns):
        width = widths[index] if index < len(widths) else ""
        colgroup.append(f'<col style="width:{_esc(width)}">' if width else "<col>")
    main = (
        '<div class="table-wrap">'
        f'{_el(trace, "table", tag="table", class_name="clinical", inner="<colgroup>" + "".join(colgroup) + "</colgroup><thead><tr>" + "".join(header) + "</tr></thead><tbody>" + "".join(body) + "</tbody>" + caption_html)}'
        "</div>"
    )
    return _chrome_open(slide, selection, trace) + main + _chrome_close(trace)
