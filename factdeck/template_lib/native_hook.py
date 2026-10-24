"""T_TEMPLATE_NATIVE — native PPTX for template-library pages.

The builder lives in ``native.py`` (HTML render -> Playwright measure -> python-pptx
text boxes / tables / shapes / connectors / freeforms, no bitmaps) and the
end-to-end job in ``pipeline.py`` (selector -> fill -> render -> measure -> native).
This module keeps the old describe/prepare envelope so callers that only need a
validated page model keep working.
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
        "status": hook.get("status") or "native",
        "note": hook.get("note") or "",
        "accepts_families": sorted(m["families"]),
        "requires": ["slot fill dict", "theme name (journal|steel)", "playwright chromium (measure)"],
        "produces": ["native PPTX: editable text boxes, native tables, shapes/lines/connectors, freeform charts"],
        "entry_points": {
            "deck": "factdeck.template_lib.pipeline.run(plan, out)",
            "cli": "python tools/template_deck.py --plan PLAN.json --out DIR",
            "slides": "factdeck.template_lib.native.build_pptx(models, out)",
            "inspect": "factdeck.template_lib.native.inspect_pptx(path)",
        },
        "does_not_touch": [
            "Route A VISUAL_* task chain",
            "output/academic_templates runtime fill",
            "commercial template packs",
        ],
    }


def prepare(family: str, fill: dict, *, theme: str = "journal",
            variant: str | None = None) -> dict[str, Any]:
    """Validate/normalize a fill and return the envelope consumed by the native builder.

    No PPTX is written here; ``pipeline.run`` renders + measures the page and calls
    ``native.build_pptx``. Shapes are only known after browser measurement.
    """
    page = normalize_fill(family, fill, variant=variant, theme=theme)
    return {
        "task": TASK,
        "status": "prepared",
        "page": page,
        "native": {
            "status": "ready",
            "builder": "factdeck.template_lib.native.build_pptx",
            "shapes": [],
            "text_boxes": [],
            "artwork_paths": page.get("artwork_paths") or [],
            "note": "shapes/text boxes are produced from the measured HTML render (pipeline.run).",
        },
    }
