# -*- coding: utf-8 -*-
"""
Extract a deckkit theme from an existing PowerPoint template.

    python -m deckkit theme-from-pptx company-template.pptx --name acme

Reads the real theme part (`ppt/theme/themeN.xml`): colour scheme (dk1/lt1/dk2/lt2,
accent1..6, hlink/folHlink) and font scheme (major/minor, latin + east-asian).
The slide-master background fill is used to detect a dark template and to seed
the page background.

The extracted palette is then mapped onto deckkit's token contract and pushed
through the same WCAG enforcer used by `theme-from`, so ingesting a sloppy
template cannot produce unreadable slides.
"""
import os
import re
import zipfile
from xml.etree import ElementTree as ET

from . import colorutil as CU
from . import theme_gen as TG

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def _srgb(el):
    if el is None:
        return None
    srgb = el.find(f"{A}srgbClr")
    if srgb is not None:
        return CU.norm(srgb.get("val"))
    sysc = el.find(f"{A}sysClr")
    if sysc is not None:
        v = sysc.get("lastClr")
        if v:
            return CU.norm(v)
        return "#000000" if sysc.get("val") == "windowText" else "#FFFFFF"
    return None


def _scheme_colors(clr_scheme):
    out = {}
    for child in list(clr_scheme):
        out[child.tag.replace(A, "")] = _srgb(child)
    return {k: v for k, v in out.items() if v}


def _fonts(font_scheme):
    out = {}
    for which in ("majorFont", "minorFont"):
        el = font_scheme.find(f"{A}{which}")
        if el is None:
            continue
        latin = el.find(f"{A}latin")
        ea = el.find(f"{A}ea")
        hans = None
        for f in el.findall(f"{A}font"):
            if f.get("script") == "Hans":
                hans = f.get("typeface")
        out[which] = {
            "latin": (latin.get("typeface") if latin is not None else "") or "",
            "ea": (ea.get("typeface") if ea is not None else "") or "",
            "hans": hans or "",
        }
    return out


def _master_bg(z):
    for name in z.namelist():
        if re.match(r"ppt/slideMasters/slideMaster\d+\.xml$", name):
            try:
                root = ET.fromstring(z.read(name))
            except ET.ParseError:
                continue
            bg = root.find(f"{P}cSld/{P}bg")
            if bg is None:
                continue
            solid = bg.find(f".//{A}solidFill")
            c = _srgb(solid) if solid is not None else None
            if c:
                return c
    return None


def read_template(path):
    """Raw extraction from a .pptx/.potx."""
    with zipfile.ZipFile(path) as z:
        theme_part = next((n for n in z.namelist()
                           if re.match(r"ppt/theme/theme\d+\.xml$", n)), None)
        if theme_part is None:
            raise ValueError("no theme part in this file (is it a real .pptx?)")
        root = ET.fromstring(z.read(theme_part))
        clr = root.find(f"{A}themeElements/{A}clrScheme")
        fs = root.find(f"{A}themeElements/{A}fontScheme")
        colors = _scheme_colors(clr) if clr is not None else {}
        fonts = _fonts(fs) if fs is not None else {}
        pres = ET.fromstring(z.read("ppt/presentation.xml"))
        sld = pres.find(f"{P}sldSz")
        size = ((int(sld.get("cx")), int(sld.get("cy"))) if sld is not None else (12192000, 6858000))
        return {"theme_part": theme_part, "colors": colors, "fonts": fonts,
                "slide_size": size, "master_bg": _master_bg(z)}


def _font_stack(fonts):
    """Prefer the CJK face when the deck is Chinese."""
    f = (fonts or {}).get("minorFont") or {}
    faces = [x for x in (f.get("hans"), f.get("ea"), f.get("latin")) if x]
    cleaned = []
    for x in faces:
        x = x.strip()
        if x and not x.startswith("+") and x not in cleaned:
            cleaned.append(x)
    if not cleaned:
        return None
    return ",".join(f"'{x}'" for x in cleaned) + ",'Microsoft YaHei',sans-serif"


