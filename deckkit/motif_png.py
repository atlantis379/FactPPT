# -*- coding: utf-8 -*-
"""
Rasterise theme-coloured motif SVGs to transparent PNGs.

Motifs are drawn with `currentColor`; for PPTX we need real bitmaps, so each
motif is rendered once per theme accent colour and cached. Decorative art may be
raster while every semantic string stays native and editable in the PPTX.
"""
import hashlib
import os

from playwright.sync_api import sync_playwright

from . import motifs

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "_motif_png")
W, H = 800, 400          # 2:1, transparent background
SCALE = 2                # 1600x800 output


def _key(name, color):
    h = hashlib.sha1(f"{name}|{color}|{W}x{H}@{SCALE}".encode()).hexdigest()[:10]
    return f"{name}-{color.lstrip('#')}-{h}.png"


def ensure(name, color, cache_dir=None):
    """Return a path to a PNG of `motif` drawn in `color` (cached)."""
    d = cache_dir or CACHE_DIR
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, _key(name, color))
    if os.path.isfile(path):
        return path
    svg = motifs.get(name)
    html = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
            f'html,body{{margin:0;padding:0;background:transparent}}'
            f'#w{{width:{W}px;height:{H}px;display:flex;align-items:center;'
            f'justify-content:center;color:{color}}}'
            f'#w svg{{width:100%;height:100%;display:block}}</style></head>'
            f'<body><div id="w">{svg}</div></body></html>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=SCALE)
        pg.set_content(html, wait_until="load")
        pg.wait_for_timeout(120)
        pg.locator("#w").screenshot(path=path, omit_background=True)
        b.close()
    return path


def ensure_many(names, color, cache_dir=None):
    return {n: ensure(n, color, cache_dir) for n in names}


def preload_theme(color, cache_dir=None):
    """Render every motif once for a theme colour."""
    return ensure_many(list(motifs.MOTIFS), color, cache_dir)
