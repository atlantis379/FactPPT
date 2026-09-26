# AI editorial asset fusion v0.1

## Purpose

Use generated visual assets to improve the finish of a presentation without allowing them to invent, obscure or replace medical meaning. This policy applies to every page and is selected from page purpose, source topic and visual strategy. It is not a rule to put an organ, vessel or other illustration on every medical page.

## Asset classes

| Class | Use | Semantic authority | Default examples |
|---|---|---|---|
| `NONSEMANTIC_EDITORIAL_BASE` | Very light texture, abstract background, paper grain or restrained decorative edge | None | pale molecular texture; low-contrast wave |
| `CONTEXTUAL_ILLUSTRATION` | Topic-relevant visual atmosphere that helps framing but does not state a medical fact | None | a generic organ, vessel, device or care-setting illustration when the paper and page purpose warrant it |
| `SOURCE_BOUND_MEDICAL_ASSET` | Figure, scan, pathology, anatomy, chart or other visual that carries an evidence claim | Source and approved semantic graph only | licensed source figure with source locator |

Generated assets may be in the first two classes only. A generated image must never stand in for a source-bound medical asset or add a diagnosis, outcome, pathway, recommendation, comparison or numeric assertion.

## Page decision

Each PageSpec declares `editorial_base_policy` as `REQUIRED`, `OPTIONAL` or `FORBIDDEN` and records the reason. A contextual illustration is optional and requires a separate decision with its topic/page-purpose rationale. Choose it when it clarifies the paper's subject and the page has a protected visual area; omit it when evidence, dense text, table reading or visual ambiguity would suffer.

Do not infer that a cardiology paper requires a heart illustration. For example, a treatment-reference comparison page can use only an editorial base, while an introductory disease-mechanism page may use a generic contextual heart illustration after review.

## Required contract record

Every included generated asset has one `editorial_assets` entry in the scene-quality contract with: unique `asset_id`; class; policy; layer role; local relative path; SHA-256; exact placement and tolerance; allowed safe-region behavior; prompt/provenance record stored beside the asset; prohibited content; and content-review state.

`NONSEMANTIC_EDITORIAL_BASE` uses `EDITORIAL_UNDERLAY`, appears before every protected text/table layer, and may intersect content-safe regions only when `allow_content_safe_underlay` is true. `CONTEXTUAL_ILLUSTRATION` uses `CONTEXTUAL_ART` and must remain outside declared text/table safe regions. `SOURCE_BOUND_MEDICAL_ASSET` uses `SOURCE_BOUND_EVIDENCE` and additionally carries the source locator, permission status and semantic binding IDs.

Where the authoring API exposes picture name or description, it must equal `asset_id`. If it does not expose either field, the embedded-media SHA-256 is the authoritative identity binding. W15 verifies the embedded-media hash, placement, declared layer order and safe-region treatment against the contract. A hash validates identity, not meaning; absence of text, numbers, claims, watermark and prohibited anatomy/device detail requires a recorded visual content review.

## Fusion rules

Put editorial base at z0, contextual art at z1, editable semantic shapes/tables/charts at z2, protected exact text at z3, and source/review notices at z4. Do not bake editable text, figures, icons, arrows, tables, labels or citations into a generated image. Maintain contrast against the actual background, not the nominal canvas color. If an asset review is unresolved, preserve `NEEDS_REVIEW`; it cannot make a W17 delivery claim.
