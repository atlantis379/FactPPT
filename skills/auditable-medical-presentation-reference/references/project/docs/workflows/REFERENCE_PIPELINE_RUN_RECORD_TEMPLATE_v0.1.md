# Reference Pipeline Run Record Template v0.1

Use one copy of this file for every reference-pipeline test.

## Run identity

- `test_id`:
- `date`:
- `source_filename`:
- `source_sha256`:
- `source_version`:
- `page_count`:
- `workflow_version`: `REFERENCE_PIPELINE_WORKFLOW_v0.1`
- `checklist_version`: `REFERENCE_PIPELINE_CHECKLIST_v0.1`

## Presentation context

- `presenter_role`:
- `audience`:
- `scenario/project_type`:
- `presentation_question`:
- `duration`:
- `language`:
- `external_research_allowed`:
- `synthetic_case`:

## Stage status

| Stage | Status | Artifact | Notes / blockers |
|---|---|---|---|
| W00 Source Registration | NOT_STARTED | | |
| W01 PDF / Page Extraction | NOT_STARTED | | |
| W02 Structured Evidence Layer | NOT_STARTED | | |
| W03 Evidence Verification Gate | NOT_STARTED | | |
| W04 Role Profile | NOT_STARTED | | |
| W05 Information Triage | NOT_STARTED | | |
| W06 Narrative / Outline | NOT_STARTED | | |
| W07 PageSpec | NOT_STARTED | | |
| W08 Semantic Binding | NOT_STARTED | | |
| W09 Medical/Numeric/Logic Audit | NOT_STARTED | | |
| W10 Approved Semantic Page Graph | NOT_STARTED | | |
| W11 Visual Strategy | NOT_STARTED | | |
| W12 Generation Routing | NOT_STARTED | | |
| W13 Visual Contract / Prompt | NOT_STARTED | | |
| W14 Page Generation | NOT_STARTED | | |
| W15 Post-generation Audit | NOT_STARTED | | |
| W16 Human Review | NOT_STARTED | | |
| W17 Delivery | NOT_STARTED | | |
| W18 Benchmark Record | NOT_STARTED | | |

## Quality metrics

- `source_traceability_coverage`:
- `numeric_exactness_checked`:
- `critical_numeric_mutations`:
- `unsupported_medical_synthesis_count`:
- `page_first_pass_rate`:
- `mean_generation_attempts_per_page`:
- `human_correction_count`:
- `red_items_reviewed`:
- `unresolved_blockers`:

## Issues

| Issue ID | Stage | Severity | Description | Owner | Resolution | Regression test |
|---|---|---|---|---|---|---|

## Human review record

| Review item | Reviewer | Decision | Comment | Timestamp |
|---|---|---|---|---|

## Lessons learned

### What worked

### What failed

### Workflow deficiencies discovered

### Proposed policy/workflow change

### Candidate regression tests

## Final disposition

Choose exactly one:

- `APPROVED_REFERENCE_OUTPUT`
- `PARTIAL_WITH_BLOCKERS`
- `FAILED_REFERENCE_RUN`

Reason:
