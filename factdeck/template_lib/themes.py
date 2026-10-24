"""Theme tokens for Template Library v1.

Colors are adapted from the existing academic 10-set *style* palettes
(`app.academic_templates.STYLES` journal + steel). Those ten sets remain
reference/QA only — this module is the runtime fill source for slot packs.
"""
from __future__ import annotations

# Academic palette seeds (accent, background, ink) — see app/academic_templates.py
_JOURNAL = ("#355E78", "#F6F4EF", "#151B24")
_STEEL = ("#466D88", "#FFFFFF", "#1E3444")


def _expand(accent: str, background: str, ink: str) -> dict[str, str]:
    """Map a 3-stop academic seed onto FactDeck's deck.html.j2 CSS variable set."""
    # primary = surface / band colour derived from accent (slightly deeper for contrast on white text)
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
        # Extra tokens for light-canvas medical-ppt-adapted layouts
        "canvas": background,
        "paper": "#FFFFFF",
        "headline": primary,
        "caption": "#8e8e93",
    }


THEMES: dict[str, dict[str, str]] = {
    "journal": _expand(*_JOURNAL),
    "steel": _expand(*_STEEL),
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
}


def get_theme(name: str) -> dict[str, str]:
    if name not in THEMES:
        raise KeyError(f"未知主题：{name}（可用：{', '.join(sorted(THEMES))}）")
    return dict(THEMES[name])


def list_themes() -> list[dict]:
    return [dict(THEME_META[k], tokens=dict(THEMES[k])) for k in ("journal", "steel")]
