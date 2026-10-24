"""Slot-pack contract: load manifest, validate fills, report capacity / overflow."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import pharma

HERE = Path(__file__).parent
MANIFEST_PATH = HERE / "manifest.json"

# Families whose variant is derived from a list length when omitted.
_CAPACITY_LIST_KEY = {
    "key_points": "items",
    "flow": "nodes",
    "timeline": "nodes",
}


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def inches_to_px(zone: dict, dpi: float = 96.0) -> dict[str, float]:
    return {k: round(float(zone[k]) * dpi, 2) for k in ("x", "y", "w", "h")}


def family_spec(family: str, manifest: dict | None = None) -> dict:
    m = manifest or load_manifest()
    fam = m["families"].get(family)
    if not fam:
        raise KeyError(f"未知版式族：{family}")
    return fam


def _capacity_count(family: str, fill: dict) -> int | None:
    """Item/node/row count used to auto-pick a capacity variant."""
    if family == "key_points":
        items = fill.get("items")
        return len(items) if isinstance(items, list) else None
    if family in ("flow", "timeline"):
        nodes = fill.get("nodes")
        return len(nodes) if isinstance(nodes, list) else None
    if family == "comparison":
        # dual_column: max(left, right); table_2n: rows
        rows = fill.get("rows")
        if isinstance(rows, list) and rows:
            return len(rows)
        left = fill.get("left_items")
        right = fill.get("right_items")
        n_l = len(left) if isinstance(left, list) else 0
        n_r = len(right) if isinstance(right, list) else 0
        if n_l or n_r:
            return max(n_l, n_r)
        return None
    return None


def resolve_variant(family: str, variant: str | None, item_count: int | None = None,
                    manifest: dict | None = None, *, fill: dict | None = None) -> str:
    """Pick a declared variant; for capacity families, derive from item/node count when omitted."""
    fam = family_spec(family, manifest)
    variants = list(fam.get("variants") or ["default"])
    capacity = fam.get("capacity") or {}

    if family == "key_points":
        if variant:
            if variant not in variants:
                raise ValueError(f"key_points 变体无效：{variant}（可用：{', '.join(variants)}）")
            need = capacity.get(variant)
            if item_count is not None and need is not None and item_count > need:
                raise ValueError(
                    f"key_points/{variant} 容量为 {need}，收到 {item_count} 条；请拆页或改用更大变体"
                )
            if item_count is not None and need is not None and item_count < 1:
                raise ValueError("key_points 至少需要 1 条要点")
            return variant
        if item_count is None:
            return "cards_3"
        for name in ("cards_3", "cards_4", "cards_6"):
            if name in capacity and item_count <= capacity[name]:
                return name
        raise ValueError(
            f"key_points 容量上限为 {max(capacity.values())}，收到 {item_count} 条；请拆页"
        )

    if family == "flow":
        if variant:
            if variant not in variants:
                raise ValueError(f"flow 变体无效：{variant}（可用：{', '.join(variants)}）")
            need = capacity.get(variant)
            if item_count is not None and need is not None and item_count > need:
                raise ValueError(
                    f"flow/{variant} 容量为 {need}，收到 {item_count} 个节点；请拆页或改用更大变体"
                )
            return variant
        if item_count is None:
            return "horizontal_4"
        # Prefer horizontal; vertical_4 only when explicitly requested
        for name in ("horizontal_4", "horizontal_5", "horizontal_6"):
            if name in capacity and item_count <= capacity[name]:
                return name
        raise ValueError(
            f"flow 容量上限为 {max(v for k, v in capacity.items() if k.startswith('horizontal'))}，"
            f"收到 {item_count} 个节点；请拆页"
        )

    if family == "timeline":
        if variant:
            if variant not in variants:
                raise ValueError(f"timeline 变体无效：{variant}（可用：{', '.join(variants)}）")
            need = capacity.get(variant)
            if item_count is not None and need is not None and item_count > need:
                raise ValueError(
                    f"timeline/{variant} 容量为 {need}，收到 {item_count} 个节点；请拆页或改用更大变体"
                )
            return variant
        if item_count is None:
            return "nodes_4"
        for name in ("nodes_4", "nodes_6"):
            if name in capacity and item_count <= capacity[name]:
                return name
        raise ValueError(
            f"timeline 容量上限为 {max(capacity.values())}，收到 {item_count} 个节点；请拆页"
        )

    if family == "comparison":
        if variant:
            if variant not in variants:
                raise ValueError(f"comparison 变体无效：{variant}（可用：{', '.join(variants)}）")
            need = capacity.get(variant)
            if item_count is not None and need is not None and item_count > need:
                raise ValueError(
                    f"comparison/{variant} 容量为 {need}，收到 {item_count} 条；请拆页或改用更大变体"
                )
            return variant
        # Prefer table_2n when rows are provided; else dual_column
        if fill and isinstance(fill.get("rows"), list) and fill.get("rows"):
            n = len(fill["rows"])
            if n > capacity.get("table_2n", 8):
                raise ValueError(
                    f"comparison/table_2n 容量为 {capacity.get('table_2n')}，收到 {n} 行；请拆页"
                )
            return "table_2n"
        if item_count is None:
            return "dual_column"
        if item_count > capacity.get("dual_column", 6):
            raise ValueError(
                f"comparison/dual_column 容量为 {capacity.get('dual_column')}，收到 {item_count} 条；请拆页"
            )
        return "dual_column"

    if variant is None:
        return variants[0]
    if variant not in variants:
        raise ValueError(f"{family} 变体无效：{variant}")
    return variant


def _len(text: Any) -> int:
    return len(str(text or "").strip())


def _check_text(slot_name: str, value: Any, rule: dict, errors: list[str]) -> None:
    if value is None or str(value).strip() == "":
        if rule.get("required"):
            errors.append(f"{slot_name}：必填")
        return
    n = _len(value)
    max_c = rule.get("max_chars")
    if max_c is not None and n > max_c:
        errors.append(f"{slot_name}：{n} 字超过容量 {max_c}（overflow={rule.get('overflow')}）")


def _check_item_list(name: str, items: Any, item_rule: dict, errors: list[str],
                     *, required: bool, cap: int | None = None) -> None:
    if not isinstance(items, list) or not items:
        if required:
            errors.append(f"{name}：必填且至少 1 条")
        return
    if cap is not None and len(items) > cap:
        errors.append(f"{name}：{len(items)} 条超过容量 {cap}")
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            # Allow bare strings for comparison bullets
            if isinstance(it, str) and "text" in item_rule:
                _check_text(f"{name}[{i}].text", it, item_rule["text"], errors)
                continue
            errors.append(f"{name}[{i}]：须为对象")
            continue
        for field, rule in item_rule.items():
            _check_text(f"{name}[{i}].{field}", it.get(field), rule, errors)


def validate_fill(family: str, fill: dict, variant: str | None = None,
                  manifest: dict | None = None) -> dict:
    """Validate a slot fill against the manifest. Returns {ok, variant, errors, warnings}."""
    m = manifest or load_manifest()
    fam = family_spec(family, m)
    errors: list[str] = []
    warnings: list[str] = []
    slots = fam.get("slots") or {}

    item_count = _capacity_count(family, fill)
    try:
        chosen = resolve_variant(
            family, variant or fill.get("variant"), item_count, m, fill=fill
        )
    except (ValueError, KeyError) as e:
        return {"ok": False, "variant": None, "errors": [str(e)], "warnings": []}

    cap = (fam.get("capacity") or {}).get(chosen)

    # Scalar slots (skip list slots handled below)
    list_slot_names = {
        "items", "nodes", "left_items", "right_items", "rows",
        "no_items", "follow_nodes", "left_nodes", "right_nodes",
    }
    for name, rule in slots.items():
        if name in list_slot_names:
            continue
        if isinstance(rule, dict) and "item" in rule:
            continue
        _check_text(name, fill.get(name), rule, errors)

    if family == "key_points" and chosen == pharma.EVIDENCE_VARIANT:
        pharma.validate(pharma.EVIDENCE_VARIANT, fill, errors, warnings, variant=chosen)

    elif family == "key_points":
        item_rule = (slots.get("items") or {}).get("item") or {}
        _check_item_list("items", fill.get("items"), item_rule, errors, required=True, cap=cap)

    elif family in pharma.FAMILIES:
        pharma.validate(family, fill, errors, warnings, variant=chosen)

    elif family == "comparison":
        if chosen == "table_2n":
            row_rule = (slots.get("rows") or {}).get("item") or {}
            _check_item_list("rows", fill.get("rows"), row_rule, errors, required=True, cap=cap)
            # labels still required as column headers
            _check_text("left_label", fill.get("left_label"), slots.get("left_label") or {}, errors)
            _check_text("right_label", fill.get("right_label"), slots.get("right_label") or {}, errors)
        else:
            left_rule = (slots.get("left_items") or {}).get("item") or {}
            right_rule = (slots.get("right_items") or {}).get("item") or {}
            _check_item_list("left_items", fill.get("left_items"), left_rule, errors,
                             required=True, cap=cap)
            _check_item_list("right_items", fill.get("right_items"), right_rule, errors,
                             required=True, cap=cap)

    elif family in ("flow", "timeline"):
        node_rule = (slots.get("nodes") or {}).get("item") or {}
        _check_item_list("nodes", fill.get("nodes"), node_rule, errors, required=True, cap=cap)

    elif family == "algorithm_tree":
        no_rule = (slots.get("no_items") or {}).get("item") or {}
        _check_item_list("no_items", fill.get("no_items"), no_rule, errors, required=True, cap=8)
        follow_rule = (slots.get("follow_nodes") or {}).get("item") or {}
        if fill.get("follow_nodes"):
            _check_item_list("follow_nodes", fill.get("follow_nodes"), follow_rule, errors,
                             required=False, cap=cap)

    elif family == "assessment_matrix":
        # Scalar groups validated via generic scalar loop; nothing list-based.
        pass

    elif family == "dual_path_tree":
        left_rule = (slots.get("left_nodes") or {}).get("item") or {}
        right_rule = (slots.get("right_nodes") or {}).get("item") or {}
        # kind/branch are optional soft fields — only enforce heading
        soft_left = {k: v for k, v in left_rule.items() if k in ("heading", "body")}
        soft_right = {k: v for k, v in right_rule.items() if k in ("heading", "body")}
        _check_item_list("left_nodes", fill.get("left_nodes"), soft_left or left_rule, errors,
                         required=True, cap=cap)
        _check_item_list("right_nodes", fill.get("right_nodes"), soft_right or right_rule, errors,
                         required=True, cap=cap)

    if family in ("cover", "section") and not fill.get("title"):
        if not any(e.startswith("title：") for e in errors):
            errors.append("title：必填")

    # Soft warning when near capacity
    for name, rule in slots.items():
        if name in list_slot_names or (isinstance(rule, dict) and "item" in rule):
            continue
        max_c = rule.get("max_chars")
        n = _len(fill.get(name))
        if max_c and n and n > max_c * 0.9 and n <= max_c:
            warnings.append(f"{name}：接近容量（{n}/{max_c}）")

    return {"ok": not errors, "variant": chosen, "errors": errors, "warnings": warnings}


def zone_map_px(family: str, manifest: dict | None = None) -> dict[str, dict[str, float]]:
    m = manifest or load_manifest()
    fam = family_spec(family, m)
    dpi = float(m["canvas"]["dpi"])
    return {name: inches_to_px(z, dpi) for name, z in (fam.get("zones_in") or {}).items()}
