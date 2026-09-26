# -*- coding: utf-8 -*-
"""
Renderer: HTML deck -> per-slide PNG + PDF, via headless Chromium.
No framework, no SPA: one static file, deterministic output.
"""
import os
import sys
import pathlib
import shutil

CANVAS = {"width": 1280, "height": 720}
SCALE = 2.0  # 2560x1440 output


def _file_url(path):
    return pathlib.Path(path).resolve().as_uri()


def render(html_path, out_dir, pdf=None, png=True, scale=SCALE, quiet=False):
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("playwright"):
            raise RuntimeError(
                "The optional deckkit HTML renderer requires Playwright. "
                "Install deckkit/requirements-render.txt and run "
                "`python -m playwright install chromium`."
            ) from exc
        raise

    os.makedirs(out_dir, exist_ok=True)
    made = {"png": [], "pdf": None}

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport=CANVAS, device_scale_factor=scale)
        pg.goto(_file_url(html_path), wait_until="load", timeout=60000)
        pg.wait_for_timeout(600)

        n = pg.evaluate("() => document.querySelectorAll('.slide').length")
        if not quiet:
            print(f"  slides found: {n}")

        if png:
            for i in range(1, int(n) + 1):
                el = pg.query_selector(f"#s{i}")
                if el is None:
                    continue
                path = os.path.join(out_dir, f"{i:02d}.png")
                el.screenshot(path=path)
                made["png"].append(path)
                if not quiet:
                    print(f"  png {i:02d} ok")

        if pdf:
            pg.pdf(path=pdf, width="1280px", height="720px",
                   print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            made["pdf"] = pdf
            if not quiet:
                print(f"  pdf -> {pdf}")

        b.close()
    return made


def render_themes(deck, out_root, theme_names, png=False, pdf=True, scale=SCALE):
    """Render the same deck under several themes (used to demonstrate theming)."""
    from . import build
    results = {}
    for tn in theme_names:
        d = os.path.join(out_root, tn)
        os.makedirs(d, exist_ok=True)
        html = os.path.join(d, "slides.html")
        build.write_html(deck, html, tn)
        pdf_path = os.path.join(d, "deck.pdf") if pdf else None
        results[tn] = render(html, os.path.join(d, "png"), pdf=pdf_path, png=png, scale=scale)
    return results
