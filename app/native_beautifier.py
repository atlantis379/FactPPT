"""Deterministic layout planning for native, editable PPTX slides.

The planner consumes only an approved Semantic Deck.  It never rewrites a
claim, invents a relationship, or drops content to make a page fit.  Its
output is a renderer-neutral BeautificationPlan that can be inspected and
tested before PowerPoint objects are created.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.editorial_assets import assets_for_page


SLIDE_WIDTH = 1280
SLIDE_HEIGHT = 720
MAX_CLAIMS_PER_PAGE = 4

DESIGN_TOKENS: dict[str, Any] = {
    "canvas": {"width": SLIDE_WIDTH, "height": SLIDE_HEIGHT, "safe_margin": 64},
    "colors": {
        "background": "#F6F8FB",
        "surface": "#FFFFFF",
        "ink": "#10243E",
        "muted": "#597086",
        "line": "#C9D5E2",
        "accent": "#087E8B",
        "accent_soft": "#DDF3F4",
        "source": "#1D6FA5",
        "synthesis": "#B56A16",
        "synthesis_soft": "#FFF0D8",
        "relationship": "#50728B",
        "white": "#FFFFFF",
        "glass": "#F7FCFD/82",
        "glass_soft": "#F7FCFD/68",
        "glass_line": "#8FB8C0/48",
        "wash": "linear(90deg, #F7FCFD/70 0%, #F7FCFD/28 72%, #F7FCFD/0 100%)",
    },
    "typography": {
        "font_family": "Microsoft YaHei",
        "title": 38,
        "message": 21,
        "body": 17,
        "meta": 12,
        "footer": 11,
    },
}


class BeautificationPlanError(ValueError):
    """Raised when a semantic page cannot be beautified without data loss."""


def _box(left: int, top: int, width: int, height: int) -> dict[str, int]:
    return {"left": left, "top": top, "width": width, "height": height}


def _source_lines(claims: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for claim in claims:
        for ref in claim.get("source_refs", []):
            document_id = str(ref.get("document_id", ""))
            locator = ref.get("locator") or {}
            if locator.get("kind") == "DOCX":
                part = locator.get("part", "body")
                section = f" section[{locator['section']}]" if locator.get("section") is not None else ""
                if locator.get("paragraph") is not None:
                    position = f"{part}{section} paragraph[{locator['paragraph']}]"
                else:
                    position = (f"{part}{section} table[{locator['table']}] "
                                f"row[{locator['row']}] col[{locator['column']}]")
            elif locator.get("kind") == "XLSX":
                position = f"{locator['sheet']}!{locator['cell']}"
            else:
                position = f"p.{int(ref.get('page', 0))}"
            line = f"{document_id} {position}"
            if line not in seen:
                seen.add(line)
                result.append(line)
    return result or ["SOURCE REQUIRED"]


def _claim_display_text(claim: dict[str, Any]) -> str:
    text = str(claim.get("normalized_claim", "")).strip()
    conditions = [str(item).strip() for item in claim.get("conditions", []) if str(item).strip()]
    if conditions:
        text += "\n\n适用条件：" + "；".join(conditions)
    return text


#: Figure intent -> the layout grammar it licenses. This is the reading's own declaration, so
#: it is the primary source of structural signals. Deriving them by substring-matching
#: `visual_type` instead threw the declaration away: `COMPARISON` maps to `EVIDENCE_MAP`, whose
#: only signal is DEFAULT, so a genuine before/after page was denied the comparison layout; and
#: no mapping ever produced SEQUENCE, which left TIMELINE unreachable.
FIGURE_INTENT_SIGNALS: dict[str, set[str]] = {
    "COMPARISON": {"COMPARE"},
    "PROGRESSION": {"SEQUENCE"},
    "PROCESS": {"FLOW"},
    "CAUSAL": {"CAUSAL"},
    "TAXONOMY": {"TAXONOMY"},
}


def _signals(page: dict[str, Any]) -> set[str]:
    visual_type = str(page.get("visual_type", "")).upper()
    signals = {"DEFAULT"}
    if any(token in visual_type for token in ("FLOW", "DECISION", "PATH", "ALGORITHM")):
        signals.add("FLOW")
    if any(token in visual_type for token in ("TIMELINE", "CYCLE", "JOURNEY", "EVOLUTION")):
        signals.add("SEQUENCE")
    if any(token in visual_type for token in ("COMPARE", "COMPARISON", "VERSUS", "MATRIX")):
        signals.add("COMPARE")
    signals |= FIGURE_INTENT_SIGNALS.get(str(page.get("figure_intent") or "").upper(), set())
    if page.get("relationships"):
        signals.add("RELATIONSHIP")
    return signals


def _candidate(archetype: str, valid: bool, score: int, reasons: list[str]) -> dict[str, Any]:
    return {
        "archetype": archetype,
        "status": "VALID" if valid else "REJECTED",
        "score": score if valid else None,
        "reasons": reasons,
    }


def _evaluate_candidates(page: dict[str, Any], *, include_focus: bool = False) -> list[dict[str, Any]]:
    # A page that renders the argument's shape rather than evidence. The reading may declare
    # ROADMAP / SECTION_QUESTION / PART_RECAP / CONSOLIDATION, and such a page legitimately cites
    # no source blocks -- which is why it cannot be scored against evidence capacity. It is the
    # only carrier the throughline has: without it the thread lives in the artifact and never
    # reaches a slide.
    if page.get("renders_structure"):
        return [_candidate("STRUCTURE_PAGE", True, 90,
                           [f"Renders the argument's shape ({page['renders_structure']}); carries no evidence."])]
    claims = page.get("claims", [])
    count = len(claims)
    signals = _signals(page)
    lengths = [len(_claim_display_text(claim)) for claim in claims]
    total_chars = sum(lengths)
    candidates: list[dict[str, Any]] = []

    candidates.append(_candidate(
        "EDITORIAL_STATEMENT",
        count == 1 and total_chars <= 420,
        86 + (12 if count == 1 else 0),
        ["Best for one dominant claim."] if count == 1 else ["Requires exactly one claim."],
    ))
    cards_valid = 1 <= count <= 4 and all(length <= 520 for length in lengths)
    candidates.append(_candidate(
        "EVIDENCE_CARDS",
        cards_valid,
        76 + (8 if 2 <= count <= 4 else 0),
        ["Balanced evidence-card grid with stable reading order."] if cards_valid else ["Claim count or text density exceeds card capacity."],
    ))
    comparison_valid = (2 <= count <= 4 and all(length <= 460 for length in lengths)
                        and (not include_focus or "COMPARE" in signals))
    candidates.append(_candidate(
        "COMPARISON_COLUMNS",
        comparison_valid,
        74 + (18 if "COMPARE" in signals else 0),
        ["Column comparison preserves independent claim boundaries."] if comparison_valid else
        (["Model layout requires an approved comparison signal."] if include_focus and "COMPARE" not in signals
         else ["Requires two to four concise claims."]),
    ))
    flow_valid = 2 <= count <= 4 and bool(page.get("relationships")) and all(length <= 340 for length in lengths)
    candidates.append(_candidate(
        "DECISION_FLOW",
        flow_valid,
        78 + (18 if "FLOW" in signals else 0) + (8 if "RELATIONSHIP" in signals else 0),
        ["Explicit relationships can be rendered as named connectors."] if flow_valid else ["Requires explicit relationships and concise nodes."],
    ))
    timeline_valid = (2 <= count <= 4 and all(length <= 300 for length in lengths)
                      and (not include_focus or "SEQUENCE" in signals))
    candidates.append(_candidate(
        "TIMELINE",
        timeline_valid,
        70 + (24 if "SEQUENCE" in signals else 0),
        ["Sequential visual grammar is compatible with the page signal."] if timeline_valid else
        (["Model layout requires an approved sequence signal."] if include_focus and "SEQUENCE" not in signals
         else ["Requires two to four concise steps."]),
    ))
    if include_focus:
        focus_valid = 2 <= count <= 4 and not page.get("relationships") and total_chars <= 650
        candidates.append(_candidate(
            "FOCUS_EVIDENCE", focus_valid, 80,
            ["The page's first Claim leads as the focal point; the remaining Claims stay visible as support."]
            if focus_valid else ["Requires two to four Claims, no explicit connectors, and moderate text density."],
        ))
        flex_valid = 2 <= count <= 4 and not page.get("relationships") and total_chars <= 750
        candidates.append(_candidate(
            "FLEX_COMPOSITION", flex_valid, 78,
            ["Model defines a bounded row/column evidence tree; the compiler resolves positions and checks fit."]
            if flex_valid else ["Requires two to four Claims without explicit connectors and moderate text density."],
        ))
    return candidates


def _text(name: str, text: str, position: dict[str, int], *, size: int, color: str,
          bold: bool = False, align: str = "left", valign: str = "top") -> dict[str, Any]:
    return {
        "kind": "text",
        "name": name,
        "text": text,
        "position": position,
        "style": {"fontSize": size, "color": color, "bold": bold, "alignment": align, "verticalAlignment": valign},
    }


def _shape(name: str, position: dict[str, int], *, fill: str, line: str,
           text: str = "", size: int = 17, color: str = "#10243E",
           bold: bool = False, align: str = "left", valign: str = "middle",
           geometry: str = "rect", line_width: int = 1) -> dict[str, Any]:
    return {
        "kind": "shape",
        "name": name,
        "geometry": geometry,
        "position": position,
        "fill": fill,
        "line": {"fill": line, "width": line_width},
        "text": text,
        "style": {"fontSize": size, "color": color, "bold": bold, "alignment": align, "verticalAlignment": valign},
    }


def _fusion_enabled(page: dict[str, Any]) -> bool:
    return bool(page.get("_fusion", {}).get("enabled"))


def _claim_colors(claim: dict[str, Any], tokens: dict[str, Any], *, fused: bool = False) -> tuple[str, str]:
    colors = tokens["colors"]
    if claim.get("provenance") == "SYNTHESIS":
        return ("#FFF3DF/78" if fused else colors["synthesis_soft"]), colors["synthesis"]
    return (colors["glass"] if fused else colors["surface"]), colors["source"]


def _relationship_connectors(page: dict[str, Any], tokens: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "name": f"clinical_relationship:{rel['id']}",
        "from": f"claim:{rel['from_claim_id']}",
        "to": f"claim:{rel['to_claim_id']}",
        "color": tokens["colors"]["relationship"],
        "width": 3,
        "direction": rel.get("direction", "FORWARD"),
    } for rel in page.get("relationships", [])]


def _title_size(text: str, width: int, height: int, sizes: tuple[int, ...]) -> int:
    """The largest title size whose measured height still fits the title box.

    The page title comes from the accepted reading artifact and is usually an action title
    ("标准下调为过去一年≥1次中重度急性加重"), routinely longer than one 38px line. Holding the
    size fixed made the compiler reject the approved title -- i.e. it demanded shorter
    evidence-carrying copy to satisfy a hard-coded box. The compiler owns the box, so it
    sizes the text to the box instead. Deterministic, and it never goes below the declared
    minimum.

    Measured with the inset the delivered text frame really gets (LD-03). Measuring at zero
    inset under-reports the wrapped line count, so the size chosen here would not be the size
    the fit gate then accepts.
    """
    from app.layout_ir import measure_text, text_frame_insets
    horizontal, vertical = text_frame_insets("text")
    for size in sizes:
        if measure_text(text, width, size, horizontal_inset=horizontal,
                        vertical_inset=vertical)["required_height"] <= height:
            return size
    return sizes[-1]


def _common_elements(page: dict[str, Any], ordinal: int, tokens: dict[str, Any]) -> list[dict[str, Any]]:
    colors = tokens["colors"]
    typo = tokens["typography"]
    page_id = page["page_id"]
    # Label what was actually drawn, not the reading's declared intent. The header used to print
    # `visual_type` while the compiler drew `selected_archetype`, so a page could be labelled
    # CLINICAL DECISION MAP and render as a card grid -- a promise the layout did not keep.
    archetype = str(page.get("_selected_archetype") or "")
    intent = str(page.get("figure_intent") or page.get("visual_type", "EVIDENCE MAP"))
    label = f"{intent.replace('_', ' ')} · {archetype.replace('_', ' ')}" if archetype else intent.replace("_", " ")
    title_text = str(page.get("title", ""))
    message_text = str(page.get("primary_message", ""))
    # A subtitle is drawn only when it says something of its own. Two cases are skipped, and both
    # were real in run_ch06's deck: a message copied from the title (every one of its 28 pages
    # carried `action_title == primary_message`, so the page showed the same line twice, one bold
    # and one grey) and an empty message (which drew a text box with no text -- an empty object,
    # not a subtitle). Whitespace-insensitive, the same normalisation `deckkit.page_contract` uses,
    # so "本章 学习主线" and "本章学习主线" are one string.
    has_own_subtitle = bool(message_text.strip()) and \
        "".join(message_text.split()) != "".join(title_text.split())
    fused = _fusion_enabled(page)
    title_width = 920 if fused else 1120
    ladder = ((34, 30, 27, 24, 21) if fused and len(title_text) > 17
              else (typo["title"], 34, 30, 27, 24, 21))
    title_size = _title_size(title_text, title_width, 58, ladder)
    elements: list[dict[str, Any]] = []
    if not fused:
        elements.append(_shape(
            f"accent:{page_id}", _box(64, 42, 8, 76),
            fill=colors["accent"], line=colors["accent"],
        ))
    elements.extend([
        _text(f"page-number:{page_id}", str(ordinal).zfill(2), _box(88, 42, 44, 24), size=typo["meta"], color=colors["accent"], bold=True),
        _text(f"visual-type:{page_id}", label, _box(138, 42, 430, 24), size=typo["meta"], color=colors["muted"], bold=True),
        _text(f"title:{page_id}", title_text, _box(88, 78, title_width, 58), size=title_size, color=colors["ink"], bold=True),
    ])
    if has_own_subtitle:
        elements.append(_text(f"primary:{page_id}", message_text, _box(88, 146, title_width, 58), size=typo["message"], color=colors["muted"]))
    return elements


def _provenance_label(claim: dict[str, Any]) -> str:
    provenance = str(claim.get("provenance", "SOURCE"))
    risk = str(claim.get("risk", "YELLOW"))
    return f"{provenance} · {risk}"


def _apply_fusion_theme(tokens: dict[str, Any], asset: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    themed = deepcopy(tokens)
    theme = asset["fusion_theme"]
    palette = theme["palette"]
    themed["colors"].update({
        "background": palette["background"],
        "surface": palette["surface"],
        "ink": palette["ink"],
        "muted": palette["muted"],
        "line": palette["line"],
        "accent": palette["accent"],
        "accent_soft": palette["accent_soft"],
        "source": palette["accent"],
        "relationship": palette["accent"],
        "synthesis": palette["warm"],
        "glass": f"{palette['surface']}/{theme['surface_opacity']}",
        "glass_soft": f"{palette['surface']}/{max(55, theme['surface_opacity'] - 14)}",
        "glass_line": f"{palette['line']}/48",
        "wash": f"linear(90deg, {palette['surface']}/72 0%, {palette['surface']}/28 72%, {palette['surface']}/0 100%)",
    })
    profile = {
        "enabled": True,
        "asset_id": asset["asset_id"],
        "reuse_mode": theme["reuse_mode"],
        "content_zone": theme["content_zone"],
        "protected_decoration_zone": theme["protected_decoration_zone"],
        "surface_policy": "TRANSLUCENT_OR_OPEN_NATIVE_SURFACES",
    }
    return themed, profile


def _layout_statement(page: dict[str, Any], tokens: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    colors, typo = tokens["colors"], tokens["typography"]
    claim = page["claims"][0]
    fused = _fusion_enabled(page)
    fill, accent = _claim_colors(claim, tokens, fused=fused)
    if fused:
        elements = [
            _shape(f"statement-field:{claim['id']}", _box(70, 234, 930, 316), fill=colors["surface"] + "/42", line="none", geometry="roundRect", line_width=0),
            _shape(f"statement-keyline:{claim['id']}", _box(88, 276, 72, 5), fill=accent + "/72", line="none", line_width=0),
            _text(f"claim:{claim['id']}", _claim_display_text(claim), _box(88, 300, 820, 178),
                  size=29, color=colors["ink"], bold=True, valign="middle"),
            _text(f"provenance:{claim['id']}", _provenance_label(claim), _box(88, 500, 500, 24),
                  size=typo["meta"], color=accent, bold=True),
        ]
        return elements, _relationship_connectors(page, tokens)
    elements = [
        _shape(f"claim:{claim['id']}", _box(88, 248, 1104, 282), fill=fill, line=accent,
               text=_claim_display_text(claim), size=27, color=colors["ink"], bold=True, align="center"),
        _text(f"provenance:{claim['id']}", _provenance_label(claim), _box(440, 548, 400, 24),
              size=typo["meta"], color=accent, bold=True, align="center"),
    ]
    return elements, _relationship_connectors(page, tokens)


def _layout_cards(page: dict[str, Any], tokens: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    colors, typo = tokens["colors"], tokens["typography"]
    claims = page["claims"]
    count = len(claims)
    positions: list[dict[str, int]]
    fused = _fusion_enabled(page)
    if fused:
        if count == 1:
            positions = [_box(88, 242, 930, 292)]
        elif count == 2:
            positions = [_box(88, 242, 448, 292), _box(560, 242, 448, 292)]
        elif count == 3:
            positions = [_box(88, 242, 296, 292), _box(400, 242, 296, 292), _box(712, 242, 296, 292)]
        else:
            positions = [_box(88, 232, 448, 150), _box(560, 232, 448, 150), _box(88, 402, 448, 150), _box(560, 402, 448, 150)]
    elif count == 1:
        positions = [_box(88, 242, 1104, 292)]
    elif count == 2:
        positions = [_box(88, 242, 540, 292), _box(652, 242, 540, 292)]
    elif count == 3:
        positions = [_box(88, 242, 348, 292), _box(466, 242, 348, 292), _box(844, 242, 348, 292)]
    else:
        positions = [_box(88, 232, 540, 150), _box(652, 232, 540, 150), _box(88, 402, 540, 150), _box(652, 402, 540, 150)]
    elements: list[dict[str, Any]] = []
    for claim, position in zip(claims, positions):
        fill, accent = _claim_colors(claim, tokens, fused=fused)
        elements.append(_shape(f"claim:{claim['id']}", position, fill=fill, line=colors["glass_line"] if fused else accent,
                               text=_claim_display_text(claim), size=typo["body"], color=colors["ink"], bold=False,
                               geometry="roundRect" if fused else "rect", line_width=1))
        if fused:
            elements.append(_shape(f"card-rail:{claim['id']}", _box(position["left"] + 18, position["top"] + 16, 46, 4), fill=accent + "/70", line="none", line_width=0))
        elements.append(_text(f"provenance:{claim['id']}", _provenance_label(claim),
                              _box(position["left"] + 18, position["top"] + position["height"] - 28, position["width"] - 36, 18),
                              size=typo["meta"], color=accent, bold=True))
    return elements, _relationship_connectors(page, tokens)


def _layout_columns(page: dict[str, Any], tokens: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    colors, typo = tokens["colors"], tokens["typography"]
    claims = page["claims"]
    fused = _fusion_enabled(page)
    available = 930 if fused else 1104
    gap = 28 if fused else 18
    width = (available - gap * (len(claims) - 1)) // len(claims)
    elements: list[dict[str, Any]] = []
    for index, claim in enumerate(claims):
        left = 88 + index * (width + gap)
        fill, accent = _claim_colors(claim, tokens, fused=fused)
        elements.extend([
            _shape(f"column-header:{claim['id']}", _box(left, 232, 56 if fused else width, 7 if fused else 10), fill=accent + ("/72" if fused else ""), line="none" if fused else accent, line_width=0 if fused else 1),
            _shape(f"claim:{claim['id']}", _box(left, 252, width, 302), fill=colors["glass_soft"] if fused else fill, line=colors["glass_line"] if fused else colors["line"],
                   text=_claim_display_text(claim), size=16, color=colors["ink"], geometry="roundRect" if fused else "rect"),
            _text(f"provenance:{claim['id']}", _provenance_label(claim), _box(left + 16, 526, width - 32, 18),
                  size=typo["meta"], color=accent, bold=True, align="center"),
        ])
    return elements, _relationship_connectors(page, tokens)


def _layout_flow(page: dict[str, Any], tokens: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    colors, typo = tokens["colors"], tokens["typography"]
    claims = page["claims"]
    fused = _fusion_enabled(page)
    available = 930 if fused else 1104
    gap = 80 if fused else 60
    width = (available - gap * (len(claims) - 1)) // len(claims)
    elements: list[dict[str, Any]] = []
    for index, claim in enumerate(claims):
        left = 88 + index * (width + gap)
        fill, accent = _claim_colors(claim, tokens, fused=fused)
        elements.extend([
            _text(f"step:{claim['id']}", str(index + 1).zfill(2), _box(left, 238, width, 28),
                  size=typo["meta"], color=accent, bold=True, align="center"),
            _shape(f"claim:{claim['id']}", _box(left, 280, width, 224), fill=fill, line=colors["glass_line"] if fused else accent,
                   text=_claim_display_text(claim), size=16, color=colors["ink"], align="center", geometry="roundRect" if fused else "rect"),
            _text(f"provenance:{claim['id']}", _provenance_label(claim), _box(left, 520, width, 20),
                  size=typo["meta"], color=accent, bold=True, align="center"),
        ])
    connectors = _relationship_connectors(page, tokens)
    return elements, connectors


def _layout_timeline(page: dict[str, Any], tokens: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    colors, typo = tokens["colors"], tokens["typography"]
    claims = page["claims"]
    fused = _fusion_enabled(page)
    available = 930 if fused else 1104
    if fused:
        width = 210 if len(claims) == 4 else (270 if len(claims) == 3 else 435)
    else:
        width = 248 if len(claims) == 4 else (1044 // len(claims))
    gap = (available - width * len(claims)) // max(1, len(claims) - 1)
    elements: list[dict[str, Any]] = [
        _shape(f"timeline-rail:{page['page_id']}", _box(100, 348 if fused else 324, 900 if fused else 1080, 4), fill=(colors["accent"] + "/44") if fused else colors["line"], line="none" if fused else colors["line"], line_width=0 if fused else 1),
    ]
    for index, claim in enumerate(claims):
        left = 88 + index * (width + gap)
        fill, accent = _claim_colors(claim, tokens, fused=fused)
        top = (222 if index % 2 == 0 else 368) if fused else (222 if index % 2 == 0 else 356)
        card_height = (100 if index % 2 == 0 else 108) if fused else 152
        elements.extend([
            _shape(f"timeline-marker:{claim['id']}", _box(left + width // 2 - 8, 340 if fused else 316, 16, 16), fill=accent, line=accent),
            _shape(f"claim:{claim['id']}", _box(left, top, width, card_height), fill=fill, line=colors["glass_line"] if fused else accent,
                   text=_claim_display_text(claim), size=15, color=colors["ink"], align="center", geometry="roundRect" if fused else "rect"),
            _text(f"provenance:{claim['id']}", _provenance_label(claim),
                  _box(left, top + card_height - 24 if fused else top + card_height + 8, width, 18),
                  size=typo["meta"], color=accent, bold=True, align="center"),
        ])
    return elements, _relationship_connectors(page, tokens)


def _layout_focus(page: dict[str, Any], tokens: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A focal Claim with supporting evidence on an open editorial canvas.

    Both slots size their text to the slot and drop the font one rung at a time, the way the
    flex grid does. The original geometry was written when Claims carried no conditions; once
    they do, a focal Claim can need 190px in a 155px box and a supporting Claim 109px in a
    58px slot, and the compiler then rejected the page instead of fitting it.
    """
    from app.layout_ir import TEXT_FRAME_INSET_HORIZONTAL, measure_text

    colors, typo = tokens["colors"], tokens["typography"]
    claims = page["claims"]
    focal_id = page["_layout_intent"]["focus_claim_id"]
    focal = next(claim for claim in claims if claim["id"] == focal_id)
    supporting = [claim for claim in claims if claim["id"] != focal_id]
    fused = _fusion_enabled(page)
    right = 602 if fused else 704
    right_width = 406 if fused else 488
    left_width = 474 if fused else 560
    band_top, band_height = 232, 368

    def fit(text: str, width: int, height: int, ladder: tuple[int, ...]) -> tuple[int, int]:
        for size in ladder:
            required = measure_text(text, width, size,
                                    horizontal_inset=TEXT_FRAME_INSET_HORIZONTAL,
                                    vertical_inset=0)["required_height"]
            if required <= height:
                return size, required
        size = ladder[-1]
        return size, measure_text(text, width, size, horizontal_inset=TEXT_FRAME_INSET_HORIZONTAL,
                                  vertical_inset=0)["required_height"]

    focal_text = _claim_display_text(focal)
    _, accent = _claim_colors(focal, tokens, fused=fused)
    focal_width = left_width - 35
    # Same band as the first supporting Claim: the focal text sits left of it, so the band's
    # left-to-right order is focal-then-support. A focal box offset below the first support row
    # reads as the page's *second* item and trips the reading-order contract (LD-01).
    focal_top = band_top
    focal_height = band_height - 40
    # Floor at a size a reader can still read. Shrinking dense approved text until it fits is
    # exactly the silent degradation the capacity gate exists to prevent: a page that cannot
    # hold its evidence must be split or re-composed, not quietly reduced.
    focal_size, focal_required = fit(focal_text, focal_width, focal_height, (25, 22, 20))
    elements = [
        _shape(f"focus-rail:{focal_id}", _box(88, focal_top - 6, 7, min(focal_height, 260)),
               fill=accent, line="none", line_width=0),
        # Declared as the slot, not as tall as the text would like: a box sized to its own
        # overflow hides it from the capacity gate, which is how a page can silently overrun.
        _text(f"claim:{focal_id}", focal_text,
              _box(114, focal_top, focal_width, min(focal_required, focal_height)),
              size=focal_size, color=colors["ink"], bold=True),
        _text(f"provenance:{focal_id}", _provenance_label(focal),
              _box(114, band_top + band_height - 28, focal_width, 18),
              size=typo["meta"], color=accent, bold=True),
    ]
    if supporting:
        step = band_height // len(supporting)
        for index, claim in enumerate(supporting):
            slot_top = band_top + index * step
            slot_height = step - 30
            text = _claim_display_text(claim)
            _, claim_accent = _claim_colors(claim, tokens, fused=fused)
            size, required = fit(text, right_width, slot_height, (21, 19, typo["body"]))
            elements.extend([
                _shape(f"support-line:{claim['id']}", _box(right, slot_top, right_width, 2),
                       fill=colors["line"], line="none", line_width=0),
                _text(f"claim:{claim['id']}", text,
                      _box(right, slot_top + 12, right_width, min(required, slot_height)),
                      size=size, color=colors["ink"]),
                _text(f"provenance:{claim['id']}", _provenance_label(claim),
                      _box(right, slot_top + step - 24, right_width, 18),
                      size=typo["meta"], color=claim_accent, bold=True),
            ])
    _assert_reading_order(page, elements)
    return elements, []


