# Reference Pipeline Full-Source Coverage Checklist v0.1

**Status:** `ACTIVE_SKILL_CHECKLIST_SUPPLEMENT`

Use with `FULL_SOURCE_EVIDENCE_COVERAGE_POLICY_v0.1.md`.

A run may not advance to W05 Information Triage unless all mandatory items are checked or an explicit `PASS_WITH_WARNINGS` records why the unchecked item cannot materially alter Triage/Narrative.

## A. Source traversal

- [ ] Source identity/hash/version recorded.
- [ ] Total source page count confirmed from actual file.
- [ ] Every page has a `SourceCoverageManifest` record.
- [ ] Substantive body pages identified.
- [ ] Reference/appendix/metadata pages identified rather than silently ignored.
- [ ] No page silently omitted because parsing was difficult.

## B. Section coverage

- [ ] Every substantive section/subsection inventoried.
- [ ] Every substantive section has Claims/SectionSummary or an explicit non-Claim classification.
- [ ] Definitions and taxonomy captured.
- [ ] Mechanism/background sections captured sufficiently to constrain later interpretation.
- [ ] Clinical manifestations / indications / exclusions captured.
- [ ] Diagnostic criteria and diagnostic-method limitations captured.
- [ ] Treatment/management sections captured.
- [ ] Uncertainty/conflict/research-gap sections captured.

## C. RED completeness

- [ ] All meaning-critical thresholds captured as operator + value + unit + context.
- [ ] All recommendation classes captured and row-bound.
- [ ] All evidence levels captured and row-bound.
- [ ] All dose/timing/special-population/contraindication/exclusion statements captured when present.
- [ ] Context-specific thresholds are not merged.
- [ ] Treatment and diagnostic ownership across clinical contexts is explicitly represented.

## D. Tables / figures / algorithms

- [ ] Every substantive table registered.
- [ ] Every substantive figure/algorithm registered.
- [ ] Meaning-critical topology/grouping/row ownership identified.
- [ ] Rendered-page inspection completed where text extraction is incomplete or layout-dependent.
- [ ] Corrupted text-layer objects have an authoritative rendered view.

## E. Coverage audit

- [ ] PageCoverageRate calculated.
- [ ] SubstantiveSectionCoverageRate calculated.
- [ ] REDObjectCoverageRate assessed.
- [ ] TableFigureRegistrationRate assessed.
- [ ] RenderedInspectionCoverage assessed for required objects.
- [ ] SilentOmissionCount = 0.
- [ ] Every partial/uncovered substantive section underwent Narrative-Changing Omission Test.
- [ ] NarrativeChangingOmissionCount = 0 before W05, or omissions were resolved and audit rerun.

## F. Downstream gate

- [ ] `full_source_coverage_audit.status` is `PASS` or `PASS_WITH_WARNINGS`.
- [ ] W03 verifies the approved full evidence universe, not an earlier sampled subset.
- [ ] W04 SubjectScope is revalidated against the full evidence universe.
- [ ] Only then may W05 Triage begin.

## Blocking rule

If any known missing/partial section could plausibly change scope, presentation question, narrative order, deep-dive selection, treatment ownership, uncertainty framing, or page allocation:

> `BLOCK → return to W02 full-source extraction`.
