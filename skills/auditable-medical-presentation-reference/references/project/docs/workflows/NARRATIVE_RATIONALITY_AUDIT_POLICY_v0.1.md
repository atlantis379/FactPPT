# Narrative Rationality Audit Policy v0.1

**Status:** `ACTIVE_SKILL_POLICY_NOT_FROZEN_SPEC`

## 1. Purpose

Insert a mandatory narrative-quality gate after Narrative Draft generation and before PageSpec construction. The goal is to verify that the presentation story itself is reasonable, source-grounded, context-appropriate and proportionate before any page decomposition or visual design begins.

This policy does not change the frozen Module 01–06 rule counts or the frozen W00–W18 numbering. It operationalizes a mandatory **W06 Narrative Rationality sub-gate** inside the existing W06→W07 boundary.

Core principle:

> **Correct evidence does not guarantee a correct presentation narrative.**
>
> **Narrative must be approved before it is decomposed into pages.**

## 2. Required execution order

Within the frozen workflow, execute:

```text
W05 Information Triage
→ W06 Narrative Draft
→ W06-NR Narrative Rationality Audit
→ Approved Narrative Architecture
→ W07 PageSpec Construction
```

W07 MUST NOT start from an unaudited Narrative Draft.

Existing S01/S02/... candidates created before W06-NR approval are `CANDIDATE_PAGE_DECOMPOSITION`, not approved PageSpecs.

## 3. Narrative object model

W06 must distinguish:

```text
NarrativeDraft
        ↓ audit
ApprovedNarrativeArchitecture
```

Recommended `ApprovedNarrativeArchitecture` fields:

- `presentation_question`
- `narrative_thesis`
- `scope_contract`
- `audience_context_ref`
- `duration_constraint`
- `narrative_sections[]`
- `deep_dive_exemplars[]`
- `main_deck_priority_map`
- `appendix_boundary`
- `narrative_risk_register[]`
- `audit_status`

Each `narrative_section` should record:

- `section_id`
- `section_role`
- `key_question`
- `key_answer`
- `evidence_dependencies[]`
- `provenance`: `SOURCE | SUMMARY | SYNTHESIS`
- `scope`
- `audience_rationale`
- `duration_rationale`
- `transition_from_previous`
- `transition_to_next`
- `clinical_relationship_claimed`: boolean
- `risk_level`

## 4. Narrative Rationality Audit dimensions

Audit every draft across all dimensions below.

### 4.1 Presentation Question Coverage
Does the Narrative actually answer every material component of the explicit Presentation Question?

Detect:
- promised but unaddressed concepts;
- sections that do not contribute to the question;
- an answer that silently narrows or broadens the question.

### 4.2 Source Support / Evidence Grounding
Every substantive narrative assertion must be traceable to approved evidence or explicitly marked SUMMARY/SYNTHESIS.

Narrative transitions are not automatically medical causality, chronology, priority or treatment sequence.

### 4.3 Clinical / Domain Logic
The order must reflect a defensible reasoning sequence for the task and audience, not merely source order.

Examples of candidate reasoning grammars include:
- recognition → framing → testing → interpretation → action;
- question → evidence → implication;
- problem → mechanism → intervention;
- study question → design → result → limitation → meaning.

No grammar is universal; choose according to context.

### 4.4 Scope Coherence
The scope introduced at the beginning must match what the Narrative actually covers.

If the Narrative moves from a broad domain into a narrower deep dive, it MUST explicitly label that section as an exemplar/deep dive and later return to the broader scope or explain why it does not.

### 4.5 Priority and Evidence Balance
Narrative emphasis should reflect the Presentation Question, audience needs and task intent—not the amount of source text available for each topic.

Reject source-volume bias such as giving a large section more presentation time solely because the source contains more pages/tables on it.

### 4.6 Audience Fit
Narrative structure, entry point, terminology burden, evidence density and actionability must be traceable to explicit AudienceProfile / AdaptationContract facets.

Unknown audience facets remain UNKNOWN; do not infer sophistication from job title alone.

### 4.7 Duration Fit
The Narrative must be feasible within the requested duration.

Duration may change depth, number of sections, appendix allocation and exemplar detail, but must not mutate source truth.

### 4.8 Missing Links / Transition Quality
Every section must answer why it follows the previous section.

Detect:
- unexplained jumps in scope;
- tool-first sequencing before the clinical/question context is established when the task is clinical reasoning;
- a treatment section appearing before the diagnostic distinction on which it depends;
- missing bridge statements.

### 4.9 Redundancy and Compression
Two sections should not exist independently if they answer the same cognitive question without distinct value.

Conversely, one section should be split when it contains multiple incompatible cognitive tasks.

### 4.10 Narrative Overreach
Audit for narrative wording that adds unsupported:
- causality;
- mandatory sequence (`first...then...`);
- superiority;
- universality;
- diagnostic sufficiency;
- treatment dependence;
- recommendation strength;
- certainty;
- population expansion.

