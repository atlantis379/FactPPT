# Full-Source Evidence Coverage Policy v0.1

**Status:** `ACTIVE_SKILL_POLICY_NOT_FROZEN_SPEC`

## 1. Purpose

Require whole-source traversal and structured coverage before Information Triage, Narrative generation, PageSpec construction, or any visual-stage work.

Core principle:

> **Narrative quality is bounded by the completeness of the evidence universe it sees.**
>
> **A presentation-relevant sample is not an acceptable substitute for full-source extraction.**

This policy does not change frozen Module 01–06 rule counts or frozen W00–W18 numbering. It introduces a mandatory `W02-FSC Full-Source Coverage Gate` after Structured Evidence extraction and before W03/W05 downstream use.

## 2. Required execution order

```text
W00 Source Registration
→ W01 PDF / Page Extraction
→ W02 Structured Evidence Layer — full-source extraction
→ W02-FSC Full-Source Evidence Coverage Audit
→ W03 Evidence Verification Gate
→ W04 Presentation Context
→ W05 Information Triage
→ W06 Narrative Draft
→ ...
```

W05 and all later presentation-semantic stages MUST NOT begin unless W02-FSC is `PASS` or `PASS_WITH_WARNINGS`.

W02-FSC `PASS` additionally requires the active `FactOracleReview`: the extraction run and reviewer run/identity are distinct; every page, including confirmed blank pages, has review evidence; RED facts are approved; disagreements are resolved; and `denominator_status=REVIEWED_COMPLETE`. Extractor/model self-review or an UNKNOWN/PARTIAL denominator cannot produce PASS.

If an incomplete evidence layer is discovered after W05/W06/W07, all dependent Triage/Narrative/PageSpec/Semantic/Visual artifacts become `STALE_REQUIRES_REBUILD`.

## 3. Definition of full-source extraction

Full-source extraction does **not** require turning every sentence into a separate Claim. It requires evidence-complete traversal of the entire source.

For every source page and substantive section:

1. the page/section is registered in a `SourceCoverageManifest`;
2. its content role is classified;
3. substantive propositions are extracted into atomic Claims or faithful SectionSummary objects;
4. all meaning-critical NumericFacts are captured with operator/value/unit/context;
5. all recommendations, recommendation classes, evidence levels, exclusions, contraindications, timing and special-population qualifiers are captured;
6. all tables/figures/algorithms with semantic content are registered and visually inspected when text extraction is insufficient;
7. conflicts/alternative thresholds are preserved as context-specific objects rather than silently merged;
8. intentionally non-Claim material is explicitly classified rather than silently skipped.

Allowed non-Claim classifications include:
- `SOURCE_METADATA`;
- `METHODS_GOVERNANCE`;
- `REFERENCE_LIST`;
- `AUTHOR_DISCLOSURE`;
- `DUPLICATE_TRANSLATION`;
- `NON_SUBSTANTIVE_LAYOUT`.

Reference-list pages need citation inventory/coverage but do not require separate medical Claims unless the body explicitly relies on information that has not itself been stated in the source narrative.

## 4. SourceCoverageManifest minimum fields

- `document_id`
- `document_hash`
- `total_pages`
- `substantive_body_pages[]`
- `reference_pages[]`
- `page_records[]`
- `section_records[]`
- `table_refs[]`
- `figure_refs[]`
- `coverage_status`
- `unresolved_pages[]`
- `unresolved_sections[]`
- `coverage_risk_register[]`

Each page record should contain:
- `page_number`
- `journal_page_if_available`
- `content_role`
- `section_labels[]`
- `extraction_status`
- `claim_ids[]`
- `numeric_fact_ids[]`
- `recommendation_fact_ids[]`
- `table_figure_refs[]`
- `visual_verification_required`
- `visual_verification_status`
- `coverage_notes`

## 5. Coverage requirements

### 5.1 Page coverage

Every page must have a coverage record. Silent page omission is BLOCK.

### 5.2 Section coverage

Every substantive section/subsection must have at least one of:
- extracted Claim(s);
- extracted Numeric/Recommendation/Relationship candidate objects;
- a faithful SectionSummary with explicit reason why atomic extraction is unnecessary at the current stage.

### 5.3 RED completeness

All RED content must be explicitly structured before Triage:
- diagnostic thresholds and operators;
- treatment doses where source-provided and meaning-critical;
- contraindications / avoid / do-not-use statements;
- recommendation class;
- evidence level;
- timing/sequence when source-authored;
- inclusion/exclusion conditions;
- special populations;
- treatment/diagnostic relationship ownership.

