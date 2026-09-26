"""Severe, renderer-independent presentation-density preflight.

These checks do not decide a layout. They identify cases where moving the same
unabridged evidence into another box cannot produce a meeting-readable slide.
Such pages go back to evidence atomicity, slide copy, or page allocation.
"""
from __future__ import annotations

from typing import Any


def issues(plan: dict[str, Any]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for page in plan.get("pages") or []:
        page_id = str(page.get("page_id") or "")
        archetype = page.get("selected_archetype")
        for element in page.get("elements") or []:
            name = str(element.get("name") or "")
            if not name.startswith("claim:"):
                continue
            text = "".join(str(element.get("text") or "").split())
            size = (element.get("style") or {}).get("fontSize")
            if archetype == "EDITORIAL_STATEMENT" and len(text) >= 140:
                found.append({"page_id": page_id, "code": "FULL_PARAGRAPH_HERO",
                              "route": "UPSTREAM_CONTENT",
                              "message": f"A {len(text)}-character Claim fills the hero area; split or compose source-faithful slide copy before layout."})
            elif isinstance(size, (int, float)) and size <= 16 and len(text) >= 170:
                found.append({"page_id": page_id, "code": "DENSE_SMALL_TYPE",
                              "route": "UPSTREAM_CONTENT",
                              "message": f"A {len(text)}-character Claim is rendered at {size}px; repaginate or decompose the evidence."})
    return found
