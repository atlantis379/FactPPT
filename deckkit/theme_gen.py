# -*- coding: utf-8 -*-
"""
Generate a complete, contrast-safe deckkit theme from a brand colour.

    python -m deckkit theme-from "#E4002B" --name cmcc-red
    python -m deckkit theme-from "#0E7C5A" --mode dark --accent "#D9A441"

Derivation is deterministic: same input -> same tokens. Every text/background
pair that carries meaning is pushed through the WCAG enforcer, so a theme
produced here cannot ship unreadable text.
"""
from . import colorutil as CU

# semantic hues reused across themes (light-mode tuned)
OK_H, WARN_H, DANGER_H = 148.0, 36.0, 6.0


def _semantic(hue, mode, sat=0.62):
    if mode == "dark":
        return CU.from_hsl(hue, sat, 0.42), CU.from_hsl(hue, min(1.0, sat), 0.12)
    return CU.from_hsl(hue, sat, 0.32), CU.from_hsl(hue, min(1.0, sat), 0.94)


def from_brand(brand, *, name="custom", mode="light", accent=None, font=None,
               label=None, radius=None, title_weight=800):
    """Return a full theme token dict derived from one brand colour."""
    brand = CU.norm(brand)
    h, s, l = CU.to_hsl(brand)
    s_cap = max(0.10, min(s, 0.92))
    dark = mode == "dark"

    if dark:
        bg = CU.from_hsl(h, min(s_cap, 0.30), 0.075)
        bg2 = CU.from_hsl(h, min(s_cap, 0.30), 0.115)
        surface = CU.from_hsl(h, min(s_cap, 0.26), 0.145)
        line = CU.from_hsl(h, min(s_cap, 0.26), 0.245)
        ink = CU.from_hsl(h, 0.20, 0.945)
        ink2 = CU.from_hsl(h, 0.16, 0.760)
        muted = CU.from_hsl(h, 0.14, 0.580)
        primary = CU.from_hsl(h, s_cap, 0.160)
        primary_soft = CU.from_hsl(h, min(s_cap, 0.45), 0.220)
        heading = CU.from_hsl(h, min(s_cap, 0.55), 0.880)
    else:
        bg = CU.from_hsl(h, min(s_cap, 0.42), 0.972)
        bg2 = CU.from_hsl(h, min(s_cap, 0.42), 0.930)
        surface = "#FFFFFF"
        line = CU.from_hsl(h, min(s_cap, 0.34), 0.858)
        ink = CU.from_hsl(h, 0.32, 0.145)
        ink2 = CU.from_hsl(h, 0.24, 0.305)
        muted = CU.from_hsl(h, 0.16, 0.505)
        primary = CU.from_hsl(h, s_cap, 0.290)
        primary_soft = CU.from_hsl(h, min(s_cap, 0.40), 0.930)
        heading = CU.from_hsl(h, min(s_cap, 0.70), 0.265)

    # accent: a near-complementary hue by default, otherwise the supplied one
    acc = CU.norm(accent) if accent else CU.from_hsl(
        h + 158, min(0.72, max(0.30, s_cap)), 0.34 if not dark else 0.60)
    accent_soft = CU.from_hsl(CU.to_hsl(acc)[0], CU.to_hsl(acc)[1], 0.13 if dark else 0.935)

    ok, ok_soft = _semantic(OK_H, mode)
    warn, warn_soft = _semantic(WARN_H, mode)
    danger, danger_soft = _semantic(DANGER_H, mode)

    # ---- enforce legibility (this is the part that makes it safe) ----
    heading = CU.ensure_contrast(heading, bg, 4.5)
    ink = CU.ensure_contrast(ink, surface, 7.0)
    ink2 = CU.ensure_contrast(ink2, surface, 4.5)
    muted = CU.ensure_contrast(muted, bg, 3.0)
    acc = CU.ensure_contrast(acc, bg, 3.0)
    # accent_text: the high-contrast variant used whenever accent colours TEXT
    accent_text = CU.ensure_contrast(acc, bg, 4.5)
    accent_text = CU.ensure_contrast(accent_text, surface, 4.5)

    on_primary = CU.pick_foreground(primary, CU.from_hsl(h, 0.10, 0.985), "#FFFFFF")
    badge = accent_text if not dark else acc
    badge_on = CU.ensure_contrast(CU.pick_foreground(badge), badge, 4.5)

    brand_bg = (f"linear-gradient(96deg,{CU.shade(primary,0.28)} 0%,{primary} 62%,"
                f"{CU.tint(primary,0.14)} 100%)")
    figure_bg = (f"linear-gradient(160deg,{CU.tint(bg, 0.05)} 0%,{CU.blend(bg, line, 0.55)} 100%)"
                 if not dark else
                 f"linear-gradient(160deg,{surface} 0%,{bg} 100%)")

    return {
        "label": label or f"品牌色 {brand}",
        "brand": brand, "mode": mode, "generated": True,
        "bg": bg, "bg2": bg2, "surface": surface,
        "ink": ink, "ink2": ink2, "muted": muted, "line": line,
        "primary": primary, "primary_soft": primary_soft,
        "accent": acc, "accent_soft": accent_soft, "on_primary": on_primary,
        "accent_text": accent_text,
        "heading": heading, "badge": badge, "badge_on": badge_on,
        "ok": ok, "ok_soft": ok_soft, "warn": warn, "warn_soft": warn_soft,
        "danger": danger, "danger_soft": danger_soft,
        "font": font or "'Microsoft YaHei','PingFang SC','Noto Sans SC',sans-serif",
        "title_weight": title_weight,
        "radius": radius or ("12px" if dark else "14px"),
        "shadow": ("0 10px 26px rgba(0,0,0,.45)" if dark else "0 8px 20px rgba(9,58,96,.10)"),
        "brand_bg": brand_bg, "figure_bg": figure_bg,
        "title_size": "27px",
    }


# pairs that carry meaning and must satisfy a contrast floor.
# `primary` is a SURFACE colour here (brand bar), so the meaningful pair is
# on_primary/primary — primary is not required to contrast with the page.
CONTRAST_PAIRS = [
    ("heading", "bg", 4.5, "标题 / 页面底色"),
    ("heading", "surface", 4.5, "标题 / 卡片"),
    ("ink", "surface", 7.0, "正文 / 卡片"),
    ("ink2", "surface", 4.5, "次级正文 / 卡片"),
    ("muted", "bg", 3.0, "脚注 / 页面底色"),
    ("accent", "bg", 3.0, "强调色标记 / 页面底色"),
    ("accent_text", "bg", 4.5, "强调色文字 / 页面底色"),
    ("accent_text", "surface", 4.5, "强调色文字 / 卡片"),
    ("on_primary", "primary", 4.5, "品牌条文字 / 品牌条底色"),
    ("badge_on", "badge", 4.5, "徽章文字 / 徽章底色"),
]


def check_theme(t):
    """Return a list of contrast violations for a theme dict."""
    bad = []
    for fg, bg, target, note in CONTRAST_PAIRS:
        if fg not in t or bg not in t:
            bad.append({"pair": f"{fg}/{bg}", "note": note, "error": "token missing"})
            continue
        r = CU.contrast(t[fg], t[bg])
        if r < target - 0.02:
            bad.append({"pair": f"{fg}/{bg}", "note": note,
                        "ratio": round(r, 2), "target": target,
                        "fg": t[fg], "bg": t[bg]})
    return bad
