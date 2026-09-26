# PageSpec & Visual Strategy Derivation Policy v0.1

**Status:** `ACTIVE_SKILL_POLICY_NOT_FROZEN_SPEC`

## 1. Purpose

Prevent the presentation pipeline from degenerating into source-layout reproduction. PageSpec must represent the presentation semantics that remain after evidence extraction, triage, context matching and narrative design. Visual Strategy must then choose the best visual grammar for that PageSpec.

Core principle:

> **Preserve source semantics, not source layout.**
>
> **PageSpec derives from synthesized presentation semantics, not from source layout, page order, table structure, figure structure, or source chapter hierarchy.**

This policy does not alter frozen Module 01–06 rules. It operationalizes the already-frozen Architect principle that Narrative Spine is driven by the Presentation Question rather than the source table of contents, and the Visual Strategy principle that visual selection is driven by Page Goal, information structure, approved semantics and precision requirements.

## 2. Layer separation

The pipeline must keep these layers distinct:

```text
Source Document / Source Layout
        ↓
Evidence Layer
Claim / NumericFact / Recommendation / FigureRef / TableFact / SourceRef
        ↓
Triage + Presentation Context
        ↓
NarrativePlan
        ↓
PageSpec
        ↓
Approved Semantic Page Graph
        ↓
Visual Strategy
        ↓
Generation Route
```

### Source / Evidence Layer
Answers: `What does the source actually say?`

### Narrative Layer
Answers: `What is the most useful sequence for this presentation question, context and audience?`

### PageSpec Layer
Answers: `What exactly must this page communicate?`

### Visual Strategy Layer
Answers: `What visual grammar best communicates the approved PageSpec without changing its meaning?`

A source page, table, figure or chapter is never automatically a presentation page.

## 3. PageSpec derivation rules

A PageSpec must be derived from:
- approved Triage decisions;
- the current `PresentationContextProfile` / AdaptationContract;
- NarrativePlan / Narrative Spine;
- approved Claim/NumericFact/Recommendation/Relationship objects;
- Presentation Question;
- page-level cognitive dependency within the deck.

A PageSpec must not be derived primarily from:
- source page boundaries;
- source table-of-contents order;
- source section headings;
- one-table-per-slide conversion;
- one-figure-per-slide conversion;
- visual similarity to the source document.

Each PageSpec requires at minimum:
- `PageGoal`;
- exactly one `PrimaryMessage`;
- `SupportingClaimIds[]`;
- `RequiredNumericFactIds[]` when applicable;
- `RequiredRelationshipIds[]` when applicable;
- `Conditions/Caveats`;
- `Provenance` for the PrimaryMessage: SOURCE / SUMMARY / SYNTHESIS;
- `SourceBindings[]`;
- `RiskLevel`;
- `PresentationDependency`;
- `source_structure_dependency`;
- `page_derivation_mode`.

## 4. PageSpec provenance

A page PrimaryMessage does not need to appear verbatim in the source.

Allowed:
- `SOURCE`: the source directly states the page proposition;
- `SUMMARY`: faithful compression of one or more source statements;
- `SYNTHESIS`: an organizing proposition supported by multiple approved source objects.

A SYNTHESIS PrimaryMessage is permitted only when all meaning-critical components are bound and the message does not introduce unsupported causality, scope, recommendation strength, comparison, diagnostic/treatment relation, or certainty.

High-risk SYNTHESIS follows existing RED / human-review rules.

## 5. Source structure dependency

Every PageSpec must classify whether source visual structure itself carries authoritative semantics:

- `AUTHORITATIVE_TOPOLOGY`: source topology/ordering/branching/geometry carries meaning that must be preserved;
- `PARTIAL_SEMANTIC_STRUCTURE`: some source grouping/order is meaning-critical, but presentation layout may be substantially redesigned;
- `EVIDENCE_ONLY`: the source table/figure is only a container for evidence; its visual structure should not constrain the presentation;
- `NONE`: the PageSpec is narrative/synthetic and has no source visual dependency.

Examples:
- guideline diagnostic algorithm → often `AUTHORITATIVE_TOPOLOGY`;
- disease taxonomy → often `PARTIAL_SEMANTIC_STRUCTURE`;
- large evidence table → often `EVIDENCE_ONLY`;
- narrative insight page synthesized from several source sections → often `NONE`.

## 6. Page derivation modes

Every page should declare one primary derivation mode:

### `SOURCE_RECONSTRUCTION`
Use when source topology itself is medically/scientifically authoritative or meaning-critical.

Preserve:
- nodes;
- edges;
- branch conditions;
- logical operators;
- ordering when meaningful;
- exact labels/numbers when required.

May redesign:
- spacing;
- typography;
- visual hierarchy;
- color;
- nonsemantic ornamentation.

### `SOURCE_SYNTHESIS`
Use when the page combines evidence from one or more source tables/figures/paragraphs into a new presentation structure.

The presentation structure may be new, but every authoritative semantic object remains source-bound.

