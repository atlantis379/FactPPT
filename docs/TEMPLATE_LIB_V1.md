# Template Library v1 — Cover / Section / 要点卡

User approval 2026-10-24: anchor layouts on [medical-ppt-design](https://github.com/grotyx/medical-ppt-design) (CC BY 4.0), strip SNUBH branding, use journal + steel color tokens, keep HTML → browser measure → native PPTX pipeline, ship cover/section + key-points first for Chinese validation. Commercial packs (SlideModel / Envato / OfficePLUS) stay out of the product.

## Attribution

Layout geometry and Pattern H (pillar cards) are adapted from **medical-ppt-design** under **CC BY 4.0**. See [`factdeck/template_lib/ATTRIBUTION.md`](../factdeck/template_lib/ATTRIBUTION.md) and the vendored license at `factdeck/template_lib/third_party/medical-ppt-design/LICENSE`.

SNUBH / SNUH logos, presenter defaults, and institutional copy are **not** included.

## What shipped (v1)

| Piece | Path | Status |
|---|---|---|
| Manifest (families, slots, capacity, font steps, overflow) | `factdeck/template_lib/manifest.json` | done |
| Themes journal + steel | `factdeck/template_lib/themes.py` | done (from academic palette seeds) |
| Slot validate + inch→px zones | `factdeck/template_lib/slots.py` | done |
| Fill → page model | `factdeck/template_lib/fill.py` | done |
| HTML/Jinja: cover, section, key_points (3/4/6) | `factdeck/template_lib/html/` | done |
| `T_TEMPLATE_NATIVE` stub | `factdeck/template_lib/native_hook.py` | stub (prepare only) |
| Artwork paths | `factdeck/template_lib/artwork/` | stub / empty TODO |
| Tests (schema + HTML + 中文样例) | `tests/test_template_lib_v1.py` | done |

The existing **10 academic template sets** (`docs/ACADEMIC_TEMPLATE_LIBRARY.md`, `output/academic_templates`) remain **style/QA reference only**. They are **not** a runtime fill source for these slot packs.

Route A (`docs/PPT_GENERATION_ROUTE.md`) is unchanged. This library adds a parallel fill→HTML path for the two families; native PPTX wiring is a clear stub.

## Families

### Cover (`tl_v1.cover`)

Slots: `kicker?`, `title`, `subtitle?`, `affiliation?`, `presenter?`, `meta?`.  
Light canvas (journal cream / steel white), accent pill, accent rule — no logo required.

### Section divider (`tl_v1.section`)

Slots: `number?`, `title`, `subtitle?`.  
Watermark number + title + short rule on the same light canvas.

### Key-points / 要点卡 (`tl_v1.key_points`)

Variants: `cards_3`, `cards_4`, `cards_6` (auto-picked from item count).  
Each item: `tag?`, `heading`, `sub?`, `body?`. Optional `takeaway`, `source`, `page`, `section`.  
Over capacity → refuse (split the page); do not silently drop items.

## How to fill

```python
from factdeck.template_lib import validate_fill, render_page_html, render_deck_html, native_prepare

fill = {
    "title": "慢性阻塞性肺疾病的诊疗要点",
    "kicker": "呼吸内科教学",
    "subtitle": "以指南要点组织课堂主线",
    "meta": "教学示意  |  2026.10",
}
assert validate_fill("cover", fill)["ok"]
html = render_page_html("cover", fill, theme="journal")

deck_html = render_deck_html([
    {"family": "cover", "fill": fill},
    {"family": "section", "fill": {"number": "02", "title": "病理生理要点", "subtitle": "气流受限与炎症"}},
    {"family": "key_points", "fill": {
        "section": "COPD",
        "title": "诊断与评估要点",
        "items": [
            {"tag": "症状", "heading": "呼吸困难", "body": "进行性、活动后加重"},
            {"tag": "检查", "heading": "肺功能", "body": "FEV1/FVC < 0.70 示气流受限"},
            {"tag": "分型", "heading": "GOLD 分级", "body": "结合症状与急性加重史"},
        ],
        "takeaway": "肺功能是确诊气流受限的关键依据",
    }},
], theme="steel")

# Native hook (stub): validates + returns envelope; no PPTX write yet
native_prepare("cover", fill, theme="journal")
```

Themes: `"journal"` | `"steel"`. Tokens reuse the FactDeck CSS variable names expected by `deck.html.j2` (`ink`, `primary`, `accent`, …) plus `canvas` / `headline` for the light layouts.

## Coordinates

Upstream inches (13.333" × 7.5") × 96 → FactDeck 1280 × 720 px. Zone tables live in `manifest.json` (`zones_in`); `zone_map_px()` converts for templates.

## Not in v1

- Full DECK contract change / auto-selection inside `/api/deck`
- Browser density fit / playwright measure for these packs (reuse later)
- Native PPTX writer for slot packs (stub only)
- Route A decorative path art (artwork stub empty)
- Patterns A–G / I–L from medical-ppt-design
- Pulling commercial template files into the repo

## Tests

```bash
cd /path/to/FactPPTv2
.venv/bin/python -m pytest tests/test_template_lib_v1.py -q
```

No PowerPoint, ImageGen, or Adobe required.