For case-report sources, direct SOURCE/SUMMARY authority is limited to the reported case/series observations and author-stated interpretation. Population-level efficacy, causality, diagnostic sufficiency or recommendation language requires `SYNTHESIS`, explicit external evidence binding and approved human medical review. Publication consent does not satisfy presentation privacy review.

### 4.11 Uncertainty Visibility
Where the source identifies conflict, limitation, evidence weakness or research gaps relevant to the task, the Narrative must not erase them.

### 4.12 Closure / Take-home Quality
The ending should close the Presentation Question. A research-gap section may be included, but a deck should not end merely because the source document ends there. Take-home statements may be SUMMARY/SYNTHESIS if fully evidence-bound.

## 5. Audit actions

For each narrative section choose one or more:

- `KEEP`
- `REWRITE`
- `MOVE_EARLIER`
- `MOVE_LATER`
- `MERGE`
- `SPLIT`
- `REMOVE_FROM_MAIN_NARRATIVE`
- `MOVE_TO_APPENDIX`
- `ADD_MISSING_BRIDGE`
- `ADD_SCOPE_DECLARATION`
- `DECLARE_DEEP_DIVE_EXEMPLAR`
- `REDEFINE_PRESENTATION_QUESTION`
- `BLOCK_PENDING_EVIDENCE_RECHECK`

## 6. Gate statuses

Exactly one:

- `PASS`
- `PASS_WITH_WARNINGS`
- `REVISIONS_REQUIRED`
- `BLOCK`

W07 may start only after status is `PASS` or `PASS_WITH_WARNINGS` and an `ApprovedNarrativeArchitecture` artifact exists.

`REVISIONS_REQUIRED` invalidates downstream candidate PageSpecs for authoritative use.

## 7. Audience differentiation audit

For benchmark cases, validate audience adaptation using controlled comparisons.

Preferred method:
- hold source, Presentation Question, scenario, language and duration constant;
- change only explicit AudienceProfile/AdaptationContract facets;
- compare Narrative Architecture.

A valid audience difference may change:
- entry point;
- background burden;
- terminology explanation;
- evidence density;
- numeric detail;
- recommendation visibility;
- mechanism depth;
- exemplar choice;
- appendix allocation;
- section order when cognitively justified.

It must not change authoritative Claim/NumericFact truth, source population, exact RED thresholds or recommendation/evidence facts.

A second control should hold audience constant and vary duration to distinguish audience adaptation from time-budget adaptation.

## 8. Narrative-to-Page boundary

W06-NR decides the **story architecture**, not the slide count or final visual grammar.

Only after narrative approval should the pipeline run a separate `Narrative-to-Page Decomposition Audit` to determine page boundaries, merge/split decisions, main-vs-appendix allocation and page-level cognitive units.

Do not reverse-engineer Narrative from a desired number of slides unless page count is an explicit hard constraint.

## 9. Regression rules

- `REG-NARR-001`: An unaudited Narrative Draft cannot produce approved PageSpecs.
- `REG-NARR-002`: Narrative must cover every material component promised by the Presentation Question or explicitly revise the question/scope.
- `REG-NARR-003`: Source TOC/page/table/figure order is not a sufficient reason for Narrative order.
- `REG-NARR-004`: Narrative transitions must not silently create clinical causality, mandatory sequence or priority.
- `REG-NARR-005`: Broad-to-narrow scope shifts require explicit deep-dive/exemplar declaration and scope return/closure.
- `REG-NARR-006`: Narrative emphasis is driven by task/audience/goal, not source-volume bias.
- `REG-NARR-007`: Audience-driven Narrative differences must be traceable to explicit context facets; job title alone is insufficient.
- `REG-NARR-008`: Duration-driven compression may relocate/omit presentation detail but cannot mutate evidence.
- `REG-NARR-009`: Missing conceptual bridges must be repaired before page decomposition.
- `REG-NARR-010`: Uncertainty material to the Presentation Question cannot be silently removed.
- `REG-NARR-011`: The Narrative ending must close the Presentation Question; source-document ending is not automatically presentation closure.
- `REG-NARR-012`: Candidate page count must not determine Narrative architecture unless page count is an explicit hard constraint.
- `REG-NARR-013`: Deep-dive exemplars must not be visually or verbally presented as the universal model for the full subject scope.
- `REG-NARR-014`: A case report cannot directly authorize population efficacy, causality, diagnostic sufficiency or clinical recommendations.
- `REG-NARR-015`: Case-derived scope/strength upgrades require SYNTHESIS provenance, external support and human approval.

## 10. Audit record minimum

Every W06-NR audit record must contain:

- context/profile reference;
- Presentation Question;
- current Narrative Draft;
- dimension-by-dimension findings;
- section-level decisions;
- identified overreach/missing links/scope shifts;
- revised Narrative candidate;
- unresolved evidence checks;
- gate status;
- downstream invalidation decision.
