"""Typed slot binding and per-slot provenance for teaching layouts.

Each fact-bearing slot names the source field it was drawn from and is
admitted only by ``gate_display``. ``ACCEPTED`` requires at least one slice
that gate admitted. A slide-level note is not provenance. ``screen_fill``
drops a shortening the gate does not admit. ``emit_on_screen`` is what the
template uses so a rejected fill is not on-screen text.

Title and body (or a flow-node title and another node's line) that share a
pair id must cite the same source object. Cross-wiring is ``REJECTED``.
A zip that drops the tail of a node list is ``NEEDS_REVIEW``. Display
``ACCEPTED`` still does not write an Approved Semantic Graph object.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from factdeck.facts import FactGateResult, UnitSlice, canon, extract_unit_slices, gate_display
from factdeck.layout_selector import clean_source
from factdeck.lexicon import DERIVATION_BY_KIND

TRACE_MARK = "【溯源】"
_FACT_KINDS = frozenset({"dose", "drug", *DERIVATION_BY_KIND})
_PAIR_ROLES = frozenset({"title", "body", "value", "line", "cell"})


@dataclass(frozen=True)
class SlotBinding:
    slot_id: str
    role: str
    kind: str
    layout_id: str
    display_text: str
    source_text: str | None = None
    source_id: str | None = None
    source_field: str | None = None
    pair_id: str | None = None
    fact_bearing: bool = False

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "role": self.role,
            "kind": self.kind,
            "layout_id": self.layout_id,
            "display_text": self.display_text,
            "source_text": self.source_text,
            "source_id": self.source_id,
            "source_field": self.source_field,
            "pair_id": self.pair_id,
            "fact_bearing": self.fact_bearing,
        }


@dataclass(frozen=True)
class SlotVerdict:
    slot_id: str
    role: str
    kind: str
    layout_id: str
    display_text: str
    source_text: str | None
    source_id: str | None
    source_field: str | None
    pair_id: str | None
    fact_bearing: bool
    status: str
    reason_code: str
    reason: str
    admitted_slices: tuple[UnitSlice, ...]
    gate_status: str | None = None
    gate_reason: str | None = None

    @property
    def provenance(self) -> str:
        if self.status == "ACCEPTED" and self.admitted_slices:
            return TRACE_MARK
        return ""

    @property
    def admits_to_approved_graph(self) -> bool:
        return False

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "role": self.role,
            "kind": self.kind,
            "layout_id": self.layout_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "source_id": self.source_id,
            "source_field": self.source_field,
            "pair_id": self.pair_id,
            "fact_bearing": self.fact_bearing,
            "provenance": self.provenance,
            "gate_status": self.gate_status,
            "gate_reason": self.gate_reason,
            "admits_to_approved_graph": False,
            "admitted_slices": [item.to_dict() for item in self.admitted_slices],
        }


@dataclass(frozen=True)
class SlideTrace:
    layout_id: str
    status: str
    reason_code: str
    bindings: tuple[SlotBinding, ...]
    slots: tuple[SlotVerdict, ...]

    def by_id(self) -> dict[str, SlotVerdict]:
        return {item.slot_id: item for item in self.slots}

    def to_dict(self) -> dict:
        return {
            "layout_id": self.layout_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "admits_to_approved_graph": False,
            "slots": [item.to_dict() for item in self.slots],
        }


def gate_keeps_display(source_text: str, display_text: str) -> bool:
    """True only when this display would be an ACCEPTED fact slot."""

    binding = _binding(
        slot_id="probe",
        role="value",
        kind="text",
        layout_id="probe",
        display_text=display_text,
        source_text=source_text,
        source_id="probe",
        source_field="body",
        pair_id=None,
        fact_bearing=True,
    )
    return judge_binding(binding).status == "ACCEPTED"


def screen_fill(source_text: str, display_text: str) -> str:
    """Keep a fill only when it is the source text or the fact gate admits it.

    A shortening or an invented string is dropped. The same characters with
    a folded space between a digit and a unit are still the source text.
    """

    display = "" if display_text is None else str(display_text)
    source = "" if source_text is None else str(source_text)
    if not display.strip():
        return ""
    if canon(display) == canon(source):
        return display
    if gate_keeps_display(source, display):
        return display
    return ""


def measure_record(verdict: SlotVerdict) -> dict:
    """Fields a measured slot must carry. Geometry is filled by the browser."""

    return {
        "id": verdict.slot_id,
        "kind": verdict.kind,
        "role": verdict.role,
        "sourceId": verdict.source_id or "",
        "sourceField": verdict.source_field or "",
        "pairId": verdict.pair_id or "",
        "fact": "1" if verdict.fact_bearing else "0",
        "status": verdict.status,
        "provenance": verdict.provenance,
        "slices": json.dumps([item.to_dict() for item in verdict.admitted_slices], ensure_ascii=False),
        "text": verdict.display_text if verdict.kind == "text" else "",
    }


def judge_binding(binding: SlotBinding) -> SlotVerdict:
    if not binding.fact_bearing:
        return _verdict(binding, "CHROME", "NOT_A_FACT", "结构槽不作为事实准入。", (), None, None)
    if binding.source_id is None or binding.source_text is None:
        return _verdict(binding, "REJECTED", "UNBOUND_SLOT", "事实槽没有绑定原文字段。", (), None, None)
    if not str(binding.display_text).strip():
        return _verdict(binding, "REJECTED", "EMPTY_DISPLAY", "屏上没有可核对的文字。", (), None, None)
    if not _contained(binding.display_text, binding.source_text):
        return _verdict(
            binding,
            "REJECTED",
            "DISPLAY_NOT_IN_SOURCE",
            "屏上文字不是所绑定原文的切片。",
            (),
            None,
            None,
        )
    gate = gate_display(binding.source_text, binding.display_text)
    if gate.status == "REJECTED":
        return _verdict(binding, "REJECTED", gate.reason_code, gate.reason, (), gate.status, gate.reason_code)
    if gate.status == "NEEDS_REVIEW":
        return _verdict(binding, "NEEDS_REVIEW", gate.reason_code, gate.reason, (), gate.status, gate.reason_code)
    matched, orphan = _match_slices(gate)
    if orphan:
        return _verdict(
            binding,
            "REJECTED",
            "SLICE_MISMATCH",
            "屏上切片没有落在闸门承认的原文切片上。",
            (),
            gate.status,
            gate.reason_code,
        )
    if not matched:
        return _verdict(
            binding,
            "BOUND",
            "NO_ADMITTED_SLICE",
            "文字已绑定原文，但事实闸门没有承认任何切片，不能标为溯源。",
            (),
            gate.status,
            gate.reason_code,
        )
    return _verdict(binding, "ACCEPTED", gate.reason_code, gate.reason, tuple(matched), gate.status, gate.reason_code)


def trace_bindings(bindings: Sequence[SlotBinding], *, layout_id: str) -> SlideTrace:
    verdicts = _apply_pairs([judge_binding(item) for item in bindings])
    return _slide(layout_id, tuple(bindings), verdicts)


def trace_slide(slide: Mapping, selection=None) -> SlideTrace:
    if selection is None:
        from factdeck.layout_selector import select_layout

        selection = select_layout(slide)
    bindings = bind_layout(slide, selection)
    return trace_bindings(bindings, layout_id=selection.layout_id)


def bind_layout(slide: Mapping, selection) -> tuple[SlotBinding, ...]:
    layout_id = selection.layout_id
    bindings = list(_chrome_bindings(slide, layout_id))
    if layout_id == "metric_row":
        bindings.extend(_metric_bindings(slide, selection))
    elif layout_id == "checklist":
        bindings.extend(_checklist_bindings(slide, selection))
    elif layout_id == "claim_evidence":
        bindings.extend(_claim_bindings(slide, selection))
    elif layout_id == "matrix_2x2":
        bindings.extend(_matrix_bindings(slide, selection))
    elif layout_id == "algorithm_tree":
        bindings.extend(_algorithm_bindings(slide, selection))
    elif layout_id == "data_table_highlight":
        bindings.extend(_table_bindings(slide, selection))
    else:
        raise KeyError(f"no slot binding for {layout_id}")
    return tuple(bindings)


def judge_flow_zip(nodes: Sequence[Mapping]) -> SlideTrace:
    """Zip every title with bodies that were filtered first.

    Nodes without a body shift the pairs, and the tail is left unpaired.
    That is the flow-node zip error. It must not keep an admitted trace.
    """

    prepared = _prepared_nodes(nodes)
    bodies = [node for node in prepared if str(node.get("body") or "").strip()]
    bindings: list[SlotBinding] = []
    paired: set[str] = set()
    for index, (title_node, body_node) in enumerate(zip(prepared, bodies)):
        pair_id = f"zip:{index}"
        paired.add(str(title_node["id"]))
        bindings.append(
            _binding(
                slot_id=f"zip-{index}-title",
                role="title",
                kind="text",
                layout_id="algorithm_tree",
                display_text=str(title_node.get("title") or ""),
                source_text=str(title_node.get("title") or ""),
                source_id=f"node:{title_node['id']}",
                source_field="title",
                pair_id=pair_id,
                fact_bearing=True,
            )
        )
        bindings.append(
            _binding(
                slot_id=f"zip-{index}-body",
                role="body",
                kind="text",
                layout_id="algorithm_tree",
                display_text=str(body_node.get("body") or ""),
                source_text=str(body_node.get("body") or ""),
                source_id=f"node:{body_node['id']}",
                source_field="body",
                pair_id=pair_id,
                fact_bearing=True,
            )
        )
    verdicts = list(_apply_pairs([judge_binding(item) for item in bindings]))
    for node in prepared:
        if str(node["id"]) in paired:
            continue
        verdicts.append(
            _bare(
                slot_id=f"zip-missing-{node['id']}",
                role="body",
                kind="text",
                layout_id="algorithm_tree",
                display_text="",
                source_text=str(node.get("body") or node.get("title") or ""),
                source_id=f"node:{node['id']}",
                source_field="body",
                pair_id=f"zip-missing:{node['id']}",
                fact_bearing=True,
                status="NEEDS_REVIEW",
                reason_code="PAIR_TRUNCATED",
                reason="流程节点的标题和正文被分开过滤后 zip，尾部节点没有配上自己的事实。",
            )
        )
    return _slide("algorithm_tree", tuple(bindings), tuple(verdicts))


def judge_item_zip(items: Sequence[Mapping]) -> SlideTrace:
    """Pair each title with the next item's body."""

    prepared = _prepared_items(items)
    if len(prepared) < 2:
        raise ValueError("item zip needs two items")
    shifted = prepared[1:] + prepared[:1]
    bindings: list[SlotBinding] = []
    for index, (title_item, body_item) in enumerate(zip(prepared, shifted)):
        pair_id = f"zip:{index}"
        bindings.append(
            _binding(
                slot_id=f"zip-{index}-title",
                role="title",
                kind="text",
                layout_id="checklist",
                display_text=str(title_item.get("title") or ""),
                source_text=str(title_item.get("title") or ""),
                source_id=f"item:{title_item['id']}",
                source_field="title",
                pair_id=pair_id,
                fact_bearing=True,
            )
        )
        bindings.append(
            _binding(
                slot_id=f"zip-{index}-body",
                role="body",
                kind="text",
                layout_id="checklist",
                display_text=str(body_item.get("body") or ""),
                source_text=str(body_item.get("body") or ""),
                source_id=f"item:{body_item['id']}",
                source_field="body",
                pair_id=pair_id,
                fact_bearing=True,
            )
        )
    return trace_bindings(bindings, layout_id="checklist")


