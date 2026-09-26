---
name: auditable-medical-presentation-reference
description: Execute the project’s auditable Model-first Reference Pipeline for transforming medical PDF/source materials into source-grounded evidence, context-matched presentation views, narrative/page semantics, verified generation contracts, controlled visual outputs, runtime-qualified execution routes, and benchmark records without silently changing source facts.
---

# Auditable Medical Presentation Reference Skill v0.4.0

## 0. Status and authority

**Skill status:** `FORMAL_REFERENCE_SKILL_v0.4.0`  
**Execution model:** Model-first reference implementation + portable runtime qualification  
**Canonical workflow:** `REFERENCE_PIPELINE_WORKFLOW_v0.1` + active versioned Skill policies/contracts  
**Canonical checklist:** `REFERENCE_PIPELINE_CHECKLIST_v0.1` plus active checklist supplements.

This Skill compiles project frozen rules into repeatable execution behavior. It does **not** replace `docs/specs/`; frozen specs remain the highest project authority. v0.4.0 adds a portable runtime qualification sub-gate inside W12 and does **not** change the frozen W00–W18 numbering or the 178 frozen Module 01–06 rules.

Authority order:
1. explicit user task constraints, provided they do not require weakening mandatory audit/safety controls;
2. `docs/specs/` frozen rules;
3. frozen reference workflow/checklist;
4. active versioned Skill policies/contracts, including Full-Source Evidence Coverage, context matching, Narrative Rationality, Narrative-to-Page Decomposition, PageSpec/Visual Strategy derivation, and Portable Runtime Capability Contract;
5. this Skill orchestration text;
6. model knowledge only where allowed and explicitly labeled.

Never silently weaken a frozen rule to complete a run.

## 1. Core operating principles

> **Semantic Intelligence → LLM**  
> **Deterministic Integrity → Code / Validator**  
> **RED clinical judgement → Human Review**  
> **Full evidence universe before presentation relevance.**  
> **Narrative must be approved before page decomposition.**  
> **Preserve source semantics, not source layout.**  
> **Runtime capability must be proven, not assumed.**

The model may perform semantic understanding, atomic-claim extraction, qualifier recognition, full-source coverage classification, presentation-context matching, triage, narrative design, relationship candidates, verification assistance, visual-strategy selection, generation-component decomposition, runtime-requirement derivation and prompt compilation.

The model is not authoritative for immutable source identity, exact offsets, schema integrity, state transitions, exact numeric equality, exact text rendering, permissions/data egress, concrete engine capability, or final RED clinical approval where deterministic/human review is required.

A vendor/model/product name is never sufficient evidence of generation capability.

## 2. When to use

Use this Skill when medical source material is provided or referenced and the task includes structuring evidence, preparing context-specific presentation content, triage, narrative/outline, page construction, semantic/medical audit, visual strategy, runtime qualification, prompt compilation, page generation, visual QA, or benchmark validation.

Do not use it as a shortcut for patient-specific diagnosis or treatment decisions. It organizes and audits source-derived presentation material.

## 3. Mandatory run inputs

Before W05 Triage, resolve and record:
- `source_files`
- `presenter_role`
- `audience`
- `subject_scope`
- `scenario_or_project_type`
- `presentation_question`
- `goal`
- `duration`
- `language`
- `external_research_allowed`
- `synthetic_case`

Before W12 effective engine binding, resolve and record:
- `RuntimeCapabilityProfile`
- `GenerationCapabilityRegistry`
- `PostGenerationVerifierCapabilityRegistry`
- project/run `DataEgressPolicy / PrivacyDecision`
- all required `MedicalVisualAssetContract` objects
- qualification evidence for every Hard-qualified capability.

Defaults:
- `external_research_allowed = false` for a source-faithful run unless explicitly requested;
- `synthetic_case = false` unless explicitly requested;
- if presenter/audience/goal/duration are unknown and materially affect Triage, ask only for minimum missing context;
- `subject_scope` must be revalidated against the W02-FSC-approved full evidence universe before W05;
- missing runtime qualification inputs do not invalidate W10/W11 semantics, but they block W12 effective route binding and W13.

## 4. Mandatory execution order

