# -*- coding: utf-8 -*-
"""Assemble a self-contained HTML deck from (deck JSON + theme)."""
import json
import os
import io

from . import themes, css, layouts
from .motifs import MOTIFS

FONT_LINKS = ""  # system fonts only: no network, portable output


def load_deck(path_or_dict):
    if isinstance(path_or_dict, dict):
        return path_or_dict
    with io.open(path_or_dict, encoding="utf-8") as f:
        return json.load(f)


def build_html(deck, theme_name=None, base_dir=None):
    meta = dict(deck.get("meta", {}))
    tn = theme_name or deck.get("theme") or themes.DEFAULT_THEME
    t = themes.get(tn)

    slides = deck.get("slides", [])
    body = []
    for i, s in enumerate(slides, start=1):
        body.append(layouts.render(s, meta, i, t))

    used = set()
    for s in slides:
        for m in (s.get("motif"), s.get("figure")):
            if m:
                used.add(m)
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{meta.get("title","deck")}</title>
{FONT_LINKS}
<style>
{css.tokens_css(t)}
{css.BASE_CSS}
</style>
</head>
<body data-theme="{tn}" data-theme-label="{t['label']}">
{chr(10).join(body)}
</body>
</html>
'''


def collect_assets(deck):
    """Every local file path referenced by the deck (images and figures)."""
    out = []
    for s in deck.get("slides", []):
        for key in ("src", "figure"):
            v = s.get(key)
            if isinstance(v, str) and v and not v.startswith(("http://", "https://", "data:")):
                out.append(v)
        for it in (s.get("images") or []):
            v = it.get("src")
            if isinstance(v, str) and v and not v.startswith(("http://", "https://", "data:")):
                out.append(v)
    return sorted(set(out))


def copy_assets(deck, html_path, base_dir):
    """Copy referenced assets next to the HTML so the export is self-contained."""
    import shutil
    dest_root = os.path.dirname(os.path.abspath(html_path))
    copied, missing = [], []
    for rel in collect_assets(deck):
        src = os.path.join(base_dir, rel)
        if not os.path.isfile(src):
            missing.append(rel)
            continue
        dst = os.path.join(dest_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
        copied.append(rel)
    return {"copied": copied, "missing": missing}


def write_html(deck, out_path, theme_name=None, base_dir=None):
    html = build_html(deck, theme_name)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    if base_dir:
        copy_assets(deck, out_path, base_dir)
    return out_path


def slide_count(deck):
    return len(deck.get("slides", []))
