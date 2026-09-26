# Semantic & Narrative Audit Protocol v0.1

**Status:** `DRAFT_SKILL_POLICY_CANDIDATE`  
**Purpose:** Audit the model-generated summary, NarrativePlan and PageSpec before any visual-generation decision is treated as current.

## 1. Principle

The pipeline must prove that the presentation semantics are correct before proving that the visual rendering is attractive.

```text
Evidence Layer
→ Triage
→ NarrativePlan
→ PageSpec
→ SEMANTIC / NARRATIVE AUDIT GATE
→ Semantic Binding / Visual Strategy
```

The audit is not a source-TOC similarity check. It tests whether the transformed presentation is source-faithful, logically useful, context-appropriate and reversible to approved evidence.

## 2. Audit dimensions

### A. Source-Semantic Fidelity
Check every PrimaryMessage and narrative transition for:
- source support;
- correct population/scope;
- conditions/exclusions;
- exact numeric operators/units;
- recommendation class/evidence level;
- modality/certainty;
- no unsupported causal or temporal strengthening.

### B. Summary Fidelity
For every SUMMARY object verify:
- no meaning-critical qualifier removed;
- no multiple source facts collapsed into a broader proposition;
- no diagnostic/treatment threshold generalized across contexts;
- reversibility to source Claim/NumericFact IDs.

### C. Synthesis Validity
For every SYNTHESIS object verify:
- all component claims are approved;
- the synthesis is necessary for the Presentation Question;
- it does not introduce unsupported causality, priority, sequence, superiority or universality;
- RED synthesis is explicitly review-required.

### D. Narrative Coherence
Check:
- Narrative answers the Presentation Question rather than source TOC;
- every section/page has a reason to exist;
- cognitive prerequisites appear before dependent decisions;
- no critical clinical context is silently dropped;
- no duplicate pages expressing the same message;
- the end state answers the opening question.

### E. PageSpec Integrity
Each PageSpec must have:
- unique PageGoal;
- exactly one PrimaryMessage;
- explicit provenance (`SOURCE|SUMMARY|SYNTHESIS`);
- supporting claim IDs;
- required numeric/relationship IDs where applicable;
- caveats/conditions;
- risk;
- page derivation mode and source-structure dependency;
- no source-layout dependency without semantic rationale.

### F. Context / Audience Fit
Audit selection, order, explanatory depth, evidence density, numeric density, recommendation visibility, visual complexity and appendix allocation against the active AdaptationContract.

Audience adaptation may omit or relocate details but may not mutate evidence.

## 3. Controlled differentiation test

Do not evaluate audience adaptation from job-title stereotypes.

Run at least two kinds of benchmark:

### Audience-isolation benchmark
Keep constant:
- source;
- Presentation Question;
- duration;
- scenario;
- language.

Change only explicit Audience facets such as baseline knowledge, evidence literacy, information need and decision responsibility.

Expected differences may include:
- background explanation;
- terminology expansion;
- evidence density;
- numeric density;
- recommendation visibility;
- narrative sequence;
- appendix allocation.

Authoritative Claim/NumericFact/Relationship IDs remain invariant.

### Duration-isolation benchmark
Keep audience/context fixed and vary duration (e.g. 10/20/45 min).

Expected difference: selection/allocation and number of pages, not medical truth.

## 4. Audit outcomes

For each Narrative/PageSpec object:
- `PASS`;
- `PASS_WITH_WARNINGS`;
- `REVISE_SUMMARY`;
- `REVISE_NARRATIVE`;
- `REVISE_PAGESPEC`;
- `NEEDS_HUMAN_REVIEW`;
- `BLOCK`.

A downstream visual artifact becomes stale when its upstream PageSpec is revised.

## 5. Required issue classes

- `SEM_SCOPE_EXPANSION`
- `SEM_SCOPE_NARROWING`
- `SEM_OPERATOR_MUTATION`
- `SEM_UNSUPPORTED_SEQUENCE`
- `SEM_UNSUPPORTED_CAUSALITY`
- `SEM_UNSUPPORTED_SUPERIORITY`
- `NARRATIVE_COVERAGE_GAP`
- `NARRATIVE_REDUNDANCY`
- `NARRATIVE_QUESTION_MISMATCH`
- `AUDIENCE_ADAPTATION_UNEXPLAINED`
- `AUDIENCE_FACT_MUTATION`
- `PAGESPEC_SOURCE_LAYOUT_LEAKAGE`

## 6. Proposed regression rules

- `REG-NARR-001`: Narrative must answer the Presentation Question, not reproduce the source TOC.
- `REG-NARR-002`: Every narrative transition that implies sequence/causality/priority must be source-supported or explicitly SYNTHESIS.
- `REG-NARR-003`: A main-deck omission that materially changes the apparent scope must be explicit or compensated by a scope statement/appendix pointer.
- `REG-AUD-001`: Audience differences must be traceable to explicit context facets, not job-title stereotypes.
- `REG-AUD-002`: Controlled audience comparison should vary audience facets while holding source/question/duration/scenario constant.
- `REG-AUD-003`: Same evidence reused across audiences preserves authoritative object IDs and exact medical truth.
- `REG-PAGE-006`: A PageSpec with a materially unsupported PrimaryMessage cannot proceed to Visual Strategy even if supporting source material is broadly related.

These are draft policy candidates and do not alter frozen Module 01–06 rules until explicitly approved/frozen.
