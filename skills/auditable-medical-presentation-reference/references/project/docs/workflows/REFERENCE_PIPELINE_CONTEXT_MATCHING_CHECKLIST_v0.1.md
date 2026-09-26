# Reference Pipeline W04 Context Matching Checklist v0.1

**Status:** `ACTIVE_SKILL_CHECKLIST_NOT_FROZEN_SPEC`

Use together with `REFERENCE_PIPELINE_CHECKLIST_v0.1.md` for Skill v0.2 runs.

## A. Presenter / Audience / Subject Population separation

- [ ] PresenterProfile recorded independently
- [ ] AudienceProfile recorded independently
- [ ] SubjectPopulationProfile recorded independently
- [ ] Presenter role was not used as a proxy for audience
- [ ] Audience type was not used as a proxy for patient population
- [ ] Subject population is traceable to source evidence / explicit presentation scope

## B. Audience profile

- [ ] Baseline medical knowledge estimated or provided
- [ ] Expected terminology familiarity recorded
- [ ] Desired clinical actionability recorded
- [ ] Expected evidence-detail level recorded
- [ ] Expected numeric-detail level recorded
- [ ] Background-explanation need recorded
- [ ] Visual complexity target recorded

## C. Subject population integrity

- [ ] Population scope preserved
- [ ] Subgroups preserved where meaning-critical
- [ ] Exclusions preserved where meaning-critical
- [ ] Conditions preserved
- [ ] Population was not broadened for simplification
- [ ] Population was not narrowed without source/goal support

## D. AdaptationContract

- [ ] depth_level
- [ ] terminology_level
- [ ] clinical_actionability
- [ ] mechanism_depth
- [ ] evidence_detail_level
- [ ] numeric_detail_level
- [ ] recommendation_visibility
- [ ] evidence_grade_visibility
- [ ] background_explanation_need
- [ ] visual_complexity
- [ ] case_example_need
- [ ] appendix_ratio
- [ ] speaker_note_depth
- [ ] source_visibility

## E. Medical invariants

Confirm W04 did not mutate:
- [ ] Claim proposition
- [ ] Claim/Fact IDs
- [ ] Numeric value
- [ ] Threshold operator/range
- [ ] Unit
- [ ] Dose
- [ ] Recommendation class
- [ ] Evidence level
- [ ] Relationship direction
- [ ] AND/OR/NOT/EXCEPT logic
- [ ] Provenance

## F. Beginner-audience handling

When exact high-risk detail is too dense for the main deck:
- [ ] detail moved to appendix/notes OR intentionally omitted from that page
- [ ] no imprecise substitute statement created
- [ ] exact authoritative fact remains unchanged in evidence layer

## G. Cross-role consistency test

For at least two context profiles derived from the same source:
- [ ] authoritative Claim IDs overlap consistently
- [ ] NumericFact IDs are unchanged where the same fact is used
- [ ] differences are selection/order/depth/presentation only
- [ ] no role-specific medical truth was invented

## Blocking rule

If Presenter/Audience/SubjectPopulation are conflated, or any authoritative medical proposition is mutated during context adaptation, W04 = `BLOCK` and W05 must not start.
