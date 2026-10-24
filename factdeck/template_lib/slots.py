"""Slot-pack contract: load manifest, validate fills, report capacity / overflow."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
MANIFEST_PATH = HERE / "manifest.json"


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


def resolve_variant(family: str, variant: str | None, item_count: int | None = None,
                    manifest: dict | None = None) -> str:
    """Pick a declared variant; for key_points, derive from item count when omitted."""
    fam = family_spec(family, manifest)
    variants = list(fam.get("variants") or ["default"])
    if family == "key_points":
        capacity = fam.get("capacity") or {}
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


def validate_fill(family: str, fill: dict, variant: str | None = None,
                  manifest: dict | None = None) -> dict:
    """Validate a slot fill against the manifest. Returns {ok, variant, errors, warnings}."""
    m = manifest or load_manifest()
    fam = family_spec(family, m)
    errors: list[str] = []
    warnings: list[str] = []
    slots = fam.get("slots") or {}

    items = fill.get("items")
    item_count = len(items) if isinstance(items, list) else None
    try:
        chosen = resolve_variant(family, variant or fill.get("variant"), item_count, m)
    except (ValueError, KeyError) as e:
        return {"ok": False, "variant": None, "errors": [str(e)], "warnings": []}

    for name, rule in slots.items():
        if name == "items":
            continue
        _check_text(name, fill.get(name), rule, errors)

    if family == "key_points":
        item_rule = (slots.get("items") or {}).get("item") or {}
        if not isinstance(items, list) or not items:
            errors.append("items：必填且至少 1 条")
        else:
            cap = (fam.get("capacity") or {}).get(chosen)
            if cap is not None and len(items) > cap:
                errors.append(f"items：{len(items)} 条超过 {chosen} 容量 {cap}")
            for i, it in enumerate(items or []):
                if not isinstance(it, dict):
                    errors.append(f"items[{i}]：须为对象")
                    continue
                for field, rule in item_rule.items():
                    _check_text(f"items[{i}].{field}", it.get(field), rule, errors)

    if family == "cover" and not fill.get("title"):
        errors.append("title：必填")
    if family == "section" and not fill.get("title"):
        errors.append("title：必填")

    # Soft warning when near capacity (optional shrink path)
    for name, rule in slots.items():
        if name == "items":
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