```text
W00 Source Registration
→ W01 PDF / Page Extraction
→ W02 Structured Evidence Layer — FULL SOURCE
→ W02-FSC Full-Source Evidence Coverage Audit
→ W03 Evidence Verification Gate
→ W04 Presentation Context & Audience Matching
→ W05 Information Triage
→ W06 Narrative Draft
→ W06-NR Narrative Rationality Audit
→ Approved Narrative Architecture
→ W06-NP Narrative-to-Page Decomposition Audit
→ Approved Page Allocation Plan
→ W07 PageSpec Construction
→ W08 Semantic Relationship & Evidence Binding
→ W09 Medical / Numeric / Logic Audit
→ W10 Approved Semantic Page Graph
→ W11 Visual Strategy Selection
→ W12 Generation Strategy Routing
   ├─ W12-A Abstract Legal Route / Component Plan
   └─ W12-RQ Runtime Qualification + W12-B Effective Engine Binding
→ W13 Visual Generation Contract + Prompt Compilation
→ W14 Page Generation / Controlled Composition
→ W15 Post-generation Visual Audit
→ W16 Human Review Gate
→ W17 Approved Delivery
→ W18 Benchmark Record + Lessons Learned
```

`W12-A / W12-RQ / W12-B` are active Skill sub-gates. They do not change frozen stage numbering.

Do not skip a blocking gate because a later model might repair it.

## 5. Stage execution rules

### W00–W01｜Source registration and extraction

Record immutable source identity and retain/point to a retrievable source. Confirm actual page count from the file. Preserve page numbering. For PDFs, use page text plus rendered-page visual evidence. Tables, figures, flowcharts, multi-column layouts, and visibly corrupted text require rendered-page inspection before evidence approval. Never silently omit unreadable pages.

### W02｜Structured Evidence Layer — full source required

W02 must traverse the entire source, not only sections predicted to be presentation-relevant.

Create source-grounded objects such as `SourceSpan`, `ClaimCandidate`, `AtomicClaim`, `NumericFact`, `RecommendationFact`, `EvidenceGradeFact`, `TableFact`, `FigureRef`, `SourceRef`, `Provenance`, `RiskLevel`, plus a `SourceCoverageManifest`/section inventory.

A SourceSpan is not automatically a Claim. A numeric token is not automatically a NumericFact. Preserve `source_quote` separately from `normalized_claim`. Preserve population, subgroup, condition, exclusion, dose, timeframe, comparator and limitations when meaning-critical. Do not create clinical edges during Claim extraction.

Full-source extraction does not mean one Claim per sentence. It means every page and substantive section is registered and its substantive meaning is represented by atomic evidence objects or a faithful section summary/classification. Reference pages may be inventory-only but may not be silently omitted.

All RED material must be structured before Triage: thresholds/operators/units/context, recommendation class/evidence level, doses/timing when present, inclusion/exclusion, special populations, contraindications, and context-specific diagnostic/treatment ownership.

### W02-FSC｜Full-Source Evidence Coverage Audit

Mandatory active policy: `FULL_SOURCE_EVIDENCE_COVERAGE_POLICY_v0.1.md`.

Audit at minimum:
- every page registered;
- every substantive section represented;
- RED object completeness;
- all substantive tables/figures/algorithms registered;
- rendered inspection completed for meaning-critical layout/topology;
- numeric context and recommendation ownership preserved;
- conflicts/alternative thresholds not silently merged;
- `SilentOmissionCount = 0`;
- every partial/uncovered section passes the Narrative-Changing Omission Test.

W05 and later stages are forbidden unless W02-FSC is `PASS` or `PASS_WITH_WARNINGS`.

If a later audit discovers a source omission that could change scope, Presentation Question, narrative order, deep-dive choice, recommendation ownership, uncertainty framing or page allocation, invalidate W05 and all dependent downstream artifacts and return to W02.

A presentation-relevant sample is never sufficient for an authoritative reference run.

### W03｜Evidence Verification Gate

Verify the W02-FSC-approved evidence universe: atomicity; scope/population/subgroup; condition/exclusion; modality/quantifier; negation; value/operator/range/unit; statistic type; HR/OR/RR/CI/P/n where applicable; recommendation class; evidence level; exact source location. Uncertain items remain uncertain; silent approximation is forbidden.

