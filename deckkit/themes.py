# -*- coding: utf-8 -*-
"""
Theme registry for deckkit.

A theme is pure data: design tokens only. Layouts never hard-code a colour,
so the same slide markup renders correctly under every theme.

Built-in themes are curated; `theme_gen.from_brand()` derives new ones from a
brand colour, and `themes_user/*.json` are loaded automatically.
"""
import io
import json
import os

# --------------------------------------------------------------------------
# token keys (all required):
#   bg bg2 surface ink ink2 muted line
#   primary primary_soft accent accent_soft on_primary
#   ok ok_soft warn warn_soft danger danger_soft
#   font title_weight radius shadow brand_bg figure_bg
# --------------------------------------------------------------------------

THEMES = {
    # 1 -------------------------------------------------- clinical (medical)
    "clinical": {
        "label": "临床蓝 · 医学学术",
        "bg": "#e7f6fd", "bg2": "#d6ecf7", "surface": "#ffffff",
        "ink": "#12314a", "ink2": "#2b4a63", "muted": "#6b8aa3", "line": "#bcdcee",
        "primary": "#033E75", "primary_soft": "#dbeaf7", "accent": "#268B90",
        "accent_soft": "#dff1f1", "accent_text": "#227B80", "on_primary": "#ffffff",
        "heading": "#033E75", "badge": "#033E75", "badge_on": "#ffffff",
        "ok": "#2f7d5b", "ok_soft": "#e5f2ea",
        "warn": "#b8791b", "warn_soft": "#fbf0dd",
        "danger": "#c0453a", "danger_soft": "#fbeae9",
        "font": "'Microsoft YaHei','PingFang SC','Noto Sans SC',sans-serif",
        "title_weight": 800, "radius": "16px",
        "shadow": "0 8px 20px rgba(9,58,96,.10)",
        "brand_bg": "linear-gradient(96deg,#033E75 0%,#0a5591 62%,#12639f 100%)",
        "figure_bg": "linear-gradient(160deg,#f4fbff 0%,#dcecf8 100%)",
        "title_size": "27px",
    },
    # 2 -------------------------------------------------- corporate (report)
    "corporate": {
        "label": "企业深蓝 · 经营汇报",
        "bg": "#f4f6f9", "bg2": "#e8edf3", "surface": "#ffffff",
        "ink": "#182534", "ink2": "#3c4b5c", "muted": "#7d8b9a", "line": "#dbe2ea",
        "primary": "#12385f", "primary_soft": "#e3eaf2", "accent": "#B77D27",
        "accent_soft": "#f8efdd", "accent_text": "#956620", "on_primary": "#ffffff",
        "heading": "#12385f", "badge": "#12385f", "badge_on": "#ffffff",
        "ok": "#2f7d5b", "ok_soft": "#e6f1ea",
        "warn": "#b3701a", "warn_soft": "#f9efdc",
        "danger": "#b03a34", "danger_soft": "#f8e9e7",
        "font": "'Microsoft YaHei','PingFang SC','Noto Sans SC',sans-serif",
        "title_weight": 800, "radius": "10px",
        "shadow": "0 6px 16px rgba(18,56,95,.10)",
        "brand_bg": "linear-gradient(96deg,#0d2b47 0%,#12385f 70%,#1b4d7c 100%)",
        "figure_bg": "linear-gradient(160deg,#fbfcfe 0%,#e9eef4 100%)",
        "title_size": "27px",
    },
    # 3 -------------------------------------------------- editorial (paper)
    "editorial": {
        "label": "纸感暖调 · 学术编辑",
        "bg": "#faf6ef", "bg2": "#f2ebdf", "surface": "#ffffff",
        "ink": "#2a2521", "ink2": "#4d453d", "muted": "#8c8175", "line": "#e3d9c9",
        "primary": "#7a3b2e", "primary_soft": "#f4e6e0", "accent": "#3F6B58",
        "accent_soft": "#e4efe9", "accent_text": "#3F6B58", "on_primary": "#ffffff",
        "heading": "#7a3b2e", "badge": "#7a3b2e", "badge_on": "#ffffff",
        "ok": "#3f6b58", "ok_soft": "#e4efe9",
        "warn": "#a9761f", "warn_soft": "#f7eeda",
        "danger": "#a33a2c", "danger_soft": "#f6e5e1",
        "font": "'Songti SC','SimSun','Noto Serif SC',Georgia,serif",
        "title_weight": 700, "radius": "4px",
        "shadow": "0 2px 8px rgba(60,45,30,.08)",
        "brand_bg": "linear-gradient(96deg,#5f2c22 0%,#7a3b2e 70%,#96513f 100%)",
        "figure_bg": "linear-gradient(160deg,#fdfbf7 0%,#f1e9dc 100%)",
        "title_size": "28px",
    },
    # 4 -------------------------------------------------- techdark
    "techdark": {
        "label": "深色科技 · 产品发布",
        "bg": "#0d1726", "bg2": "#132135", "surface": "#16243a",
        "ink": "#eaf2fb", "ink2": "#b9cbe0", "muted": "#7d93ad", "line": "#26384f",
        "primary": "#0e2a45", "primary_soft": "#1b3b5c", "accent": "#25C2C7",
        "accent_soft": "#123438", "accent_text": "#25C2C7", "on_primary": "#ffffff",
        "heading": "#eaf2fb", "badge": "#25c2c7", "badge_on": "#06202b",
        "ok": "#4ad295", "ok_soft": "#123027",
        "warn": "#e0a53c", "warn_soft": "#33280f",
        "danger": "#f2705f", "danger_soft": "#3a1c19",
        "font": "'Microsoft YaHei','PingFang SC','Noto Sans SC',sans-serif",
        "title_weight": 800, "radius": "12px",
        "shadow": "0 10px 26px rgba(0,0,0,.45)",
        "brand_bg": "linear-gradient(96deg,#08121f 0%,#0e2a45 60%,#123f5c 100%)",
        "figure_bg": "linear-gradient(160deg,#16243a 0%,#0f1c2e 100%)",
        "title_size": "27px",
    },
    # 5 -------------------------------------------------- mono (consulting)
    "mono": {
        "label": "极简黑白 · 咨询风格",
        "bg": "#ffffff", "bg2": "#f2f2f2", "surface": "#ffffff",
        "ink": "#111111", "ink2": "#3d3d3d", "muted": "#8a8a8a", "line": "#dcdcdc",
        "primary": "#111111", "primary_soft": "#ededed", "accent": "#C0392B",
        "accent_soft": "#f7e9e7", "accent_text": "#C0392B", "on_primary": "#ffffff",
        "heading": "#111111", "badge": "#111111", "badge_on": "#ffffff",
        "ok": "#2f6b45", "ok_soft": "#e8f0ea",
        "warn": "#9c6b12", "warn_soft": "#f6f0e2",
        "danger": "#c0392b", "danger_soft": "#f7e9e7",
        "font": "'Microsoft YaHei','PingFang SC','Noto Sans SC',sans-serif",
        "title_weight": 900, "radius": "0px",
        "shadow": "none",
        "brand_bg": "#111111",
        "figure_bg": "linear-gradient(160deg,#fafafa 0%,#ededed 100%)",
        "title_size": "28px",
    },
}

