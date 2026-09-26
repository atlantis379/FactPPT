# Narrative-to-Page Decomposition Audit Policy v0.1

**Status:** `ACTIVE_SKILL_POLICY_NOT_FROZEN_SPEC`

## 1. Purpose

Insert a mandatory page-decomposition gate after `ApprovedNarrativeArchitecture` and before authoritative PageSpec construction.

Core principle:

> **A reasonable Narrative does not guarantee a reasonable slide decomposition.**
>
> **Page boundaries must follow cognitive units, audience needs and duration constraints—not source page/table/figure boundaries or a preselected slide count.**

This policy does not change frozen Module 01–06 rule counts or the frozen W00–W18 numbering. It operationalizes a mandatory `W06-NP Narrative-to-Page Decomposition Audit` inside the W06→W07 boundary.

## 2. Required execution order

```text
W05 Information Triage
→ W06 Narrative Draft
→ W06-NR Narrative Rationality Audit
→ Approved Narrative Architecture
→ W06-NP Narrative-to-Page Decomposition Draft
→ W06-NP Decomposition Audit
→ Approved Page Allocation Plan
→ W07 PageSpec Construction
```

W07 MUST NOT begin until both `W06-NR` and `W06-NP` are `PASS` or `PASS_WITH_WARNINGS`.

## 3. Page Allocation Plan object

The decomposition gate must produce an `ApprovedPageAllocationPlan` distinct from PageSpec.

Recommended fields:
- `approved_narrative_ref`
- `context_profile_ref`
- `duration_constraint`
- `page_count_status`: `EMERGENT | HARD_CONSTRAINT`
- `candidate_page_count`
- `main_deck_pages[]`
- `appendix_allocations[]`
- `merge_split_decisions[]`
- `transition_map[]`
- `decomposition_risk_register[]`
- `audit_status`

Each candidate page should record:
- `candidate_page_id`
- `narrative_section_refs[]`
- `cognitive_unit`
- `page_question`
- `primary_message_candidate`
- `supporting_evidence_refs[]`
- `dependency_on_previous_page`
- `dependency_for_next_page`
- `main_or_appendix`
- `display_intent`
- `density_estimate`
- `split_merge_rationale`
- `audience_rationale`
- `duration_rationale`

`display_intent` describes the communication task only, e.g. `CLASSIFY`, `COMPARE`, `ROUTE`, `EXPLAIN`, `SHOW_EVIDENCE`, `CONNECT_DIAGNOSIS_TO_ACTION`, `SUMMARIZE_UNCERTAINTY`. It is not yet a Visual Strategy or visual type.

## 4. Mandatory audit dimensions

### 4.1 Cognitive Unit Integrity
Each page candidate should answer one coherent cognitive question. A page that mixes unrelated tasks must be split or rewritten.

### 4.2 Unique Primary Message
Each page candidate must support one primary message candidate. Two independent primary messages usually indicate a split; two pages with the same primary message usually indicate a merge or redundancy problem.

### 4.3 Narrative Dependency and Order
Page order must preserve the approved Narrative logic. A page must not require concepts that are introduced only later unless the dependency is explicitly intentional.

### 4.4 Missing Bridge Detection
When two narrative sections cannot transition naturally at page level, add a bridge, merge them, or revise the decomposition. Do not let page boundaries create a new conceptual jump that was not present in the approved Narrative.

### 4.5 Information Density / Cognitive Load
Estimate whether the candidate page can be understood and presented within the expected speaking time. Dense RED tables, multiple decision branches, many exact values or several treatment contexts may require split, progressive disclosure or appendix allocation.

### 4.6 Mergeability
Merge candidates when separate pages would merely repeat the same cognitive question, evidence set or conclusion.

### 4.7 Splittability
Split candidates when one page contains multiple incompatible tasks, multiple independent decisions, or too many exact/RED objects for reliable comprehension and visual verification.

### 4.8 Main Deck vs Appendix Allocation
A fact may be important and still belong in appendix/notes. Allocation follows the Presentation Question, AudienceProfile, AdaptationContract and duration—not absolute medical importance alone.

### 4.9 Scope Balance
A deep-dive exemplar may receive more space only when explicitly justified by the Approved Narrative Architecture. It must not crowd out the broader scope or be mistaken for a universal model.

