# Frozen Rules Compilation for Reference Skill v0.1

**Compilation status:** `REFERENCE_COMPILED_FROM_FROZEN_SPECS`  
**Numbered frozen rules represented:** 178  
**Additional frozen governance:** Rule Enforcement / Policy Engine principles

This file is a behavioral compilation and navigation map. The authoritative exact wording remains in repository `docs/specs/`.

## Authority map

| Module | Frozen scope | Count | Skill responsibility |
|---|---:|---:|---|
| Module 01｜Claim Table | v0.1 | 7 | Build atomic, source-grounded evidence objects |
| Module 02｜Information Triage | v0.1 | 8 | Select for current presentation without deleting evidence |
| Module 03｜Medical Information Architect | v0.1 | 10 | Build narrative/page semantics without inventing facts |
| Module 04｜Semantic Relationship & Evidence Binding | v0.1 | 60 | Bind data/clinical/context/visual semantics and provenance |
| Module 05｜Medical Verifier & Source Fidelity Gate | Batches 1–4 | 52 | Verify source fidelity, semantics, issues, conflicts/external checks |
| Module 06｜Prompt-driven Medical Visual Generation | Batches 1–3 | 41 | Contract, visual strategy, qualified routing |

Total: **178 numbered frozen rules**. Module 05 remains partially frozen at Batches 1–4; this Skill must not invent a non-existent frozen Batch 5.

## Module 01｜Claim Table v0.1 — 7 frozen rules

1. One Claim expresses one independently verifiable medical proposition.
2. Store `source_quote` and `normalized_claim` separately.
3. Numbers, thresholds, recommendation classes and evidence levels are separately structured.
4. SOURCE / SUMMARY / SYNTHESIS provenance begins at Claim level.
5. Claim stores facts only; relationships belong in Edge/SemanticRelationship and must not be silently inferred during Claim extraction.
6. The same fact from multiple sources may form a Canonical Claim; conflicting sources must never be automatically fused.
7. Any content that requires external medical knowledge to complete may not be marked SOURCE.

Operational implications: SourceSpan ≠ Claim; numeric token ≠ NumericFact; preserve meaning-critical population/condition/dose/time qualifiers; conflicts remain explicit.

## Module 02｜Information Triage v0.1 — 8 frozen rules

1. Triage decides whether content belongs in this presentation, not its absolute medical importance.
2. Presentation Question is the highest-level filter and must exist before Triage.
3. Consider Audience, Project Type, Goal and Duration.
4. Risk Level is a constraint, not a simple weight; RED does not mean every RED fact must appear.
5. When removing a qualifier would change meaning, process the related Claims as a Meaning-Preserving Bundle.
6. Output exactly MUST_INCLUDE / SHOULD_INCLUDE / APPENDIX / EXCLUDED; EXCLUDED never deletes the source Claim.
7. Every TriageDecision has a reason; user overrides are permitted and logged.
8. Triage decides content selection and Presentation Dependency only; it does not create medical relationships or pages.

## Module 03｜Medical Information Architect v0.1 — 10 frozen rules

1. Architect organizes how to tell the story; it does not decide whether medical facts are true.
2. Build a Narrative Spine around the Presentation Question rather than copying the source TOC.
3. Narrative Spine, Section titles and Primary Messages retain SOURCE/SUMMARY/SYNTHESIS provenance.
4. Each page has a Page Goal and exactly one Primary Message; Supporting Claims support that message.
5. Page semantic hierarchy is `Primary Message → Supporting Claims → Conditions/Data → Source`.
6. Meaning-Preserving Bundles cannot be split by layout/time constraints in ways that change meaning.
7. Architect may create Presentation Dependency and recommend Functional Visuals but cannot create unverified Clinical Edges/Relationships.
8. Audience adaptation mainly changes cognitive order and depth, not the underlying Claim.
9. Architect outputs NarrativePlan/PageSpec, not final visuals, and must not fill source gaps for narrative completeness.
10. User may reorder Sections/Pages/Narrative; override is logged; presentation order changes do not automatically change Clinical Relationships.

## Rule Enforcement / Policy Engine — frozen governance

- Rule author, executor and verifier are separate responsibilities.
- Hard Constraints must not exist only in prompts.
- **A HARD:** Schema Validator, Capability Control/RBAC/API allowlist, State Machine, Deterministic Validator → violation blocks.
- **B SEMANTIC:** Semantic QA + Medical Verifier → block or HUMAN_REVIEW_REQUIRED.
- **C HUMAN-GOVERNED:** conflicts, RED synthesis, contested critical interpretation → HUMAN_REVIEW_REQUIRED.
- Orchestrator decides what runs next; Policy Engine decides whether output may advance.
- Least-privilege capability boundaries apply.