### W04｜Presentation Context & Audience Matching

W04 must output a structured open-facet `PresentationContextProfile`.

Model independently:
- `DomainContextProfile`;
- `PresenterProfile`;
- `AudienceProfile` with one or more `AudienceSegment` objects;
- `SubjectScopeProfile`;
- `ScenarioProfile`;
- `TaskIntentProfile`;
- `ConstraintProfile`;
- `AdaptationContract`;
- `ContextIntegrityCheck`.

Role labels are descriptive hints, not authoritative adaptation logic. Unknown facets remain UNKNOWN/UNRESOLVED rather than being stereotyped from a job title or specialty.

Adaptation may change selection, ordering, explanatory depth, terminology explanation, main-deck/appendix allocation, examples, visual complexity and speaker-note depth. It must not mutate source truth conditions, subject scope, condition/exclusion, dose, threshold/operator/range, statistic value, recommendation class, evidence level, relationship direction/logical operator or provenance.

Run `ContextIntegrityCheck` before W05. BLOCK if W04 mutated an authoritative evidence object.

### W05｜Information Triage

Triage consumes the **full verified evidence universe**, not a sampled subset.

Allowed outputs: `MUST_INCLUDE`, `SHOULD_INCLUDE`, `APPENDIX`, `EXCLUDED`. Every decision has a reason. Apply the W04 AdaptationContract to selection/allocation only; never rewrite source facts. Preserve Meaning-Preserving Bundles. EXCLUDED content remains in the evidence layer.

### W06｜Narrative Draft

Build the Narrative around the `PresentationQuestion + Context + Goal + full verified evidence universe`, not by mechanically copying the source TOC, page order, section sequence, table order or figure order.

The Narrative answers: **How should the verified evidence be told for this presentation?**

### W06-NR｜Narrative Rationality Audit

Mandatory active policy: `NARRATIVE_RATIONALITY_AUDIT_POLICY_v0.1.md`.

An unaudited Narrative Draft may not create approved PageSpecs. Audit Presentation Question coverage, source support, domain logic, scope coherence, priority/evidence balance, audience fit, duration fit, missing bridges, redundancy/compression, narrative overreach, uncertainty visibility and closure.

Broad→narrow deep dives require explicit exemplar declaration and scope return/closure. Narrative transitions must not silently create causality, mandatory sequence, superiority or recommendation strength.

Required output: `ApprovedNarrativeArchitecture` with gate `PASS` or `PASS_WITH_WARNINGS`.

### W06-NP｜Narrative-to-Page Decomposition Audit

Mandatory active policy: `NARRATIVE_TO_PAGE_DECOMPOSITION_AUDIT_POLICY_v0.1.md`.

A reasonable Narrative does not guarantee reasonable slide decomposition. Page boundaries follow cognitive units, dependencies, audience needs and duration—not source page/table/figure boundaries or a preselected slide count.

Audit one coherent cognitive unit / one PrimaryMessage candidate per page, dependency/order, missing bridges, cognitive load, mergeability/splittability, main-vs-appendix allocation, scope balance, source-layout independence and page-count neutrality.

`Display Intent` may be defined here but is not yet Visual Strategy.

Required output: `ApprovedPageAllocationPlan` with gate `PASS` or `PASS_WITH_WARNINGS`.

### W07｜PageSpec Construction

**PageSpec derives from summarized/synthesized presentation semantics, not from source layout or source chapter structure.**

W07 requires:
- W02-FSC-approved full evidence universe;
- approved Triage decisions;
- current AdaptationContract;
- ApprovedNarrativeArchitecture;
- ApprovedPageAllocationPlan;
- approved Claim/NumericFact/Recommendation/Relationship objects;
- presentation-level cognitive dependency.

Each PageSpec requires:
- one `PageGoal`;
- exactly one `PrimaryMessage`;
- supporting Claim IDs;
- required NumericFact/Relationship IDs when applicable;
- meaning-critical conditions/caveats;
- explicit source bindings;
- risk level;
- PrimaryMessage provenance: `SOURCE`, `SUMMARY`, or `SYNTHESIS`;
- `PresentationDependency`;
- `source_structure_dependency`;
- `page_derivation_mode`.