def _binding(
    *,
    slot_id: str,
    role: str,
    kind: str,
    layout_id: str,
    display_text: str,
    source_text: str | None,
    source_id: str | None,
    source_field: str | None,
    pair_id: str | None,
    fact_bearing: bool,
) -> SlotBinding:
    return SlotBinding(
        slot_id=slot_id,
        role=role,
        kind=kind,
        layout_id=layout_id,
        display_text=display_text,
        source_text=source_text,
        source_id=source_id,
        source_field=source_field,
        pair_id=pair_id,
        fact_bearing=fact_bearing,
    )


def _verdict(
    binding: SlotBinding,
    status: str,
    reason_code: str,
    reason: str,
    slices: tuple[UnitSlice, ...],
    gate_status: str | None,
    gate_reason: str | None,
) -> SlotVerdict:
    return _bare(
        slot_id=binding.slot_id,
        role=binding.role,
        kind=binding.kind,
        layout_id=binding.layout_id,
        display_text=binding.display_text,
        source_text=binding.source_text,
        source_id=binding.source_id,
        source_field=binding.source_field,
        pair_id=binding.pair_id,
        fact_bearing=binding.fact_bearing,
        status=status,
        reason_code=reason_code,
        reason=reason,
        admitted_slices=slices,
        gate_status=gate_status,
        gate_reason=gate_reason,
    )


