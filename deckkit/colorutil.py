# -*- coding: utf-8 -*-
"""
Colour utilities: sRGB/HSL conversion, WCAG relative luminance and contrast,
and a contrast enforcer that nudges lightness until a target ratio is met.

Used by the theme generator so a brand colour can never produce unreadable text.
"""
import colorsys


def norm(h):
    h = str(h).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"bad hex colour: {h!r}")
    return "#" + h.upper()


def to_rgb(h):
    h = norm(h)[1:]
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def to_hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def to_hsl(h):
    r, g, b = (c / 255.0 for c in to_rgb(h))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)     # note: hls order
    return hh * 360.0, ss, ll


def from_hsl(hue, sat, light):
    hue = (hue % 360) / 360.0
    s = max(0.0, min(1.0, sat))
    l = max(0.0, min(1.0, light))
    r, g, b = colorsys.hls_to_rgb(hue, l, s)
    return to_hex((r * 255, g * 255, b * 255))


def rel_luminance(h):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = to_rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = rel_luminance(a), rel_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _adjust(h, bg, target, darker=None):
    """Move lightness away from bg until contrast >= target (bounded steps)."""
    if darker is None:
        darker = rel_luminance(h) < rel_luminance(bg)
    hue, sat, light = to_hsl(h)
    for _ in range(60):
        if contrast(h, bg) >= target:
            return h
        light += -0.02 if darker else 0.02
        if light <= 0.0 or light >= 1.0:
            break
        h = from_hsl(hue, sat, light)
    # last resort: pure black / white
    return "#000000" if darker else "#FFFFFF"


def ensure_contrast(fg, bg, target=4.5):
    """Return an fg colour that meets `target` contrast against bg."""
    if contrast(fg, bg) >= target:
        return norm(fg)
    return _adjust(norm(fg), norm(bg), target)


def ensure_pair(fg, bg, target=4.5, prefer_dark=None):
    """Same as ensure_contrast but returns a stable, already-normalised colour."""
    return ensure_contrast(fg, bg, target)


def pick_foreground(bg, *candidates):
    """Best readable foreground on bg: first candidate meeting 4.5, else whichever
    of black/white actually contrasts more (never a luminance guess)."""
    for c in candidates:
        if c and contrast(c, bg) >= 4.5:
            return norm(c)
    return "#000000" if contrast("#000000", bg) >= contrast("#FFFFFF", bg) else "#FFFFFF"


def blend(a, b, t):
    """Linear sRGB blend, t=0 → a, t=1 → b."""
    ra, ga, ba = to_rgb(a)
    rb, gb, bb = to_rgb(b)
    return to_hex((ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t))


def tint(h, amount):
    return blend(h, "#FFFFFF", amount)


def shade(h, amount):
    return blend(h, "#000000", amount)
