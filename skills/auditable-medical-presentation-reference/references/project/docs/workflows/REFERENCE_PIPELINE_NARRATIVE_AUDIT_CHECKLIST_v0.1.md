# Reference Pipeline Narrative Audit Checklist v0.1

**Status:** `ACTIVE_SKILL_CHECKLIST_SUPPLEMENT`

Use after W06 Narrative Draft and before W07 PageSpec.

## W06-NR Narrative Rationality Gate

- [ ] Presentation Question is explicit and current.
- [ ] Narrative answers every material part of the Presentation Question.
- [ ] Narrative order is justified by task/context/audience, not source TOC/page order.
- [ ] Every substantive narrative assertion is source-bound or labeled SUMMARY/SYNTHESIS.
- [ ] Narrative transitions do not silently create causality, mandatory sequence, priority, superiority or universality.
- [ ] Broad-to-narrow scope shifts are explicitly declared as deep-dive/exemplar when applicable.
- [ ] Narrative returns to or closes the broader scope after a deep dive.
- [ ] Emphasis is driven by task/audience/goal, not source-volume bias.
- [ ] Audience adaptation is traceable to explicit context facets; unknown facets remain unknown.
- [ ] Duration is feasible without semantic mutation.
- [ ] Missing conceptual bridges have been repaired.
- [ ] Redundant sections have been merged/removed or justified.
- [ ] Relevant uncertainty/conflicts/research gaps are visible.
- [ ] Ending closes the Presentation Question and is not merely the source-document ending.
- [ ] `ApprovedNarrativeArchitecture` artifact exists.
- [ ] Gate status is `PASS` or `PASS_WITH_WARNINGS` before proceeding.

## W06-NP Narrative-to-Page Decomposition Gate

- [ ] Slide/page count is treated as emergent unless explicitly given as a hard constraint.
- [ ] Each page candidate answers one coherent cognitive question.
- [ ] Each page candidate has one primary-message candidate.
- [ ] Page boundaries are not copied from source page/table/figure/chapter boundaries.
- [ ] Page order preserves Approved Narrative dependencies.
- [ ] No page boundary creates a new conceptual jump.
- [ ] Duplicate/redundant page candidates are merged or justified.
- [ ] Overloaded pages are split, simplified by allocation, or blocked.
- [ ] RED semantic density is feasible for comprehension and later visual verification.
- [ ] Deep-dive exemplar page allocation is explicitly justified and scope-safe.
- [ ] Main-deck vs appendix allocation is traceable to Presentation Question, context and duration.
- [ ] `display_intent` describes communication task only and does not prematurely choose Visual Strategy.
- [ ] Merge/split decisions do not mutate authoritative evidence.
- [ ] `ApprovedPageAllocationPlan` artifact exists.
- [ ] Gate status is `PASS` or `PASS_WITH_WARNINGS` before W07.

## Blocking rule

If any mandatory item above is unresolved, S01/S02/... remain `CANDIDATE_PAGE_DECOMPOSITION` and may not be labeled approved PageSpecs or enter authoritative visual generation.