def _bare(
    *,
    slot_id: str,
    role: str,
    kind: str,
    layout_id: str,
    display_text: str,
    source_text: str | None,
    source_id: str | None,
    source_field: str | None,
    pair_id: str | None,
    fact_bearing: bool,
    status: str,
    reason_code: str,
    reason: str,
    admitted_slices: tuple[UnitSlice, ...] = (),
    gate_status: str | None = None,
    gate_reason: str | None = None,
) -> SlotVerdict:
    return SlotVerdict(
        slot_id=slot_id,
        role=role,
        kind=kind,
        layout_id=layout_id,
        display_text=display_text,
        source_text=source_text,
        source_id=source_id,
        source_field=source_field,
        pair_id=pair_id,
        fact_bearing=fact_bearing,
        status=status,
        reason_code=reason_code,
        reason=reason,
        admitted_slices=admitted_slices,
        gate_status=gate_status,
        gate_reason=gate_reason,
    )


def _slide(layout_id: str, bindings: tuple[SlotBinding, ...], verdicts: tuple[SlotVerdict, ...]) -> SlideTrace:
    rejected = next((item for item in verdicts if item.status == "REJECTED"), None)
    review = next((item for item in verdicts if item.status == "NEEDS_REVIEW"), None)
    if rejected is not None:
        return SlideTrace(layout_id, "REJECTED", rejected.reason_code, bindings, verdicts)
    if review is not None:
        return SlideTrace(layout_id, "NEEDS_REVIEW", review.reason_code, bindings, verdicts)
    return SlideTrace(layout_id, "CLEAN", "PAIRS_CONSISTENT", bindings, verdicts)


