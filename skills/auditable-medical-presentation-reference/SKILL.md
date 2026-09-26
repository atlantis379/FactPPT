---
name: auditable-medical-presentation-reference
description: Structure medical sources into auditable presentation evidence, narrative and visual contracts; validate source-bound semantics, exact data and P05-style editable evidence with portable local checks. Use for source-faithful medical presentation work and its Skill validation, not patient-specific advice.
---

# Auditable Medical Presentation Reference Skill v0.9.0

## Purpose and scope

This is the SKILL stage of SKILL → AGENT → online website. It supplies portable instructions, contracts and local checks; it does not require an Agent service or website. Construct rules from the general semantic/visual/quality model before testing a sample. P05 is a regression fixture, not a universal composition. Preserve source facts, qualifiers, recommendation strength, numeric context and logical ownership while adapting the presentation to audience and purpose.

Semantic interpretation is model-assisted. Exact integrity is checked by code. Final RED clinical decisions remain human-reviewed. No vendor name, model-written PASS or old runtime qualification grants a current capability.

Explicit user scope and authorization are preserved. Frozen source rules remain the project evidence baseline; the active v0.5 contract governs prototype exploration, executable validation and dual-artifact delivery. Do not silently weaken a safety gate or turn a reference example into a universal medical rule. This release does not change the 178 frozen rules or W00–W18 numbers.

## Read only what the task needs

- Always read [general quality system](contracts/QUALITY_SYSTEM_v0.5.md) before selecting layouts or defining acceptance, then [integrity and quality](contracts/INTEGRITY_AND_QUALITY_v0.5.md) for execution, validation or prototype work.
- Source/evidence work: [frozen rules compilation](references/FROZEN_RULES_COMPILATION.md) and bundled [quality requirements](references/project/docs/specs/04_QUALITY_AND_COMPLIANCE.md).
- **Reading → structure → narrative → allocation (W01-R, mandatory before W02):** [policy](references/project/docs/workflows/SOURCE_READING_TO_NARRATIVE_DERIVATION_POLICY_v0.2.md), [checklist](references/project/docs/workflows/REFERENCE_PIPELINE_READING_AUDIT_CHECKLIST_v0.2.md), schema `schemas/reading_structure_artifact.v0.2.schema.json`, **[rule compilation](references/project/docs/workflows/W01R_RULE_COMPILATION_v1.0.md)** (all 17 rules, the nine checks, the four corrected gate defects, the verification record). The model reads the full extracted text, derives the structure, orders the narrative and allocates pages; code verifies that this happened and that it is traceable. Heading-marker or page splitting may inventory the material but never constitutes the structure. **The method is material-agnostic**: language, domain roles and marker lexicons are declared per run in `profile`. No page may be designed before acceptance.
- Source intake, cross-page structure or delivery privacy: [page privacy and document surface gate](contracts/PAGE_PRIVACY_AND_DOCUMENT_SURFACE_GATE_v0.1.md).
- Independent truth review, corrections or amended sources: [fact oracle and version-chain contract](contracts/INDEPENDENT_FACT_ORACLE_AND_VERSION_CHAIN_v0.1.md).
- Case reports/case series: [case-report evidence boundary](references/CASE_REPORT_EVIDENCE_BOUNDARY_v0.1.md).
- Full pipeline: [workflow](references/project/docs/workflows/REFERENCE_PIPELINE_WORKFLOW_v0.1.md), [checklist](references/project/docs/workflows/REFERENCE_PIPELINE_CHECKLIST_v0.1.md), [stage contracts](contracts/STAGE_OUTPUT_CONTRACTS_v0.3.md).
- Coverage: [full-source policy](references/project/docs/workflows/FULL_SOURCE_EVIDENCE_COVERAGE_POLICY_v0.1.md).
- Adaptation: [context policy](references/project/docs/workflows/PRESENTATION_CONTEXT_MATCHING_POLICY_v0.2.md).
- Narrative/page boundaries: [narrative](references/project/docs/workflows/NARRATIVE_RATIONALITY_AUDIT_POLICY_v0.1.md), [decomposition](references/project/docs/workflows/NARRATIVE_TO_PAGE_DECOMPOSITION_AUDIT_POLICY_v0.1.md).
- Visuals: [derivation](references/project/docs/workflows/PAGESPEC_VISUAL_STRATEGY_DERIVATION_POLICY_v0.1.md), [AI editorial-base and source-data fusion](contracts/AI_EDITORIAL_DATA_FUSION_v0.2.md) when a generated background is selected, [client template intake](contracts/CLIENT_TEMPLATE_INTAKE_v0.1.md) when a company or hospital template is selected, [runtime contract](contracts/PORTABLE_RUNTIME_CAPABILITY_CONTRACT_v0.1.md).
- Native editable page beautification: [MVP contract](contracts/NATIVE_EDITABLE_BEAUTIFICATION_MVP_v0.1.md) and `schemas/native_beautification_plan.v0.1.schema.json`.
- ChatGPT Image underlays: [provider boundary and hash-bound intake](contracts/CHATGPT_IMAGE_EDITORIAL_UNDERLAY_v0.1.md); read only when a generated non-semantic background is requested or supplied.

