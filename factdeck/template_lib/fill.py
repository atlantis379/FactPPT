"""Fill slot packs → normalized page models for HTML (and later native) render."""
from __future__ import annotations

from typing import Any

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
        page.update({
            "section": (fill.get("section") or "").strip(),
            "title": (fill.get("title") or "").strip(),
            "items": items,
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