def to_theme(ex, *, name="custom", mode=None, font=None, label=None):
    """Map an extracted scheme onto deckkit tokens (contrast-enforced)."""
    c = ex.get("colors", {})
    lt1 = c.get("lt1") or "#FFFFFF"
    dk1 = c.get("dk1") or "#000000"
    lt2 = c.get("lt2")
    dk2 = c.get("dk2")
    accents = [c.get(f"accent{i}") for i in range(1, 7)]
    accents = [a for a in accents if a]

    # decide light/dark from the master background, else from lt1
    bg_seed = ex.get("master_bg") or lt1
    if mode is None:
        mode = "dark" if CU.rel_luminance(bg_seed) < 0.42 else "light"

    # OOXML convention: accent1 is the primary brand colour, accent2 the first
    # emphasis colour. "Most saturated" would pick an orange logo colour here and
    # lose the corporate navy, so follow the convention instead.
    def sat(h):
        return CU.to_hsl(h)[1]
    brand = accents[0] if accents else (dk2 or dk1)

    t = TG.from_brand(brand, name=name, mode=mode, font=font or _font_stack(ex.get("fonts")),
                      label=label or f"模板导入 · {os.path.basename(str(ex.get('source', name)))}")

    # adopt the template's own background / surface / ink where they are usable
    if mode == "light":
        if bg_seed and CU.rel_luminance(bg_seed) > 0.72:
            t["bg"] = bg_seed
            t["bg2"] = lt2 or CU.blend(bg_seed, "#FFFFFF", 0.35)
        if lt1 and CU.rel_luminance(lt1) > 0.6:
            t["surface"] = lt1
        ink = dk2 or dk1
        if ink:
            t["ink"] = CU.ensure_contrast(ink, t["surface"], 7.0)
            t["heading"] = CU.ensure_contrast(_darken_hue(brand, 0.30), t["bg"], 4.5)
    else:
        t["bg"] = bg_seed if CU.rel_luminance(bg_seed) < 0.25 else t["bg"]
        t["surface"] = CU.blend(t["bg"], "#FFFFFF", 0.06)
        t["bg2"] = CU.blend(t["bg"], "#FFFFFF", 0.03)
        if lt2 and CU.rel_luminance(lt2) > 0.10:
            t["surface"] = CU.blend(t["bg"], lt2, 0.10)
        # in a dark template dk2 is normally the LIGHT text slot; prefer it
        ink_seed = dk2 if (dk2 and CU.rel_luminance(dk2) > 0.55) else (lt1 or dk2)
        t["ink"] = CU.ensure_contrast(ink_seed, t["surface"], 7.0)
        t["heading"] = CU.ensure_contrast(accents[0] if accents else lt1, t["bg"], 4.5)

    # accent2 (the template's first emphasis colour) becomes deckkit's accent
    if len(accents) > 1:
        alt = [a for a in accents[1:] if CU.to_hsl(a)[1] > 0.18]
        if alt:
            t["accent"] = CU.ensure_contrast(alt[0], t["bg"], 3.0)
            t["accent_text"] = CU.ensure_contrast(t["accent"], t["bg"], 4.5)
            t["accent_text"] = CU.ensure_contrast(t["accent_text"], t["surface"], 4.5)
            t["accent_soft"] = CU.blend(t["accent"], t["bg"], 0.86)

    # re-enforce everything after the swaps
    t["ink2"] = CU.ensure_contrast(t["ink2"], t["surface"], 4.5)
    t["muted"] = CU.ensure_contrast(t["muted"], t["bg"], 3.0)
    t["heading"] = CU.ensure_contrast(t["heading"], t["bg"], 4.5)
    t["heading"] = CU.ensure_contrast(t["heading"], t["surface"], 4.5)
    t["accent"] = CU.ensure_contrast(t["accent"], t["bg"], 3.0)
    t["accent_text"] = CU.ensure_contrast(t["accent_text"], t["bg"], 4.5)
    t["accent_text"] = CU.ensure_contrast(t["accent_text"], t["surface"], 4.5)
    t["on_primary"] = CU.pick_foreground(t["primary"])
    t["badge"] = t["accent_text"] if mode == "light" else t["accent"]
    t["badge_on"] = CU.ensure_contrast(CU.pick_foreground(t["badge"]), t["badge"], 4.5)
    t["brand_bg"] = (f"linear-gradient(96deg,{CU.shade(t['primary'],0.28)} 0%,{t['primary']} 62%,"
                     f"{CU.tint(t['primary'],0.14)} 100%)")
    t["mode"] = mode
    t["extracted_from"] = ex.get("theme_part")
    t["template_colors"] = c
    return t


def _darken_hue(h, amount):
    hue, sat, light = CU.to_hsl(h)
    return CU.from_hsl(hue, min(0.85, sat), max(0.12, light * (1 - amount)))


def from_pptx(path, *, name="custom", mode=None, font=None, label=None):
    ex = read_template(path)
    ex["source"] = path
    return to_theme(ex, name=name, mode=mode, font=font, label=label)