All required project rules are bundled under `references/project/docs`. Legacy v0.4 instructions and runtime profiles are historical context only. `SKILL_MANIFEST.json` selects the active version; do not merge versioned registries heuristically.

## Inputs and modes

Record source files/hash/version, presenter, audience, subject scope, scenario, presentation question, goal, duration, language, external research permission and synthetic-case permission. Ask only for missing context that materially affects the task. External research and synthetic cases default off. Audience adaptation may change explanation, selection and order, never source truth.

Use `DELIVERY` for authoritative output. Use `DESIGN_PROTOTYPE` for locked-content layout experiments after W10/W11, including P05 Skill validation. A prototype can proceed while runtime qualification is pending, but must retain NOT_FOR_DELIVERY status and cannot enter W17. Record missing upstream evidence as unknown/stale rather than fabricating a full-run PASS.

## Execution order and gates

W00 register/intake source → W01 extract/document structure → W02 full evidence → W02-FSC independent-oracle coverage → W03 verify → W04 context → W05 triage → W06 narrative → W06-NR narrative/case-boundary audit → W06-NP page allocation → W07 PageSpec → W08 semantic bindings → W09 audit → W10 approved graph → W11 visual strategy → W12-A abstract route → W12-RQ qualification → W12-B effective binding → W13 contract → W14 generation → W15 separate quality + page-privacy results → W16 human review → W17 delivery → W18 benchmark.

- W00/W01: immutable identity and actual page count. Reject download/status, MIME, magic-byte, size or hash mismatch before parsing. Record explicit correction/amendment edges and claim-level effective facts. Register cross-page tables, footnotes, OCR/render routing, DICOM metadata/pixel inspections and every unreadable page.
- W02/FSC: traverse all pages/sections before relevance filtering. Capture all RED conditions, operators, units, exclusions, recommendation/evidence levels and relationship ownership. Source quote and normalized claim are separate. Coverage PASS requires a distinct reviewer/run, page-complete oracle and resolved disagreements; otherwise the denominator is UNKNOWN/PARTIAL.
- W03: verify numeric values, source location, negation, scope, timing, statistical type and recommendation ownership. SOURCE needs a source reference; SUMMARY must be faithful; SYNTHESIS is labeled and high-risk synthesis requires review. External evidence stays isolated.
- W04/W05: preserve meaning bundles and full evidence even when excluded from main slides. Revalidate source scope after coverage. Do not infer expertise solely from job title.
- W06/NR/NP: answer the presentation question with approved evidence; audit entailment, scope, transitions, uncertainty, audience, duration and closure. A case report directly supports only case-scoped observations; population, efficacy, causality, diagnostic-sufficiency or recommendation upgrades require labeled SYNTHESIS, external support and human approval. Page boundaries follow cognitive purpose, not source page/table order or an arbitrary count.
- W07/W08: one PageGoal and PrimaryMessage per page, approved support IDs, explicit logic and context. Record `source_structure_dependency` and `page_derivation_mode`. Adjacency/color/order must not invent causality, superiority or AND/OR relations.
- W09/W10: unresolved critical numeric, scope, comparison, relationship or RED issues block authority. Only current approved object versions enter the semantic graph.
- W11: derive visual grammar from page purpose and approved information structure. Preserve source topology only where it carries meaning. A verified table or text-forward page is a valid fallback.
- W12: abstract route is separate from actual engine qualification. Preflight detects dependencies; executed positive/negative evidence grants only tested, version-bound capabilities. Statistical geometry has an explicit simple-SVG validator and calibration fixtures; other formats/engines require their own qualification.
- W13/W14: compile locked content, display transformations, safe regions, scene ownership and prohibited changes. For the native beautification route, evaluate five deterministic archetypes, retain candidate scores/rejections, validate the BeautificationPlan, then create named editable objects. Preserve native editable evidence and a separate review render. Select one visual base: a hash-bound AI editorial base or a client-supplied company/hospital template. ChatGPT Image/Figma may fill only declared non-semantic asset slots; claims, numbers, labels, sources and relationship connectors remain native. A generative background or contextual illustration is only used through a hash-bound editorial asset contract; medical meaning remains source-bound. A client template is recorded through its own hash-bound intake contract and preserved brand regions. When an AI editorial base is selected, compile an editorial fusion plan that binds its prompt provenance, source-owned native layers, palette, content zone, protected visible-background zone, translucent/open surface policy and final render review. Reject the mechanical `full-frame bitmap + opaque generic white panels` pattern. Check all higher layers against protected content. Never allow a generative repaint of protected semantics.
- W15: source/semantic, numeric/logic, composition, rendered review and privacy have separate results. Inspect every final page across text, notes, embedded-image OCR, DICOM metadata/pixels, faces/marks, document metadata and filenames. `NOT_TESTABLE` is not clearance. Residual and cross-page consistency scans bind the final artifact hash.
- W16/W17: clinical and design decisions are separate. RED human approval binds the current artifact hash and reviewer. Prototypes, stale objects and unresolved gates cannot become approved delivery.
- W18: retain failures, revisions, evidence hashes, benchmark scope and limitations; do not rewrite history as PASS.