def _apply_pairs(verdicts: list[SlotVerdict]) -> tuple[SlotVerdict, ...]:
    groups: dict[str, list[SlotVerdict]] = defaultdict(list)
    for item in verdicts:
        if item.pair_id and item.fact_bearing and item.role in _PAIR_ROLES:
            groups[item.pair_id].append(item)
    overridden = {item.slot_id: item for item in verdicts}
    for members in groups.values():
        source_ids = {item.source_id for item in members if item.source_id}
        if len(source_ids) <= 1:
            continue
        for item in members:
            overridden[item.slot_id] = replace(
                item,
                status="REJECTED",
                reason_code="PAIR_MISMATCH",
                reason="标题和正文绑定了不同的事实，不能沿用其中一条的溯源。",
                admitted_slices=(),
                gate_status=item.gate_status,
                gate_reason=item.gate_reason,
            )
    return tuple(overridden[item.slot_id] for item in verdicts)


def _contained(display: str, source: str) -> bool:
    folded_display = canon(display)
    folded_source = canon(source)
    if not folded_display:
        return False
    return folded_display == folded_source or folded_display in folded_source


def _match_slices(gate: FactGateResult) -> tuple[list[UnitSlice], list[UnitSlice]]:
    pool = list(gate.evidence_slices)
    matched: list[UnitSlice] = []
    orphan: list[UnitSlice] = []
    for shown in gate.display_slices:
        index = next((i for i, item in enumerate(pool) if _same_slice(item, shown)), None)
        if index is None:
            orphan.append(shown)
            continue
        matched.append(pool.pop(index))
    return matched, orphan


def _same_slice(evidence: UnitSlice, shown: UnitSlice) -> bool:
    if evidence.kind != shown.kind:
        return False
    if evidence.kind == "dose":
        return evidence.token == shown.token and evidence.unit == shown.unit
    return canon(evidence.text) == canon(shown.text)


def _has_facts(text: str) -> bool:
    return any(item.kind in _FACT_KINDS for item in extract_unit_slices(text))


def _prepared_items(items: Sequence[Mapping]) -> list[dict]:
    ready = []
    for index, item in enumerate(items, start=1):
        copy = dict(item)
        copy.setdefault("id", f"item-{index}")
        ready.append(copy)
    return ready


def _prepared_nodes(nodes: Sequence[Mapping]) -> list[dict]:
    ready = []
    for index, node in enumerate(nodes, start=1):
        copy = dict(node)
        copy.setdefault("id", f"node-{index}")
        ready.append(copy)
    return ready


def _chrome_bindings(slide: Mapping, layout_id: str) -> list[SlotBinding]:
    bindings = [
        _chrome(layout_id, "kicker", "text", str(slide.get("kicker") or ""), "slide", "kicker"),
        _chrome(layout_id, "title", "text", str(slide.get("title") or ""), "slide", "title"),
        _chrome(layout_id, "title-rule", "line", "", "slide", "title-rule"),
        _chrome(layout_id, "folio", "text", str(slide.get("page") or ""), "slide", "page"),
        _chrome(layout_id, "source", "text", _source_line(slide), "slide", "source"),
    ]
    figure = slide.get("figure")
    if figure:
        bindings.append(_chrome(layout_id, "fig", "text", str(figure), "slide", "figure"))
    return bindings


def _chrome(
    layout_id: str,
    slot_id: str,
    kind: str,
    display: str,
    source_id: str | None,
    source_field: str | None,
) -> SlotBinding:
    return _binding(
        slot_id=slot_id,
        role="chrome",
        kind=kind,
        layout_id=layout_id,
        display_text=display,
        source_text=display,
        source_id=source_id,
        source_field=source_field,
        pair_id=None,
        fact_bearing=False,
    )


