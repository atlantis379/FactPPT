"""Pick a slide layout from the content relation.

Parallel bullets are not a card wall. ``key_points`` (one equal floating card
per item, including 5- and 6-column rows) is retired. A body slide gets one
anchor — a hero number, a takeaway, or a relation diagram — and the rest is
set in ruled columns, a checklist, a matrix, or evidence lines.

An anchor fill that is not the source field is kept only by ``screen_fill``.
That calls the fact gate. A clip the gate does not admit is not the anchor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LAYOUTS = (
    "metric_row",
    "checklist",
    "matrix_2x2",
    "claim_evidence",
    "algorithm_tree",
    "data_table_highlight",
    "comparison",
    "cover",
    "section",
)

RETIRED_LAYOUTS = frozenset({"key_points", "equal_card_wall", "card_columns"})

RELATION_ALIAS = {
    "并列要点": "parallel_fallback",
    "并列要点（兜底）": "parallel_fallback",
    "parallel_fallback": "parallel_fallback",
    "key_points": "parallel_fallback",
    "metric": "metric",
    "指标": "metric",
    "checklist": "checklist",
    "清单": "checklist",
    "步骤序列": "sequence",
    "sequence": "sequence",
    "matrix": "matrix",
    "矩阵": "matrix",
    "claim_evidence": "claim_evidence",
    "主张与依据": "claim_evidence",
    "threshold": "threshold",
    "条件/阈值判断": "threshold",
    "table": "table",
    "多行×多列数据": "table",
    "comparison": "comparison",
    "A vs B 对照": "comparison",
    "对照": "comparison",
}

METRIC_VALUE = re.compile(
    r"^\s*[<>≤≥＞＜]?\s*\d+(?:\.\d+)?"
    r"(?:\s*[-–—~～]\s*\d+(?:\.\d+)?)?"
    r"\s*(?:%|％|岁|月|周|天|个|倍)?\s*$"
)
ACTION_PREFIX = re.compile(r"^(?:确认|检查|避免|采取|接种|切换|戒烟|停用|启用|评估|复查|随访|记录|教育|建议)")
DURATION = re.compile(r"(?:连续\s*)?(\d+)\s*(个月|周|天|年)")
DEBUG_TOKEN = re.compile(
    r"(?:[0-9a-f]{8,}|\bf\d{3,}\b|\bd2\.bu\.[A-Za-z0-9]+\b|\bex_[A-Za-z0-9._]+\b)",
    re.I,
)

# A repeated layout may yield to another reading only when the scores are this close.
RHYTHM_GAP = 15


@dataclass(frozen=True)
class Selection:
    layout_id: str
    variant: str
    reason: str
    columns: int
    anchor: dict

    def to_dict(self) -> dict:
        return {
            "layout_id": self.layout_id,
            "variant": self.variant,
            "reason": self.reason,
            "columns": self.columns,
            "anchor": self.anchor,
        }


@dataclass(frozen=True)
class _Candidate:
    layout_id: str
    variant: str
    score: int
    reason: str
    columns: int
    anchor: dict


def clean_source(text: str) -> str:
    """Drop debug ids and source hashes. Keep the human title."""
    cleaned = DEBUG_TOKEN.sub("", text or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s*；\s*", "；", cleaned)
    return cleaned.strip(" ；;")


def is_metric_item(item: dict) -> bool:
    if item.get("kind") == "metric":
        return True
    value = str(item.get("value") or "").strip()
    if value and METRIC_VALUE.match(value):
        return True
    body = str(item.get("body") or "").strip()
    return bool(body and len(body) <= 16 and METRIC_VALUE.match(body))


def metric_display(item: dict) -> str:
    value = str(item.get("value") or "").strip()
    if value:
        return value
    body = str(item.get("body") or "").strip()
    if is_metric_item(item):
        return body
    return value or body


def is_action_item(item: dict) -> bool:
    if item.get("kind") == "action":
        return True
    title = str(item.get("title") or "")
    body = str(item.get("body") or "")
    return bool(ACTION_PREFIX.search(title) or ACTION_PREFIX.search(body))


def normalize_relation(slide: dict) -> str | None:
    raw = slide.get("relation")
    if raw in RELATION_ALIAS:
        return RELATION_ALIAS[raw]
    if raw in (None, ""):
        proposed = slide.get("proposed") or ""
        if proposed in RELATION_ALIAS:
            return RELATION_ALIAS[proposed]
        if slide.get("items"):
            return "parallel_fallback"
        return None
    if isinstance(raw, str) and raw in RELATION_ALIAS:
        return RELATION_ALIAS[raw]
    return "parallel_fallback"


def _items(slide: dict) -> list[dict]:
    items = slide.get("items") or []
    return [item for item in items if isinstance(item, dict)]


def _with_ids(items: list[dict]) -> list[dict]:
    ready = []
    for index, item in enumerate(items, start=1):
        copy = dict(item)
        copy.setdefault("id", f"item-{index}")
        ready.append(copy)
    return ready


def _statement_item(slide: dict, items: list[dict], hero: dict | None) -> dict | None:
    title = str(slide.get("title") or "")
    others = [item for item in items if item is not hero and not is_metric_item(item) and item.get("body")]
    for item in others:
        if item.get("title") == title:
            return item
    if not others:
        return None
    return max(others, key=lambda item: len(str(item.get("body") or "")))


def _screened_metric_value(item: dict) -> str:
    """A value that is not the body must be a gate-admitted slice of that body."""

    value = str(item.get("value") or "").strip()
    body = str(item.get("body") or "").strip()
    if value and body:
        from factdeck.slots import screen_fill

        return screen_fill(body, value)
    return metric_display(item)


def _metric_anchor(slide: dict, items: list[dict], variant: str) -> dict:
    metrics = [item for item in items if is_metric_item(item)]
    hero = metrics[0] if metrics else (items[0] if items else {})
    statement = _statement_item(slide, items, hero if metrics else None)
    return {
        "kind": "metric",
        "label": hero.get("title") or slide.get("title") or "",
        "value": _screened_metric_value(hero) if hero else "",
        "statement": (statement or {}).get("body") or "",
        "statement_label": (statement or {}).get("title") or "",
        "source_item_id": hero.get("id"),
        "statement_item_id": (statement or {}).get("id"),
        "variant": variant,
    }


def _checklist_anchor(slide: dict, items: list[dict]) -> dict:
    for item in items:
        blob = f"{item.get('title') or ''}{item.get('body') or ''}"
        match = DURATION.search(blob)
        if match:
            body = str(item.get("body") or "")
            title = str(item.get("title") or "")
            clip = f"{match.group(1)}{match.group(2)}"
            source = body if DURATION.search(body) else title
            from factdeck.slots import screen_fill

            # A digit-unit clip such as 「3个月」 drops 连续 / 及以上. The
            # fact gate is the only way that clip becomes anchor text.
            value = screen_fill(source, clip)
            return {
                "kind": "metric",
                "label": item.get("title") or slide.get("title") or "",
                "value": value,
                "statement": item.get("body") or "",
                "statement_label": item.get("title") or "",
                "source_item_id": item.get("id"),
                "statement_item_id": item.get("id"),
            }
    lead = items[0] if items else {}
    return {
        "kind": "statement",
        "label": slide.get("kicker") or "",
        "value": slide.get("title") or "",
        "statement": lead.get("body") or "",
        "statement_label": lead.get("title") or "",
        "source_item_id": lead.get("id"),
        "statement_item_id": lead.get("id"),
    }


def _claim_anchor(slide: dict, items: list[dict]) -> dict:
    evidenced = [item for item in items if item.get("evidence")]
    claim = evidenced[0] if evidenced else (items[0] if items else {})
    evidence_text = claim.get("evidence") or claim.get("body") or ""
    claim_text = claim.get("body") if claim.get("evidence") else (claim.get("title") or slide.get("title") or "")
    if claim.get("evidence") and claim.get("body"):
        claim_text = claim.get("body")
    return {
        "kind": "statement",
        "label": claim.get("title") or slide.get("title") or "",
        "value": claim_text,
        "statement": evidence_text,
        "statement_label": "依据",
        "source_item_id": claim.get("id"),
        "statement_item_id": claim.get("id"),
    }


def _guard(selection: Selection, item_count: int) -> Selection:
    if selection.layout_id in RETIRED_LAYOUTS or selection.layout_id not in LAYOUTS:
        raise RuntimeError(f"retired or unknown layout: {selection.layout_id}")
    if item_count >= 4 and selection.layout_id in {"metric_row", "checklist", "claim_evidence", "matrix_2x2"}:
        if selection.columns >= item_count or selection.columns > 3:
            raise RuntimeError(
                f"equal column wall: {item_count} items would use {selection.columns} columns"
            )
    if selection.layout_id == "metric_row" and selection.columns > 3:
        raise RuntimeError("metric row is capped at 3 figures")
    return selection


def _finish(ranked: list[_Candidate], previous: str | None, item_count: int) -> Selection:
    if not ranked:
        raise RuntimeError("no layout candidate")
    best = ranked[0]
    reason = best.reason
    if previous and best.layout_id == previous:
        alternate = next((item for item in ranked[1:] if best.score - item.score <= RHYTHM_GAP), None)
        if alternate is not None:
            best = alternate
            reason = f"{best.reason}；与上一页相同，改用相近关系的版式"
        else:
            reason = f"{reason}；与上一页相同，无合格替代，保留"
    selection = Selection(best.layout_id, best.variant, reason, best.columns, best.anchor)
    return _guard(selection, item_count)


def _note_columns(count: int) -> int:
    # Three or fewer notes stay one wide column so Chinese is not sliced into a short grid.
    if count <= 3:
        return 1
    return 2


def select_layout(slide: dict, previous: str | None = None) -> Selection:
    """Return the layout for this slide.

    ``previous`` is the layout id of the prior body slide. A repeat is kept
    when no equally fitting layout exists. It is never broken by falling
    back to equal-height cards.
    """
    role = slide.get("role") or "body"
    items = _with_ids(_items(slide))
    relation = normalize_relation(slide)
    nodes = slide.get("nodes") or []
    table = slide.get("table")
    axes = slide.get("axes") or {}
    count = len(items)

    if role == "cover":
        return _finish([_Candidate("cover", "cover", 100, "封面不参与要点分栏", 1, {"kind": "cover"})], previous, 0)
    if role == "section":
        return _finish([_Candidate("section", "section", 100, "章节页不参与要点分栏", 1, {"kind": "section"})], previous, 0)

    if nodes or (relation == "threshold" and nodes):
        anchor = {"kind": "diagram", "label": slide.get("title") or "", "value": "", "source_item_id": None}
        reason = "条件/阈值判断用固定节点的决策图，不降级为要点卡片"
        if slide.get("proposed") == "key_points":
            reason += "（拒绝由算法树降级为 key_points）"
        return _finish([_Candidate("algorithm_tree", "guideline", 100, reason, 0, anchor)], previous, 0)

    if table or relation == "table":
        columns = table.get("columns") if isinstance(table, dict) else []
        highlight = ""
        if isinstance(table, dict) and table.get("highlight_columns") and columns:
            index = table["highlight_columns"][0]
            if 0 <= index < len(columns):
                highlight = str(columns[index])
        anchor = {"kind": "table", "label": highlight or (slide.get("title") or ""), "value": "", "source_item_id": None}
        return _finish(
            [_Candidate("data_table_highlight", "clinical", 100, "多行对照用临床比较表，按列意宽并高亮关键列", 1, anchor)],
            previous,
            0,
        )

    if relation == "comparison":
        anchor = {"kind": "diagram", "label": slide.get("title") or "", "value": "", "source_item_id": None}
        return _finish(
            [_Candidate("comparison", "two_column", 100, "A/B 对照保持对照页", 2, anchor)],
            previous,
            count,
        )

    if relation == "matrix" or (axes.get("rows") and axes.get("cols") and count == 4):
        anchor = {
            "kind": "diagram",
            "label": " / ".join(str(name) for name in axes.get("cols") or []),
            "value": " / ".join(str(name) for name in axes.get("rows") or []),
            "source_item_id": None,
        }
        return _finish(
            [_Candidate("matrix_2x2", "axes", 100, "四项并且给出行列轴，用 2×2 矩阵而不是四张卡片", 2, anchor)],
            previous,
            count,
        )

    if relation == "claim_evidence":
        return _finish(
            [_Candidate("claim_evidence", "lead", 100, "主张与依据分栏，依据降到次级", 2, _claim_anchor(slide, items))],
            previous,
            count,
        )

    if relation == "metric":
        variant = "band" if 1 < count <= 3 else "hero"
        columns = min(3, count) if variant == "band" else 1
        return _finish(
            [_Candidate("metric_row", variant, 100, "数值关系用一行指标，最多三列，共享基线", columns, _metric_anchor(slide, items, variant))],
            previous,
            count,
        )

    if relation in {"checklist", "sequence"}:
        columns = 1 if count <= 3 else 2
        variant = "sequence" if relation == "sequence" else "review"
        return _finish(
            [_Candidate("checklist", variant, 100, "步骤或复核清单用编号通栏，最多两列", columns, _checklist_anchor(slide, items))],
            previous,
            count,
        )

    # Parallel fallback: infer a relation. Never emit one card per bullet.
    metrics = [item for item in items if is_metric_item(item)]
    evidenced = [item for item in items if item.get("evidence")]
    actions = [item for item in items if is_action_item(item)]
    ranked: list[_Candidate] = []

    if evidenced and count and len(evidenced) / count >= 0.5:
        ranked.append(
            _Candidate(
                "claim_evidence",
                "lead",
                90,
                "过半条目带依据，主张与依据分栏",
                2,
                _claim_anchor(slide, items),
            )
        )
    if metrics and len(metrics) == count and count <= 3:
        ranked.append(
            _Candidate(
                "metric_row",
                "band" if count > 1 else "hero",
                92,
                "条目本身是数值，排成共享基线的指标行",
                min(3, count) if count > 1 else 1,
                _metric_anchor(slide, items, "band" if count > 1 else "hero"),
            )
        )
    elif metrics:
        anchor = _metric_anchor(slide, items, "hero_plus_notes")
        hidden = {anchor.get("source_item_id"), anchor.get("statement_item_id")}
        listed = len([item for item in items if item.get("id") not in hidden])
        ranked.append(
            _Candidate(
                "metric_row",
                "hero_plus_notes",
                85,
                "并列要点里有一个数值锚点，其余改为通栏说明，不再按条数等分卡片",
                _note_columns(listed),
                anchor,
            )
        )
    if evidenced and not any(item.layout_id == "claim_evidence" for item in ranked):
        ranked.append(
            _Candidate(
                "claim_evidence",
                "lead",
                78,
                "存在独立依据，升为主张与依据",
                2,
                _claim_anchor(slide, items),
            )
        )
    if actions or count >= 4 or count == 0:
        columns = 1 if count <= 3 else 2
        score = 70 if actions else 60
        reason = "并列动作改为清单" if actions else "并列要点改为清单，禁止按条数生成等分卡片"
        ranked.append(_Candidate("checklist", "review", score, reason, columns, _checklist_anchor(slide, items)))
    elif count:
        ranked.append(
            _Candidate(
                "checklist",
                "review",
                55,
                "少量定性要点用单栏清单，而不是等宽卡片",
                1,
                _checklist_anchor(slide, items),
            )
        )

    ranked.sort(key=lambda item: -item.score)
    return _finish(ranked, previous, count)
