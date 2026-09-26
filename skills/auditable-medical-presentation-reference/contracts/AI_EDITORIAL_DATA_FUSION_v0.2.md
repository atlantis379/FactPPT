# AI editorial base and source-data fusion v0.2

## Purpose

This contract makes AI editorial bases part of a source-bound page composition. It prevents two common failures: a decorative image that sits behind unrelated cards, and an attractive generated image that silently replaces evidence. The rule applies only when a PageSpec elects an AI editorial base. A page may still select a text-forward or source-figure strategy with no generated asset.

An AI editorial base and a client-supplied company or hospital template are alternate visual bases. Selecting a client template follows `CLIENT_TEMPLATE_INTAKE_v0.1.md` and disables this AI-base route for that page family.

The generated asset supplies atmosphere, rhythm and palette. Source-derived data, labels, figures, tables, relationship lines and clinical qualifiers remain native, editable semantic objects.

## Decision before generation

At W11/W13, define a `fusion_intent` from the PageGoal, approved semantic bindings, target viewing scale and user visual direction. Record:

- the chosen mode: `EDGE_FRAMED`, `FIELD_INTEGRATED` or `SECTION_RHYTHM`;
- the source hash, PageSpec ID and every semantic object ID visible on the page;
- the protected reading zones and the background-visible zones that should remain open after composition;
- each semantic object’s source anchor, native editability, z-order and licensed visual relation;
- the nonsemantic editorial zones, including their role as edge texture, lower rhythm, palette field or negative space.

Choose the mode from the information structure. `EDGE_FRAMED` keeps artwork on the page margins when a dense table or figure needs a quiet central field. `FIELD_INTEGRATED` allows the editorial field to remain visibly present between native content groups. `SECTION_RHYTHM` uses the same restrained editorial language to connect pages in a section while each page keeps its own evidence structure. A mode does not grant medical authority or replace a source-derived figure.

Do not define fusion from a previous slide’s coordinates, number of cards or a preferred organ illustration. Start from the current PageSpec and the approved evidence graph.

## Asset prompt and provenance

The prompt describes only nonsemantic visual vocabulary: palette, edge density, negative space, texture, directional rhythm and crop. It must prohibit text, digits, axes, arrows, logos, anatomy, devices, pathology, diagnoses, treatment statements, outcomes, claims and watermarks unless the asset is separately approved as source-bound medical evidence.

Store a prompt-provenance record next to the generated file. It names the generation route/version, prompt hash or exact prompt under the run’s access policy, reference images and their role, prohibited content, reviewer, asset hash and output dimensions. Reference images may set visual style, never donate medical facts.

The editorial asset contract remains mandatory: hash, class, placement, layer role and content-review state. `NONSEMANTIC_EDITORIAL_BASE` is placed at z0 as `EDITORIAL_UNDERLAY`; native semantic shapes/tables/charts are z2; protected exact text is z3; visible sources and review notices are z4.

## Native semantic fusion

Fusion means the background and information layout share a deliberate reading rhythm. It does not mean baking data into an image or floating text arbitrarily over art.

- Every visible data or claim object has a source anchor and stays `native_editable: true` in the fusion plan.
- A semantic group may respond to the editorial field through spacing, palette, a source-licensed sequence, or grouping. It must declare that relation as `READING_ORDER`, `GROUPING_ONLY`, `EVIDENCE_EMPHASIS` or `SEQUENCE_LICENSED_BY_SOURCE`.
- Colour and adjacency do not imply superiority, causality, clinical sequence, AND/OR logic or a treatment recommendation unless the semantic graph licenses that meaning.
- A page using `FIELD_INTEGRATED` declares one or more protected zones with a minimum visible-background ratio. The composition checker reads the final PPTX and rejects opaque later layers that consume too much of those zones.
- Use a card, table or chart when the evidence needs it. Do not suppress a required native evidence form merely to expose more background.

## Three-part audit

1. **Plan binding.** Validate `editorial_fusion_plan.v0.1.schema.json` and run `evaluate_quality.py editorial-fusion --plan PLAN.json --scene SCENE.json --out RESULT.json`. This checks that the semantic IDs, source anchors, asset identity, layer roles and protected zones agree.
2. **Actual composition.** Add the plan reference to `scene_quality_contract.schema.json` as `editorial_fusion`, then run the normal PPTX quality check on every page. It verifies the asset is the declared underlay and measures whether protected background-visible zones were later occluded by opaque shapes or non-base images.
3. **Final render.** Bind the final PPTX hash and page render hash. An independent reviewer checks background visibility, semantic-text legibility, hierarchy alignment and absence of semantic replacement. Missing or author-only review remains `NEEDS_REVIEW`; it never becomes delivery approval by an automated score.

## Adjustment loop

When a result fails, classify the repair before changing a page.

| Finding | Repair |
|---|---|
| Background visually detached but semantic layout is sound | Retarget the nonsemantic prompt or crop and create a new asset revision; keep source bindings unchanged. |
| Opaque panels hide a declared field | Recompose the native semantic layer, reduce nonessential opaque surfaces, or select `EDGE_FRAMED`. |
| Text loses contrast or reading order | Reflow native content or revise background placement; do not bake text into the asset. |
| Generated visual carries a claim or resembles evidence | Reject the asset, preserve the prior source-bound semantics and regenerate only an allowed editorial base. |
| Data or logic no longer reads clearly | Return to W11/W13 and select a source-preserving table, chart or text-forward composition. |

Each repair creates a new asset or scene revision and new final render evidence. Never overwrite a prior accepted hash.
