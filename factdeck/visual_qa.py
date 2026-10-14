"""Early visual QA for the A route: checks that run before the full-deck export.

- preflight_layout: the export's browser overflow/overlap gate, run at layout submission.
- contrast_issues: locked text against what is actually behind it (native surface or artwork).
- occlusion_issues: opaque native surfaces hiding artwork, or artwork containers that
  extend beyond the native surface laid over them.
- vector_preview: clean PNG | Adobe SVG as rendered by Chromium | native trace, side by side.
  Chromium renders SVG gradients; a renderer without gradient support paints them black.

These are signals for the worker and the page reviewer; only overflow/overlap block,
exactly as the final export does.
"""
from __future__ import annotations

import copy
from pathlib import Path

CONTRAST_MIN = 3.0          # WCAG large-text minimum; below it locked content is hard to read
ARTWORK_COVER_MIN = 0.04    # share of a native surface's area where hidden artwork differs from its backdrop


def preflight_layout(model, font, components=()):
    """Same browser measurement and automatic fitting as factdeck.visual_render.render, one page, no artwork."""
    from playwright.sync_api import sync_playwright
    from factdeck.visual_render import document, fit_orphan_headers, fit_text_lineboxes, ORPHAN_HEADER_JS, LAYOUT_CHECK_JS
    m = copy.deepcopy(model); m["rasters"] = []; m["figures"] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(); page = browser.new_page(viewport={"width": 1280, "height": 720})
        def load():
            page.set_content(document([m], [[]], font)); page.evaluate("document.fonts.ready")
        load()
        if fit_orphan_headers(m, page.locator("#slide1").evaluate(ORPHAN_HEADER_JS), components): load()
        metrics = page.locator("#slide1").evaluate("el => [...el.querySelectorAll('[data-qa-text]')].map(n=>({scroll_w:n.scrollWidth,client_w:n.clientWidth,scroll_h:n.scrollHeight,client_h:n.clientHeight}))")
        if fit_text_lineboxes(m, metrics): load()
        checks = page.locator("#slide1").evaluate(LAYOUT_CHECK_JS)
        browser.close()
    return {"overflow": checks["overflow"], "overlap": checks["overlap"]}


def _rgb(hex_value):
    h = hex_value.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _lum(rgb):
    def ch(c):
        c = c / 255; return c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb); return .2126 * r + .7152 * g + .0722 * b


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True); return (la + .05) / (lb + .05)


def _area(a):
    return max(0, a["w"]) * max(0, a["h"])


def _overlap(a, b):
    return max(0, min(a["x"]+a["w"], b["x"]+b["w"]) - max(a["x"], b["x"])) * max(0, min(a["y"]+a["h"], b["y"]+b["h"]) - max(a["y"], b["y"]))


def _opaque(shape):
    f = shape.get("fill"); return bool(f) and f.get("a", 1) >= .9


def _crop(image, box):
    sx, sy = image.width / 1280, image.height / 720
    x0, y0 = max(0, round(box["x"]*sx)), max(0, round(box["y"]*sy))
    x1, y1 = min(image.width, round((box["x"]+box["w"])*sx)), min(image.height, round((box["y"]+box["h"])*sy))
    return image.crop((x0, y0, x1, y1)) if x1 > x0 and y1 > y0 else None


