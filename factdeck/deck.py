"""Default generation entry for teaching layouts.

This package has no HTTP ``/api/deck``. ``build_deck`` is that entry.
Each page is ``select_layout`` then ``render_html``. The template binds
every slot and admits on-screen fact text through the display fact gate.
There is no second renderer that skips the gate.

Cover, section, and comparison have no teaching-layout body. This entry
does not invent one for them. After the slim pass it refuses an equal
card wall: four or more peer cards in multiple columns with no admitted
metric, evidence, or action to differentiate them. A dangling
half-sentence is omitted with its bullet or slot.

``prepare_deck`` slims a SUMMARY before ``select_layout``. Bullets that
cannot bind to a source slice are omitted. Chapter limits are
``max_sections``, ``max_pages``, and ``bullets_per_section`` (see
``factdeck.summary.ChapterLimits``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from factdeck.html_templates import render_html
from factdeck.layout_selector import refuse_equal_card_wall, select_layout
from factdeck.slots import trace_slide
from factdeck.summary import ChapterLimits, DeckSummary, prepare_deck

# No HTTP route. Callers use build_deck.
API_DECK = None
RENDERER = "factdeck.html_templates.render_html"


@dataclass(frozen=True)
class DeckPage:
    preview_id: str | None
    title: str
    layout_id: str
    variant: str
    reason: str
    columns: int
    html: str
    trace_status: str
    selection: dict
    renderer: str = RENDERER

    def to_dict(self) -> dict:
        return {
            "preview_id": self.preview_id,
            "title": self.title,
            "layout_id": self.layout_id,
            "variant": self.variant,
            "reason": self.reason,
            "columns": self.columns,
            "trace_status": self.trace_status,
            "selection": self.selection,
            "renderer": self.renderer,
            "api_deck": API_DECK,
        }


def build_deck(
    slides: Sequence[Mapping] | None = None,
    *,
    summary: DeckSummary | Mapping | None = None,
    limits: ChapterLimits | None = None,
    max_sections: int | None = None,
    max_pages: int | None = None,
    bullets_per_section: int | None = None,
) -> list[DeckPage]:
    """Render teaching pages through the template library.

    The slim pass runs first. ``previous`` is threaded the same way as the
    preview deck, so a repeated layout can move to a close alternative.
    The HTML for each page comes only from ``render_html``.
    """

    prepared = prepare_deck(
        slides,
        summary=summary,
        limits=limits,
        max_sections=max_sections,
        max_pages=max_pages,
        bullets_per_section=bullets_per_section,
    )
    pages: list[DeckPage] = []
    previous: str | None = None
    for slide in prepared.slides:
        payload = dict(slide)
        selection = select_layout(payload, previous=previous)
        refuse_equal_card_wall(payload, selection)
        html = render_html(payload, selection)
        trace = trace_slide(payload, selection)
        marker = f'data-layout="{selection.layout_id}"'
        if marker not in html:
            raise RuntimeError("template library did not render this page")
        preview = payload.get("preview_id")
        pages.append(
            DeckPage(
                preview_id=str(preview) if preview else None,
                title=str(payload.get("title") or ""),
                layout_id=selection.layout_id,
                variant=selection.variant,
                reason=selection.reason,
                columns=selection.columns,
                html=html,
                trace_status=trace.status,
                selection=selection.to_dict(),
            )
        )
        previous = selection.layout_id
    return pages
