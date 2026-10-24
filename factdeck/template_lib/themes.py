"""Theme tokens for Template Library v1.

Colors are adapted from the existing academic 10-set *style* palettes
(`app.academic_templates.STYLES` journal + steel) plus a paid-quality
`premium_clinical` system for showcase / commercial craft.

Those ten academic sets remain reference/QA only — this module is the
runtime fill source for slot packs.
"""
from __future__ import annotations

# Academic palette seeds (accent, background, ink) — see app/academic_templates.py
_JOURNAL = ("#355E78", "#F6F4EF", "#151B24")
_STEEL = ("#466D88", "#FFFFFF", "#1E3444")

# Premium clinical — one cohesive paid-quality system (not FreePPT outline boxes).
# Deep ink + single steel-teal accent + warm paper + soft tonal surfaces.
_PREMIUM = {
    "ink": "#0E1A2B",
    "primary": "#14364F",
    "primary2": "#1F4E6E",
    "accent": "#1A6B7C",
    "accent2": "#2A8594",
    "accent-on-dark": "#9AD0D9",
    "soft": "#E4EEF1",
    "sky": "#F2F5F7",
    "line": "#C9D6DC",
    "muted": "#5A6B78",
    "canvas": "#F4F2EC",
    "paper": "#FFFFFF",
    "headline": "#0E1A2B",
    "caption": "#7A8794",
    "surface": "#E8F0F3",
    "surface2": "#F7F5F0",
    "rail": "#1A6B7C",
    "shadow": "rgba(14, 26, 43, 0.10)",
    "shadow-soft": "rgba(14, 26, 43, 0.06)",
    "on-accent": "#FFFFFF",
    "takeaway-bg": "#E4F1F4",
}


def _expand(accent: str, background: str, ink: str) -> dict[str, str]:
    """Map a 3-stop academic seed onto FactDeck's deck.html.j2 CSS variable set."""
    primary = accent
    primary2 = {
        "#355E78": "#4A7590",
        "#466D88": "#5A8099",
    }.get(accent, accent)
    accent2 = {
        "#355E78": "#5A8AA6",
        "#466D88": "#6B93A8",
    }.get(accent, accent)
    on_dark = {
        "#355E78": "#A8C5D6",
        "#466D88": "#B0C8D6",
    }.get(accent, "#C5D5E0")
    soft = {
        "#355E78": "#E8EEF2",
        "#466D88": "#E6EEF3",
    }.get(accent, "#EEF2F5")
    sky = background if background.upper() != "#FFFFFF" else "#F2F5F8"
    line = {
        "#355E78": "#D4DCE3",
        "#466D88": "#D2DBE3",
    }.get(accent, "#D8E0E8")
    muted = {
        "#355E78": "#5A6B7E",
        "#466D88": "#5C6F80",
    }.get(accent, "#5A6B7E")
    surface = {
        "#355E78": "#E8EEF2",
        "#466D88": "#E8EEF3",
    }.get(accent, "#EEF2F5")
    return {
        "ink": ink,
        "primary": primary,
        "primary2": primary2,
        "accent": accent,
        "accent2": accent2,
        "accent-on-dark": on_dark,
        "soft": soft,
        "sky": sky,
        "line": line,
        "muted": muted,
        "canvas": background,
        "paper": "#FFFFFF",
        "headline": ink if accent == "#466D88" else primary,
        "caption": "#8e8e93",
        "surface": surface,
        "surface2": sky,
        "rail": accent,
        "shadow": "rgba(21, 27, 36, 0.08)",
        "shadow-soft": "rgba(21, 27, 36, 0.05)",
        "on-accent": "#FFFFFF",
        "takeaway-bg": soft,
    }


THEMES: dict[str, dict[str, str]] = {
    "journal": _expand(*_JOURNAL),
    "steel": _expand(*_STEEL),
    "premium_clinical": dict(_PREMIUM),
}

THEME_META = {
    "journal": {
        "id": "journal",
        "name": "医学期刊风",
        "suitable_for": "资料密集、重视来源与限定条件的医学课程。",
        "tone": "克制、清晰、低饱和蓝灰",
        "reference_academic_id": "01_journal",
    },
    "steel": {
        "id": "steel",
        "name": "临床会议风",
        "suitable_for": "临床会议、病例讨论及专业交流。",
        "tone": "钢蓝、紧凑、正式",
        "reference_academic_id": "10_steel",
    },
    "premium_clinical": {
        "id": "premium_clinical",
        "name": "精品临床教学",
        "suitable_for": "付费级医学教育课件、医院教学查房、药企 MLR 教学稿。",
        "tone": "深墨、钢青强调、暖纸面、色块分层，非描边白盒",
        "reference_academic_id": None,
        "craft": "paid_quality_v1.2",
    },
}


def get_theme(name: str) -> dict[str, str]:
    if name not in THEMES:
        raise KeyError(f"未知主题：{name}（可用：{', '.join(sorted(THEMES))}）")
    return dict(THEMES[name])


def list_themes() -> list[dict]:
    order = ("premium_clinical", "journal", "steel")
    return [dict(THEME_META[k], tokens=dict(THEMES[k])) for k in order]
