# Reference Skill run record v0.5

Record scope before testing. Do not infer a complete pipeline run from a page regression.

## Identity and context
- test_id / date / skill_version=v0.5.0 / schema_version=0.5.0
- mode: DESIGN_PROTOTYPE or DELIVERY; delivery_eligible
- question, audience, viewing mode, duration, language and source scope
- source identities, original/edited artifact hashes and inherited evidence references
- active contract version/hash; runtime/code/font identities

## State
Use schemas/run_state.schema.json and run scripts/skill_tool.py state.
Record W00–W18, subgates W02-FSC/W06-NR/W06-NP/W12-A/W12-RQ/W12-B, stale objects and blockers.
Prototype W14 is at most PARTIAL_PASS and W17 cannot PASS. W18 records failed runs too.

## Quality
Use schemas/quality_evaluation.schema.json; independently record source_coverage, semantic_integrity, data_geometry, visible_glyphs, composition and narrative.
Each result has scope, actual findings, evidence paths/hashes and explicit applicability.
Unknown source denominators remain UNKNOWN. Specify actual tested format/capability.

## Review and corrections
Record issue ID, responsible stage, input/output versions, repair class, revalidation and regression case.
Independent reviewer ID, method, artifact/render hashes, limitations and disagreements.
Clinical human approval, if required, is separate and binds the exact current artifact hash.

## Disposition
APPROVED_REFERENCE_OUTPUT / PARTIAL_WITH_BLOCKERS / FAILED_REFERENCE_RUN.
List remaining scope limits without upgrading a successful checker test into a successful artifact or clinical approval.