`PrimaryMessage` does not need to occur verbatim in the source. SUMMARY/SYNTHESIS is valid when fully supported and does not add unsupported causality, scope, certainty, recommendation strength, comparison or clinical relationship.

Required `source_structure_dependency` values:
- `AUTHORITATIVE_TOPOLOGY`;
- `PARTIAL_SEMANTIC_STRUCTURE`;
- `EVIDENCE_ONLY`;
- `NONE`.

Required `page_derivation_mode` values:
- `SOURCE_RECONSTRUCTION`;
- `SOURCE_SYNTHESIS`;
- `NARRATIVE_SYNTHESIS`.

Source Fidelity is evaluated against meaning, not layout similarity.

### W08｜Semantic Relationship & Evidence Binding

Bind only supported or explicitly synthesis/review-required relationships. Preserve direction, conditions, temporal structure, AND/OR/NOT/EXCEPT, recommendation/evidence association, data ownership, grouping/legend/series ownership and comparability status. Visual grammar itself is semantic.

### W09–W10｜Audit and Approved Semantic Page Graph

Audit Source Fidelity, Numeric Fidelity, Title entailment, Relationship fidelity, contextual implication, comparison validity, recommendation strength, evidence level, conflicts and RED synthesis. Only approved/current object versions enter the Approved Semantic Page Graph.

### W11｜Visual Strategy

Visual Strategy is selected from the **approved PageSpec information structure**, not from the source visual form.

Select from:
`PageGoal + PrimaryMessage + InformationStructure + ApprovedRelationships + PrecisionRequirement + AdaptationContract + source_structure_dependency`.

Before selecting a visual type, answer:
1. What must this page communicate?
2. What approved information structure must be visible?
3. Does a source figure/table/algorithm contain meaning-critical topology?
4. If yes, which topology elements are protected?
5. If no, is the source visual merely an evidence container?
6. What visual grammar best serves the PageSpec, even if it looks very different from the source?

```text
Source contains table / figure / algorithm
        ↓
Does source visual structure itself carry authoritative meaning?
        ├─ YES → preserve protected semantic topology; redesign presentation form
        └─ NO  → extract evidence objects; re-synthesize visual structure from PageSpec
```

Record `page_derivation_mode`, `source_structure_dependency`, protected topology, source-visual reuse rationale, rejected source-layout dependencies, selected visual type, precision requirement and generation constraints.

A source visual may be reused only for a semantic reason. Table/Matrix and `NO_VALID_VISUAL` remain valid. Do not choose a weaker medical visual because a generator is easier to use.

### W12｜Generation Routing

W12 has two distinct responsibilities:

**W12-A Abstract routing:** decompose each W11-approved visual into minimum necessary generation components and derive the legal route classes/capability requirements without naming an unqualified concrete engine.

**W12-B Effective engine binding:** bind those route classes to exact engine/renderer/compositor/verifier versions only after W12-RQ qualification passes.

Resolve components using qualified routes such as `DETERMINISTIC_CHART`, `DETERMINISTIC_DIAGRAM`, `EXACT_CONTENT_COMPOSITOR`, `VERIFIED_MEDICAL_ASSET_RENDERER`, `PROMPT_DRIVEN_IMAGE`, `HYBRID_COMPOSITION`. Router cannot change selected Visual Type or medical semantics.

W12-A may PASS while W12-B remains BLOCKED. In that state W10/W11 do not need to be repeated unless upstream semantics change.

### W12-RQ｜Runtime Qualification & Portability

Mandatory active contract: `PORTABLE_RUNTIME_CAPABILITY_CONTRACT_v0.1.md`.

This is a W12 sub-gate, not a new frozen workflow stage.

#### Trigger

Enter Runtime Qualification Mode when:
- `RuntimeCapabilityProfile` is missing;
- a required capability has no qualified record;
- an engine/model/renderer/compositor/verifier version materially changes;
- a relevant CapabilityRecord is `STALE` or `UNQUALIFIED`;
- the Skill is moved to a new runtime/platform;
- W12 requires a route class absent from the current registry.

#### Required behavior

