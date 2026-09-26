# Presentation Context Matching Policy v0.2

**Status:** `ACTIVE_SKILL_POLICY_NOT_FROZEN_SPEC`  
**Supersedes for Skill execution:** `PRESENTATION_CONTEXT_MATCHING_POLICY_v0.1.md`

## 1. Purpose

Generalize W04 so the presentation system is not coupled to a particular department, specialty, profession, job title, disease area, or patient population.

The core model must support arbitrary medical/scientific source materials and heterogeneous presentation contexts while preserving the same verified evidence layer.

This policy does **not** change frozen Module 01–06 rules. It operationalizes audience/context adaptation as a versioned Skill policy.

## 2. Core principle: roles are compositional, not enumerated

The system must not treat labels such as `cardiologist`, `resident`, `medical student`, `MSL`, or `department director` as the authoritative adaptation logic.

A role label is only a human-readable hint. Adaptation is determined from explicit context facets.

```text
Role label / free text
        ↓
Context Facet Normalization
        ↓
PresentationContextProfile
        ↓
AdaptationContract
```

No fixed list of departments or specialties is required to use W04.

## 3. W04 output model

```text
PresentationContextProfile
├─ DomainContextProfile
├─ PresenterProfile
├─ AudienceProfile
│  └─ AudienceSegment[]
├─ SubjectScopeProfile
├─ ScenarioProfile
├─ TaskIntentProfile
├─ ConstraintProfile
└─ AdaptationContract
```

### 3.1 DomainContextProfile

Describes the knowledge domain without hard-coding a specialty taxonomy.

Minimum concepts:
- `domain_label`: free text, e.g. cardiology / oncology / respiratory medicine / dentistry / pharmacology / hospital management;
- `specialty_tags[]`: optional open tags;
- `source_material_type`: guideline / consensus / RCT / meta-analysis / textbook / case series / product evidence / policy / operations / other;
- `jurisdiction_or_regulatory_context`: optional;
- `domain_notes`: optional.

The system may normalize common labels but must retain the user/source wording.

### 3.2 PresenterProfile

Describes the presenter as open facets rather than a closed job-title enum.

Minimum concepts:
- `role_label`: free text;
- `professional_function[]`: open tags such as clinical care / research / teaching / medical affairs / management / policy / student / other;
- `domain_expertise[]`: open tags;
- `expertise_level`: optional normalized scale;
- `decision_authority`: NONE / INFORM / RECOMMEND / DECIDE / MIXED / UNKNOWN;
- `evidence_literacy`: BASIC / INTERMEDIATE / ADVANCED / EXPERT / UNKNOWN;
- `presentation_responsibility`: free text;
- `known_constraints[]`.

A title alone must not determine the adaptation contract.

### 3.3 AudienceProfile

Audience may be homogeneous or mixed.

```text
AudienceProfile
└─ AudienceSegment[]
```

Each `AudienceSegment` may contain:
- `segment_label`: free text;
- `professional_or_social_context[]`: open tags;
- `domain_expertise[]`: open tags;
- `expertise_level`;
- `evidence_literacy`;
- `decision_responsibility`;
- `information_need[]`;
- `expected_action_after_presentation[]`;
- `priority`: PRIMARY / SECONDARY / TERTIARY;
- `estimated_share`: optional;
- `accessibility_or_language_needs[]`.

Mixed audiences must not be collapsed into a single fictitious average user when this would hide conflicting needs.

### 3.4 SubjectScopeProfile

`SubjectPopulationProfile` from v0.1 is generalized to `SubjectScopeProfile`.

The subject of a presentation is not always a patient population. It may be:
- a disease/phenotype;
- a patient subgroup;
- a study population;
- a diagnostic technology;
- an intervention/drug/device;
- a mechanism/pathway;
- a clinical workflow;
- a guideline/recommendation set;
- a research program;
- a healthcare policy/management object;
- another source-defined entity.

Minimum concepts:
- `scope_label`: source-faithful free text;
- `scope_type`: open string with normalized tags when available;
- `population_constraints[]`: optional;
- `condition_constraints[]`: optional;
- `intervention_constraints[]`: optional;
- `time_constraints[]`: optional;
- `geography_or_setting[]`: optional;
- `source_object_refs[]`;
- `scope_notes`.

Audience simplification must never mutate SubjectScope.

### 3.5 ScenarioProfile

Examples include but are not limited to:
- academic conference;
- department teaching;
- undergraduate lecture;
- journal club;
- multidisciplinary case conference;
- guideline interpretation;
- medical affairs scientific exchange;
- management briefing;
- policy briefing;
- patient/public education.

The field is open-ended.

### 3.6 TaskIntentProfile

Task intent must be explicit and is independent of job title.

Examples:
- explain;
- teach;
- compare evidence;
- support discussion;
- interpret a guideline;
- prepare decision context;
- report trial results;
- summarize current state;
- identify uncertainty/research gaps.