### 4.10 Source-layout Independence
A source page, table, figure or chapter does not create a page boundary by itself. One-table-per-slide, one-figure-per-slide and source-section-per-slide conversion are invalid decomposition rationales.

### 4.11 Page-count Neutrality
If page count is not an explicit hard constraint, the page count must emerge from the approved Narrative, duration and cognitive-load audit. Do not force the Narrative into 7/8/9 pages in advance.

If the user gives a hard page-count constraint, the system may compress, merge or move content to appendix, but must report resulting tradeoffs and cannot mutate source semantics.

### 4.12 Audience and Duration Traceability
Any merge/split/main-vs-appendix decision materially driven by audience or duration must be traceable to explicit context facets. Do not infer simplification from job title alone.

### 4.13 Display Intent Before Visual Strategy
The decomposition gate may decide that a page needs comparison, routing, classification, explanation or evidence display, but it must not prematurely select a specific visual grammar solely because the source used one.

## 5. Audit actions

Allowed actions:
- `KEEP_PAGE_CANDIDATE`
- `MERGE_WITH_PREVIOUS`
- `MERGE_WITH_NEXT`
- `SPLIT_INTO_MULTIPLE_CANDIDATES`
- `MOVE_EARLIER`
- `MOVE_LATER`
- `ADD_BRIDGE_PAGE_OR_BRIDGE_CONTENT`
- `MOVE_TO_APPENDIX`
- `PROMOTE_FROM_APPENDIX`
- `REDUCE_MAIN_DECK_DETAIL`
- `DECLARE_DEEP_DIVE_PAGE`
- `REMOVE_REDUNDANT_PAGE`
- `REVISE_DISPLAY_INTENT`
- `BLOCK_PENDING_NARRATIVE_REVISION`
- `BLOCK_PENDING_EVIDENCE_RECHECK`

## 6. Gate statuses

Exactly one:
- `PASS`
- `PASS_WITH_WARNINGS`
- `REVISIONS_REQUIRED`
- `BLOCK`

W07 PageSpec may start only when:
1. `ApprovedNarrativeArchitecture` exists;
2. `ApprovedPageAllocationPlan` exists;
3. W06-NR and W06-NP are `PASS` or `PASS_WITH_WARNINGS`.

## 7. Regression rules

- `REG-DECOMP-001`: Approved PageSpecs cannot be created before an Approved Narrative Architecture exists.
- `REG-DECOMP-002`: Approved PageSpecs cannot be created before an Approved Page Allocation Plan exists.
- `REG-DECOMP-003`: Source page/table/figure/chapter boundaries are not valid page-boundary reasons by themselves.
- `REG-DECOMP-004`: Each candidate page must correspond to one coherent cognitive unit and one primary-message candidate.
- `REG-DECOMP-005`: Two candidates that answer the same cognitive question without distinct value must be merged or justified.
- `REG-DECOMP-006`: A candidate containing multiple independent decisions or excessive RED semantic density must be split, simplified by allocation, or blocked.
- `REG-DECOMP-007`: Page order must preserve approved Narrative dependencies and cannot introduce hidden clinical sequencing.
- `REG-DECOMP-008`: Deep-dive exemplars require explicit scope rationale and may not consume the broader narrative without closure.
- `REG-DECOMP-009`: Main-vs-appendix allocation must be traceable to Presentation Question, context and duration.
- `REG-DECOMP-010`: Slide count must emerge from Narrative/decomposition unless explicitly provided as a hard constraint.
- `REG-DECOMP-011`: Display Intent is not Visual Strategy; page decomposition must not be driven by source visual form.
- `REG-DECOMP-012`: Audience/duration-driven merge/split decisions may change presentation allocation but never authoritative evidence semantics.

## 8. Minimum audit record

Every decomposition audit must record:
- Approved Narrative Architecture reference;
- current page candidates;
- page-level cognitive question and primary-message candidate;
- merge/split decisions and rationale;
- dependency/order findings;
- density/cognitive-load findings;
- main/appendix decisions;
- page-count rationale;
- unresolved evidence or narrative issues;
- final Approved Page Allocation Plan;
- gate status.