```text
IF RuntimeCapabilityProfile missing
→ RUN_QUALIFICATION

IF required capability lacks qualified evidence
→ RUN affected benchmark subset

IF engine/model/version materially changed
→ INVALIDATE affected CapabilityRecords
→ REQUALIFY affected subset

IF capability passes
→ issue version-bound CapabilityRecord

IF capability fails
→ mark NOT_QUALIFIED

IF no legal route remains
→ UNROUTABLE / HUMAN_REVIEW_REQUIRED
```

Runtime qualification must use `GENERATION_RUNTIME_QUALIFICATION_BENCHMARK_PACK_v0.1` or a later compatible pack.

The benchmark is capability-scoped rather than vendor-scoped. A runtime may qualify for `PROMPT_EDITORIAL_BASE` while remaining `NOT_QUALIFIED` for exact text or topology.

The baseline qualification domains are:
- deterministic diagram/topology;
- matrix/layout ownership and logic;
- exact content composition;
- verified medical asset rendering;
- prompt-driven non-semantic editorial base.

Every Hard-qualified capability must be bound to:
- exact engine/renderer/compositor/verifier version;
- benchmark fixture ids;
- observed results;
- verifier evidence;
- limitations;
- invalidation triggers.

Qualification must include adversarial/negative fixtures. A verifier that only accepts correct examples but cannot reject known corruptions is not qualified for that failure class.

For exact text/numeric/topology/logic/provenance, structured output manifests are the authoritative verification path whenever available. OCR/pixel reading is fallback/secondary only and cannot by itself approve RED exact content.

Material runtime changes invalidate affected runtime qualifications, not upstream medical semantics. Re-run the minimum affected benchmark subset unless contract dependencies changed.

### W13｜Visual Generation Contract / Prompt Compiler

W13 is forbidden until W12-B has at least one qualified, executable, verifiable route for every mandatory generation component.

Produce lock levels, Mandatory Content Object Register, Exact Text Register, Visual Semantic Contract, Layout Freedom Envelope, Visual Hierarchy Contract, Medical Visual Asset Contract, Prohibited Transformations and Post-generation Verification Contract. Prompt is a compiled execution artifact, not the source of truth.

### W14｜Page Generation / Controlled Composition

Default authoritative route for RED, high-precision, semantically dense, or engine-noncompliant pages:

```text
Prompt-driven Editorial Base
→ Deterministic Semantic Diagram
→ Deterministic Data Geometry
→ Exact Content Overlay
→ Source/Citation Overlay
→ Flatten
```

Protected Semantic Layers must not be generatively repainted, internally relaid out, geometrically warped, relabeled, semantically cropped or overwritten.

### W15｜Post-generation Visual Audit

Audit against the same contract and separately evaluate `PageGoalFidelity`, `PrimaryMessageFidelity`, Evidence Fidelity, mandatory object coverage, exact text/numeric fidelity, relationship fidelity, visual-semantic fidelity, protected topology, unauthorized source expansion, labels/axes/legends, citations, crop/occlusion/warp and protected-layer integrity.

Use the runtime-qualified verifier registry. For RED pages, every locked obligation needs an AUTHORITATIVE structured verifier where the renderer/compositor emits a manifest, plus rendered-asset visual review and W16 human review.

`LayoutSimilarity` may be recorded for analysis but is never an approval criterion. A page may look very different from the source and PASS; a near-identical redraw can FAIL if PageGoal or PrimaryMessage fidelity fails.

### W16｜Human Review

Required for RED content, high-risk synthesis, contested interpretation, unresolved source conflict, uncertain extraction affecting meaning and final visual-QA exceptions. Human override is logged separately and does not erase issue history.

### W17–W18｜Delivery and benchmark

Deliver only approved/current artifacts. Record benchmark metrics, source-coverage audit, context profile, Narrative/PageSpec derivation, visual rationale, runtime qualification, corrections and lessons even for failed runs.

## 6. Non-negotiable blocking conditions

