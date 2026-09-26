# Integrity and quality contract v0.5

This active extension implements the 2026-09-05 audit without changing the frozen W00–W18 stage numbers or source facts. Historical runtime profiles are evidence only, never an effective capability registry.

## Execution modes

- `DESIGN_PROTOTYPE`: may explore layout after W10/W11 using locked inputs. Mark NOT_FOR_DELIVERY in the run manifest and visibly identify prototype status on the review artifact. Missing W12 qualification remains missing. Never record an authoritative W14/W17 PASS for this branch.
- `DELIVERY`: every mandatory subgate and quality component must pass; RED requires human review of the exact current output hash. Clinical review and composition review are separate. No implicit approval by timeout.

## Deterministic validation boundary

Use `scripts/integrity.py` for exact structured diffs, finite Decimal value comparisons with context, AND reconstruction, run-state and evidence-closure checks. Use `scripts/skill_tool.py state|qualification` to run both schema and semantic constraints. A schema-only PASS is insufficient. These checks do not establish clinical entailment, legal permission or authenticity of a human reviewer.

Render manifests record input identity, actual object IDs, visible text/geometry, implementation/font/output hashes and object ownership. Read final PPTX/XML/table cells independently where available. A manifest copied from input cannot by itself certify visible output. Bind final render review to the same output and rendering engine versions. Models may review entailment, narrative and visible meaning; they cannot replace exact code diffs or erase a hard failure.

## Lossless semantic factoring

Only AND conjunction factoring is implemented by the reference validator. For each original bundle retain unique Fact IDs, exact semantic content, source namespace, scope, operator, value and unit. Shared display slots carry a per-bundle Fact-ID map; equal strings with different scope are not common facts. Reconstruct each bundle as shared bindings AND its own specific facts, then compare complete semantic objects as a multiset. Bundle order and ownership remain locked. Duplicate IDs, swapped bindings and missing/extra conditions fail even when counts match.

OR/NOT/EXCEPT or nested formulas require a separately qualified equivalence checker; until then show original logic without factoring. Approved formatting transformations (spaces, line breaks, superscript notation) must be explicit in the page display contract, never inferred globally. Numeric semantic checks and exact visible-string checks are separate.

## Protected composition and typography

Every later layer, including unprotected decoration, is checked against protected lower-layer alpha support. Unique z_order is required. Only integer translations are supported by the reference assembler. Overlap exceptions name both layers, an exact region, contract version/id and reason. Whole-layer overlap allowlists are rejected. Semi-transparent overlap also counts.

`runtime_executors/exact_overlay.py` uses one explicitly selected font file per object for both measurement and drawing, checks cmap coverage and ink bounds, rejects invalid line heights and intersecting text ink. Font index/hash and renderer versions travel in the manifest. The final-PPTX checker additionally requires hash-bound render evidence and an independent visual-review checklist before Q-GLYPH can pass. Unsupported glyphs fail; never silently fallback. This renderer is an optional bitmap overlay adapter, not a PPTX renderer or a clinical verifier. New font/runtime combinations require affected benchmark reruns.

## CompositionQualityGate

Record the page's reference design, target display size, hierarchy, reading order, content-safe regions, minimum typography and allowed overlaps before rendering. Evaluate separately:

1. title and approved primary message readable without clipping;
2. group/row/column ownership and AND logic visually unambiguous;
3. all meaning-critical details legible at full review size and intended viewing scale;
4. no ordinary art obscures protected content or implies unauthorized ranking;
5. source, scope and required review notices remain visible;
6. native editability where requested, plus final-format rendering review.

Use dimension findings with evidence, not a single aesthetic score. Hard semantic failure cannot be averaged away. Stress long titles, longest cell text, unusual glyphs and narrow boxes. Density failure returns to decomposition rather than deleting locked facts. A small footer may be acceptable for a desktop review prototype but must be judged again for projection; prototype PASS does not grant projection suitability.

## Numeric data display scope

Current P05 validation covers exact threshold text, units and table-cell ownership. P05 table/text PASS does not qualify statistical chart geometry. The general quality system adds a separately tested simple-SVG geometry adapter; run its own benchmark before use. All other chart formats/engines remain unqualified until separately validated.

Every chart capability must separately test raw/display values and explicit rounding, unit conversions, denominator/population/timepoint, missing versus zero, interval bounds, axis transform and ticks, zero/log-axis policy, legend/series ownership and comparability. Required negative fixtures include label-correct/geometry-wrong, swapped series, missing-to-zero and misplaced confidence intervals.

## Source coverage and narrative calibration

Coverage records distinguish known inventory totals, independently reviewed totals and UNKNOWN denominators. Never report 100% RED recall using only the extractor's own list as denominator. Page count, section inventory, tables, footnotes, thresholds/recommendation candidates and cross-page continuations form a separate review checklist. Unresolved meaning-critical segments block approval; reference inventory is not evidence of medical completeness.

Narrative review records evidence dependencies and separately tests entailment, causal/sequence strength, scope, question coverage, duration and closure. Keep blind counterexamples (causality upgrade, lost exception, universalized exemplar). Hold source/context constant while varying audience or duration when validating adaptation. Independent review can be a separate manual pass; an Agent service is not required.

## Qualification evidence

Every tested positive/negative has a concrete input artifact, expected result, actual result, exact implementation hash/version, and input/output hashes. Distinguish `POLICY_UNSUPPORTED`, `TESTED_REJECTED`, `NOT_EXECUTED`; policy text is not a negative test execution. Qualified records require both polarities, successful linked results and exact executor identity. Changing code, fonts, model, schema or output contract invalidates the affected scope. Model review additionally records prompt/model versions, attempts and disagreement; do not select only the best run.

## Delivery and portability

An editable request produces both `EditableSemanticArtifact` and `FlattenedReviewRender`. One PageSpec owns one slide plus its review render. Preserve prior revisions; do not overwrite evidence when correcting.

Release the package with `PACKAGE_LOCK.json`. `scripts/skill_tool.py verify-package` verifies every locked path/hash. Runtime paths/fonts come from explicit configuration. Run preflight and requalification in the target environment; old capability evidence does not travel as current authority. Qualification binds the runtime evidence file hash as well as code, schema and font identities. Third-party fonts are not redistributed by this package. Required frozen rules/workflows are bundled under `references/project/docs/`; runtime code is optional and versioned independently.
