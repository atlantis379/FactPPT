"""HTML template → Chrome measure → native PPTX, plus preview PNGs.

``render_previews`` does not choose a layout or fill a page itself. It
measures the pages ``build_deck`` already rendered through the template
library. There is no parallel deck path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from factdeck.deck import build_deck
from factdeck.fixtures import preview_slides
from factdeck.measure import measure_html
from factdeck.pptx_export import add_measured_slide, new_presentation

CONTACT_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; width: 2400px; height: 1560px; overflow: hidden; background: #E6E1D6;
  font-family: "Noto Sans", "WenQuanYi Micro Hei", sans-serif; color: #0E2C4A; }
header { padding: 28px 36px 8px; }
h1 { margin: 0; font-size: 32px; font-weight: 700; }
p.sub { margin: 6px 0 0; font-size: 16px; color: #5E7184; }
.grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 22px 22px; padding: 18px 36px 28px; }
figure { margin: 0; }
img { width: 100%; height: auto; display: block; background: #fff; }
figcaption { margin-top: 6px; font-size: 16px; line-height: 1.35; }
figcaption b { font-weight: 700; }
"""


def render_previews(out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prs = new_presentation()
    slides = preview_slides()
    pages = build_deck(slides)
    manifest = []
    for slide, page in zip(slides, pages):
        png = out_dir / f"preview-{page.preview_id}.png"
        html_path = out_dir / f"preview-{page.preview_id}.html"
        html_path.write_text(page.html, encoding="utf-8")
        slots = measure_html(page.html, png)
        drawn = add_measured_slide(prs, slots)
        structural = [slot for slot in slots if slot.get("kind") in {"shape", "line"} or (slot.get("text") or "").strip()]
        if len(drawn.shapes) < len([slot for slot in slots if slot.get("kind") in {"shape", "line"}]):
            raise RuntimeError(f"{page.preview_id} dropped structural slots")
        manifest.append(
            {
                "preview_id": page.preview_id,
                "title": slide.get("title"),
                "page": slide.get("page"),
                "proposed": slide.get("proposed"),
                "relation": slide.get("relation"),
                "selection": page.selection,
                "trace_status": page.trace_status,
                "renderer": page.renderer,
                "png": str(png),
                "slots": len(slots),
                "shapes": len(drawn.shapes),
                "structural_slots": len(structural),
            }
        )
    pptx_path = out_dir / "preview-teaching-layouts.pptx"
    prs.save(pptx_path)
    contact = _contact_html(manifest, out_dir)
    contact_png = out_dir / "preview-contact-sheet.png"
    contact_html_path = out_dir / "preview-contact-sheet.html"
    contact_html_path.write_text(contact, encoding="utf-8")
    measure_html(contact, contact_png, window=(2400, 1560), require_slots=False, html_path=contact_html_path)
    (out_dir / "selector-decisions.json").write_text(
        json.dumps({"pptx": str(pptx_path), "slides": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def _contact_html(manifest: list[dict], out_dir: Path) -> str:
    figures = []
    for item in manifest:
        name = Path(item["png"]).name
        selection = item["selection"]
        figures.append(
            "<figure>"
            f'<img src="{name}" alt="{item["title"]}">'
            f'<figcaption><b>{selection["layout_id"]}</b> · {selection["variant"]}<br>{selection["reason"]}</figcaption>'
            "</figure>"
        )
    body = (
        "<header><h1>教学版式重组 · 生物制剂样本页</h1>"
        "<p class=\"sub\">并列要点不再铺成等分卡片。锚点是数值、主张或决策图；其余降为通栏、清单或表。</p></header>"
        f'<div class="grid">{"".join(figures)}</div>'
    )
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<style>{CONTACT_CSS}</style></head><body>{body}</body></html>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render teaching-layout previews")
    parser.add_argument("--out", type=Path, default=Path("/opt/cursor/artifacts"))
    args = parser.parse_args()
    manifest = render_previews(args.out)
    for item in manifest:
        print(f"{item['preview_id']}: {item['selection']['layout_id']} → {item['png']}")


if __name__ == "__main__":
    main()