### `NARRATIVE_SYNTHESIS`
Use when the page communicates an organizing insight needed by the presentation narrative but not represented as one source visual/page.

The insight must be supported by approved evidence and labeled SUMMARY/SYNTHESIS as appropriate.

`SOURCE_RECONSTRUCTION` is not inherently more faithful than `SOURCE_SYNTHESIS`. Fidelity is evaluated against source meaning, not layout similarity.

## 7. Visual Strategy decision gate

Before selecting a visual type, W11 must answer:

1. What is the PageGoal and PrimaryMessage?
2. What approved information structure does the PageSpec contain?
3. Does any source visual topology carry authoritative meaning?
4. If yes, which topology elements are protected?
5. If no, is the source visual merely an evidence container?
6. What visual grammar best serves the PageSpec rather than the source layout?
7. What precision / exact-text / topology locks apply?

Decision logic:

```text
Source contains table/figure/algorithm
        ↓
Does source visual structure itself carry authoritative meaning?
        ├─ YES → preserve protected semantic topology, redesign presentation
        └─ NO  → extract evidence objects, re-synthesize visual structure from PageSpec
```

## 8. Visual Strategy output additions

W11 VisualStrategyDecision should record:
- `page_derivation_mode`;
- `source_structure_dependency`;
- `protected_source_topology_elements[]`;
- `source_visual_reuse_reason`;
- `visual_structure_rationale`;
- `rejected_source_layout_dependencies[]`;
- `selected_visual_type`;
- `precision_requirement`;
- `generation_constraints`.

`source_visual_reuse_reason` must be semantic, not aesthetic convenience.

## 9. Anti-patterns

Reject or revise when any of the following occurs:
- one source table automatically becomes one slide;
- one source figure automatically becomes one slide;
- source chapter sequence is mechanically copied into the deck;
- a slide title merely repeats a source heading without relation to the Presentation Question;
- the visual type is chosen because the source used that type, even though the PageSpec requires a different information structure;
- an image generator or renderer expands the page toward source material not included in the PageSpec;
- evidence fidelity is confused with layout fidelity.

## 10. Regression rules

- `REG-PAGE-001`: PageSpec derives from Triage + Context + Narrative + approved evidence, never directly from source layout/page boundaries.
- `REG-PAGE-002`: Source table/figure/chapter does not automatically create a presentation page.
- `REG-PAGE-003`: PrimaryMessage may be SUMMARY/SYNTHESIS when fully supported; source verbatim wording is not required.
- `REG-PAGE-004`: PageSpec must declare `source_structure_dependency` and `page_derivation_mode`.
- `REG-PAGE-005`: Source Fidelity and Layout Fidelity are separate; layout similarity is not an approval criterion.
- `REG-VSTRAT-001`: Visual Strategy is selected from PageSpec information structure, not source visual form.
- `REG-VSTRAT-002`: Preserve source topology only when topology itself carries approved meaning.
- `REG-VSTRAT-003`: When source visual structure is not authoritative, extract evidence and re-synthesize the presentation visual.
- `REG-VSTRAT-004`: SOURCE_RECONSTRUCTION / SOURCE_SYNTHESIS / NARRATIVE_SYNTHESIS are explicit first-class derivation modes.
- `REG-VSTRAT-005`: Any source visual reuse requires a semantic rationale and provenance binding.
- `REG-VSTRAT-006`: A visually accurate reconstruction that misses the approved PageGoal/PrimaryMessage is FAIL.
- `REG-VSTRAT-007`: A new synthesis visual may differ radically from the source layout and still PASS when semantic bindings, precision and PageGoal fidelity pass.

## 11. Interaction with W15

Post-generation QA must separately evaluate:
- `PageGoalFidelity`;
- `PrimaryMessageFidelity`;
- `EvidenceFidelity`;
- `ProtectedTopologyFidelity` when applicable;
- `UnauthorizedSourceExpansion`;
- `LayoutSimilarity` — informational only, never a pass criterion.

A page can therefore:
- look very different from the source and PASS;
- look very similar to the source and FAIL.

## 12. Current Test 001 application

For the CMVD consensus benchmark:
- S02 classification: `SOURCE_RECONSTRUCTION` or `SOURCE_SYNTHESIS` with `PARTIAL_SEMANTIC_STRUCTURE`; preserve the 4-type/9-subtype taxonomy, not the original table layout.
- S03 diagnostic methods: `SOURCE_SYNTHESIS` with `EVIDENCE_ONLY`; the original diagnostic table should not dictate the slide structure.
- S04 diagnostic algorithm: `SOURCE_RECONSTRUCTION` with `AUTHORITATIVE_TOPOLOGY`; preserve clinically meaningful branches/conditions from the source algorithm.
- The previously generated treatment-overview S05 is not accepted merely because its content is source-related; if the approved S05 PageSpec is INOCA phenotyping, the treatment page fails `PageGoalFidelity` and must be rejected or moved only after Narrative/PageSpec revision.