Do not advance when unresolved:
- full source has not been traversed/registered;
- W02-FSC is not PASS/PASS_WITH_WARNINGS before W05;
- a substantive source section is silently omitted;
- a narrative-changing source omission is unresolved;
- SOURCE Claim lacks SourceRef;
- NumericFact lacks exact source binding;
- RED threshold/dose/recommendation/evidence level is unverified;
- context-specific threshold or recommendation ownership was merged incorrectly;
- relationship direction is unsupported;
- direct comparison lacks comparability clearance;
- corrupted layout-dependent evidence was not visually checked;
- context facets are conflated or authoritative scope mutated;
- Narrative has not passed W06-NR;
- Page Allocation has not passed W06-NP;
- PageSpec was mechanically derived from source layout/page/table/figure rather than approved Narrative/Triage semantics;
- source topology is treated as authoritative without semantic justification;
- a meaning-critical source topology is discarded or altered without approval;
- a concrete engine capability is inferred from model/vendor name instead of qualification evidence;
- required runtime qualification is missing, stale or incompatible;
- exact text cannot be rendered/verified;
- route lacks executable verification;
- a meaning-bearing medical asset lacks a valid asset contract;
- Protected Semantic Layer would be repainted;
- required RED human review is missing.

## 7. Provenance and risk

Provenance:
- `SOURCE`: directly supported;
- `SUMMARY`: faithful compression;
- `SYNTHESIS`: multi-source/model organization; high-risk synthesis requires review;
- `EXTERNAL_VERIFICATION`: external evidence kept separate from source facts.

Risk:
- `GREEN`: background/repetition/low-risk descriptive content;
- `YELLOW`: mechanism/research summaries/moderate semantic risk;
- `RED`: diagnostic thresholds, dose, contraindication, special populations, recommendation/evidence grade, indication/exclusion/timing, treatment/diagnostic relation and decision-critical medical content.

YELLOW alone never authorizes semantic expansion or FULL_IMAGE.

## 8. Mandatory regression rules

### Full-source evidence coverage
- `REG-FSC-001` through `REG-FSC-010`: follow `FULL_SOURCE_EVIDENCE_COVERAGE_POLICY_v0.1.md`.

### Context matching
- `REG-CTX-001` through `REG-CTX-013`: follow `PRESENTATION_CONTEXT_MATCHING_POLICY_v0.2.md`.

### Narrative rationality
- `REG-NARR-001` through `REG-NARR-013`: follow `NARRATIVE_RATIONALITY_AUDIT_POLICY_v0.1.md`.

### Narrative-to-page decomposition
- `REG-DECOMP-001` through `REG-DECOMP-012`: follow `NARRATIVE_TO_PAGE_DECOMPOSITION_AUDIT_POLICY_v0.1.md`.

### PageSpec derivation
- `REG-PAGE-001`: PageSpec derives from full approved evidence + Triage + Context + Approved Narrative + Approved Page Allocation, never directly from source layout/page boundaries.
- `REG-PAGE-002`: Source table/figure/chapter does not automatically create a presentation page.
- `REG-PAGE-003`: PrimaryMessage may be SUMMARY/SYNTHESIS when fully supported; source verbatim wording is not required.
- `REG-PAGE-004`: PageSpec declares `source_structure_dependency` and `page_derivation_mode`.
- `REG-PAGE-005`: Source Fidelity and Layout Fidelity are separate; layout similarity is not an approval criterion.

### Visual Strategy derivation
- `REG-VSTRAT-001`: Visual Strategy is selected from PageSpec information structure, not source visual form.
- `REG-VSTRAT-002`: Preserve source topology only when topology itself carries approved meaning.
- `REG-VSTRAT-003`: When source visual structure is not authoritative, extract evidence and re-synthesize the presentation visual.
- `REG-VSTRAT-004`: `SOURCE_RECONSTRUCTION`, `SOURCE_SYNTHESIS`, `NARRATIVE_SYNTHESIS` are first-class derivation modes.
- `REG-VSTRAT-005`: Any source visual reuse requires a semantic rationale and provenance binding.
- `REG-VSTRAT-006`: A visually accurate source reconstruction that misses approved PageGoal/PrimaryMessage is FAIL.
- `REG-VSTRAT-007`: A synthesis visual may differ radically from source layout and still PASS when semantics, precision and PageGoal fidelity pass.