def _source_line(slide: Mapping) -> str:
    source = clean_source(str(slide.get("source") or ""))
    if source and not source.startswith("来源"):
        return f"来源：{source}"
    return source


def _fact(
    layout_id: str,
    slot_id: str,
    role: str,
    display: str,
    source: str,
    source_id: str,
    source_field: str,
    pair_id: str,
    *,
    kind: str = "text",
) -> SlotBinding:
    return _binding(
        slot_id=slot_id,
        role=role,
        kind=kind,
        layout_id=layout_id,
        display_text=display,
        source_text=source,
        source_id=source_id,
        source_field=source_field,
        pair_id=pair_id,
        fact_bearing=True,
    )


def _metric_bindings(slide: Mapping, selection) -> list[SlotBinding]:
    layout_id = selection.layout_id
    items = _prepared_items(slide.get("items") or [])
    if selection.variant == "band":
        bindings = [_chrome(layout_id, "metric-band", "shape", "", None, None)]
        for index, item in enumerate(items[:3], start=1):
            bindings.extend(_item_title_value(layout_id, item, f"m{index}"))
        return bindings
    anchor = selection.anchor or {}
    hero_id = anchor.get("source_item_id")
    statement_id = anchor.get("statement_item_id")
    hero = next((item for item in items if item.get("id") == hero_id), items[0] if items else None)
    statement = next((item for item in items if item.get("id") == statement_id), None)
    bindings = [_chrome(layout_id, "hero", "shape", "", None, None)]
    if hero is not None:
        source_id = f"item:{hero['id']}"
        shown, value_source, value_field = _resolve_metric_fill(hero, str(anchor.get("value") or ""))
        bindings.append(
            _fact(layout_id, "hero-label", "title", str(anchor.get("label") or hero.get("title") or ""), str(hero.get("title") or ""), source_id, "title", source_id)
        )
        bindings.append(
            _fact(layout_id, "hero-value", "value", shown, value_source, source_id, value_field, source_id)
        )
    if statement is not None:
        label = str(anchor.get("statement_label") or "")
        if label and label != str(slide.get("title") or ""):
            bindings.append(
                _fact(layout_id, "take-label", "title", label, str(statement.get("title") or ""), f"item:{statement['id']}", "title", f"item:{statement['id']}")
            )
        bindings.append(
            _fact(
                layout_id,
                "take-text",
                "body",
                str(anchor.get("statement") or statement.get("body") or ""),
                str(statement.get("body") or ""),
                f"item:{statement['id']}",
                "body",
                f"item:{statement['id']}",
            )
        )
    else:
        statement_text = str(anchor.get("statement") or "")
        if not _has_facts(statement_text):
            bindings.append(_chrome(layout_id, "take-text", "text", statement_text, None, None))
    hidden = {hero_id, statement_id}
    notes = [item for item in items if item.get("id") not in hidden]
    for index, item in enumerate(notes, start=1):
        bindings.append(_chrome(layout_id, f"n{index}-idx", "text", f"{index:02d}", f"item:{item['id']}", "index"))
        bindings.extend(_item_title_body(layout_id, item, f"n{index}"))
    return bindings


def _resolve_metric_fill(item: Mapping, display: str | None = None) -> tuple[str, str, str]:
    """Return display, source text, and source field for a metric value.

    A value field that is not the body is judged against the body. It is
    not allowed to be its own source, so a shortened or stitched number
    cannot skip the fact gate.
    """

    raw_value = str(item.get("value") or "").strip()
    body = str(item.get("body") or "")
    differs = bool(raw_value and body.strip() and canon(raw_value) != canon(body))
    if display is None or (display == "" and differs):
        shown = raw_value or body
    else:
        shown = display
    if differs:
        return shown, body, "body"
    if raw_value:
        return shown, raw_value, "value"
    return shown, body, "body"


def _item_title_value(layout_id: str, item: Mapping, prefix: str, *, label_key: str | None = None, value_key: str | None = None) -> list[SlotBinding]:
    label_id = label_key or f"{prefix}-label"
    value_id = value_key or f"{prefix}-value"
    source_id = f"item:{item['id']}"
    title = str(item.get("title") or "")
    shown, source, field = _resolve_metric_fill(item)
    return [
        _fact(layout_id, label_id, "title", title, title, source_id, "title", source_id),
        _fact(layout_id, value_id, "value", shown, source, source_id, field, source_id),
    ]


