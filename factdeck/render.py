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

Visual comparison against the previous teaching deck (beige paper, navy metric tile, dark sidebar, letter-spaced kicker, pill chips).

Layout ids, fact gate, slot pairing, summary slim, and half-sentence omission are unchanged.

## What changed on the page
- White 16:9 slide. Full-width medical-blue title bar: small section label, large white title, figure number on the right. The bar is the measured title rule, so the PPTX background matches the PNG.
- Margins are about 104px. Footer is a page number and a source line.
- metric_row: the key figure is a large numeral on white, then a lead sentence, then a single numbered list. The dark metric tile is gone.
- checklist: the anchor is a left-rule lead sentence. The six actions are one numbered list. The dark sidebar and two-column grid are gone.
- claim_evidence: the claim is a large sentence; evidence sits under it as a list.
- matrix_2x2: one bordered lecture table (blue column heads, gray row heads, white cells).
- algorithm_tree: one flowchart of plain rectangles and a dashed exclusion box. Captions are words. The threshold is bold type, not a pill.
- data_table_highlight: a bordered comparison table. 是 / 否 are bold colored words, not filled badges.
- Type is WenQuanYi Micro Hei. The title is larger than the body. Body text is near-black on white.
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
        "<p class=\"sub\">每页一条标题，正文是少量编号要点，或一张表 / 一幅路径图。页脚只有页码和来源。</p></header>"
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
