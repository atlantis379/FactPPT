# General quality system v0.5

This contract is the rule-construction layer. P05, a particular chart type, a font or an existing composition is a test fixture, never the origin of a universal design prescription. Read this before choosing layouts or defining acceptance thresholds. It supplements INTEGRITY_AND_QUALITY_v0.5.md.

## 1. Rules precede artifacts

The dependency chain is:

`TaskContext → Source/Evidence Contract → Semantic Graph → Visual Encoding Contract → Scene/Layout Contract → Runtime Evidence → Actual Artifact → Independent Quality Results`.

An artifact may supply regression evidence about a rule. It may not retroactively define the rule so that the artifact passes. Freeze each test's contract before executing it; a contract change creates a new version and invalidates its prior acceptance. No hardcoded P05 coordinates, palette, three-column count or 3+4 condition count belongs in this general layer.

## 2. Separate invariants from context-dependent choices

Hard invariants: exact source identity; traceable meaning-bearing objects; truthful operators/units/context; explicit relationship ownership; no lost mandatory conditions; no unsupported comparison or causal claim; current evidence; no unauthorized occlusion; no approval of untested capabilities.

Context-dependent constraints: target audience and viewing mode, aspect ratio, minimum readable type, contrast target, density, allowable wrapping, number of pages and degree of explanation. Declare their values and rationale in a versioned per-run contract before rendering. The Skill does not universally require a particular font, palette, layout, column count or visual metaphor.

Preferences: decorative motif, whitespace rhythm and aesthetic reference. Optimize only after hard constraints and context-dependent acceptance are met. A preference cannot erase an evidence object or weaken a hard rule.

## 3. Semantic and visual models

Each semantic object has an immutable ID/version, kind, source references, scope/namespace, risk and exact/summary/synthesis status. Numeric facts separate raw decimal value, operator, unit, statistic role, denominator, population, timeframe, interval and display formatting. Missing values are explicit; no default zero. Derivations bind formula and input IDs and are marked synthesis.

Each visual encoding binds semantic IDs to visual channels: text, position, length, area, color, grouping, edge direction, sequence or emphasis. Declare whether the channel is categorical, quantitative, ordered or purely decorative. A quantitative channel requires a qualified transform; a categorical channel cannot silently imply rank. Layout changes must preserve all locked bindings and logical expressions.

Scene objects carry IDs, semantic bindings, regions, z-order, role, visible strings, font resources and asset hashes. Layout is derived from content/encoding/context constraints. Reflow, split, factoring or moving detail to an authorized appendix are repair decisions with provenance; they do not remove locked truth conditions. Factor only when a qualified equivalence checker can reconstruct every original scoped object.

## 4. Independent quality dimensions

| Rule family | Required comparison | Executable part | Independent review part |
|---|---|---|---|
| Q-SRC | immutable source and independent inventory vs extracted objects | page/section IDs, source hashes, exact anchors, missing/extra objects | whether inventory is meaning-complete and risk labels are correct |
| Q-SEM | approved graph vs actual text/data/relationships | exact/Decimal/identity/logic diff | source entailment, translation and interpretation |
| Q-DATA | raw data + declared encoding vs final chart primitives | recompute linear/log coordinates, baselines, intervals, series/order, labels and missing values | comparability and appropriateness of the encoding |
| Q-GLYPH | locked strings + declared font resources vs final format and render | actual format text/font readback, font cmap, size/bounds, image hashes | final visible glyphs, punctuation, superscripts and clipping |
| Q-COMP | frozen scene/context constraints vs actual rendered page | bounds, z-order occlusion, text region collision, contrast, mandatory objects, safe zones | reading order, grouping, cognitive load and visible meaning |
| Q-NARR | question + evidence + independently annotated assertions vs narrative | coverage, dependency order, duration, wording/scope integrity and closure | reasoning quality, certainty/causality, emphasis and audience fit |

These dimensions cannot replace one another. Exact labels with wrong geometry fail Q-DATA. Correct data in an unreadable layout fail Q-COMP. Attractive layout with omitted conditions fails Q-SEM. A font cmap PASS with corrupt visible output fails Q-GLYPH. A source page inventory is not 100% semantic recall.

## 5. Statistical geometry qualification

`scripts/quality_checks.py::validate_chart_svg` reads final SVG primitives independently and recomputes geometry from declared decimal data. Its explicitly supported subset is simple linear bars and linear/log point, line and interval charts on a white review background, with untransformed primitives, explicit IDs, opaque paint and labels. Unsupported colors/paint syntax, invisibility and transforms/styles are rejected, not assumed correct. This does not qualify every chart library, PPTX chart engine, radar/pie/area chart or arbitrary SVG.