## Module 04｜Semantic Relationship & Evidence Binding v0.1 — 60 frozen rules

### Batch 1｜Semantic Assertion & Title Entailment — 8
- Audience-inferable facts/comparisons/conditions/causality/support/time/clinical relations are semantic and auditable.
- Titles bind to approved Claims.
- Semantic strength may not exceed source strength.
- Qualifiers are preserved.
- Combined judgement is SYNTHESIS unless directly sourced.
- Unsupported title/presupposition fails entailment.

### Batch 2｜Data Binding — 12
- Bind value + metric + unit + population + outcome + time + intervention/comparator + statistic type + source.
- Numeric equality alone is not sufficient semantic binding.
- Preserve baseline/change, absolute/relative, individual/aggregate and effect-vs-uncertainty distinctions.
- Bind effect size with CI/P/N where source meaning requires them.
- Derived values are SYNTHESIS and use allowed derivation paths.
- Missing/unknown/not-reported are distinct states.
- OCR-estimated data remains uncertain until verified.
- Cross-study direct comparison requires Comparability clearance.
- RED data reaches final output only when BOUND and verified/human-approved as required.

### Batch 3｜Clinical Relationship — 14
- Relationship provenance is independent of Claim provenance.
- Relationship type, direction and conditions are structured.
- SOURCE relationship needs direct source support.
- Verify direction; no default transitivity.
- Preserve qualifiers and logical operators.
- Negation/contraindication/exclusion are explicit.
- Recommendation strength/class/evidence are bound to the correct recommendation relation.
- Temporal, association, prediction and causal relationships are distinct.
- Multi-source paths retain individual source bindings.
- Do not auto-connect graph nodes for visual/story completeness.
- RED synthesis/conflict is not auto-approved.
- Final visual connectors bind approved relationship IDs.

### Batch 4｜Contextual Relationship — 11
- Page adjacency, section order and narrative sequencing can imply semantics and require audit.
- Presentation order, dependency, contextual implication and clinical relationship are separate.
- Context Contract defines permitted inheritance.
- Semantic transition triggers are checked.
- Do not auto-inherit context across changed scope.
- Implicit comparison triggers Comparability.
- Practice implications need entailment.
- Rhetorical/title presuppositions are auditable.
- Checker detects implication; it does not invent the missing relation.

### Batch 5｜Visual Semantic Binding & Medical Visual Provenance — 15
- Pure Styling and Semantic Visual Encoding are separate.
- Grouping/proximity/alignment/enclosure/position/hierarchy may carry semantics and require binding.
- Color/size/shape carry semantic meaning when used for risk/effect/category/etc.
- Presentation Priority differs from Clinical/Evidence/Risk Priority.
- Axis/legend/scale/encoding bind to data semantics and must not mislead.
- Connectors bind approved relationship IDs.
- Medical Semantic Provenance and Visual Asset Provenance are separate.
- Adapted/generated medical visuals require QA.
- AI-generated medical visuals default to `medical_verified=false` until verified.
- Semantic visuals are stored as objects + relationships.
- RED visual provenance coverage must be complete.
- Text inside images is auditable content.
- Copyright/licensing is distinct from semantic validity.

## Module 05｜Medical Verifier & Source Fidelity Gate — 52 frozen rules

**Current frozen scope:** Batch 1–4 only. Do not treat Module 05 as fully frozen beyond these batches.

### Batch 1｜Verifier Role & Source Fidelity — 10
- Verifier checks generated meaning against source.
- Source Fidelity ≠ Clinical Correctness.
- Verification modes are separated: SOURCE_FIDELITY / CROSS_SOURCE_CONSISTENCY / EXTERNAL_MEDICAL_CHECK.
- Verifier is read-only with respect to source semantic objects.
- Verify claims, titles, data, relationships, context and semantic visuals.
- Verification result includes source span/evidence.
- Do not fill source gaps with model knowledge.
- RED content is gated.
- Confidence score is not evidence.

### Batch 2｜Semantic Fidelity Verification — 12
- Use minimum sufficient source span.
- Compare structured semantic frames/diffs, not only text similarity.
- Verify scope, quantifier, modality, negation, logical operators, relation type and recommendation semantics.
- Multi-source synthesis identifies each contributing source.
- Inspect all directly relevant sources rather than cherry-picking supportive evidence.

### Batch 3｜Issue Resolution & Re-verification Loop — 14
- Route issues to responsible upstream module.
- Revisions are immutable/versioned.
- Downstream dependents become stale after material semantic change.
- Perform targeted re-verification plus relevant regression verification.
- Deleting content does not automatically resolve root cause.
- Prefer earliest root cause.
- Maintain issue state machine and retry budget.
- Track recurrent issues.
- Human override is separate from verification result.
- Revised version must be reverified.
- Approved graph binds explicit versions.
- Relevant downstream gates rerun.

