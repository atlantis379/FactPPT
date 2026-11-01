"""Fill slot packs → normalized page models for HTML (and later native) render."""
from __future__ import annotations

from typing import Any

from . import pharma
from . import slots as slotmod
from .themes import get_theme


def _as_text_items(raw: list | None) -> list[dict[str, Any]]:
    """Normalize bullet lists that may be strings or {text: ...} dicts."""
    out = []
    for i, it in enumerate(raw or []):
        if isinstance(it, str):
            text = it.strip()
        elif isinstance(it, dict):
            text = (it.get("text") or "").strip()
        else:
            text = str(it or "").strip()
        out.append({"text": text, "index": i + 1})
    return out


def _text_em(text: str) -> float:
    """Width of a string in ems: CJK/full-width glyphs are 1 em, the rest about 0.56 em."""
    return sum(1.0 if ord(c) > 0x2E7F else 0.56 for c in text)


def _lines(text: str, width_px: float, pt: float) -> int:
    if not text:
        return 0
    per_line = max(1.0, width_px / (pt * 4 / 3))
    return max(1, -int(-_text_em(text) // per_line))


# Key-point type scale: the largest step whose tallest card fits the body zone.  Caps per column
# count keep narrow columns from breaking every few characters.
_KP_BODY_CAP = {1: 22, 2: 22, 3: 20, 4: 18, 5: 16, 6: 15}
_KP_HEAD_CAP = {1: 30, 2: 30, 3: 28, 4: 24, 5: 21, 6: 19}
_KP_STEPS = (22, 20, 18, 16, 15, 14, 13, 12)


def _kp_scale(items: list[dict[str, Any]], cols: int, body_h: float) -> dict[str, float]:
    """Font sizes and card height sized to the content, so light pages are not tall empty cards."""
    inner_w = (1228 - 8 - 20 * (cols - 1)) / cols - 48
    for body_pt in _KP_STEPS:
        if body_pt > _KP_BODY_CAP[cols]:
            continue
        head_pt = min(_KP_HEAD_CAP[cols], round(body_pt * 1.4))
        sub_pt = max(12, round(body_pt * 0.9))
        tallest = 0.0
        for it in items:
            h = 52.0 + 13 * 4 / 3 * 1.2 + 10  # padding + index/tag row
            h += _lines(it["heading"], inner_w, head_pt) * head_pt * 4 / 3 * 1.18 + 10
            if it["sub"]:
                h += _lines(it["sub"], inner_w, sub_pt) * sub_pt * 4 / 3 * 1.3 + 10
            if it["body"]:
                h += _lines(it["body"], inner_w, body_pt) * body_pt * 4 / 3 * 1.5
            tallest = max(tallest, h)
        if tallest <= body_h * 0.9 or body_pt == _KP_STEPS[-1]:
            card_h = min(body_h, max(tallest + 24, min(260.0, body_h)))
            return {"body_pt": body_pt, "head_pt": head_pt, "sub_pt": sub_pt, "card_h": round(card_h)}
    raise AssertionError("unreachable")


_CMP_STEPS = (20, 18, 16, 15, 14)


def _cmp_scale(left: list[dict[str, Any]], right: list[dict[str, Any]], body_h: float) -> dict[str, float]:
    """Bullet size and panel height for the two-column comparison, sized to the fuller side."""
    inner_w = (1228 - 8 - 48) / 2 - 44 - 20
    for pt in _CMP_STEPS:
        tallest = max(56 + 42 + sum(_lines(it["text"], inner_w, pt) * pt * 4 / 3 * 1.4 for it in side)
                      + 14 * max(len(side) - 1, 0) for side in (left, right))
        if tallest <= body_h * 0.9 or pt == _CMP_STEPS[-1]:
            return {"item_pt": pt, "col_h": round(min(body_h, max(tallest + 24, min(300.0, body_h))))}
    raise AssertionError("unreachable")


def normalize_fill(family: str, fill: dict, *, variant: str | None = None,
                   theme: str = "journal") -> dict[str, Any]:
    """Validate and normalize a fill into a page model ready for HTML render.

    Raises ValueError when the slot contract fails.
    """
    report = slotmod.validate_fill(family, fill, variant=variant)
    if not report["ok"]:
        raise ValueError("；".join(report["errors"]))
    tokens = get_theme(theme)
    zones = slotmod.zone_map_px(family)
    chosen = report["variant"]
    page: dict[str, Any] = {
        "id": fill.get("id") or f"tl-{family}",
        "layout": family,
        "family": family,
        "variant": chosen,
        "template_id": slotmod.family_spec(family)["template_id"],
        "theme_name": theme,
        "theme": tokens,
        "zones_px": zones,
        "artwork_paths": fill.get("artwork_paths") or [],  # stub: empty OK in v1
        "contract": report,
    }
    if family == "cover":
        page.update({
            "kicker": (fill.get("kicker") or "").strip(),
            "title": (fill.get("title") or "").strip(),
            "subtitle": (fill.get("subtitle") or "").strip(),
            "affiliation": (fill.get("affiliation") or "").strip(),
            "presenter": (fill.get("presenter") or "").strip(),
            "meta": (fill.get("meta") or "").strip(),
        })
    elif family == "section":
        number = fill.get("number")
        if number is None or str(number).strip() == "":
            number = "01"
        page.update({
            "number": str(number).strip().zfill(2)[:4],
            "title": (fill.get("title") or "").strip(),
            "subtitle": (fill.get("subtitle") or "").strip(),
        })
    elif family == "key_points" and chosen == pharma.EVIDENCE_VARIANT:
        page.update(pharma.normalize(pharma.EVIDENCE_VARIANT, fill, variant=chosen))
    elif family in pharma.FAMILIES:
        page.update(pharma.normalize(family, fill, variant=chosen))
    elif family == "key_points":
        items = []
        for i, it in enumerate(fill.get("items") or []):
            items.append({
                "tag": (it.get("tag") or "").strip(),
                "heading": (it.get("heading") or "").strip(),
                "sub": (it.get("sub") or "").strip(),
                "body": (it.get("body") or "").strip(),
                "index": i + 1,
            })
        takeaway = (fill.get("takeaway") or "").strip()
        body_h = zones["body_card"]["h"] - 12 - (70 if takeaway else 0)
        page.update({
            "section": (fill.get("section") or "").strip(),
            "title": (fill.get("title") or "").strip(),
            "items": items,
            "scale": _kp_scale(items, min(max(len(items), 1), 6), body_h),
            "takeaway": (fill.get("takeaway") or "").strip(),
            "source": (fill.get("source") or "").strip(),
            "page": str(fill.get("page") or "").strip(),
            "capacity": slotmod.family_spec(family).get("capacity", {}).get(chosen),
        })
    elif family == "comparison":
        rows = []
        for i, r in enumerate(fill.get("rows") or []):
            if isinstance(r, dict):
                rows.append({
                    "left": (r.get("left") or "").strip(),
                    "right": (r.get("right") or "").strip(),
                    "index": i + 1,
                })
        page.update({
            "section": (fill.get("section") or "").strip(),
            "title": (fill.get("title") or "").strip(),
            "left_label": (fill.get("left_label") or "").strip(),
            "right_label": (fill.get("right_label") or "").strip(),
            "left_items": _as_text_items(fill.get("left_items")),
            "scale": _cmp_scale(_as_text_items(fill.get("left_items")), _as_text_items(fill.get("right_items")),
                                zones["body_card"]["h"] - 12 - (70 if (fill.get("takeaway") or "").strip() else 0)),
            "right_items": _as_text_items(fill.get("right_items")),
            "rows": rows,
            "takeaway": (fill.get("takeaway") or "").strip(),
            "source": (fill.get("source") or "").strip(),
            "page": str(fill.get("page") or "").strip(),
            "capacity": slotmod.family_spec(family).get("capacity", {}).get(chosen),
        })
    elif family == "flow":
        nodes = []
        for i, it in enumerate(fill.get("nodes") or []):
            nodes.append({
                "tag": (it.get("tag") or "").strip(),
                "heading": (it.get("heading") or "").strip(),
                "body": (it.get("body") or "").strip(),
                "index": i + 1,
            })
        page.update({
            "section": (fill.get("section") or "").strip(),
            "title": (fill.get("title") or "").strip(),
            "nodes": nodes,
            "orientation": "vertical" if str(chosen).startswith("vertical") else "horizontal",
            "takeaway": (fill.get("takeaway") or "").strip(),
            "source": (fill.get("source") or "").strip(),
            "page": str(fill.get("page") or "").strip(),
            "capacity": slotmod.family_spec(family).get("capacity", {}).get(chosen),
        })
    elif family == "timeline":
        nodes = []
        for i, it in enumerate(fill.get("nodes") or []):
            nodes.append({
                "label": (it.get("label") or "").strip(),
                "heading": (it.get("heading") or "").strip(),
                "body": (it.get("body") or "").strip(),
                "index": i + 1,
            })
        page.update({
            "section": (fill.get("section") or "").strip(),
            "title": (fill.get("title") or "").strip(),
            "nodes": nodes,
            "takeaway": (fill.get("takeaway") or "").strip(),
            "source": (fill.get("source") or "").strip(),
            "page": str(fill.get("page") or "").strip(),
            "capacity": slotmod.family_spec(family).get("capacity", {}).get(chosen),
        })
    elif family == "algorithm_tree":
        follow = []
        for i, it in enumerate(fill.get("follow_nodes") or []):
            follow.append({
                "heading": (it.get("heading") or "").strip(),
                "body": (it.get("body") or "").strip(),
                "index": i + 1,
            })
        page.update({
            "section": (fill.get("section") or "").strip(),
            "title": (fill.get("title") or "").strip(),
            "figure": (fill.get("figure") or "").strip(),
            "takeaway": (fill.get("takeaway") or "").strip(),
            "source": (fill.get("source") or "").strip(),
            "page": str(fill.get("page") or "").strip(),
            "start_heading": (fill.get("start_heading") or "").strip(),
            "start_body": (fill.get("start_body") or "").strip(),
            "decision_heading": (fill.get("decision_heading") or "").strip(),
            "decision_threshold": (fill.get("decision_threshold") or "").strip(),
            "yes_label": (fill.get("yes_label") or "").strip(),
            "yes_heading": (fill.get("yes_heading") or "").strip(),
            "yes_body": (fill.get("yes_body") or "").strip(),
            "no_label": (fill.get("no_label") or "").strip(),
            "no_heading": (fill.get("no_heading") or "").strip(),
            "no_items": _as_text_items(fill.get("no_items")),
            "follow_nodes": follow,
            "capacity": slotmod.family_spec(family).get("capacity", {}).get(chosen),
        })
    elif family == "assessment_matrix":
        page.update({
            "section": (fill.get("section") or "").strip(),
            "title": (fill.get("title") or "").strip(),
            "figure": (fill.get("figure") or "").strip(),
            "takeaway": (fill.get("takeaway") or "").strip(),
            "source": (fill.get("source") or "").strip(),
            "page": str(fill.get("page") or "").strip(),
            "x_left": (fill.get("x_left") or "").strip(),
            "x_right": (fill.get("x_right") or "").strip(),
            "y_top": (fill.get("y_top") or "").strip(),
            "y_bottom": (fill.get("y_bottom") or "").strip(),
            "e_label": (fill.get("e_label") or "").strip(),
            "e_rx": (fill.get("e_rx") or "").strip(),
            "e_note": (fill.get("e_note") or "").strip(),
            "a_label": (fill.get("a_label") or "").strip(),
            "a_rx": (fill.get("a_rx") or "").strip(),
            "a_note": (fill.get("a_note") or "").strip(),
            "b_label": (fill.get("b_label") or "").strip(),
            "b_rx": (fill.get("b_rx") or "").strip(),
            "b_note": (fill.get("b_note") or "").strip(),
            "x_hint": (fill.get("x_hint") or "").strip(),
            "y_hint": (fill.get("y_hint") or "").strip(),
            "footnote": (fill.get("footnote") or "").strip(),
            "capacity": slotmod.family_spec(family).get("capacity", {}).get(chosen),
        })
    elif family == "dual_path_tree":
        def _path_nodes(raw: list | None) -> list[dict[str, Any]]:
            out = []
            for i, it in enumerate(raw or []):
                if not isinstance(it, dict):
                    continue
                out.append({
                    "heading": (it.get("heading") or "").strip(),
                    "body": (it.get("body") or "").strip(),
                    "kind": (it.get("kind") or "drug").strip() or "drug",
                    "branch": (it.get("branch") or "").strip(),
                    "index": i + 1,
                })
            return out

        left = _path_nodes(fill.get("left_nodes"))
        right = _path_nodes(fill.get("right_nodes"))
        # Collapse split_left + split_right into render steps
        right_steps: list[dict[str, Any]] = []
        i = 0
        while i < len(right):
            n = right[i]
            if n["kind"] == "split_left" and i + 1 < len(right) and right[i + 1]["kind"] == "split_right":
                right_steps.append({"type": "split", "left": n, "right": right[i + 1]})
                i += 2
            else:
                right_steps.append({"type": "node", "node": n})
                i += 1
        page.update({
            "section": (fill.get("section") or "").strip(),
            "title": (fill.get("title") or "").strip(),
            "figure": (fill.get("figure") or "").strip(),
            "takeaway": (fill.get("takeaway") or "").strip(),
            "source": (fill.get("source") or "").strip(),
            "page": str(fill.get("page") or "").strip(),
            "left_label": (fill.get("left_label") or "").strip(),
            "right_label": (fill.get("right_label") or "").strip(),
            "left_nodes": left,
            "right_nodes": right,
            "right_steps": right_steps,
            "footnote": (fill.get("footnote") or "").strip(),
            "capacity": slotmod.family_spec(family).get("capacity", {}).get(chosen),
        })
    else:
        raise KeyError(family)
    return page


def fill_deck(pages: list[dict], *, theme: str = "journal") -> dict:
    """Normalize a list of {family, fill, variant?} into a mini deck for HTML render."""
    models = []
    for i, entry in enumerate(pages):
        family = entry["family"]
        fill = dict(entry.get("fill") or entry)
        fill.setdefault("id", entry.get("id") or f"p{i + 1}")
        models.append(normalize_fill(
            family, fill, variant=entry.get("variant"), theme=entry.get("theme") or theme
        ))
    return {
        "title": pages[0].get("fill", pages[0]).get("title") if pages else "template_lib",
        "theme": theme,
        "theme_tokens": get_theme(theme),
        "pages": models,
        "library": "factdeck.template_lib.v1",
    }