def _item_title_body(layout_id: str, item: Mapping, prefix: str) -> list[SlotBinding]:
    source_id = f"item:{item['id']}"
    title = str(item.get("title") or "")
    body = str(item.get("body") or "")
    return [
        _fact(layout_id, f"{prefix}-title", "title", title, title, source_id, "title", source_id),
        _fact(layout_id, f"{prefix}-body", "body", body, body, source_id, "body", source_id),
    ]


def _checklist_bindings(slide: Mapping, selection) -> list[SlotBinding]:
    layout_id = selection.layout_id
    items = _prepared_items(slide.get("items") or [])
    anchor = selection.anchor or {}
    source_item_id = anchor.get("source_item_id")
    item = next((entry for entry in items if entry.get("id") == source_item_id), items[0] if items else None)
    bindings = [_chrome(layout_id, "anchor", "shape", "", None, None)]
    if item is not None:
        source_id = f"item:{item['id']}"
        label = str(anchor.get("label") or "")
        title = str(item.get("title") or "")
        body = str(item.get("body") or "")
        statement = str(anchor.get("statement") or "")
        if label and _contained(label, title):
            bindings.append(_fact(layout_id, "anchor-label", "title", label, title, source_id, "title", source_id))
        elif label and _has_facts(label):
            bindings.append(_fact(layout_id, "anchor-label", "title", label, title, source_id, "title", source_id))
        else:
            bindings.append(_chrome(layout_id, "anchor-label", "text", label or title, source_id, "title"))
        value = str(anchor.get("value") or "")
        if value:
            if _contained(value, body) and _has_facts(body):
                bindings.append(_fact(layout_id, "anchor-value", "value", value, body, source_id, "body", source_id))
            elif _contained(value, title) and _has_facts(title):
                bindings.append(_fact(layout_id, "anchor-value", "value", value, title, source_id, "title", source_id))
            elif _has_facts(value) and (body or title):
                source_text = body or title
                field = "body" if body else "title"
                bindings.append(_fact(layout_id, "anchor-value", "value", value, source_text, source_id, field, source_id))
            elif not _has_facts(value):
                bindings.append(_chrome(layout_id, "anchor-value", "text", value, source_id, "title"))
        bindings.append(_fact(layout_id, "anchor-text", "body", statement or body, body, source_id, "body", source_id))
    for index, entry in enumerate(items, start=1):
        bindings.append(_chrome(layout_id, f"c{index}-idx", "text", f"{index:02d}", f"item:{entry['id']}", "index"))
        bindings.extend(_item_title_body(layout_id, entry, f"c{index}"))
    return bindings


def _claim_bindings(slide: Mapping, selection) -> list[SlotBinding]:
    layout_id = selection.layout_id
    items = _prepared_items(slide.get("items") or [])
    anchor = selection.anchor or {}
    claim_id = anchor.get("source_item_id")
    claim = next((item for item in items if item.get("id") == claim_id), items[0] if items else None)
    bindings: list[SlotBinding] = []
    if claim is not None:
        source_id = f"item:{claim['id']}"
        label = str(anchor.get("label") or claim.get("title") or "")
        bindings.append(_fact(layout_id, "claim-label", "title", label, str(claim.get("title") or ""), source_id, "title", source_id))
        claim_text = str(anchor.get("value") or "")
        if claim.get("evidence") and claim.get("body"):
            field, source = "body", str(claim.get("body") or "")
        elif claim.get("evidence"):
            field, source = "title", str(claim.get("title") or "")
        else:
            field, source = "body", str(claim.get("body") or claim_text)
        bindings.append(_fact(layout_id, "claim-text", "body", claim_text, source, source_id, field, source_id))
    bindings.append(_chrome(layout_id, "ev-label", "text", "依据", None, None))
    rows, primary_done = _claim_rows(items, claim_id)
    for index, row in enumerate(rows, start=1):
        source_id = f"item:{row['id']}"
        if row["title_source"] and _contained(row["title"], row["title_source"]):
            bindings.append(_fact(layout_id, f"e{index}-title", "title", row["title"], row["title_source"], source_id, "title", source_id))
        else:
            bindings.append(_chrome(layout_id, f"e{index}-title", "text", row["title"], source_id, "title"))
        bindings.append(_fact(layout_id, f"e{index}-body", "body", row["text"], row["source"], source_id, row["field"], source_id))
    if not primary_done and anchor.get("statement"):
        source_id = f"item:{claim['id']}" if claim is not None else "slide"
        bindings.append(
            _fact(layout_id, "e0-title", "title", str(anchor.get("statement_label") or ""), str(anchor.get("statement_label") or ""), source_id, "title", source_id)
        )
        bindings.append(
            _fact(layout_id, "e0-body", "body", str(anchor.get("statement") or ""), str(anchor.get("statement") or ""), source_id, "body", source_id)
        )
    return bindings