### Batch 4｜Cross-source Conflict & External Medical Verification — 16
- Determine Source Context before declaring conflict.
- Conflict types are explicit.
- Source-version relationships are explicit.
- Supersession is claim-level, not automatic whole-document truth.
- Source Priority ≠ truth.
- Source type has functional semantics.
- Evidence publication, guideline recommendation and regulatory approval are distinct evidence functions.
- Regulatory claims require independent verification when relevant.
- External checks are explicit and source pools isolated.
- External sources are qualified and time-stamped (`verified_as_of`).
- External findings do not automatically rewrite source facts.
- Newest source is not automatically most applicable.
- Retraction/correction status is tracked.
- Evidence synthesis provenance is explicit.

## Module 06｜Prompt-driven Medical Visual Generation — 41 frozen rules

### Batch 1｜Visual Generation Contract & Prompt Compiler — 14
- Generation begins from Approved Semantic Page Graph, not raw PDF/free-text prompt.
- Build a structured Visual Generation Contract first.
- Locks: HARD_LOCK / SEMANTIC_LOCK / BOUNDED_CREATIVE / FREE_CREATIVE; unauthorized downgrade forbidden.
- Claims/NumericFacts/thresholds/units/drug names/population/conditions/exclusions/recommendation/evidence/clinical relationships/logical operators/source bindings are locked according to semantic risk.
- Unique Page Goal + Primary Message.
- Mandatory medically meaningful objects go into Mandatory Content Object Register.
- Exact high-risk strings go into Exact Text Register.
- Clinical/logical/grouping/hierarchy/color semantics go into Visual Semantic Contract.
- Functional Visual Type is selected upstream; image model cannot downgrade it for aesthetics.
- Layout freedom uses bounded regions/reading flow/hierarchy.
- Presentation priority is separated from Clinical/Evidence/Risk priority.
- Medical Visual Assets have explicit contracts.
- Declare FULL_IMAGE or CONTROLLED_COMPOSITION; high-risk precise pages prefer controlled composition.
- Prohibited Transformations are explicit.
- Same contract is used for post-generation QA.

### Batch 2｜Visual Strategy Selector — 13
- Decision basis: Page Goal + Visual Intent + Information Structure + Approved Semantic Relationships + Precision Requirement.
- Hard Gate before scoring.
- Standard-aware candidate generation for applicable CONSORT/PRISMA/STARD/etc.
- Statistical visual must match data shape.
- Time Series / Time-to-event / Individual Longitudinal Course / Event Sequence / Duration are distinct.
- Preserve clinical logic including branches/exclusions/AND/OR/NOT/EXCEPT.
- Comparison visual requires Comparability clearance.
- Selector cannot invent semantics.
- Precision-preserving representation; Table/Matrix are first-class.
- `NO_VALID_VISUAL` / text-forward page are legal.
- Visual Strategy ≠ Generation Strategy.
- Save candidates/exclusions/rationale and allow AMBIGUOUS / NEEDS_HUMAN_REVIEW.
- Visual grammar may express only licensed semantics.

### Batch 3｜Generation Strategy Router — 14
- Router resolves approved VisualStrategyDecision into executable route; cannot alter Visual Type/Page Goal/medical semantics.
- Route at minimum necessary semantic granularity while preserving bindings.
- Hard Route Qualification precedes optimization.
- Exact quantitative geometry uses qualified, verifiable routes.
- Meaning-critical topology uses lockable/verifiable topology routes.
- ExactTextRegister items use authoritative-string rendering paths.
- Medical assets obey MedicalVisualAssetContract.
- Protected Semantic Layers cannot be semantically repainted/rearranged/warped/rewritten; only proven semantic-invariant transformations are allowed.
- Router executes DataEgress/Privacy policy, not redefine it.
- Hard routing relies only on version-bound qualified capability evidence.
- Fallback cannot degrade semantics/precision/visual type/verification requirements.
- Material capability changes invalidate affected qualifications/routes.
- Generation Execution Provenance is separate from Medical Semantic and Visual Asset Provenance.
- A route is eligible only if executable post-generation verification exists.

## Cross-module invariants

1. Raw PDF → final visual is never a direct path.
2. Source fidelity and clinical correctness are separate.
3. SOURCE/SUMMARY/SYNTHESIS provenance remains explicit.
4. RED medical content requires stronger verification/human review.
5. Design/generation models cannot mutate locked facts/relations/bindings.
6. No “100% accuracy” claims; auditability and traceability are the defensible product claims.
7. Synthetic cases default OFF and remain separate from Source Fact Layer.
8. Presentation deck vs reference/notes/backup distinction is preserved.
9. PPT is the delivery container, not the visual generation engine.
10. Frozen rules are not overridden by versioned policy registries or calibration weights.
