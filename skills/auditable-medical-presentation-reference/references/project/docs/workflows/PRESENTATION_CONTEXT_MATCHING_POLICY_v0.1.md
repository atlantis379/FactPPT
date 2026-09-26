# Presentation Context & Audience Matching Policy v0.1

**Status:** `ACTIVE_SKILL_POLICY_NOT_FROZEN_SPEC`

## 1. Purpose

Define how the reference pipeline adapts one verified medical evidence layer to different presentation contexts without changing the underlying medical facts.

This policy does **not** replace or weaken frozen Module 01–06 rules. It operationalizes the already-frozen principle that audience adaptation changes selection/order/depth rather than the underlying Claim.

## 2. Three contexts must be modeled separately

### PresenterProfile
Who is presenting.

Examples:
- specialist / department director;
- attending physician;
- resident;
- medical teacher;
- medical affairs/scientific staff.

### AudienceProfile
Who receives the presentation.

Examples:
- subspecialist physicians;
- general clinicians;
- residents;
- undergraduate medical students;
- non-specialist health professionals;
- management / policy audience;
- patient/public education audience.

### SubjectPopulationProfile
Which patient/clinical population the medical statement applies to.

Examples:
- INOCA;
- IOCA;
- MINOCA;
- MIOCA;
- STEMI after PCI;
- CABG patients;
- women / postmenopausal women;
- patients with hypertrophic cardiomyopathy;
- HFpEF;
- other source-defined subgroups.

**Presenter Role, Audience, and Subject Population must never be inferred as substitutes for one another.**

## 3. Hard adaptation boundary

Audience adaptation may change:
- content selection;
- ordering;
- explanatory depth;
- terminology explanation depth;
- main-deck versus appendix allocation;
- examples used to explain an already-approved fact;
- visual complexity;
- speaker-note depth.

Audience adaptation must not change:
- underlying medical proposition;
- subject population scope;
- condition / exclusion;
- dose;
- threshold/operator/range;
- statistic value;
- recommendation class;
- evidence level;
- clinical relationship direction or logical operator;
- source provenance.

## 4. PresentationContextProfile

W04 must output a structured `PresentationContextProfile` containing:

```text
PresentationContextProfile
├─ PresenterProfile
├─ AudienceProfile
├─ SubjectPopulationProfile
├─ ScenarioProfile
├─ GoalProfile
├─ DurationProfile
└─ AdaptationContract
```

## 5. AdaptationContract fields

At minimum:

- `depth_level`: BASIC / INTERMEDIATE / ADVANCED / EXPERT;
- `terminology_level`: EXPLAIN_ALL / EXPLAIN_SPECIALIST_TERMS / SPECIALIST_NATIVE;
- `clinical_actionability`: EDUCATIONAL / PRACTICE_ORIENTED / DECISION_SUPPORTING_PRESENTATION;
- `mechanism_depth`: LOW / MEDIUM / HIGH;
- `evidence_detail_level`: LOW / MEDIUM / HIGH / FULL;
- `numeric_detail_level`: CORE_ONLY / DECISION_CRITICAL / FULL_RELEVANT;
- `recommendation_visibility`: HIDE_NONCRITICAL / KEY_ONLY / FULL_RELEVANT;
- `evidence_grade_visibility`: HIDE_NONCRITICAL / KEY_ONLY / FULL_RELEVANT;
- `background_explanation_need`: LOW / MEDIUM / HIGH;
- `visual_complexity`: LOW / MEDIUM / HIGH;
- `case_example_need`: NONE / OPTIONAL / RECOMMENDED;
- `appendix_ratio`: LOW / MEDIUM / HIGH;
- `speaker_note_depth`: LOW / MEDIUM / HIGH;
- `source_visibility`: STANDARD / HIGH / MAXIMUM.

These are presentation-control variables, not medical truth variables.

## 6. Default audience matching matrix

