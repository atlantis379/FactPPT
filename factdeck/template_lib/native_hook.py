"""T_TEMPLATE_NATIVE stub — hook for later native PPTX fill without changing Route A.

v1 only validates the slot contract and can emit HTML. Native path assembly
(reusing factdeck.render / Route A decorative paths) is intentionally stubbed.
"""
from __future__ import annotations

from typing import Any

from .fill import normalize_fill
from .slots import load_manifest


TASK = "T_TEMPLATE_NATIVE"


def describe() -> dict[str, Any]:
    m = load_manifest()
    hook = m.get("native_hook") or {}
    return {
        "task": hook.get("task") or TASK,
        "status": hook.get("status") or "stub",
        "note": hook.get("note") or "",
        "accepts_families": sorted(m["families"]),
        "requires": ["slot fill dict", "theme name (journal|steel)"],
        "produces_when_ready": ["native PPTX shapes + text boxes"],
        "produces_now": ["validated page model", "HTML via html_render"],
        "artwork": "factdeck/template_lib/artwork/paths.stub.json (empty TODO)",
        "does_not_touch": [
            "Route A VISUAL_* task chain",
            "output/academic_templates runtime fill",
            "commercial template packs",
        ],
    }


def prepare(family: str, fill: dict, *, theme: str = "journal",
            variant: str | None = None) -> dict[str, Any]:
    """Validate/normalize a fill and return a native-ready envelope (no PPTX write)."""
    page = normalize_fill(family, fill, variant=variant, theme=theme)
    return {
        "task": TASK,
        "status": "prepared",
        "page": page,
        "native": {
            "status": "stub",
            "shapes": [],
            "text_boxes": [],
            "artwork_paths": page.get("artwork_paths") or [],
            "todo": "Wire python-pptx text boxes from zones_px; optional Route A path groups.",
        },
    }