## Run local checks

Use Python 3.11+ in an isolated environment with `requirements-validation.txt` (tested pins). Fonts are explicitly provided and not redistributed. Change directory to the extracted Skill root before using the commands below, or invoke each script by its absolute path. Evidence references resolve within the explicit evidence root.

```text
python scripts/skill_tool.py preflight --font PATH_TO_FONT
python scripts/skill_tool.py source-intake SOURCE_INTAKE.json --root EVIDENCE_ROOT
python scripts/skill_tool.py fact-oracle FACT_ORACLE_REVIEW.json
python scripts/skill_tool.py source-chain SOURCE_VERSION_CHAIN.json
python scripts/skill_tool.py case-boundary CASE_BOUNDARY_REVIEW.json
python scripts/skill_tool.py document-structure DOCUMENT_STRUCTURE.json
python scripts/skill_tool.py privacy-gate PRIVACY_SURFACE_AUDIT.json
python scripts/skill_tool.py beautification-plan BEAUTIFICATION_PLAN.json --deck APPROVED_SEMANTIC_DECK.json
python scripts/skill_tool.py chatgpt-image-asset CHATGPT_IMAGE_ASSET.json --root WORKSPACE_ROOT
python scripts/run_medical_gate_benchmarks.py --out NEW_MEDICAL_GATE_EVIDENCE_DIRECTORY
python scripts/run_benchmarks.py --out NEW_EVIDENCE_DIRECTORY --font PATH_TO_CJK_FONT --symbol-font PATH_TO_SYMBOL_FONT
python scripts/run_quality_benchmarks.py --out NEW_GENERAL_QUALITY_EVIDENCE_DIRECTORY
python scripts/evaluate_quality.py pptx --contract PAGE_CONTEXT.json --artifact FINAL.pptx --fonts FONTS.json --render-evidence FINAL_RENDER_REVIEW.json --out NEW_PPTX_QUALITY.json
python scripts/evaluate_quality.py editorial-asset --contract EDITORIAL_ASSET.json --artifact ASSET.png --out NEW_EDITORIAL_ASSET_QUALITY.json
python scripts/evaluate_quality.py editorial-fusion --plan FUSION_PLAN.json --scene SCENE.json --out NEW_EDITORIAL_FUSION_QUALITY.json
python scripts/evaluate_quality.py client-template --contract CLIENT_TEMPLATE.json --artifact TEMPLATE_OR_BACKGROUND --out NEW_CLIENT_TEMPLATE_QUALITY.json
python scripts/skill_tool.py state RUN_STATE.json
python scripts/skill_tool.py qualification QUALIFICATION.json --root EVIDENCE_DIRECTORY
python scripts/skill_tool.py quality-evaluation QUALITY_EVALUATION.json --root EVIDENCE_DIRECTORY
python scripts/skill_tool.py package NEW_PACKAGE.zip
python scripts/skill_tool.py verify-package EXTRACTED_PACKAGE_DIRECTORY
```

The active state schema is `schemas/run_state.schema.json` (schema 0.5.0 / skill v0.5.0); qualification uses `schemas/runtime_qualification_result.v0.2.schema.json`. CLI runs schema plus cross-reference checks. Exact clinical output uses `scripts/integrity.py` plus final-format extraction. Renderer self-report alone is insufficient.

P05-style factoring uses `factor_and`/`validate_factoring`: exact per-bundle identities and complete semantic objects, not just 3+4=7 counts. For an existing P05 content contract, first run `python scripts/p05_adapter.py --content CONTENT.json --w10 W10.json --out NEW_DIRECTORY`; do not pass the raw phenotypes format directly to `factor_and`. OR/NOT/EXCEPT factoring is unsupported until qualified. Formatting mappings must be explicit and source-bound. A symbol font is explicitly bound to Unicode unit objects because not all CJK fonts include superscript minus; this is not implicit fallback.

## Failure and disposition

Record issue, responsible stage, affected object/version, evidence and remediation. Create a new revision, invalidate only its dependent scope, and rerun affected checks. A narrative-changing omission returns to W02 and rebuilds W05+. Runtime changes requalify affected W12+ without automatically changing W00–W11 semantics. Stop repeated failed repair according to the run's retry budget; retain unresolved status.

Final disposition is exactly `APPROVED_REFERENCE_OUTPUT`, `PARTIAL_WITH_BLOCKERS` or `FAILED_REFERENCE_RUN`. For P05 prototype validation, report component check results and limits; do not claim full-source extraction or final clinical approval was performed.