Do not infer a patient-specific treatment decision merely because the presenter is a clinician.

### 3.7 ConstraintProfile

May contain:
- duration;
- language;
- slide/page limit;
- source-fidelity requirement;
- external-research permission;
- compliance restrictions;
- confidentiality/data-egress restrictions;
- delivery format;
- accessibility constraints.

## 4. Adaptation is need-based, not title-based

Generate `AdaptationContract` from the full context profile, especially:

```text
Audience information need
+ expertise/evidence literacy
+ decision responsibility
+ task intent
+ scenario
+ duration/format constraints
+ domain context
+ approved SubjectScope
```

Do not derive adaptation primarily from department, specialty, age, title, or organizational seniority.

## 5. AdaptationContract

Recommended fields remain presentation-control variables:
- `depth_level`;
- `terminology_level`;
- `clinical_or_operational_actionability`;
- `mechanism_depth`;
- `evidence_detail_level`;
- `numeric_detail_level`;
- `recommendation_visibility`;
- `evidence_grade_visibility`;
- `background_explanation_need`;
- `visual_complexity`;
- `comparison_detail_level`;
- `uncertainty_visibility`;
- `case_example_need`;
- `appendix_ratio`;
- `speaker_note_depth`;
- `source_visibility`;
- `primary_audience_segment_ids[]`;
- `segment_conflict_handling`;
- `adaptation_rationale[]`.

These fields may evolve as versioned Skill policy. They are not medical truth fields.

## 6. Core invariants

W04 may alter:
- content selection;
- order;
- explanatory depth;
- terminology explanations;
- examples used to explain approved facts;
- visual complexity;
- main-deck vs appendix allocation;
- speaker-note depth.

W04 must not alter:
- Claim truth conditions;
- population/scope;
- condition/exclusion;
- dose;
- threshold/operator/range;
- statistic value;
- recommendation class;
- evidence level;
- clinical relationship direction/logical operator;
- source provenance.

## 7. Open-role rules

- `REG-CTX-006`: No department/specialty/job-title enumeration may be required by the core context model.
- `REG-CTX-007`: Role labels are descriptive hints; adaptation must be facet-based.
- `REG-CTX-008`: Unknown context facets remain `UNKNOWN/UNRESOLVED`; do not stereotype or infer them from a title.
- `REG-CTX-009`: AudienceProfile must support multiple segments and conflicting information needs.
- `REG-CTX-010`: SubjectScope is not assumed to be a patient population.
- `REG-CTX-011`: DomainContext is independent from PresenterRole and AudienceRole.
- `REG-CTX-012`: Role presets, if used, are versioned convenience templates and never core truth.
- `REG-CTX-013`: Two contexts with the same job title may yield different AdaptationContracts when intent, expertise, responsibility, duration, or audience needs differ.

Existing rules remain active:
- `REG-CTX-001`: Presenter, Audience and Subject Scope are independent.
- `REG-CTX-002`: Audience simplification cannot broaden/narrow source scope.
- `REG-CTX-003`: Adaptation cannot mutate RED thresholds/doses/recommendation/evidence grades.
- `REG-CTX-004`: Omit or move unnecessary RED detail to notes/appendix rather than rewrite it imprecisely.
- `REG-CTX-005`: Same authoritative evidence across contexts reuses the same Claim/NumericFact IDs.

## 8. Preset registry boundary

Optional presets may be provided for convenience, e.g.:
- specialist academic talk;
- undergraduate teaching;
- journal club;
- executive briefing;
- patient education.

Presets live in a versioned registry and only pre-fill facet values. They must not become required categories and must be editable/overridable before W05.

## 9. ContextIntegrityCheck v0.2

Must verify:
1. no required context dimension was silently inferred from a role title;
2. Presenter, Audience, Domain and SubjectScope remain independent;
3. mixed audiences are represented when material;
4. adaptation rationale is traceable to explicit context facets;
5. source facts and scope are unchanged;
6. any omitted detail is a presentation omission, not an evidence mutation;
7. role preset use, if any, is recorded and does not override explicit user context.

Possible status:
- `PASS`;
- `PASS_WITH_WARNINGS`;
- `NEEDS_CLARIFICATION`;
- `NEEDS_HUMAN_REVIEW`;
- `BLOCK`.

## 10. Example: same CMVD source, open contexts

The same verified CMVD evidence layer can support, for example:

- a cardiology fellow teaching junior residents;
- an imaging specialist presenting diagnostic-method evidence to a multidisciplinary audience;
- a pharmacologist discussing mechanism/treatment evidence;
- an undergraduate teacher giving a cardiovascular physiology lecture;
- a medical affairs professional summarizing source evidence for scientific exchange;
- a hospital manager receiving a diagnostic-capability briefing.

These are not six hard-coded roles. They are six different combinations of domain, presenter function, audience needs, task intent and constraints.
