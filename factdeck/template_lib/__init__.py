"""FactDeck Template Library v1 — cover / section / key-points / comparison / flow / timeline.

Layouts adapted from medical-ppt-design (CC BY 4.0); SNUBH branding stripped.
Colors from journal + steel academic palettes (runtime tokens here; 10-set library
remains reference-only). See ATTRIBUTION.md and docs/TEMPLATE_LIB_V1.md.
"""
from .fill import fill_deck, normalize_fill
from .html_render import render_deck_html, render_page_html, write_deck_html
from .native_hook import TASK as T_TEMPLATE_NATIVE, describe as native_describe, prepare as native_prepare
from .slots import load_manifest, validate_fill, zone_map_px
from .themes import THEMES, get_theme, list_themes

__all__ = [
    "THEMES",
    "T_TEMPLATE_NATIVE",
    "fill_deck",
    "get_theme",
    "list_themes",
    "load_manifest",
    "native_describe",
    "native_prepare",
    "normalize_fill",
    "render_deck_html",
    "render_page_html",
    "validate_fill",
    "write_deck_html",
    "zone_map_px",
]
