# Template Library v1 — Cover / Section / 要点卡 / 对照 / 流程 / 时间轴

User approval 2026-10-24: anchor layouts on [medical-ppt-design](https://github.com/grotyx/medical-ppt-design) (CC BY 4.0), strip SNUBH branding, use journal + steel color tokens, keep HTML → browser measure → native PPTX pipeline, ship cover/section + key-points first for Chinese validation. Follow-up feedback the same day: card grids alone cannot express logic (对照 / 流程 / 时间轴) — add non-card families while **keeping** 要点卡.

Commercial packs (SlideModel / Envato / OfficePLUS) stay out of the product.

## Attribution

Layout geometry and Patterns **C** (two-column), **H** (pillar cards), **J** (timeline), **K** (process flow) are adapted from **medical-ppt-design** under **CC BY 4.0**. See [`factdeck/template_lib/ATTRIBUTION.md`](../factdeck/template_lib/ATTRIBUTION.md) and the vendored license at `factdeck/template_lib/third_party/medical-ppt-design/LICENSE`.

SNUBH / SNUH logos, presenter defaults, and institutional copy are **not** included.

## What shipped (v1 → v1.2)

| Piece | Path | Status |
|---|---|---|
| Manifest (families, slots, capacity, font steps, overflow) | `factdeck/template_lib/manifest.json` | done (v1.1.0) |
| Themes journal + steel + premium_clinical + **gold_clinical** | `factdeck/template_lib/themes.py` | done (v1.3 GOLD density) |
| Slot validate + inch→px zones | `factdeck/template_lib/slots.py` | done |
| Fill → page model | `factdeck/template_lib/fill.py` | done |
| HTML/Jinja: cover, section, key_points (3/4/6) | `factdeck/template_lib/html/` | done |
| HTML/Jinja: **comparison**, **flow**, **timeline** | `factdeck/template_lib/html/` | done (v1.1) |
| HTML/Jinja: **algorithm_tree**, **assessment_matrix**, **dual_path_tree** | `factdeck/template_lib/html/` | done (v1.3 GOLD) |
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
**Kept for 要点**; use the logic families below when the slide is a contrast, pathway, or course.

### Comparison / 对照 (`tl_v1.comparison`) — Pattern C

Variants: `dual_column` (default), `table_2n` (when `rows[]` is provided).  
Dual-column contrast (e.g. 急性加重 vs 稳定期, 推荐 vs 不推荐): `left_label` / `right_label` + `left_items` / `right_items` (each item `{text}` or a bare string).  
Table variant: same labels as headers + `rows: [{left, right}, …]` (capacity 8).  
Visual: vertical divider / 2-column table inside the body card — **not** a pillar-card grid.

### Flow / 流程 (`tl_v1.flow`) — Pattern K

Variants: `horizontal_4` / `horizontal_5` / `horizontal_6` (auto), `vertical_4` (explicit).  
`nodes: [{tag?, heading, body?}]` — outline stage boxes + accent arrows (诊断路径 / 阶梯治疗).  
Over capacity → refuse.

### Timeline / 时间轴 (`tl_v1.timeline`) — Pattern J

Variants: `nodes_4`, `nodes_6` (auto).  
`nodes: [{label, heading, body?}]` — milestone track (就诊→检查→治疗→随访): accent rule + dots, labels above, copy below. **No boxes.**

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
    {"family": "comparison", "fill": {
        "title": "急性加重期与稳定期对照",
        "left_label": "急性加重",
        "right_label": "稳定期",
        "left_items": [{"text": "症状急性恶化，评估感染与呼吸衰竭"}],
        "right_items": [{"text": "长效支气管舒张剂维持，强调戒烟与随访"}],
    }},
    {"family": "flow", "fill": {
        "title": "疑诊到确诊的四步路径",
        "nodes": [
            {"heading": "危险因素", "body": "吸烟史与症状"},
            {"heading": "体征筛查", "body": "呼吸音与形态"},
            {"heading": "肺功能", "body": "舒张后比值"},
            {"heading": "综合评估", "body": "症状与加重史"},
        ],
    }},
    {"family": "timeline", "fill": {
        "title": "一例 COPD 患者就诊病程",
        "nodes": [
            {"label": "D0", "heading": "就诊", "body": "活动后气促"},
            {"label": "D1", "heading": "检查", "body": "肺功能与胸片"},
            {"label": "D3", "heading": "治疗", "body": "启动吸入方案"},
            {"label": "W4", "heading": "随访", "body": "症状与装置复查"},
        ],
    }},
], theme="steel")

# Native hook (stub): validates + returns envelope; no PPTX write yet
native_prepare("cover", fill, theme="journal")
```

Themes: **`"gold_clinical"`** (GOLD teaching density) | `"premium_clinical"` | `"journal"` | `"steel"`. Tokens reuse the FactDeck CSS variable names expected by `deck.html.j2` (`ink`, `primary`, `accent`, …) plus `canvas` / `headline` / `surface` / `rail` / `shadow` for craft.

## Paid quality (v1.2)

User feedback 2026-10-24: v1.1 previews looked like cheap bordered cards. Craft pass:

| Choice | What changed |
|---|---|
| Showcase theme | `premium_clinical` — deep ink, one steel-teal accent, warm paper, soft tonal surfaces |
| Cards | Accent left rail + soft elevation; lead card inverted gradient; oversized watermark indices — **not** identical gray outline boxes |
| Comparison | Filled header bands + VS medallion + dual tonal panels |
| Flow | Continuous pathway rail under filled nodes + SVG chevrons (not SmartArt outlines) |
| Timeline | Gradient milestone rail + ringed dots inside a soft paper well |
| Typography | Noto Sans CJK SC first; stronger weight/size hierarchy; tracking −0.01em |
| Avoided | Thin `#D9D9D9` nest boxes, pill-badge-as-design, dark neon SaaS, hospital logos |

