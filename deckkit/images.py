# -*- coding: utf-8 -*-
"""
Image geometry: crop planning, validation and verification.

A photo dropped into a fixed slot must be CROPPED, not stretched, and the crop
must be predictable. This module computes the visible region deterministically
from (source size, slot aspect, focal point) and exposes it in three forms:

  * CSS      -> object-position: fx% fy%   (with object-fit: cover)
  * OOXML    -> crop_left / crop_right / crop_top / crop_bottom ratios
  * audit    -> the same numbers re-derived so the rendered page can be checked

Policy:
  * a missing/unreadable asset becomes a labelled placeholder, never a stretch
  * crops are forbidden from cutting the declared focal point out of frame
  * upscaling beyond `MAX_UPSCALE` raises a legibility warning (never silently)
"""
import os
import struct

MAX_UPSCALE = 3.0


# --------------------------------------------------------------------- probing
def _png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    return struct.unpack(">II", head[16:24])


def _jpeg_size(path):
    with open(path, "rb") as f:
        data = f.read()
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seg
    raise ValueError("no JPEG SOF marker")


def probe(path):
    """(width, height) or None when the file is missing / not a real image."""
    if not path or not os.path.isfile(path):
        return None
    try:
        if path.lower().endswith(".png"):
            return _png_size(path)
        if path.lower().endswith((".jpg", ".jpeg")):
            return _jpeg_size(path)
        # fall back to Pillow for other formats
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------- geometry
def crop_plan(iw, ih, slot_w, slot_h, fx=0.5, fy=0.5):
    """Deterministic cover-crop.

    Semantics are exactly CSS `object-fit:cover` + `object-position:fx% fy%`:
    the source point at (fx, fy) lands at (fx, fy) of the frame. That makes the
    plan and the rendered page comparable term by term, and the OOXML crop
    ratios are derived from the same rectangle.
    """
    if iw <= 0 or ih <= 0 or slot_w <= 0 or slot_h <= 0:
        raise ValueError("crop_plan needs positive sizes")
    slot_ar = slot_w / slot_h
    img_ar = iw / ih

    if img_ar > slot_ar:                      # image too wide -> trim sides
        vis_h = float(ih)
        vis_w = vis_h * slot_ar
        x0 = (iw - vis_w) * fx
        y0 = 0.0
    else:                                     # image too tall -> trim top/bottom
        vis_w = float(iw)
        vis_h = vis_w / slot_ar
        x0 = 0.0
        y0 = (ih - vis_h) * fy

    crop = {
        "x": round(x0, 4), "y": round(y0, 4),
        "w": round(vis_w, 4), "h": round(vis_h, 4),
    }
    ooxml = {
        "left": round(x0 / iw, 6),
        "right": round((iw - (x0 + vis_w)) / iw, 6),
        "top": round(y0 / ih, 6),
        "bottom": round((ih - (y0 + vis_h)) / ih, 6),
    }
    upscale = max(slot_w / vis_w, slot_h / vis_h)
    return {
        "source": {"w": iw, "h": ih},
        "slot": {"w": slot_w, "h": slot_h, "ar": round(slot_ar, 4)},
        "crop": crop, "ooxml_crop": ooxml,
        "object_position": f"{round(fx*100, 2)}% {round(fy*100, 2)}%",
        "focal": {"x": fx, "y": fy},
        "upscale": round(upscale, 3),
    }


def focal_visible(plan):
    """The declared focal point must survive the crop."""
    fx = plan["focal"]["x"] * plan["source"]["w"]
    fy = plan["focal"]["y"] * plan["source"]["h"]
    c = plan["crop"]
    return (c["x"] - 0.5 <= fx <= c["x"] + c["w"] + 0.5 and
            c["y"] - 0.5 <= fy <= c["y"] + c["h"] + 0.5)


def spec_errors(sl):
    """Slide-level problems that must block rendering."""
    errs = []
    items = _items(sl)
    if not items:
        errs.append("no images declared")
    for i, it in enumerate(items):
        src = it.get("src")
        if not src:
            errs.append(f"image[{i}] has no src")
        fx, fy = it.get("focal", [0.5, 0.5]) if isinstance(it.get("focal"), list) else (0.5, 0.5)
        if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
            errs.append(f"image[{i}] focal point outside 0..1")
    return errs


# --------------------------------------------------------------- slot geometry
# One source of truth for image boxes, shared by the HTML layout and the PPTX
# exporter so the two cannot drift (same approach as charts.py).
GEOM = {
    "image-hero": lambda n: [{"x": 0, "y": 0, "w": 1280, "h": 720}],
    "image-split-left": lambda n: [{"x": 30, "y": 150, "w": 592, "h": 470}],
    "image-split-right": lambda n: [{"x": 658, "y": 150, "w": 592, "h": 470}],
    "image-grid2": lambda n: [
        {"x": 30, "y": 168, "w": 604, "h": 330},
        {"x": 646, "y": 168, "w": 604, "h": 330}],
    "image-grid3": lambda n: [
        {"x": 30, "y": 168, "w": 393, "h": 300},
        {"x": 443, "y": 168, "w": 393, "h": 300},
        {"x": 857, "y": 168, "w": 393, "h": 300}],
    "image-grid4": lambda n: [
        {"x": 30, "y": 160, "w": 604, "h": 236},
        {"x": 646, "y": 160, "w": 604, "h": 236},
        {"x": 30, "y": 412, "w": 604, "h": 236},
        {"x": 646, "y": 412, "w": 604, "h": 236}],
}


def layout_kind(sl):
    """Which geometry key a slide uses."""
    kind = (sl.get("type") or "").lower()
    if kind == "image-hero":
        return "image-hero"
    if kind == "image-split":
        return "image-split-right" if (sl.get("side") or "left").lower() == "right" else "image-split-left"
    n = min(4, max(2, len(sl.get("images") or [])))
    return f"image-grid{n}"


def slot_boxes(sl):
    return GEOM[layout_kind(sl)](len(_items(sl)))


def _items(sl):
    if sl.get("images"):
        return sl["images"]
    return [sl] if sl.get("src") else []


def audit_slide(sl, base_dir, slot_boxes):
    """Compare the planned crop with what the page actually renders."""
    issues = []
    plans = []
    items = _items(sl)
    for i, it in enumerate(items):
        size = probe(os.path.join(base_dir, it["src"])) if it.get("src") else None
        if size is None:
            plans.append({"index": i, "missing": True, "src": it.get("src")})
            continue
        box = slot_boxes[i]
        fx, fy = (it.get("focal") or [0.5, 0.5])[:2]
        plan = crop_plan(size[0], size[1], box["w"], box["h"], fx, fy)
        plan["index"] = i
        plan["src"] = it["src"]
        if not focal_visible(plan):
            issues.append({"check": "FOCAL_CROPPED", "image": i,
                           "focal": plan["focal"], "crop": plan["crop"]})
        if plan["upscale"] > MAX_UPSCALE:
            issues.append({"check": "UPSCALE", "image": i,
                           "factor": plan["upscale"], "limit": MAX_UPSCALE})
        plans.append(plan)
    return {"issues": issues, "plans": plans}