A section containing RED material cannot be marked covered solely because a broad summary Claim exists.

### 5.4 Table and figure completeness

Each semantically relevant source table/figure/algorithm must be registered. If its topology, row ownership, recommendation grade, exact numeric value or grouping is meaning-critical, rendered visual inspection is mandatory.

### 5.5 Coverage before relevance

`Presentation Relevance` may be evaluated only after full-source coverage exists.

Forbidden sequence:
```text
sample likely-important source sections
→ extract only those sections
→ Triage/Narrative
```

Required sequence:
```text
full source traversal / evidence universe
→ coverage audit
→ Triage
→ Narrative
```

## 6. Full-source coverage audit dimensions

Audit:
1. `PageCoverageRate`;
2. `SubstantiveSectionCoverageRate`;
3. `REDObjectCoverageRate`;
4. `TableFigureRegistrationRate`;
5. `RenderedInspectionCoverage` for required visual objects;
6. `NumericContextCoverage`;
7. `RecommendationOwnershipCoverage`;
8. `ConflictPreservationCoverage`;
9. `SilentOmissionCount`;
10. `NarrativeChangingOmissionCount`.

## 7. Gate statuses

Exactly one:
- `PASS`
- `PASS_WITH_WARNINGS`
- `REVISIONS_REQUIRED`
- `BLOCK`

W03/W05 downstream use is blocked when:
- any substantive page/section is silently unprocessed;
- RED content is known to exist but is not structurally extracted;
- table/figure semantics required for interpretation have not been visually checked;
- recommendation ownership across contexts is incomplete;
- a missing source section could materially change Triage or Narrative.

## 8. Narrative-changing omission test

For every uncovered/partially covered substantive section, ask:

> If this section had been fully extracted before Triage, could it change the presentation question, scope, narrative order, deep-dive choice, page allocation, recommendation ownership, uncertainty framing or PrimaryMessage?

If `YES` or `PLAUSIBLY_YES`:
- mark `NARRATIVE_CHANGING_OMISSION`;
- invalidate W05 and downstream artifacts;
- rebuild the evidence layer and rerun Triage/Narrative.

## 9. Regression rules

- `REG-FSC-001`: Every source page must have a coverage record before W05.
- `REG-FSC-002`: Every substantive section must be extracted or explicitly summarized/classified; silent omission is forbidden.
- `REG-FSC-003`: Presentation-relevant sampling cannot substitute for full-source extraction.
- `REG-FSC-004`: All RED facts/recommendations/conditions must be structured before Triage.
- `REG-FSC-005`: Reference pages may be inventory-only but cannot be silently omitted from the source manifest.
- `REG-FSC-006`: Table/figure/algorithm objects with meaning-critical layout/topology require rendered inspection.
- `REG-FSC-007`: Context-specific thresholds and recommendation ownership must not be merged during full extraction.
- `REG-FSC-008`: Discovery of a narrative-changing omission invalidates W05 and all downstream presentation-semantic artifacts.
- `REG-FSC-009`: Triage decides what enters the presentation only after the full evidence universe is available.
- `REG-FSC-010`: Coverage completeness is evaluated independently from eventual main-deck inclusion.
- `REG-FSC-011`: The extractor's own inventory cannot certify its denominator; a distinct reviewed oracle is required for PASS.
- `REG-FSC-012`: Every page-level oracle record must carry independent evidence, including confirmed blank/non-substantive pages.

## 10. Required artifacts

A compliant run should produce before W05:

```text
01_page_extraction/
02_evidence/
├─ full_source_coverage_manifest.json
├─ section_inventory.json
├─ claims.json
├─ numeric_facts.json
├─ recommendation_facts.json
├─ table_figure_registry.json
└─ full_source_coverage_audit.json
03_evidence_verification.json
```

## 11. Interaction with existing policies

- Context Matching may describe audience/task before full-source coverage, but source-scope conclusions must be revalidated after W02-FSC.
- Information Triage is downstream of the full evidence universe.
- Narrative Rationality Audit cannot compensate for missing source extraction.
- Narrative-to-Page Decomposition and PageSpec derivation consume only evidence originating from a W02-FSC-approved evidence universe.
- Downstream visual fidelity cannot repair upstream source-coverage omissions.