### Runtime qualification / portability
- `REG-RUNTIME-001`: Missing RuntimeCapabilityProfile blocks W12-B but does not invalidate W10/W11.
- `REG-RUNTIME-002`: Vendor/model name is never Hard Capability Evidence.
- `REG-RUNTIME-003`: Every Hard-qualified capability is engine/version/benchmark bound.
- `REG-RUNTIME-004`: Material engine/model/renderer/compositor/verifier change marks affected CapabilityRecords STALE.
- `REG-RUNTIME-005`: Requalification may be incremental only when the affected capability boundary is explicit and dependencies are unchanged.
- `REG-RUNTIME-006`: Qualification includes negative/adversarial fixtures and must reject known corruptions.
- `REG-RUNTIME-007`: Exact text/numeric/topology/logic/provenance approval is manifest-first when machine-readable outputs exist; OCR alone cannot approve RED exact content.
- `REG-RUNTIME-008`: A capability PASS never grants untested adjacent capabilities; e.g. Editorial Base PASS does not authorize exact text or topology.
- `REG-RUNTIME-009`: If no qualified legal route remains, return `UNROUTABLE / HUMAN_REVIEW_REQUIRED`; do not degrade semantics.
- `REG-RUNTIME-010`: Runtime qualification artifacts are auditable/persistent and travel with the portable Skill package or target-environment profile.

### Test 001 source/generation
- `REG-PDF-001`: corrupted/garbled flowchart text requires rendered-page inspection.
- `REG-NUM-001`: CFR/IMR/FFR and similar thresholds preserve operator, value, unit and context.
- `REG-REC-001`: recommendation class/evidence level remain bound to the correct row.
- `REG-VIS-001`: RED decision pages use protected topology/exact-text layers.
- `REG-ROLE-001`: role adaptation changes depth/selection/order only, not facts.
- `REG-GEN-001`: one PageSpec produces one page image.
- `REG-GEN-002`: cover pages may not be enriched with unrequested medical facts.
- `REG-GEN-003`: image generation may not invent exact medical numeric labels.
- `REG-GEN-004`: source edition and publication year are separate; `2023版` must not become `2024版`.
- `REG-GEN-005`: YELLOW does not permit semantic expansion.
- `REG-GEN-006`: repeated PageSpec fidelity failure triggers capability downgrade for authoritative rendering.
- `REG-GEN-007`: YELLOW alone is insufficient for FULL_IMAGE.
- `REG-GEN-008`: semantic density/exact-object count participate in FULL_IMAGE eligibility.
- `REG-GEN-009`: a noncompliant engine may provide nonsemantic art direction/background, not authoritative content rendering.

## 9. Failure/revision loop

When a stage fails: record an Issue; route it to earliest responsible stage; create a new immutable revision; mark dependent downstream objects stale; rerun required upstream extraction/audit/verification; rerun downstream regression tests only after the responsible stage passes. Deleting a visible symptom does not resolve the root issue.

If the failure is a narrative-changing source omission, the earliest responsible stage is W02 and W05+ must be rebuilt.

If the failure is runtime qualification only, invalidate/requalify the affected CapabilityRecord and rerun W12-B/W13+ as necessary; do not rebuild W02–W11 unless medical semantics changed.

## 10. Standard run artifacts v0.4.0

```text
runs/<test_id>/
├─ 00_run_record.md
├─ 00_source_manifest.json
├─ 01_page_extraction/
├─ 02_evidence/
│  ├─ full_source_coverage_manifest.json
│  ├─ section_inventory.json
│  ├─ claims.json
│  ├─ numeric_facts.json
│  ├─ recommendation_facts.json
│  ├─ table_figure_registry.json
│  └─ full_source_coverage_audit.json
├─ 03_evidence_verification.json
├─ 04_presentation_context_profile.json
├─ 04_adaptation_contract.json
├─ 04_context_integrity_check.json
├─ 05_triage.json
├─ 06_narrative_draft.json
├─ 06_narrative_rationality_audit.json
├─ 06_approved_narrative_architecture.json
├─ 06_page_allocation_audit.json
├─ 06_approved_page_allocation_plan.json
├─ 07_page_specs.json
├─ 07_pagespec_derivation_audit.json
├─ 08_semantic_bindings.json
├─ 09_audit.json
├─ 10_approved_semantic_page_graph.json
├─ 11_visual_strategy.json
├─ 11_visual_strategy_derivation_audit.json
├─ 12_generation_routes.json
├─ 12_runtime_qualification/
│  ├─ runtime_capability_profile.json
│  ├─ generation_capability_registry.json
│  ├─ verifier_capability_registry.json
│  ├─ data_egress_policy.json
│  ├─ asset_contracts/
│  ├─ qualification_results.json
│  └─ capability_records.json
├─ 13_visual_generation_contracts/
├─ 13_prompts/
├─ 14_generated_pages/
├─ 15_visual_qa/
├─ 16_human_review/
├─ 17_delivery/
└─ 18_benchmark.json
```