def _claim_rows(items: list[dict], claim_id) -> tuple[list[dict], bool]:
    rows = []
    primary_done = False
    for item in items:
        if item.get("id") == claim_id and item.get("evidence"):
            title = str(item.get("title") or "")
            rows.append(
                {
                    "id": item["id"],
                    "title": title or "依据",
                    "title_source": title,
                    "text": str(item.get("evidence") or ""),
                    "source": str(item.get("evidence") or ""),
                    "field": "evidence",
                }
            )
            primary_done = True
        elif item.get("id") != claim_id:
            text = item.get("evidence") or item.get("body") or item.get("value") or ""
            if text:
                if item.get("evidence"):
                    field = "evidence"
                elif item.get("value") and not item.get("body"):
                    field = "value"
                else:
                    field = "body"
                title = str(item.get("title") or "")
                rows.append(
                    {
                        "id": item["id"],
                        "title": title,
                        "title_source": title,
                        "text": str(text),
                        "source": str(item.get(field) or text),
                        "field": field,
                    }
                )
        elif item.get("id") == claim_id:
            primary_done = True
    return rows, primary_done


def _matrix_bindings(slide: Mapping, selection) -> list[SlotBinding]:
    layout_id = selection.layout_id
    items = _prepared_items(slide.get("items") or [])
    if len(items) != 4:
        raise ValueError("matrix_2x2 requires 4 items")
    axes = slide.get("axes") or {}
    rows = list(axes.get("rows") or ["", ""])
    cols = list(axes.get("cols") or ["", ""])
    bindings = [
        _chrome(layout_id, "mx-corner", "shape", "", None, None),
        _chrome(layout_id, "mx-c0", "shape", "", None, None),
        _chrome(layout_id, "mx-c1", "shape", "", None, None),
        _chrome(layout_id, "mx-r0", "shape", "", None, None),
        _chrome(layout_id, "mx-r1", "shape", "", None, None),
        _chrome(layout_id, "mx-c0t", "text", str(cols[0]), "axis:col:0", "cols"),
        _chrome(layout_id, "mx-c1t", "text", str(cols[1]), "axis:col:1", "cols"),
        _chrome(layout_id, "mx-r0t", "text", str(rows[0]), "axis:row:0", "rows"),
        _chrome(layout_id, "mx-r1t", "text", str(rows[1]), "axis:row:1", "rows"),
    ]
    for index, item in enumerate(items):
        bindings.extend(_item_title_body(layout_id, item, f"x{index}"))
    return bindings


def _algorithm_bindings(slide: Mapping, selection) -> list[SlotBinding]:
    layout_id = selection.layout_id
    prepared = _prepared_nodes(slide.get("nodes") or [])
    nodes = {node["id"]: node for node in prepared}
    edges = list(slide.get("edges") or [])
    decision = next((node for node in nodes.values() if node.get("type") == "decision"), None)
    start = next((node for node in nodes.values() if node.get("type") == "start"), None)
    yes_edge = next((edge for edge in edges if edge.get("from") == (decision or {}).get("id") and edge.get("label") == "是"), None)
    no_edge = next((edge for edge in edges if edge.get("from") == (decision or {}).get("id") and edge.get("label") == "否"), None)
    bindings: list[SlotBinding] = []
    if decision and yes_edge and no_edge:
        if start:
            bindings.extend(_node_bindings(layout_id, start))
            bindings.append(_chrome(layout_id, "stem-start", "line", "", None, None))
        bindings.extend(_node_bindings(layout_id, decision))
        bindings.append(_chrome(layout_id, "stem-decision", "line", "", None, None))
        bindings.append(_chrome(layout_id, "bridge", "line", "", None, None))
        yes_nodes = _chain(yes_edge["to"], edges, nodes)
        no_nodes = _chain(no_edge["to"], edges, nodes)
        bindings.extend(_arm_bindings(layout_id, "yes", str(yes_edge.get("label") or ""), yes_edge, yes_nodes))
        bindings.extend(_arm_bindings(layout_id, "no", str(no_edge.get("label") or ""), no_edge, no_nodes))
        return bindings
    for index, node in enumerate(prepared):
        if index:
            bindings.append(_chrome(layout_id, f"stem-{index}", "line", "", None, None))
        bindings.extend(_node_bindings(layout_id, node))
    return bindings