def _layout_flex(page: dict[str, Any], tokens: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve a model-authored composition tree into locked native Claim boxes."""
    colors, typo = tokens["colors"], tokens["typography"]
    intent = page["_layout_intent"]
    claims = {claim["id"]: claim for claim in page["claims"]}
    width = 930 if _fusion_enabled(page) else 1104
    elements: list[dict[str, Any]] = []

    def place(node: dict[str, Any], box: dict[str, int]) -> None:
        if node["kind"] == "claim":
            if box["width"] < 180 or box["height"] < 100:
                raise BeautificationPlanError(
                    f"Page {page['page_id']} FLEX_COMPOSITION gives Claim {node['claim_id']} "
                    "less than 180×100px; regroup or split the page.")
            claim = claims[node["claim_id"]]
            focal = claim["id"] == intent.get("focus_claim_id")
            _, accent = _claim_colors(claim, tokens, fused=_fusion_enabled(page))
            inset = 16 if focal else 0
            claim_text = _claim_display_text(claim)
            from app.layout_ir import TEXT_FRAME_INSET_HORIZONTAL, measure_text
            length = len(claim_text)
            # The ladder reaches down to the body token. A Claim that carries its
            # meaning-preserving conditions is legitimately long, so the composition the
            # model chose has to fit the approved text -- trimming the text to fit a
            # hard-coded size would drop exactly the qualifiers the bundle exists to keep.
            ladder = ((32, 27, 23, 20, 18) if length <= 45 else
                      (27, 23, 20, 18, 17) if length <= 90 else (23, 20, 18, 17)) if focal else (
                (27, 23, 20, 18) if length <= 45 else
                (23, 20, 18, 17) if length <= 90 else (20, 18, 17))
            text_width = box["width"] - inset
            available_height = box["height"] - 46

            def _fits(size: int) -> bool:
                return measure_text(claim_text, text_width, size,
                                    horizontal_inset=TEXT_FRAME_INSET_HORIZONTAL,
                                    vertical_inset=0)["required_height"] <= available_height

            font_size = next((size for size in ladder if _fits(size)), ladder[-1])
            # Measure against the width the rendered frame really offers. The writer
            # emits DrawingML defaults, so a text box loses ~0.2 in of horizontal room;
            # ignoring that put a third wrapped line on top of the provenance label.
            required = measure_text(claim_text, text_width, font_size,
                                    horizontal_inset=TEXT_FRAME_INSET_HORIZONTAL,
                                    vertical_inset=0)["required_height"]
            text_height = min(max(required + 8, 42), available_height)
            content_height = text_height + 32
            text_top = box["top"] + max(12, (box["height"] - content_height) // 2)
            elements.append(_shape(f"flex-rule:{claim['id']}",
                                   _box(box["left"], text_top - 8,
                                        7 if focal else box["width"],
                                        min(content_height + 10, box["height"] - 12) if focal else 2),
                                   fill=accent if focal else colors["line"], line="none", line_width=0))
            elements.append(_text(f"claim:{claim['id']}", claim_text,
                                  _box(box["left"] + inset, text_top, text_width, text_height),
                                  size=font_size, color=colors["ink"], bold=focal))
            elements.append(_text(f"provenance:{claim['id']}", _provenance_label(claim),
                                  _box(box["left"] + inset, text_top + text_height + 10,
                                       text_width, 18),
                                  size=typo["meta"], color=accent, bold=True))
            return
        children = node["children"]
        direction = node["kind"]
        gap = node.get("gap", 20)
        axis = "width" if direction == "row" else "height"
        start = "left" if direction == "row" else "top"
        available = box[axis] - gap * (len(children) - 1)
        total_weight = sum(child.get("weight", 1) for child in children)
        cursor = box[start]
        remaining = available
        for index, child in enumerate(children):
            size = remaining if index == len(children) - 1 else round(available * child.get("weight", 1) / total_weight)
            child_box = dict(box)
            child_box[start] = cursor
            child_box[axis] = size
            place(child, child_box)
            cursor += size + gap
            remaining -= size

    # 370px, not 334: a Claim that carries its meaning-preserving conditions needs about
    # 110-180px, and a two-row grid at 334 leaves each leaf only ~111px of usable height.
    # The band 564..600 was empty (the source footer sits at 666), so the composition gets
    # the room instead of the text being shrunk past legibility.
    place(intent["layout_tree"], _box(88, 230, width, 370))
    _assert_reading_order(page, elements)
    return elements, []


def _assert_reading_order(page: dict[str, Any], elements: list[dict[str, Any]]) -> None:
    """Reject a model composition whose geometry reorders the approved Claims.

    A natural "two columns" tree -- row[column[c1,c2], column[c3,c4]] -- puts c1 and c3 in
    the same visual band, so the page reads c1, c3, c2, c4. The approved order is part of the
    narrative, so that is a silent rewrite. `render_readback` catches it after rendering, but
    a designer should hear about it while designing, with the fix in the message.
    """
    from app import render_readback

    claim_names = [element["name"] for element in elements
                   if str(element.get("name", "")).startswith("claim:")]
    if len(claim_names) < 2:
        return
    shapes = [{"name": element["name"],
               "box": (element["position"]["left"], element["position"]["top"],
                       element["position"]["width"], element["position"]["height"])}
              for element in elements if element.get("name") in claim_names]
    actual = [f"claim:{claim['id']}" for claim in page["claims"]]
    if render_readback.compute_visual_order(shapes) != actual:
        raise BeautificationPlanError(
            f"Page {page['page_id']} FLEX_COMPOSITION would read in a different order than the "
            "approved Claims. Group with rows on the outside and columns inside "
            "(column[row[...], row[...]]) so each band holds consecutive Claims.")


def _layout_structure(page: dict[str, Any], tokens: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Title, the throughline in the reading's own words, and the arc segments beneath it.

    No Claims by design: this page states the argument the deck is about to make. Its text comes
    from the reading (`structure_text`), so what a viewer reads is the model's derived throughline
    rather than a caption the renderer invented to fill a box.
    """
    from app.layout_ir import TEXT_FRAME_INSET_HORIZONTAL, measure_text

    colors, typo = tokens["colors"], tokens["typography"]
    page_id = page["page_id"]
    text = str(page.get("structure_text") or "").strip()
    segments = [str(item).strip() for item in (page.get("structure_segments") or []) if str(item).strip()]
    elements: list[dict[str, Any]] = []
    band_top, band_width, band_height = 250, 1104, 202
    size = 21
    for candidate in (30, 28, 26, 24, 21):
        required = measure_text(text, band_width - 110, candidate,
                                horizontal_inset=TEXT_FRAME_INSET_HORIZONTAL, vertical_inset=0)["required_height"]
        size = candidate
        if required <= 142:
            break
    elements.append(_shape(f"structure-field:{page_id}", _box(88, band_top, band_width, band_height),
                           fill=colors["accent_soft"], line="none", line_width=0))
    elements.append(_shape(f"structure-rail:{page_id}", _box(88, band_top, 9, band_height),
                           fill=colors["accent"], line="none", line_width=0))
    elements.append(_text(f"structure:{page_id}", text, _box(130, band_top + 30, band_width - 110, 142),
                          size=size, color=colors["ink"], bold=True, valign="middle"))
    if segments:
        gap = 24
        step = (band_width - gap * (len(segments) - 1)) // len(segments)
        for index, segment in enumerate(segments):
            left = 88 + index * (step + gap)
            elements.append(_shape(f"segment-rule:{page_id}:{index}", _box(left, 500, step, 3),
                                   fill=colors["accent"], line="none", line_width=0))
            elements.append(_text(f"segment-number:{page_id}:{index}", f"{index + 1:02d}",
                                  _box(left, 520, 48, 28), size=20, color=colors["accent"], bold=True))
            elements.append(_text(f"segment-text:{page_id}:{index}", segment,
                                  _box(left + 52, 522, step - 52, 32),
                                  size=typo["body"], color=colors["ink"], valign="middle"))
    return elements, []


LAYOUT_BUILDERS = {
    "STRUCTURE_PAGE": _layout_structure,
    "EDITORIAL_STATEMENT": _layout_statement,
    "EVIDENCE_CARDS": _layout_cards,
    "COMPARISON_COLUMNS": _layout_columns,
    "DECISION_FLOW": _layout_flow,
    "TIMELINE": _layout_timeline,
    "FOCUS_EVIDENCE": _layout_focus,
    "FLEX_COMPOSITION": _layout_flex,
}


def compile_beautification_plan(
    deck: dict[str, Any],
    *,
    tokens: dict[str, Any] | None = None,
    editorial_assets: list[dict[str, Any]] | None = None,
    layout_ir: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile an auditable, deterministic layout plan for an approved deck."""
    effective_tokens = deepcopy(tokens or DESIGN_TOKENS)
    effective_assets = list(editorial_assets or [])
    if layout_ir is not None:
        from app.layout_ir import validate_layout_ir
        validate_layout_ir(deck, layout_ir)
    intent_by_page = {item["page_id"]: item for item in layout_ir["pages"]} if layout_ir else {}
    pages: list[dict[str, Any]] = []
    for ordinal, page in enumerate(deck.get("pages", []), start=1):
        page_id = str(page.get("page_id", f"page-{ordinal}"))
        if page.get("charts") or page.get("required_chart_ids"):
            raise BeautificationPlanError(
                f"Page {page_id} declares charts, but the native writer has no chart-data contract; "
                "delivery is blocked until chart series and labels can be read back.")
        claims = page.get("claims", [])
        if page.get("renders_structure"):
            structure_text = str(page.get("structure_text") or "").strip()
            segments = page.get("structure_segments") or []
            if not structure_text and not any(str(item).strip() for item in segments):
                raise BeautificationPlanError(
                    f"Page {page_id} renders a structure page without structure_text or "
                    "structure_segments; generation is blocked.")
        if not claims and not page.get("renders_structure"):
            raise BeautificationPlanError(f"Page {page_id} has no approved Claims; beautification is blocked.")
        if len(claims) > MAX_CLAIMS_PER_PAGE:
            raise BeautificationPlanError(
                f"Page {page_id} has {len(claims)} Claims; split the PageSpec before beautification (maximum {MAX_CLAIMS_PER_PAGE})."
            )
        claim_ids = [str(claim.get("id", "")) for claim in claims]
        if not all(claim_ids) or len(set(claim_ids)) != len(claim_ids):
            raise BeautificationPlanError(f"Page {page_id} contains missing or duplicate Claim IDs.")
        for relationship in page.get("relationships", []):
            if not relationship.get("id"):
                raise BeautificationPlanError(f"Page {page_id} contains a Relationship without an ID.")
            endpoints = {relationship.get("from_claim_id"), relationship.get("to_claim_id")}
            if not endpoints <= set(claim_ids):
                raise BeautificationPlanError(f"Page {page_id} relationship {relationship.get('id')} points outside the page Claim set.")
        intent = intent_by_page.get(page_id)
        candidates = _evaluate_candidates(page, include_focus=layout_ir is not None)
        valid = [candidate for candidate in candidates if candidate["status"] == "VALID"]
        if not valid:
            raise BeautificationPlanError(f"Page {page_id} has no safe native layout candidate; revise or split the PageSpec.")
        selected = (next(item for item in valid if item["archetype"] == intent["archetype"])
                    if intent else sorted(valid, key=lambda item: (-int(item["score"]), item["archetype"]))[0])
        page_assets = assets_for_page(effective_assets, page_id)
        page_tokens = effective_tokens
        fusion_profile: dict[str, Any] = {"enabled": False, "variant": "NONE"}
        page_for_layout = deepcopy(page)
        page_for_layout["_selected_archetype"] = selected["archetype"]
        if intent:
            page_for_layout["_layout_intent"] = intent
        if page_assets:
            page_tokens, fusion_profile = _apply_fusion_theme(effective_tokens, page_assets[0])
            fusion_profile["variant"] = {
                "EDITORIAL_STATEMENT": "OPEN_FIELD",
                "EVIDENCE_CARDS": "SOFT_CARDS",
                "COMPARISON_COLUMNS": "SPLIT_FIELD",
                "TIMELINE": "RHYTHM_BANDS",
                "DECISION_FLOW": "FLOW_NODES",
                "FOCUS_EVIDENCE": "OPEN_FIELD",
                "FLEX_COMPOSITION": "OPEN_FIELD",
            }[selected["archetype"]]
            page_for_layout["_fusion"] = fusion_profile
        layout_elements, connectors = LAYOUT_BUILDERS[selected["archetype"]](page_for_layout, page_tokens)
        source_lines = _source_lines(claims)
        elements = _common_elements(page_for_layout, ordinal, page_tokens) + layout_elements
        elements.append(_text(
            f"source-trace:{page_id}", "Source traceability: " + " · ".join(source_lines),
            _box(88, 666, 930 if page_assets else 1104, 20), size=page_tokens["typography"]["footer"],
            color=page_tokens["colors"]["muted"],
        ))
        pages.append({
            "page_id": page_id,
            "visual_type": page.get("visual_type"),
            "selected_archetype": selected["archetype"],
            "selection_score": selected["score"],
            "layout_intent": intent,
            "candidates": candidates,
            "elements": elements,
            "connectors": connectors,
            "source_lines": source_lines,
            "claim_ids": claim_ids,
            "required_text_by_object": {
                f"claim:{claim['id']}": [str(condition).strip() for condition in claim.get("conditions", [])
                                         if str(condition).strip()]
                for claim in claims
            },
            "relationship_ids": [str(item.get("id")) for item in page.get("relationships", [])],
            "editorial_assets": page_assets,
            "fusion": fusion_profile,
            "speaker_notes": [
                "[Sources]", *source_lines, "", "Claims: " + ", ".join(claim_ids),
                "Relationships: " + ", ".join(
                    f"{item.get('id')}:{item.get('relation_type', 'UNSPECIFIED')}:{item.get('direction', 'FORWARD')}"
                    for item in page.get("relationships", [])
                ),
                "Layout: " + selected["archetype"],
                "Fusion: " + fusion_profile["variant"],
            ],
        })
    plan = {
        "schema_version": "native_beautification_plan.v0.1",
        "renderer": "artifact-tool-native-editable",
        "native_editable": True,
        "semantic_deck_project_id": deck.get("project_id"),
        "external_asset_policy": {
            "allowed_roles": ["BACKGROUND_TEXTURE", "DECORATIVE_ILLUSTRATION", "NON_SEMANTIC_ICON"],
            "protected_native_roles": ["TITLE", "PRIMARY_MESSAGE", "CLAIM", "NUMERIC_EVIDENCE", "SOURCE", "RELATIONSHIP"],
            "providers": ["chatgpt-image", "figma"],
            "default": "ENABLED_WITH_VALIDATED_MANIFEST" if effective_assets else "DISABLED",
        },
        "tokens": effective_tokens,
        "layout_ir": layout_ir,
        "pages": pages,
    }
    from app.layout_ir import assess_plan_text_fit
    plan["text_fit"] = assess_plan_text_fit(plan)
    # A qualifier printed outside its frame is an omission in the delivered view.
    # Reject it before the writer can auto-shrink or clip the approved wording.
    conditioned = {f"claim:{claim['id']}" for page in deck.get("pages", [])
                   for claim in page.get("claims", []) if claim.get("conditions")}
    condition_fit_issues = [issue for issue in plan["text_fit"]["issues"]
                            if issue["object"] in conditioned or
                            str(issue["object"]).startswith("source-trace:")]
    if condition_fit_issues:
        summary = "; ".join(f"{item['page_id']}:{item['object']} needs {item['required_height']}px "
                            f"but has {item['declared_height']}px" for item in condition_fit_issues)
        raise BeautificationPlanError("Required conditions or source locations do not fit; split or revise the page: " + summary)
    selected_fit_issues = [issue for issue in plan["text_fit"]["issues"]
                           if issue["page_id"] in intent_by_page]
    if selected_fit_issues:
        summary = "; ".join(f"{item['page_id']}:{item['object']} needs {item['required_height']}px "
                            f"but has {item['declared_height']}px" for item in selected_fit_issues)
        raise BeautificationPlanError("Model-selected layout does not fit approved text; revise or split the page: " + summary)
    result = validate_beautification_plan(deck, plan)
    if result["status"] != "PASS":
        raise BeautificationPlanError("Invalid BeautificationPlan: " + "; ".join(issue["message"] for issue in result["issues"]))
    return plan


def validate_beautification_plan(deck: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Verify geometry, semantic coverage, native editability and plan identity."""
    issues: list[dict[str, Any]] = []
    if not plan.get("native_editable"):
        issues.append({"type": "NATIVE_EDITABILITY", "message": "Plan is not declared native-editable."})
    deck_pages = deck.get("pages", [])
    plan_pages = plan.get("pages", [])
    if len(deck_pages) != len(plan_pages):
        issues.append({"type": "PAGE_COUNT", "message": "Plan page count differs from Semantic Deck."})
    for deck_page, plan_page in zip(deck_pages, plan_pages):
        page_id = deck_page.get("page_id")
        if page_id != plan_page.get("page_id"):
            issues.append({"type": "PAGE_ID", "page_id": page_id, "message": "Plan page identity changed."})
        names = [element.get("name") for element in plan_page.get("elements", [])]
        expected_claims = {f"claim:{claim['id']}" for claim in deck_page.get("claims", [])}
        rendered_claims = {name for name in names if str(name).startswith("claim:")}
        if expected_claims != rendered_claims:
            issues.append({"type": "CLAIM_FIDELITY", "page_id": page_id, "message": "Plan Claim objects do not exactly match the page Claim set."})
        expected_relationships = {f"clinical_relationship:{item['id']}" for item in deck_page.get("relationships", [])}
        rendered_relationships = {item.get("name") for item in plan_page.get("connectors", [])}
        if expected_relationships != rendered_relationships:
            issues.append({"type": "RELATIONSHIP_FIDELITY", "page_id": page_id, "message": "Plan connector IDs do not exactly match explicit Relationships."})
        for element in plan_page.get("elements", []):
            position = element.get("position", {})
            left, top = position.get("left", -1), position.get("top", -1)
            width, height = position.get("width", 0), position.get("height", 0)
            if left < 0 or top < 0 or width <= 0 or height <= 0 or left + width > SLIDE_WIDTH or top + height > SLIDE_HEIGHT:
                issues.append({"type": "OUT_OF_BOUNDS", "page_id": page_id, "object": element.get("name"), "message": "Planned object is outside the slide canvas."})
        for claim in deck_page.get("claims", []):
            planned = next((item for item in plan_page.get("elements", []) if item.get("name") == f"claim:{claim['id']}"), None)
            if planned and str(claim.get("normalized_claim", "")) not in str(planned.get("text", "")):
                issues.append({"type": "CLAIM_TEXT", "page_id": page_id, "object": claim.get("id"), "message": "Claim text was altered or omitted in the plan."})
            if planned:
                for condition in claim.get("conditions", []):
                    if str(condition).strip() and str(condition).strip() not in str(planned.get("text", "")):
                        issues.append({"type": "CONDITION_OMITTED", "page_id": page_id,
                                       "object": claim.get("id"), "condition": condition,
                                       "message": "A required condition is missing from the planned Claim text."})
        for asset in plan_page.get("editorial_assets", []):
            if asset.get("provider") != "chatgpt-image" or asset.get("asset_class") != "NONSEMANTIC_EDITORIAL_BASE" or asset.get("layer_role") != "EDITORIAL_UNDERLAY":
                issues.append({"type": "EDITORIAL_ASSET_AUTHORITY", "page_id": page_id, "message": "External asset exceeds the non-semantic underlay role."})
        fusion = plan_page.get("fusion", {})
        if plan_page.get("editorial_assets") and not fusion.get("enabled"):
            issues.append({"type": "EDITORIAL_FUSION", "page_id": page_id, "message": "Editorial underlay lacks an active native-layer fusion profile."})
        if fusion.get("enabled"):
            protected_left = fusion["protected_decoration_zone"]["left"]
            for element in plan_page.get("elements", []):
                if str(element.get("name", "")).startswith("claim:"):
                    position = element["position"]
                    if position["left"] + position["width"] > protected_left:
                        issues.append({"type": "FUSION_SAFE_ZONE", "page_id": page_id, "object": element.get("name"), "message": "Claim surface intrudes into the protected editorial decoration zone."})
                    if element.get("fill") in {"#FFFFFF", "#F8FCFD"}:
                        issues.append({"type": "FUSION_SURFACE", "page_id": page_id, "object": element.get("name"), "message": "Opaque generic claim surface breaks underlay/native-layer fusion."})
    return {"status": "PASS" if not issues else "FAIL", "issues": issues, "pages_checked": len(plan_pages)}
