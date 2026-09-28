"""Client brand: colours and fonts taken from a customer's own PowerPoint template.

Reads the template's theme part (colour scheme, font scheme, master background)
and maps it onto FactDeck's theme tokens. Every token is pushed through a
contrast check (WCAG ratios) so a template cannot produce unreadable slides; the
colours actually used are recorded next to the template's originals. Brand only
changes appearance — layouts, text and checks are the same as for built-in themes.
"""
from __future__ import annotations

import io

from deckkit import colorutil as CU
from deckkit.theme_from_pptx import read_template, _font_stack

WHITE = "#FFFFFF"
DEFAULT_FONT = "Microsoft YaHei"


class BrandError(ValueError):
    pass


def _first_face(fonts: dict) -> str | None:
    """The template's body font for Chinese text (Hans, then East Asian, then Latin)."""
    f = (fonts or {}).get("minorFont") or {}
    for face in (f.get("hans"), f.get("ea"), f.get("latin")):
        face = (face or "").strip()
        if face and not face.startswith("+"):
            return face
    return None


def tokens_from_scheme(colors: dict) -> dict:
    accents = [colors.get(f"accent{i}") for i in range(1, 7)]
    accents = [a for a in accents if a]
    brand = accents[0] if accents else (colors.get("dk2") or colors.get("dk1") or "#1F3A5F")
    others = [a for a in accents[1:] if CU.to_hsl(a)[1] > 0.18]
    accent_seed = others[0] if others else brand

    primary = CU.ensure_contrast(brand, WHITE, 7.0)          # titles; white text sits on it
    primary2 = CU.ensure_contrast(CU.tint(primary, 0.18), WHITE, 4.5)
    accent = CU.ensure_contrast(accent_seed, WHITE, 4.5)     # emphasis text on white
    accent2 = CU.ensure_contrast(CU.tint(accent, 0.2), WHITE, 3.0)
    on_dark = CU.ensure_contrast(CU.tint(accent, 0.55), primary, 4.5)
    ink = CU.ensure_contrast(colors.get("dk1") or "#1A1A1A", WHITE, 7.0)
    return {"ink": ink, "primary": primary, "primary2": primary2, "accent": accent, "accent2": accent2,
            "accent-on-dark": on_dark, "soft": CU.blend(accent, WHITE, 0.88), "sky": CU.blend(primary, WHITE, 0.95),
            "line": CU.blend(primary, WHITE, 0.84), "muted": CU.ensure_contrast(CU.blend(ink, WHITE, 0.45), WHITE, 4.5)}


def from_template(content: bytes) -> dict:
    try:
        ex = read_template(io.BytesIO(content))
    except Exception as e:                       # not a zip, no theme part, broken XML
        raise BrandError(f"无法读取模板主题：{e}") from None
    if not ex.get("colors"):
        raise BrandError("模板中没有配色方案")
    tokens = tokens_from_scheme(ex["colors"])
    return {"tokens": tokens, "font": _first_face(ex.get("fonts")), "font_stack": _font_stack(ex.get("fonts")),
            "template_colors": ex["colors"], "template_fonts": ex.get("fonts", {}), "master_background": ex.get("master_bg"),
            "contrast": {"primary_on_white": round(CU.contrast(tokens["primary"], WHITE), 2),
                         "accent_on_white": round(CU.contrast(tokens["accent"], WHITE), 2),
                         "accent_on_dark": round(CU.contrast(tokens["accent-on-dark"], tokens["primary"]), 2),
                         "ink_on_white": round(CU.contrast(tokens["ink"], WHITE), 2)}}
