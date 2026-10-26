"""SUMMARY outline and the slimming pass in front of ``build_deck``.

A summary is an ordered list of sections. Each section holds bullets that
must bind to a source span. ``slim_summary`` drops a bullet that cannot
bind, drops a clinical string the display fact gate does not accept, and
drops whole bullets past the section budget. It copies kept strings. It
does not rewrite numbers, doses, or drug names.

Chaptering knobs live on ``ChapterLimits``:

- ``max_sections`` keeps the first N sections in outline order. A section
  that loses every bullet still occupies one of those N slots and emits
  no page. Later sections are ``SECTION_CUT``.
- ``max_pages`` keeps the first N teaching pages after that cut. Empty
  sections emit no page, so they do not consume this budget. A later
  page that was inside the section budget is ``PAGE_CUT``. One section
  may own several slides that share ``section_id``; ``max_sections``
  keeps that whole section, and ``max_pages`` can keep its first slide.
- ``bullets_per_section`` keeps the first N bullets in the section that
  bind to a source slice. The budget is shared by every slide in the
  section. Further bound bullets are ``OVERFLOW`` and are omitted whole.
  They are not clipped and they are not spilled onto another page.
  Unbound bullets do not consume the budget.

``None`` leaves that cap off. Defaults are ``None``, so an already-bound
teaching deck is unchanged. Zero emits nothing for that cap. A negative
value raises ``ValueError``. A bool raises ``TypeError``.

``build_deck`` runs this pass before layout selection. Cover, section,
and comparison still have no body template; this pass does not invent
one. A bullet whose text is a dangling half-sentence of its source is
``HALF_SENTENCE`` and is omitted whole. The deck entry refuses an equal
card wall when the admitted facts do not differentiate those peers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from factdeck.facts import canon, dangling_half_sentence, extract_unit_slices, gate_display
from factdeck.lexicon import DERIVATION_BY_KIND

# Default chaptering. None leaves an already-bound teaching deck unchanged.
DEFAULT_MAX_SECTIONS: int | None = None
DEFAULT_MAX_PAGES: int | None = None
DEFAULT_BULLETS_PER_SECTION: int | None = None

BULLET_REASONS = (
    "ADMITTED",
    "UNBOUND",
    "UNGATED",
    "HALF_SENTENCE",
    "OVERFLOW",
    "SECTION_CUT",
    "PAGE_CUT",
)

_FACT_FIELDS = ("body", "evidence", "text", "value")
_FIELD_NAMES = frozenset({*_FACT_FIELDS, "title"})
_FACT_KINDS = frozenset({"dose", "drug", *DERIVATION_BY_KIND})
_STRUCTURAL_ROLES = frozenset({"cover", "section", "comparison"})


@dataclass(frozen=True)
class ChapterLimits:
    """Caps for ``slim_summary`` and ``build_deck``. See the module docstring."""

    max_sections: int | None = DEFAULT_MAX_SECTIONS
    max_pages: int | None = DEFAULT_MAX_PAGES
    bullets_per_section: int | None = DEFAULT_BULLETS_PER_SECTION


@dataclass(frozen=True)
class SummaryBullet:
    """One outline bullet. ``text`` is copied from the caller, never rewritten."""

    bullet_id: str
    text: str
    source_text: str | None
    source_id: str | None
    source_field: str
    item_id: str
    title: str = ""
    slide_index: int | None = None

    def to_dict(self) -> dict:
        return {
            "bullet_id": self.bullet_id,
            "text": self.text,
            "source_text": self.source_text,
            "source_id": self.source_id,
            "source_field": self.source_field,
            "item_id": self.item_id,
            "title": self.title,
            "slide_index": self.slide_index,
        }


@dataclass(frozen=True)
class SummarySection:
    """One chapter. ``slide_indexes`` point at the slides this section came from."""

    section_id: str
    title: str
    bullets: tuple[SummaryBullet, ...]
    role: str = "body"
    slide_indexes: tuple[int, ...] = ()

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "role": self.role,
            "slide_indexes": list(self.slide_indexes),
            "bullets": [bullet.to_dict() for bullet in self.bullets],
        }


@dataclass(frozen=True)
class DeckSummary:
    """Ordered SUMMARY. Downstream pages slim against these sections."""

    sections: tuple[SummarySection, ...]

    def to_dict(self) -> dict:
        return {"sections": [section.to_dict() for section in self.sections]}


@dataclass(frozen=True)
class SlimmedBullet:
    bullet: SummaryBullet
    kept: bool
    reason: str
    stripped_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlimmedSection:
    """``emitted`` means the section survived ``max_sections``.

    ``max_pages`` can still drop its slides. Those bullets are ``PAGE_CUT``.
    """

    section: SummarySection
    bullets: tuple[SlimmedBullet, ...]
    emitted: bool


@dataclass(frozen=True)
class PreparedDeck:
    """Slides after the slim pass, before ``select_layout``."""

    summary: DeckSummary
    sections: tuple[SlimmedSection, ...]
    slides: tuple[dict, ...]
    limits: ChapterLimits


@dataclass(frozen=True)
class _Page:
    slide: dict
    slide_index: int | None
    section_id: str


def resolve_limits(
    limits: ChapterLimits | None = None,
    *,
    max_sections: int | None = None,
    max_pages: int | None = None,
    bullets_per_section: int | None = None,
) -> ChapterLimits:
    """Keyword arguments replace a ``ChapterLimits`` field when they are not None."""

    base = limits or ChapterLimits()
    return ChapterLimits(
        max_sections=_bound("max_sections", base.max_sections if max_sections is None else max_sections),
        max_pages=_bound("max_pages", base.max_pages if max_pages is None else max_pages),
        bullets_per_section=_bound(
            "bullets_per_section",
            base.bullets_per_section if bullets_per_section is None else bullets_per_section,
        ),
    )


def summary_from_outline(outline: Mapping) -> DeckSummary:
    """Build a SUMMARY from ``{"sections": [{"id", "title", "bullets": [...]}]}``.

    Each bullet's ``text`` is copied. A bullet with no ``source_text`` cannot
    bind; the slim pass drops it instead of inventing a span.
    """

    if not isinstance(outline, Mapping):
        raise TypeError("outline must be a mapping")
    sections = []
    for section_index, raw in enumerate(outline.get("sections") or [], start=1):
        if not isinstance(raw, Mapping):
            raise TypeError("outline sections must be mappings")
        section_id = str(raw.get("id") or raw.get("section_id") or f"section-{section_index}")
        bullets = []
        for bullet_index, bullet in enumerate(raw.get("bullets") or [], start=1):
            if not isinstance(bullet, Mapping):
                raise TypeError("outline bullets must be mappings")
            if "text" in bullet:
                text = str(bullet.get("text") or "")
            else:
                text = str(bullet.get("body") or "")
            if "source_text" in bullet:
                source = bullet.get("source_text")
                source_text = str(source) if source is not None and str(source).strip() else None
            else:
                source_text = None
            field = str(bullet.get("source_field") or "body")
            if field not in _FIELD_NAMES:
                field = "body"
            item_id = str(bullet.get("id") or f"bullet-{bullet_index}")
            source_id = str(bullet["source_id"]) if bullet.get("source_id") else None
            bullets.append(
                SummaryBullet(
                    bullet_id=f"{section_id}:{item_id}",
                    text=text,
                    source_text=source_text,
                    source_id=source_id,
                    source_field=field,
                    item_id=item_id,
                    title=str(bullet.get("title") or ""),
                    slide_index=None,
                )
            )
        sections.append(
            SummarySection(
                section_id=section_id,
                title=str(raw.get("title") or ""),
                bullets=tuple(bullets),
                role=str(raw.get("role") or "body"),
            )
        )
    return DeckSummary(sections=tuple(sections))


def summary_from_slides(slides: Sequence[Mapping]) -> DeckSummary:
    """One section per ``section_id`` / ``chapter_id`` / ``preview_id``.

    Slides that share a section id are one chapter, in input order. An item
    field with no ``source_text`` is its own source span. An explicit empty
    ``source_text`` cannot bind.
    """

    groups: list[tuple[str, list[int]]] = []
    index_of: dict[str, int] = {}
    for slide_index, slide in enumerate(slides):
        if not isinstance(slide, Mapping):
            raise TypeError("slides must be mappings")
        section_id = _section_id(slide, slide_index + 1)
        if section_id not in index_of:
            index_of[section_id] = len(groups)
            groups.append((section_id, []))
        groups[index_of[section_id]][1].append(slide_index)
    sections = []
    for section_id, indexes in groups:
        first = slides[indexes[0]]
        bullets = []
        for slide_index in indexes:
            slide = slides[slide_index]
            for item_index, item in enumerate(slide.get("items") or [], start=1):
                if not isinstance(item, Mapping):
                    continue
                bullet = _bullet_from_item(section_id, slide_index, item, item_index)
                if bullet is not None:
                    bullets.append(bullet)
        sections.append(
            SummarySection(
                section_id=section_id,
                title=str(first.get("title") or ""),
                bullets=tuple(bullets),
                role=str(first.get("role") or "body"),
                slide_indexes=tuple(indexes),
            )
        )
    return DeckSummary(sections=tuple(sections))


def slim_summary(
    summary: DeckSummary,
    *,
    limits: ChapterLimits | None = None,
    slides: Sequence[Mapping] | None = None,
) -> tuple[SlimmedSection, ...]:
    """Drop unbound, ungated, and overflow bullets. Do not rewrite their text."""

    caps = limits or ChapterLimits()
    items = _items_by_slide(slides or [])
    slimmed = []
    for section_index, section in enumerate(summary.sections):
        emitted = caps.max_sections is None or section_index < caps.max_sections
        judged: list[tuple[SummaryBullet, str, tuple[str, ...]]] = []
        for bullet in section.bullets:
            if not emitted:
                judged.append((bullet, "SECTION_CUT", ()))
                continue
            item = items.get((bullet.slide_index, bullet.item_id)) if bullet.slide_index is not None else None
            reason, stripped = _judge_bullet(bullet, item)
            judged.append((bullet, reason, stripped if reason == "ADMITTED" else ()))
        kept = 0
        merged = []
        for bullet, reason, stripped in judged:
            if reason == "ADMITTED" and caps.bullets_per_section is not None and kept >= caps.bullets_per_section:
                merged.append(SlimmedBullet(bullet, False, "OVERFLOW"))
                continue
            if reason == "ADMITTED":
                kept += 1
                merged.append(SlimmedBullet(bullet, True, "ADMITTED", stripped_fields=stripped))
                continue
            merged.append(SlimmedBullet(bullet, False, reason))
        slimmed.append(SlimmedSection(section, tuple(merged), emitted))
    return tuple(slimmed)


def prepare_deck(
    slides: Sequence[Mapping] | None = None,
    *,
    summary: DeckSummary | Mapping | None = None,
    limits: ChapterLimits | None = None,
    max_sections: int | None = None,
    max_pages: int | None = None,
    bullets_per_section: int | None = None,
) -> PreparedDeck:
    """Slim a slide list or an outline into the pages ``build_deck`` may render.

    Pass slides or a summary, not both. Slides are the teaching-layout input.
    A summary mapping uses ``summary_from_outline``.
    """

    caps = resolve_limits(
        limits,
        max_sections=max_sections,
        max_pages=max_pages,
        bullets_per_section=bullets_per_section,
    )
    slide_list, deck_summary = _inputs(slides, summary)
    sections = slim_summary(deck_summary, limits=caps, slides=slide_list)
    projected = _project(slide_list, sections)
    sections, projected = _cut_pages(sections, projected, caps.max_pages)
    return PreparedDeck(deck_summary, sections, tuple(projected), caps)


def bullet_binds(text: str, source_text: str | None) -> str:
    """``ADMITTED`` only when ``text`` is an accepted slice of ``source_text``.

    The string is not rewritten. Anything the fact gate does not accept is
    ``UNGATED``. A missing span or a string that is not in that span is
    ``UNBOUND``. A clip the gate accepts only as a dangling half-sentence
    is ``HALF_SENTENCE`` and is omitted whole.
    """

    if source_text is None or not str(source_text).strip():
        return "UNBOUND"
    display = "" if text is None else str(text)
    source = str(source_text)
    if not display.strip():
        return "UNBOUND"
    folded = canon(display)
    source_folded = canon(source)
    if folded != source_folded and folded not in source_folded:
        return "UNBOUND"
    gate = gate_display(source, display)
    if gate.status != "ACCEPTED":
        return "UNGATED"
    if dangling_half_sentence(source, display, gate):
        return "HALF_SENTENCE"
    return "ADMITTED"


def field_admission(item: Mapping, field: str) -> str:
    """Admission of one item field. Empty text cannot bind."""

    text = "" if item.get(field) is None else str(item.get(field))
    if not text.strip():
        return "UNBOUND"
    return bullet_binds(text, _field_source(item, field, text))


def _inputs(
    slides: Sequence[Mapping] | None,
    summary: DeckSummary | Mapping | None,
) -> tuple[list[Mapping] | None, DeckSummary]:
    provided = list(slides or [])
    if summary is not None and provided:
        raise ValueError("pass slides or a summary, not both")
    if summary is None:
        return provided, summary_from_slides(provided)
    if isinstance(summary, DeckSummary):
        return None, summary
    if isinstance(summary, Mapping):
        return None, summary_from_outline(summary)
    raise TypeError("summary must be a DeckSummary or an outline mapping")


def _project(slides: list[Mapping] | None, sections: Sequence[SlimmedSection]) -> list[_Page]:
    if slides is None:
        return _synthesize(sections)
    by_index = {}
    for section in sections:
        for bullet in section.bullets:
            if bullet.bullet.slide_index is not None:
                by_index.setdefault(bullet.bullet.slide_index, []).append((section, bullet))
    projected = []
    for slide_index, slide in enumerate(slides):
        if not isinstance(slide, Mapping):
            raise TypeError("slides must be mappings")
        role = str(slide.get("role") or "body")
        if role in _STRUCTURAL_ROLES:
            continue
        pairs = by_index.get(slide_index, [])
        section = pairs[0][0] if pairs else _section_for_slide(sections, slide_index)
        if section is None or not section.emitted:
            continue
        if not pairs and _has_structure(slide):
            projected.append(_Page(dict(slide), slide_index, section.section.section_id))
            continue
        if not pairs:
            continue
        projected_slide = _project_slide(slide, [bullet for _section, bullet in pairs])
        if projected_slide is not None:
            projected.append(_Page(projected_slide, slide_index, section.section.section_id))
    return projected


def _synthesize(sections: Sequence[SlimmedSection]) -> list[_Page]:
    projected = []
    for slimmed in sections:
        if not slimmed.emitted or slimmed.section.role in _STRUCTURAL_ROLES:
            continue
        kept = [bullet for bullet in slimmed.bullets if bullet.kept]
        if not kept:
            continue
        items = [_item_from_bullet(bullet.bullet) for bullet in kept]
        sources = [bullet.bullet.source_text for bullet in kept]
        slide = {
            "preview_id": slimmed.section.section_id,
            "title": _display_title(slimmed.section.title, sources),
            "role": "body",
            "items": items,
        }
        projected.append(_Page(slide, None, slimmed.section.section_id))
    return projected


def _cut_pages(
    sections: Sequence[SlimmedSection],
    projected: list[_Page],
    max_pages: int | None,
) -> tuple[tuple[SlimmedSection, ...], list[dict]]:
    if max_pages is None or len(projected) <= max_pages:
        return tuple(sections), [page.slide for page in projected]
    kept_pages = projected[:max_pages]
    surviving = set(range(len(kept_pages)))
    slot_of_slide_index = {}
    slot_of_section = {}
    for slot, page in enumerate(projected):
        if page.slide_index is not None:
            slot_of_slide_index[page.slide_index] = slot
        else:
            slot_of_section[page.section_id] = slot
    retagged = []
    for slimmed in sections:
        bullets = []
        for decision in slimmed.bullets:
            if not decision.kept:
                bullets.append(decision)
                continue
            slide_index = decision.bullet.slide_index
            if slide_index is not None:
                slot = slot_of_slide_index.get(slide_index)
            else:
                slot = slot_of_section.get(slimmed.section.section_id)
            if slot is None or slot not in surviving:
                bullets.append(SlimmedBullet(decision.bullet, False, "PAGE_CUT"))
                continue
            bullets.append(decision)
        retagged.append(SlimmedSection(slimmed.section, tuple(bullets), slimmed.emitted))
    return tuple(retagged), [page.slide for page in kept_pages]


def _project_slide(slide: Mapping, decisions: list[SlimmedBullet]) -> dict | None:
    by_item = {decision.bullet.item_id: decision for decision in decisions}
    raw_items = [item for item in (slide.get("items") or []) if isinstance(item, Mapping)]
    represented = 0
    changed = False
    items = []
    for item_index, item in enumerate(slide.get("items") or [], start=1):
        if not isinstance(item, Mapping):
            changed = True
            continue
        item_id = _item_id(item, item_index)
        decision = by_item.get(item_id)
        if decision is None:
            changed = True
            continue
        represented += 1
        if not decision.kept:
            changed = True
            continue
        if decision.stripped_fields:
            changed = True
            items.append(_strip_item(item, decision.stripped_fields))
            continue
        items.append(item)
    if represented != len(raw_items):
        changed = True
    if not items and not _has_structure(slide):
        return None
    if not changed and not _matrix_broken(slide, items):
        return dict(slide)
    copy = dict(slide)
    copy["items"] = items
    if _matrix_broken(copy, items):
        copy.pop("axes", None)
        if copy.get("relation") in {"matrix", "矩阵"}:
            copy.pop("relation", None)
    return copy


def _section_for_slide(sections: Sequence[SlimmedSection], slide_index: int) -> SlimmedSection | None:
    for section in sections:
        if slide_index in section.section.slide_indexes:
            return section
    return None


def _has_structure(slide: Mapping) -> bool:
    return bool(slide.get("nodes") or slide.get("table"))


def _matrix_broken(slide: Mapping, items: list) -> bool:
    return slide.get("relation") in {"matrix", "矩阵"} and len(items) != 4


def _item_from_bullet(bullet: SummaryBullet) -> dict:
    item = {"id": bullet.item_id}
    title = bullet.title
    if title and bullet.source_field != "title":
        if not _has_facts(title) or bullet_binds(title, bullet.source_text) == "ADMITTED":
            item["title"] = title
    item[bullet.source_field] = bullet.text
    return item


def _display_title(title: str, sources: Sequence[str | None]) -> str:
    if not title or not _has_facts(title):
        return title
    for source in sources:
        if source and bullet_binds(title, source) == "ADMITTED":
            return title
    return ""


def _judge_bullet(bullet: SummaryBullet, item: Mapping | None) -> tuple[str, tuple[str, ...]]:
    reason = bullet_binds(bullet.text, bullet.source_text)
    if reason != "ADMITTED":
        return reason, ()
    if item is None:
        return "ADMITTED", ()
    stripped = []
    for field in ("title", *_FACT_FIELDS):
        if field == bullet.source_field:
            continue
        raw = item.get(field)
        text = "" if raw is None else str(raw)
        if not text.strip():
            continue
        if field == "title" and not _has_facts(text):
            continue
        source = _field_source(item, field, text)
        if bullet_binds(text, source) != "ADMITTED":
            stripped.append(field)
    return "ADMITTED", tuple(stripped)


def _strip_item(item: Mapping, fields: tuple[str, ...]) -> dict:
    copy = dict(item)
    for field in fields:
        if field == "title":
            copy["title"] = ""
            continue
        copy.pop(field, None)
    return copy


def _bullet_from_item(section_id: str, slide_index: int, item: Mapping, item_index: int) -> SummaryBullet | None:
    field = _primary_field(item)
    if field is None:
        return None
    text = str(item.get(field) or "")
    if not text.strip():
        return None
    item_id = _item_id(item, item_index)
    source_id = str(item["source_id"]) if item.get("source_id") else f"item:{item_id}"
    return SummaryBullet(
        bullet_id=f"{section_id}:{slide_index}:{item_id}",
        text=text,
        source_text=_field_source(item, field, text),
        source_id=source_id,
        source_field=field,
        item_id=item_id,
        title=str(item.get("title") or ""),
        slide_index=slide_index,
    )


def _primary_field(item: Mapping) -> str | None:
    for field in _FACT_FIELDS:
        if str(item.get(field) or "").strip():
            return field
    title = str(item.get("title") or "")
    if title.strip() and _has_facts(title):
        return "title"
    return None


def _field_source(item: Mapping, field: str, text: str) -> str | None:
    if "source_text" in item:
        source = item.get("source_text")
        if source is None or not str(source).strip():
            return None
        return str(source)
    body = str(item.get("body") or "")
    if field == "value" and body.strip() and canon(text) != canon(body):
        return body
    return text


def _item_id(item: Mapping, item_index: int) -> str:
    if item.get("id"):
        return str(item["id"])
    return f"item-{item_index}"


def _section_id(slide: Mapping, position: int) -> str:
    for key in ("section_id", "chapter_id"):
        value = slide.get(key)
        if value:
            return str(value)
    preview = slide.get("preview_id")
    if preview:
        return str(preview)
    return f"section-{position}"


def _items_by_slide(slides: Sequence[Mapping]) -> dict[tuple[int, str], Mapping]:
    found = {}
    for slide_index, slide in enumerate(slides):
        if not isinstance(slide, Mapping):
            continue
        for item_index, item in enumerate(slide.get("items") or [], start=1):
            if isinstance(item, Mapping):
                found[(slide_index, _item_id(item, item_index))] = item
    return found


def _has_facts(text: str) -> bool:
    return any(item.kind in _FACT_KINDS for item in extract_unit_slices(text or ""))


def _bound(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int or None")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value