Qualification includes correct and corrupt artifacts: label-correct/height-wrong; axis clipping; series or category swap; zero-baseline violation; wrong log mapping; missing-to-zero; interval displacement; wrong unit/context label; reversed line order. A new chart mechanism needs its own fixture and final-format adapter. Runtime qualification is scoped to the actual checker/format/version, not the term “statistical chart”.

## 6. Final visible glyph rule

Use `scripts/pptx_quality.py` for actual PPTX text/font readback and `runtime_executors/exact_overlay.py` for same-resource bitmap glyph validation. Neither is an OCR substitute. For each deliverable, bind the exact final file hash, render hash, renderer/version and declared font hashes; review every page at the contracted scale. The render-evidence record names the final artifact hash, slide number, render path/hash, renderer id/version and an independent visual-review checklist for glyphs, clipping and meaning-critical text. A displayed figure's text cannot pass solely because input JSON is correct. If renderer output or the independent review record cannot be inspected, keep Q-GLYPH unresolved.

Use explicit per-script/per-object font resources when one font lacks required codepoints. This is a declared capability dependency, not silent fallback. Changing the font requires requalification and rerender, even if text strings are unchanged.

## 7. Composition gate without template overfitting

The page contract defines purpose, primary message, reading sequence, grouping, target viewing scale, text/contrast thresholds, content-safe zones and allowed intersections. Validators consume those values; they do not contain template coordinates. Reviewers assess the intended reading path and relationship clarity against that contract. Automatic checks are hard evidence about geometry, not an aesthetic score.

Store independent findings with `dimension`, `object_id`, `expected`, `observed`, `severity`, `evidence_ref/hash`, `responsible_stage` and `repair_class`. Repair classes are `RECOMPOSE`, `REFLOW`, `SPLIT_PAGE`, `RESELECT_ENCODING`, `REFINE_CONTEXT`, `RECHECK_SOURCE`, `REQUALIFY_RUNTIME`. Changes to color/position in a sample alone do not close a general rule issue.

## 8. Full-source coverage calibration

The denominator comes from an independent source review or a labeled synthetic gold fixture, never solely from the extractor's own output. Record the source hash, reviewer/pass identity, source page/section inventory, and anchored semantic objects. Check footnotes, negation, cross-page continuations, exclusions, table ownership, conflicts and all meaning-critical numeric/recommendation objects.

`validate_coverage` compares extraction against that anchored oracle. It fails unknown denominators, mismatched identities, same-pass self-certification, missing sections/objects and semantic changes with unchanged quotations. It cannot prove that an independently annotated real source oracle is complete; that remains a separate review. Report `UNKNOWN`, or “agreement with reviewed inventory”, rather than inventing recall.

Calibration tests include synthetic full-source fixtures and, where available, reviewed real-source inventory. P05 can verify a page's 21 owned conditions, not the whole PDF. Preserve this scope in every report.

## 9. Narrative calibration

Separate the author's narrative from a reviewer annotation. The reviewer sees the question, approved evidence and raw narrative, and supplies reviewed assertion wording, support, scope, modality/causal strength, dependencies, required question coverage, duration and closure. Unknown wording remains unreviewed; do not assign a known assertion ID to altered text.

`validate_narrative` deterministically checks against this annotation. Required questions are bound to required reviewed assertion IDs; dependencies are supplied by the independent reference and closure binds actual present assertions. An author's answers/closure labels alone cannot satisfy coverage. It does not infer medical entailment from keywords. Calibration fixtures include causal strengthening, negation/exception loss, universalizing a scoped example, missing bridge/dependency, missing answer, duration overflow and absent closure. Keep explicit reviewer disagreement rather than averaging away a critical error.

For broader Skill quality evaluation, use independent reviewers or held-out material and record pass consistency, missed corruptions and false alarms. One case's agreement cannot certify all narratives or audiences.

## 10. Acceptance records and applicability

Use `schemas/quality_evaluation.schema.json`. Every applicable dimension returns PASS, FAIL or NEEDS_REVIEW with evidence. NOT_APPLICABLE needs an explicit scope reason (e.g. a native threshold matrix contains no statistical geometry). It does not count as a tested capability. Missing evidence is never PASS. An independent overall delivery decision is the conjunction of applicable component acceptance, current runtime qualification and required human review.

Keep prototypes separate from authoritative delivery. A P05 test may deliberately FAIL under a new rule and still be a successful regression test because the rule detected the defect. Report both the fixture's actual quality and whether the checker behaved correctly.
