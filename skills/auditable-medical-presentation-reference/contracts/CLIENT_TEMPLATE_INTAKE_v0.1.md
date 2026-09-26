# Client template intake v0.1

## Visual-base choice

Each presentation run selects exactly one visual base for a page family:

- `AI_EDITORIAL_BASE`: a generated nonsemantic background governed by `AI_EDITORIAL_DATA_FUSION_v0.2.md`.
- `CLIENT_TEMPLATE`: a company or hospital asset supplied by the client.

These paths are parallel and mutually exclusive. Do not put an AI editorial base underneath, over, or inside a client template merely to make the result look more polished. A client template can contain its own background artwork, logo, colour system, master slides and footer; those are the selected visual base.

The choice is explicit in `scene_quality_contract.visual_base`. The PPTX validator rejects a page that declares `CLIENT_TEMPLATE` while also carrying a nonsemantic AI editorial base or an editorial fusion plan.

## Accepted client inputs

`PPTX_TEMPLATE` is the preferred entry when the client provides a usable corporate or hospital PowerPoint file. Import it, inspect slide size, masters, layouts, placeholders, fonts, logo placement and footer behavior. Preserve masters and layouts in the output. Do not rebuild it as a screenshot unless the client supplied only a flat image.

`BACKGROUND_IMAGE` is the entry for a single approved cover, background, or exported page visual. Use it as a client-owned underlay. Keep brand regions such as logo, header and footer intact; place all source-derived semantic content in declared safe regions as native editable shapes, tables and charts.

The client asset establishes visual identity only. It never establishes a medical fact, recommendation, data point, figure interpretation or source citation. Existing embedded text must be reviewed as brand-only or held for inspection before use.

## Contract and intake record

Create `client_template_contract.v0.1.schema.json` for every supplied template or background. It records the exact file hash, input class, chosen application mode, canvas, preserved brand regions, semantic-safe regions and review status. Copy the template ID, hash and preserved brand-region boxes into `scene_quality_contract.client_template_binding`; the final-PPTX checker then rejects editable semantic text that enters a protected brand region.

Use `PRESERVE_MASTERS_AND_LAYOUTS` for a `PPTX_TEMPLATE`. Use `BACKGROUND_UNDERLAY` for a `BACKGROUND_IMAGE`. Do not mix the two modes. The template contract does not claim legal rights beyond the client-supplied status; retain the intake source and approval context in the project record.

Run:

```text
python scripts/evaluate_quality.py client-template --contract CLIENT_TEMPLATE.json --artifact TEMPLATE_OR_BACKGROUND --out TEMPLATE_QUALITY.json
```

The deterministic check validates file identity, input/mode compatibility, canvas bounds, and collisions between preserved brand regions and semantic-safe regions. It cannot prove that the client owns rights to the file or that a PPTX renderer preserves every Office feature; final render review remains required.

## Composition and review

When using a PPTX template, work on a copy, import it, and update the template’s existing placeholders or layouts. When a client background image is selected, bind it as the required base image and preserve the contracted brand regions. In both cases:

- visible medical data, labels, sources and relationship cues remain native editable objects with approved semantic bindings;
- source notes remain readable and are not hidden by a branded footer;
- semantic objects do not overlap preserved logos, headers, footers or decorative frames;
- final render review checks the actual template appearance, brand preservation, text legibility and source visibility.

Changing a supplied template file, master, crop or background image creates a new template hash and invalidates dependent scene and render evidence.