def _median(pixels):
    if not pixels: return None
    return tuple(sorted(p[i] for p in pixels)[len(pixels)//2] for i in range(3))


def _dist(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def _sample(img, step=2):
    w, h = img.size; data = img.load()
    return [data[x, y] for y in range(0, h, step) for x in range(0, w, step)]


def contrast_issues(model, image_path):
    """Each locked text box against its backdrop: the topmost opaque native surface, else the artwork."""
    from PIL import Image
    image = Image.open(image_path).convert("RGB"); issues = []
    for index, t in enumerate(model["texts"]):
        runs = [r for p in t.get("paras", []) for r in p if r.get("text", "").strip() and r.get("color")]
        if not runs or t.get("hidden"): continue
        ink = _rgb(runs[0]["color"]["hex"]); text = "".join(r["text"] for r in runs)[:40]
        under = [s for s in model.get("shapes", []) if _opaque(s) and _overlap(s, t) >= .6 * max(1, _area(t))]
        if under:
            back, basis = _rgb(under[-1]["fill"]["hex"]), "native_surface"
        else:
            crop = _crop(image, t)
            if crop is None: continue
            # Ignore pixels that look like the text itself (design images still contain text).
            back = _median([p for p in _sample(crop) if _dist(p, ink) > 60]) or _median(_sample(crop))
            basis = "artwork"
        ratio = contrast(ink, back)
        if ratio < CONTRAST_MIN:
            issues.append({"type": "LOW_CONTRAST", "text_index": index, "text": text, "ink": "#%02X%02X%02X" % ink,
                           "backdrop": "#%02X%02X%02X" % back, "basis": basis, "ratio": round(ratio, 2)})
    return issues


def occlusion_issues(model, clean_path):
    """Opaque native surfaces that hide artwork, or sit on a container that continues past them."""
    from PIL import Image
    image = Image.open(clean_path).convert("RGB"); issues = []
    paper = _median(_sample(_crop(image, {"x": 0, "y": 0, "w": 1280, "h": 30}), 2))   # artwork paper at the top edge
    for index, s in enumerate(model.get("shapes", [])):
        if not _opaque(s) or _area(s) < .01 * 1280 * 720: continue
        crop = _crop(image, s)
        if crop is None: continue
        pixels = _sample(crop); base = _median(pixels)
        hidden = sum(_dist(p, base) > 48 for p in pixels) / len(pixels)
        if hidden > ARTWORK_COVER_MIN:
            issues.append({"type": "ARTWORK_HIDDEN", "shape_index": index, "box": {k: s[k] for k in ("x", "y", "w", "h")}, "hidden_share": round(hidden, 3)})
        inset = max(s.get("radius", 0), 8) + 4
        def strips(d):
            return {"bottom": {"x": s["x"]+inset, "y": s["y"]+s["h"]+d, "w": s["w"]-2*inset, "h": 8},
                    "top": {"x": s["x"]+inset, "y": s["y"]-d-8, "w": s["w"]-2*inset, "h": 8},
                    "left": {"x": s["x"]-d-8, "y": s["y"]+inset, "w": 8, "h": s["h"]-2*inset},
                    "right": {"x": s["x"]+s["w"]+d, "y": s["y"]+inset, "w": 8, "h": s["h"]-2*inset}}
        near, far = strips(4), strips(24)
        for side in near:
            tones = []
            for box in (near[side], far[side]):
                covered = any(_opaque(o) and _overlap(o, box) >= .5 * max(1, _area(box)) for o in model.get("shapes", []) if o is not s)
                strip = None if covered or box["w"] <= 0 or box["h"] <= 0 else _crop(image, box)
                tones.append(_median(_sample(strip, 1)) if strip else None)
            # The artwork's own container tone continues at least 24px past the native surface.
            if all(t and _dist(t, base) <= 4 and _dist(t, paper) > 5 for t in tones):
                issues.append({"type": "CONTAINER_EXTENDS", "shape_index": index, "side": side, "box": {k: s[k] for k in ("x", "y", "w", "h")},
                               "artwork_tone": "#%02X%02X%02X" % tones[0]})
    return issues


def vector_preview(svg_bytes, clean_path, out_path, components=()):
    """Three panels at 640×360: clean PNG, Adobe SVG in Chromium, native trace (what PowerPoint receives)."""
    import base64
    from PIL import Image
    from playwright.sync_api import sync_playwright
    from factdeck.native_vectors import trace_svg
    from factdeck.visual_render import svg_markup
    vec, stats = trace_svg(svg_bytes, components)
    raw = "data:image/svg+xml;base64," + base64.b64encode(svg_bytes).decode()
    out_path = Path(out_path); panels = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(); page = browser.new_page(viewport={"width": 1280, "height": 720})
        for markup in (f'<img src="{raw}" style="width:1280px;height:720px;display:block">',
                       f'<div style="position:relative;width:1280px;height:720px;background:#F6F4EF">{svg_markup(vec)}</div>'):
            page.set_content(f'<html><body style="margin:0;background:#F6F4EF">{markup}</body></html>')
            panels.append(Image.open(__import__("io").BytesIO(page.screenshot())).convert("RGB"))
        browser.close()
    clean = Image.open(clean_path).convert("RGB")
    sheet = Image.new("RGB", (1920, 360), "white")
    for i, im in enumerate([clean, *panels]): sheet.paste(im.resize((640, 360)), (640*i, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True); sheet.save(out_path)
    return {"preview": str(out_path), "panels": ["clean", "svg_chromium", "native_trace"], "vector": stats}