def _chain(start_id: str, edges: list, nodes: dict) -> list[dict]:
    ordered = []
    seen = set()
    current = start_id
    while current and current not in seen and current in nodes:
        seen.add(current)
        ordered.append(nodes[current])
        current = next((edge.get("to") for edge in edges if edge.get("from") == current), None)
    return ordered


def _arm_bindings(layout_id: str, name: str, label: str, edge: Mapping, nodes: list[dict]) -> list[SlotBinding]:
    source_id = f"edge:{edge.get('from')}->{edge.get('to')}"
    bindings = [
        _chrome(layout_id, f"stem-{name}", "line", "", None, None),
        _binding(
            slot_id=f"label-{name}",
            role="edge",
            kind="text",
            layout_id=layout_id,
            display_text=label,
            source_text=str(edge.get("label") or ""),
            source_id=source_id,
            source_field="label",
            pair_id=None,
            fact_bearing=False,
        ),
    ]
    for index, node in enumerate(nodes):
        if index:
            bindings.append(_chrome(layout_id, f"stem-{name}-{index}", "line", "", None, None))
        bindings.extend(_node_bindings(layout_id, node))
    return bindings


def _node_bindings(layout_id: str, node: Mapping) -> list[SlotBinding]:
    source_id = f"node:{node['id']}"
    pair_id = source_id
    kind = node.get("type") or "action"
    chip = {"start": "起始", "decision": "判定", "action": "处置", "exclude": "排除"}.get(kind, "处置")
    bindings = [
        _chrome(layout_id, str(node["id"]), "shape", "", source_id, "node"),
        _binding(
            slot_id=f"{node['id']}-chip",
            role="chip",
            kind="text",
            layout_id=layout_id,
            display_text=chip,
            source_text=chip,
            source_id=source_id,
            source_field="chip",
            pair_id=None,
            fact_bearing=False,
        ),
        _fact(layout_id, f"{node['id']}-title", "title", str(node.get("title") or ""), str(node.get("title") or ""), source_id, "title", pair_id),
    ]
    body = str(node.get("body") or "")
    if body:
        bindings.append(_fact(layout_id, f"{node['id']}-body", "body", body, body, source_id, "body", pair_id))
    for index, line in enumerate(node.get("lines") or [], start=1):
        text = str(line)
        bindings.append(_fact(layout_id, f"{node['id']}-line{index}", "line", text, text, source_id, f"line{index}", pair_id))
    return bindings


def _table_bindings(slide: Mapping, selection) -> list[SlotBinding]:
    layout_id = selection.layout_id
    table = slide.get("table") or {}
    columns = list(table.get("columns") or [])
    rows = list(table.get("rows") or [])
    bindings = [_chrome(layout_id, "table", "shape", "", "table", "table")]
    for index, name in enumerate(columns):
        bindings.append(_chrome(layout_id, f"th-{index}", "text", str(name), f"column:{index}", "columns"))
    for r_index, row in enumerate(rows):
        label = str(row.get("label") or "")
        bindings.append(_chrome(layout_id, f"r{r_index}-h", "text", label, f"row:{r_index}", "label"))
        for c_index, value in enumerate(row.get("cells") or [], start=1):
            text = str(value)
            source_id = f"cell:{r_index}:{c_index}"
            bindings.append(_fact(layout_id, f"r{r_index}-c{c_index}", "cell", text, text, source_id, "text", source_id))
    caption = str(table.get("caption") or "")
    if caption:
        bindings.append(_chrome(layout_id, "caption", "text", caption, "table", "caption"))
    return bindings


def emit_fact_value(verdict: SlotVerdict) -> bool:
    """A value slot is drawn only when the fact gate admitted a slice."""

    if verdict.role != "value" or not verdict.fact_bearing:
        return True
    return verdict.status == "ACCEPTED"


def emit_on_screen(verdict: SlotVerdict) -> bool:
    """Fact text is drawn only when the gate did not reject or hold it.

    ``REJECTED`` and ``NEEDS_REVIEW`` stay off the slide for every role.
    A value slot still needs an admitted slice. Chrome, and verbatim prose
    with no fact slice, still render.
    """

    if verdict.status in {"REJECTED", "NEEDS_REVIEW"}:
        return False
    return emit_fact_value(verdict)


def measured_text(slot: Mapping) -> str:
    """Text a measured slot may draw. The template gate is not optional here."""

    text = str(slot.get("text") or "").strip()
    status = str(slot.get("status") or "")
    if status in {"REJECTED", "NEEDS_REVIEW"}:
        return ""
    if str(slot.get("fact") or "") == "1" and str(slot.get("role") or "") == "value" and status != "ACCEPTED":
        return ""
    return text
