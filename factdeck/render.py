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
html, body { margin: 0; width: 2400px; height: 1560px; overflow: hidden; background: #F4F7FA;
  font-family: "WenQuanYi Micro Hei", "Droid Sans Fallback", "Noto Sans", sans-serif; color: #1A1A1A; }
header { padding: 28px 36px 8px; }
h1 { margin: 0; font-size: 32px; font-weight: 700; color: #0E4D7B; }
p.sub { margin: 6px 0 0; font-size: 16px; color: #5C6770; }
.grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 22px 22px; padding: 18px 36px 28px; }
figure { margin: 0; }
img { width: 100%; height: auto; display: block; background: #fff; border: 1px solid #D5DCE3; }
figcaption { margin-top: 6px; font-size: 16px; line-height: 1.35; color: #243040; }
figcaption b { font-weight: 700; color: #0E4D7B; }
"""

COMPARE_NOTES = """# COMPARE_NOTES

Density pass on the hospital-lecture deck. Layout ids, fact gate, slot pairing, summary slim, and half-sentence omission are unchanged. No new clinical sentences.

## Before
- Side margin about 104px. Title bar 136px. Gap under the bar about 40px.
- Checklist text sat in one column even when the selector asked for two. The algorithm was about 1220px wide. Tables used the inset content box, with open white under short lists.

## After
- Side margin 56px (inside 48–64). Title bar is still full-width medical blue, now 88px. Gap under the bar is 20px (inside 16–24).
- Body blocks aim at roughly 60% of the 1920×1080 slide: checklist, claim, matrix, algorithm, and the comparison table use a 720px content block across the content width.
- Checklist: six actions are two columns under a full-width lead. One to three items keep that lead in a side column. Undifferentiated peers stay one column.
- Metric row: three or fewer notes sit beside the numeral and the admitted lead sentence. That sentence stays in the body, so the footer is only the page number and the source.
- Claim and evidence stack full width. The admitted claim sentence is the lead, and the same sentence is one footer line. Page number and source stay.
- Matrix and the comparison table span the content width. The algorithm split is 96% of that width, above the 80% floor.
- Still a white lecture slide: no equal-card wall, no dark metric tile, no pill chips.

## Measured on the biologics preview (1920×1080)
- Title bar 88px. Gap under the bar 20px. Side inset 56px.
- Content block above the footer rule, as a share of the slide: metric 62.8%, checklist 62.8%, claim 62.8%, matrix 62.8%, table 62.4%, algorithm 60.3%.
- Checklist, claim, matrix, and table span the content width. The algorithm's ink is 96% of that width.
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
    (out_dir / "COMPARE_NOTES.md").write_text(COMPARE_NOTES, encoding="utf-8")
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
        "<header><h1>医院课件 · 生物制剂样本页</h1>"
        "<p class=\"sub\">页边 56px，标题栏压低。清单、表和路径图铺在内容区里。页脚保留页码和来源。</p></header>"
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
