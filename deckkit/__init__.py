# -*- coding: utf-8 -*-
"""
deckkit — theme-pluggable PPT beautification pipeline.

    deck JSON  +  theme  ->  self-contained HTML  ->  PNG / PDF  (and PPTX)

Design goals
------------
* **Theme-independent layouts**: no layout contains a literal colour, so the same
  content renders correctly under every theme (clinical / corporate / editorial /
  techdark / mono).
* **Content-independent themes**: a theme is pure data (tokens), so adding a new
  visual style never touches layout code.
* **Deterministic geometry**: each slide is a fixed 1280x720 canvas with
  absolutely-positioned blocks; nothing can push content off-canvas.
* **No AI dependency**: motif illustrations are vector and drawn with
  `currentColor`, so they inherit whatever palette the theme defines.
"""
from .themes import THEMES, DEFAULT_THEME, get as get_theme
from .build import build_html, write_html, load_deck, slide_count
from .render import render, render_themes
from . import motifs, layouts, css

__all__ = [
    "THEMES", "DEFAULT_THEME", "get_theme",
    "build_html", "write_html", "load_deck", "slide_count",
    "render", "render_themes", "motifs", "layouts", "css",
]
__version__ = "0.1.0"