| Audience | Depth | Terminology | Evidence detail | Numeric detail | Recommendation/evidence grade | Visual complexity | Background explanation |
|---|---|---|---|---|---|---|---|
| Subspecialist physicians | EXPERT | SPECIALIST_NATIVE | FULL | FULL_RELEVANT | FULL_RELEVANT | HIGH | LOW |
| General clinicians | ADVANCED | EXPLAIN_SPECIALIST_TERMS | HIGH | DECISION_CRITICAL | KEY_ONLY/FULL_RELEVANT | MEDIUM-HIGH | MEDIUM |
| Residents | INTERMEDIATE-ADVANCED | EXPLAIN_SPECIALIST_TERMS | MEDIUM-HIGH | DECISION_CRITICAL | KEY_ONLY | MEDIUM | MEDIUM |
| Medical undergraduates | INTERMEDIATE | EXPLAIN_ALL | MEDIUM | CORE_ONLY | KEY_ONLY or notes | LOW-MEDIUM | HIGH |
| Non-specialist health professionals | BASIC-INTERMEDIATE | EXPLAIN_ALL | LOW-MEDIUM | CORE_ONLY | HIDE_NONCRITICAL | LOW | HIGH |
| Management/policy | INTERMEDIATE | EXPLAIN_SPECIALIST_TERMS | MEDIUM | CORE_ONLY | KEY_ONLY | MEDIUM | MEDIUM |
| Patient/public education | BASIC | EXPLAIN_ALL | LOW | CORE_ONLY | HIDE_NONCRITICAL | LOW | HIGH |

This matrix is a starting policy and may be versioned/calibrated; it is not frozen medical truth.

## 7. Subject-population preservation

If a Claim is scoped to a source-defined population, the W04 AdaptationContract must preserve that scope even when the audience is simplified.

Example:

```text
SOURCE:
"In INOCA patients ... CFR <2.0 ..."

Allowed undergraduate adaptation:
"在 INOCA 患者中，CFR<2.0 是本共识用于判断微循环功能异常的重要界值之一。"

Forbidden adaptation:
"冠心病患者 CFR<2.0 即可诊断 CMVD。"
```

The second version broadens the subject population and changes the medical proposition.

## 8. Context matching sequence

W04 executes in this order:

1. Identify PresenterProfile.
2. Identify AudienceProfile.
3. Identify SubjectPopulationProfile from approved source evidence; do not derive it from the audience.
4. Identify Scenario / Goal / Duration.
5. Generate AdaptationContract.
6. Run `ContextIntegrityCheck`.
7. Pass only the AdaptationContract to W05 Triage and downstream presentation modules.

## 9. ContextIntegrityCheck

Must check:
- presenter/audience/subject population are separately populated;
- no source fact was rewritten during W04;
- no threshold/dose/recommendation/evidence grade was simplified into a different proposition;
- no population/subgroup was broadened or narrowed without explicit source/goal support;
- any omitted details are presentation omissions, not mutations to the evidence layer.

Possible results:
- `PASS`;
- `PASS_WITH_WARNINGS`;
- `NEEDS_HUMAN_REVIEW`;
- `BLOCK`.

## 10. Regression rules

- `REG-CTX-001`: Presenter Role, Audience, and Subject Population are independent fields.
- `REG-CTX-002`: Audience simplification cannot broaden or narrow Subject Population.
- `REG-CTX-003`: Audience simplification cannot mutate a RED threshold/dose/recommendation/evidence grade.
- `REG-CTX-004`: If a beginner audience does not need a RED detail in the main deck, move it to notes/appendix rather than rewrite it imprecisely.
- `REG-CTX-005`: Different Role/Audience outputs derived from the same evidence must preserve identical authoritative Claim/NumericFact IDs.

## 11. CMVD Test 001 application

The CMVD consensus is especially useful because the source itself distinguishes multiple clinical populations (e.g., INOCA, IOCA, MINOCA, MIOCA, PCI/CABG-related and non-atherosclerotic disease-related CMVD). W04 must not collapse these medical populations merely because the audience is broader or more junior.