Previews: `/workspace/sync/template-lib-v1/previews/premium-*.png`.

## GOLD density (v1.3)

User feedback after v1.2: premium_* still read as empty SaaS cards. Remake three COPD teaching pages with **non-isomorphic diagram grammars** inspired by public GOLD Pocket/Teaching slide *layout language* (structure only — no GOLD artwork/logo copy):

| Family | Pattern | COPD demo |
|---|---|---|
| `algorithm_tree` | Decision tree, solid yes / dashed no | 疑诊→肺功能确诊（FEV1/FVC < 0.70） |
| `assessment_matrix` | Dense ABE 2×2 matrix | mMRC/CAT × 加重史 → A/B/E |
| `dual_path_tree` | CME dual-column escalation | 呼吸困难 vs 急性加重（eos 分层） |

Theme **`gold_clinical`**: deep navy header bar, single gold accent line, functional greys. Ban: three equal empty cards, giant watermark numbers, full-width bottom summary bars, breadcrumb chips, first-card gradient.

Previews: `/workspace/sync/template-lib-gold/` (`01-algorithm`, `02-abe-matrix`, `03-tx-tree`).

## v1.3.1 — Pharma / congress chart-led families

Layout language from public pharma IR / congress decks (structure only; research in
`/workspace/sync/layout-research-pharma/REPORT.md`). Every page = action title (conclusion
sentence) + figure/table id + ONE main chart/diagram + 3–4 number-led takeaways + abbreviation /
reference / honesty footer (`示例数据，教学示意，非诊疗建议` · `版式参考药企学术会议幻灯（仅结构）`
are defaulted when omitted).

| Family | Grammar | COPD demo page |
|---|---|---|
| `trial_design` | week axis + R box (ratio, N) + arms with n + follow-up + endpoint marker; inclusion / endpoint hierarchy / design facts | 52 周双盲 1:1 随机设计 |
| `forest_plot` | table + log-axis CI plot in one aligned SVG, ref line at 1, one highlighted row, favours labels | eos / 年龄 / 吸烟亚组 RR |
| `endpoint_readout` (`bar` / `line`; KM planned) | main chart with 95% CI error bars or weekly line + n-at-risk, stats box, rail | 年化加重率 −30%；FEV1 +82 mL |
| `moa_cascade` | 5 stage columns, item boxes, gold drug callouts with T-bar connectors routed in gutters | 2 型炎症级联 4 个作用点 |
| `data_table_highlight` | 12–18 rows, arms + total, zebra greys, exactly one highlighted row, footnotes | 基线特征表 |
| `landscape_swimlane` | lanes per class, Phase III bars on year axis, met / not met / ongoing markers (shape + text), today line | 5 类靶点 10 项研究（虚构） |
| `key_points` / `evidence_takeaways` | 3–4 number-led conclusions; superscript evidence ids → footer refs; verbatim quote + doc/page column | 本节小结 |

Chart geometry is computed in `factdeck/template_lib/pharma.py` from the fill payload (explicit px
coordinates → maps 1:1 to native PPTX shapes later); templates only draw SVG/HTML primitives.
Validation checks data, not just text length (lo ≤ est ≤ hi, log axis brackets 1, one highlight,
series length = categories, callout targets exist, study status ∈ met/not_met/ongoing, evidence ids
defined, takeaways number-led).

Fixtures (demo data, fictional study names): `factdeck/template_lib/pharma_fixtures.py`.
Render + Playwright layout QA (overflow / outside-canvas / footer overlap / SVG text collisions):

```bash
.venv/bin/python tools/render_pharma_previews.py --out /workspace/sync/template-lib-pharma
.venv/bin/python tools/pharma_contact_sheet.py
.venv/bin/python -m pytest tests/test_template_lib_v1.py tests/test_template_lib_pharma.py -q
```

## Coordinates

Upstream inches (13.333" × 7.5") × 96 → FactDeck 1280 × 720 px. Zone tables live in `manifest.json` (`zones_in`); `zone_map_px()` converts for templates. Content families share the medical-ppt four-zone skeleton (header / headline / body card / footer).

## Not in v1.3 (same as v1.2 gaps)

- Full DECK contract change / auto-selection inside `/api/deck`
- Browser density fit / playwright measure for these packs (reuse later)
- Native PPTX writer for slot packs (stub only)
- Route A decorative path art (artwork stub empty)
- Patterns A–B / D–G / I / L from medical-ppt-design
- Pulling commercial template files into the repo

## Tests

```bash
cd /path/to/FactPPTv2
.venv/bin/python -m pytest tests/test_template_lib_v1.py -q
```

No PowerPoint, ImageGen, or Adobe required.

## Layout selector (v1.3.1 + selector)

`factdeck/template_lib/selector.py` picks one layout per slide from its *content* (title, text, optional
structured data) and records why. Steps: rule-based relation classifier (中文 + English signals, plus
structured-data signals) → per-layout minimum-data check with a fixed downgrade chain (never fabricates
data) → optional tie-break among qualified candidates whose scores are close (pluggable; LLM answers must
be in the candidate set, otherwise the deterministic rule wins) → deck rhythm (no identical layout on
consecutive content pages; chart pages ≥ 1/3 when qualified candidates allow; cover/section exempt).

```bash
.venv/bin/python tools/copd_layout_plan.py                 # COPD sample → slide-level content plan
.venv/bin/python tools/select_layouts.py --render          # selection.json + selection-report.md + PNGs
.venv/bin/python tools/select_layouts.py --llm             # optional LLM tie-break (EASYPPT_SEMANTIC_MODEL_*)
.venv/bin/python -m pytest tests/test_layout_selector.py -q
```