Portable Skill package additionally carries:

```text
runtime_benchmarks/
├─ GENERATION_RUNTIME_QUALIFICATION_BENCHMARK_PACK_v0.1.md
└─ GENERATION_RUNTIME_QUALIFICATION_FIXTURES_v0.1.json
```

## 11. Final disposition

Exactly one: `APPROVED_REFERENCE_OUTPUT`, `PARTIAL_WITH_BLOCKERS`, or `FAILED_REFERENCE_RUN`. Never approve while a mandatory gate remains unresolved.

## 12. Canonical references

- `docs/specs/01_PRD.md`
- `docs/specs/02_ARCHITECTURE.md`
- `docs/specs/03_DATA_SCHEMA.md`
- `docs/specs/04_QUALITY_AND_COMPLIANCE.md`
- `docs/specs/05_MVP_TEST_PLAN.md`
- `docs/specs/FROZEN_SPEC_MANIFEST.json`
- `docs/workflows/REFERENCE_PIPELINE_WORKFLOW_v0.1.md`
- `docs/workflows/REFERENCE_PIPELINE_CHECKLIST_v0.1.md`
- `docs/workflows/FULL_SOURCE_EVIDENCE_COVERAGE_POLICY_v0.1.md`
- `docs/workflows/REFERENCE_PIPELINE_FULL_SOURCE_COVERAGE_CHECKLIST_v0.1.md`
- `docs/workflows/PRESENTATION_CONTEXT_MATCHING_POLICY_v0.2.md`
- `docs/workflows/NARRATIVE_RATIONALITY_AUDIT_POLICY_v0.1.md`
- `docs/workflows/NARRATIVE_TO_PAGE_DECOMPOSITION_AUDIT_POLICY_v0.1.md`
- `docs/workflows/PAGESPEC_VISUAL_STRATEGY_DERIVATION_POLICY_v0.1.md`
- `docs/workflows/REFERENCE_PIPELINE_RUN_RECORD_TEMPLATE_v0.1.md`
- `docs/workflows/runs/REFERENCE_PIPELINE_TEST_001_CMVD.md`
- `skills/auditable-medical-presentation-reference/contracts/STAGE_OUTPUT_CONTRACTS_v0.3.md`
- `skills/auditable-medical-presentation-reference/contracts/PORTABLE_RUNTIME_CAPABILITY_CONTRACT_v0.1.md`
- `skills/auditable-medical-presentation-reference/SKILL_RUNTIME_PORTABILITY_MANIFEST_v0.1.json`
- `skills/auditable-medical-presentation-reference/schemas/presentation_context_profile.v0.2.schema.json`
- `skills/auditable-medical-presentation-reference/schemas/runtime_capability_profile.v0.1.schema.json`
- `skills/auditable-medical-presentation-reference/schemas/post_generation_verifier_capability_registry.v0.1.schema.json`
- `skills/auditable-medical-presentation-reference/schemas/medical_visual_asset_contract.v0.1.schema.json`
- `skills/auditable-medical-presentation-reference/schemas/runtime_qualification_result.v0.1.schema.json`
- `skills/auditable-medical-presentation-reference/runtime_benchmarks/GENERATION_RUNTIME_QUALIFICATION_BENCHMARK_PACK_v0.1.md`
- `skills/auditable-medical-presentation-reference/runtime_benchmarks/GENERATION_RUNTIME_QUALIFICATION_FIXTURES_v0.1.json`
- `skills/auditable-medical-presentation-reference/references/FROZEN_RULES_COMPILATION.md`
- `skills/auditable-medical-presentation-reference/references/TEST_001_CMVD_LESSONS.md`
