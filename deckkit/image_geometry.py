# -*- coding: utf-8 -*-
"""
Independent verification of image cropping on the rendered page.

The checker does not trust the build: it reads `naturalWidth/Height`,
`clientWidth/Height`, `object-fit` and `object-position` from the live DOM, then
re-implements the CSS cover algorithm itself and compares the resulting visible
source rectangle against `images.crop_plan()` recomputed from the deck JSON.

Checks
  FIT            object-fit must be `cover` (never `fill`/stretch)
  BOX_ASPECT     the rendered box must have the declared slot aspect
  FOCAL          object-position must equal the declared focal point
  CROP_RECT      the visible source rectangle must equal the planned rectangle
  ASSET          the image must actually load (a broken src is not a crop)
  UPSCALE        warn when the crop is enlarged beyond the declared limit
"""
import os
import pathlib
import re

from playwright.sync_api import sync_playwright

from . import images as IM

TOL = 1.5   # source pixels

_JS = r"""(sel) => {
  const out = [];
  document.querySelectorAll(sel).forEach((el) => {
    const cs = getComputedStyle(el);
    out.push({
      src: el.getAttribute('src') || '',
      naturalW: el.naturalWidth || 0, naturalH: el.naturalHeight || 0,
      clientW: el.clientWidth || 0, clientH: el.clientHeight || 0,
      fit: cs.objectFit, position: cs.objectPosition,
      slotW: +(el.getAttribute('data-slot-w') || 0),
      slotH: +(el.getAttribute('data-slot-h') || 0),
      focalX: +(el.getAttribute('data-focal-x') || 0),
      focalY: +(el.getAttribute('data-focal-y') || 0),
      complete: el.complete,
    });
  });
  return out;
}"""


def _pct(v):
    m = re.match(r"([\d.]+)%\s+([\d.]+)%", (v or "").strip())
    if not m:
        return None
    return float(m.group(1)) / 100.0, float(m.group(2)) / 100.0


def _css_visible(rendered):
    """Re-implement CSS object-fit:cover + object-position to get the source rect."""
    iw, ih = rendered["naturalW"], rendered["naturalH"]
    bw, bh = rendered["clientW"], rendered["clientH"]
    if min(iw, ih, bw, bh) <= 0:
        return None
    scale = max(bw / iw, bh / ih)
    vis_w, vis_h = bw / scale, bh / scale
    fx, fy = _pct(rendered["position"]) or (0.5, 0.5)
    x0 = (iw - vis_w) * fx
    y0 = (ih - vis_h) * fy
    return {"x": x0, "y": y0, "w": vis_w, "h": vis_h}


def read_rendered(html_path, mutate=None):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        pg.goto(pathlib.Path(html_path).resolve().as_uri(), wait_until="load", timeout=60000)
        pg.wait_for_timeout(500)
        if mutate:
            pg.evaluate("() => { " + mutate + " }")
            pg.wait_for_timeout(150)
        res = pg.evaluate(_JS, ".slide img.ph-img")
        b.close()
    return res


def compare(deck, base_dir, rendered):
    """Return the issue list (empty == PASS)."""
    issues = []
    items = []
    for sl in deck.get("slides", []):
        if not (sl.get("type") or "").startswith("image-"):
            continue
        boxes = IM.slot_boxes(sl)
        for i, it in enumerate(IM._items(sl)):
            items.append((sl, it, boxes[min(i, len(boxes) - 1)]))

    if len(rendered) != len(items):
        issues.append({"check": "ASSET", "detail":
                       f"rendered {len(rendered)} images for {len(items)} declared"})

    for (sl, it, box), rd in zip(items, rendered):
        src = it.get("src", "")
        fx, fy = (it.get("focal") or [0.5, 0.5])[:2]
        tag = os.path.basename(src)

        # 0) the RIGHT asset must occupy the slot (identity, not just geometry)
        got_src = os.path.basename((rd.get("src") or "").split("?")[0])
        if got_src and got_src != tag:
            issues.append({"check": "SRC_MISMATCH", "expected": tag, "actual": got_src})

        if rd["naturalW"] <= 0 or not rd["complete"]:
            issues.append({"check": "ASSET", "image": tag, "detail": "image did not load"})
            continue

        # 1) no stretching
        if rd["fit"] != "cover":
            issues.append({"check": "FIT", "image": tag, "expected": "cover", "actual": rd["fit"]})

        # 2) box aspect matches the declared slot
        slot_ar = box["w"] / box["h"]
        box_ar = rd["clientW"] / max(1, rd["clientH"])
        if abs(box_ar - slot_ar) / slot_ar > 0.02:
            issues.append({"check": "BOX_ASPECT", "image": tag,
                           "expected": round(slot_ar, 3), "actual": round(box_ar, 3)})

        # 3) focal point as declared
        got = _pct(rd["position"])
        if got is None or abs(got[0] - fx) > 0.01 or abs(got[1] - fy) > 0.01:
            issues.append({"check": "FOCAL", "image": tag,
                           "expected": [fx, fy], "actual": got})

        # 4) the visible source rectangle equals the plan
        plan = IM.crop_plan(rd["naturalW"], rd["naturalH"], rd["clientW"], rd["clientH"], fx, fy)
        shown = _css_visible(rd)
        if shown is None:
            issues.append({"check": "CROP_RECT", "image": tag, "detail": "no visible rect"})
        else:
            for f in ("x", "y", "w", "h"):
                if abs(shown[f] - plan["crop"][f]) > TOL:
                    issues.append({"check": "CROP_RECT", "image": tag, "field": f,
                                   "expected": round(plan["crop"][f], 2),
                                   "actual": round(shown[f], 2)})

        # 5) legibility: upscaling beyond the limit
        if plan["upscale"] > IM.MAX_UPSCALE:
            issues.append({"check": "UPSCALE", "image": tag,
                           "factor": plan["upscale"], "limit": IM.MAX_UPSCALE})
    return issues


def audit(deck, html_path, base_dir=None, mutate=None):
    rendered = read_rendered(html_path, mutate=mutate)
    issues = compare(deck, base_dir, rendered)
    return {"status": "PASS" if not issues else "FAIL", "issues": issues,
            "images_checked": len(rendered)}


# --------------------------------------------------------------------------
# Negative fixtures: each injected corruption MUST be caught.
# --------------------------------------------------------------------------
NEGATIVE_FIXTURES = [
    ("stretched", """
        document.querySelectorAll('.slide img.ph-img').forEach(el => {
          el.style.objectFit = 'fill';
          el.style.width = '100%'; el.style.height = '100%'; });
    """),
    ("focal-reset", """
        document.querySelectorAll('.slide img.ph-img').forEach(el => {
          el.style.objectPosition = '0% 0%'; });
    """),
    ("aspect-broken", """
        const el = document.querySelectorAll('.slide img.ph-img')[0];
        if (el) el.style.height = '120px';
    """),
    ("src-swapped", """
        const els = document.querySelectorAll('.slide img.ph-img');
        if (els.length > 1) {
          const b = els[1].getAttribute('src');
          els[1].setAttribute('src', els[0].getAttribute('src'));
          els[0].setAttribute('src', b);
        }
    """),
    ("asset-missing", """
        const el = document.querySelectorAll('.slide img.ph-img')[0];
        if (el) el.setAttribute('src', 'assets/images/__nope__.jpg');
    """),
]
