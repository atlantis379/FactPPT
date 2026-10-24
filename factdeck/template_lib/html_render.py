"""Jinja HTML render for Template Library v1 slot packs (no browser / PPTX required)."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .fill import fill_deck, normalize_fill
from .themes import get_theme

HERE = Path(__file__).parent
HTML_DIR = HERE / "html"


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(HTML_DIR)),
        autoescape=select_autoescape(["html", "xml", "j2"]),
    )
    return env


def render_page_html(family: str, fill: dict, *, theme: str = "journal",
                     variant: str | None = None) -> str:
    page = normalize_fill(family, fill, variant=variant, theme=theme)
    fam_html = {
        "cover": "cover.html.j2",
        "section": "section.html.j2",
        "key_points": "key_points.html.j2",
    }[family]
    return _env().get_template(fam_html).render(page=page, theme=page["theme"])


def render_deck_html(pages: list[dict], *, theme: str = "journal") -> str:
    deck = fill_deck(pages, theme=theme)
    env = _env()
    bodies = []
    for page in deck["pages"]:
        fam_html = {
            "cover": "cover.html.j2",
            "section": "section.html.j2",
            "key_points": "key_points.html.j2",
        }[page["family"]]
        bodies.append(env.get_template(fam_html).render(page=page, theme=page["theme"]))
    shell = env.get_template("deck_shell.html.j2")
    return shell.render(deck=deck, slides=bodies, theme=get_theme(theme))


def write_deck_html(pages: list[dict], out: Path, *, theme: str = "journal") -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_deck_html(pages, theme=theme), encoding="utf-8")
    return out
