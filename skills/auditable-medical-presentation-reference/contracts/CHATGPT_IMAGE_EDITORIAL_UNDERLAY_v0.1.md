# ChatGPT Image editorial underlay v0.1

## Scope

ChatGPT Image may generate a bitmap only for a page's non-semantic visual underlay. It does not receive authority over a title, Claim, quote, numeric fact, label, source, table, chart, medical image or Relationship connector. The route is optional and defaults off unless a validated manifest is supplied.

## Generation and intake

Use the built-in image generation route by default. The prompt must request a 16:9 editorial background with protected negative space and explicitly exclude text, letters, numbers, logos, watermarks, arrows, charts, tables, medical structures, devices, people, clinical symbols and factual content. A project-bound output is copied into the workspace without deleting the original generated file.

Before W14, validate `chatgpt_image_editorial_asset.v0.1` and check:

- path resolves inside the workspace without parent traversal;
- PNG signature and IHDR are genuine;
- SHA-256 matches the manifest;
- dimensions are at least 1280×720 and landscape-compatible;
- provider, generation mode, asset class and layer role are exact;
- target page IDs are explicit;
- a complete `fusion_theme` declares the approved palette, content zone, protected decoration zone, surface opacity and reuse mode;
- all six content-review checks are true and status is PASS.

## Composition

Insert the underlay at z0 over the full 1280×720 canvas before adding any editable shape. All semantic objects remain at higher z-order. At most one editorial underlay is allowed per page in this MVP. The same asset may be reused on multiple pages only when that reuse is declared in `page_ids` and `reuse_mode=MASTER_UNDERLAY`.

The native layer must consume the underlay's fusion theme instead of merely covering it. In the reference implementation this means:

- title, primary message, Claim surfaces and connectors inherit the approved underlay palette;
- opaque generic white Claim panels are prohibited while an editorial underlay is active;
- Claim surfaces stay inside the declared content zone and outside the protected decoration zone;
- surfaces are translucent or open, with soft palette-derived borders rather than unrelated hard outlines;
- each archetype records one native fusion variant: `OPEN_FIELD`, `SOFT_CARDS`, `SPLIT_FIELD`, `RHYTHM_BANDS` or `FLOW_NODES`;
- semantic text and Relationship connectors remain native even when their surrounding visual surface is translucent.

The immutable delivery identity includes the underlay SHA-256. A different generated bitmap therefore produces a new delivery snapshot even when the Semantic Deck is unchanged.

## Verification

W15 checks that the number of picture objects equals the approved asset plan, the asset ID is retained in the picture metadata, at least one embedded media part matches the approved SHA-256 byte-for-byte, the selected fusion variant is retained in speaker notes, no Claim surface intrudes into the protected decoration zone, and no active-underlay Claim uses an opaque generic white fill. Semantic-object verification runs unchanged. A picture hash proves identity, not absence of semantic content; the visual content review and final rendered-page inspection remain mandatory.