DEFAULT_THEME = "clinical"

# ---------------------------------------------------------------- user themes
# Generated themes live as JSON in deckkit/themes_user/<name>.json and are picked
# up automatically, so `--theme my-brand` works across every command.
USER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes_user")


def _load_user_themes():
    out = {}
    if not os.path.isdir(USER_DIR):
        return out
    for fn in sorted(os.listdir(USER_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with io.open(os.path.join(USER_DIR, fn), encoding="utf-8") as f:
                t = json.load(f)
            name = t.get("name") or os.path.splitext(fn)[0]
            t["user_theme"] = True
            out[name] = t
        except Exception:  # noqa: BLE001
            continue
    return out


THEMES.update(_load_user_themes())


def get(name):
    """Resolve a theme by name; a '#RRGGBB' string generates one on the fly."""
    if isinstance(name, str) and name.startswith("#"):
        from . import theme_gen as TG
        t = TG.from_brand(name)
        t["name"] = name
        return t
    if name in THEMES:
        return THEMES[name]
    raise KeyError(f"unknown theme {name!r}; available: {', '.join(THEMES)}")


def save_user_theme(name, tokens):
    """Persist a generated theme so later runs can reference it by name."""
    os.makedirs(USER_DIR, exist_ok=True)
    data = dict(tokens)
    data["name"] = name
    path = os.path.join(USER_DIR, f"{name}.json")
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    THEMES[name] = data
    return path
