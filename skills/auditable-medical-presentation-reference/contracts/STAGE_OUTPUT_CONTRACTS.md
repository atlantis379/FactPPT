# Stage Output Contracts v0.1

This file makes the frozen workflow executable as a stateful Skill. Fields are minimum required concepts; implementation-specific schemas may add fields but must not weaken these contracts.

| Stage | Required input | Required output | Blocking failure |
|---|---|---|---|
| W00 | source file(s) | SourceManifest with immutable id/hash/version/retrieval pointer | source identity not reproducible |
| W01 | SourceManifest | ExtractedPage records + rendered-page refs + warnings | silent page omission / unresolved layout corruption |
| W02 | ExtractedPage | SourceSpan, ClaimCandidate, AtomicClaim, NumericFact, SourceRef, provenance | SOURCE object lacks source binding |
| W03 | evidence objects | VerificationResult per meaning-critical object | unresolved RED fact / numeric semantics uncertain |
| W04 | verified evidence + context | RoleProfile | role context missing before Triage |
| W05 | RoleProfile + evidence | TriageDecision set | unclassified required evidence / meaning bundle broken |
| W06 | Triage set | NarrativePlan | unsupported narrative fact added |
| W07 | NarrativePlan | PageSpec[] | page lacks unique PrimaryMessage/source layer |
| W08 | PageSpec + approved evidence | SemanticRelationship/DataBinding/ContextBinding/VisualSemantic licenses | unsupported edge or invalid comparison |
| W09 | semantic page graph candidate | Issue/Verification results | source/numeric/logic failure unresolved |
| W10 | verified current objects | ApprovedSemanticPageGraph | stale/unapproved version included |
| W11 | approved graph | VisualStrategyDecision | no valid visual and selector fabricates one |
| W12 | strategy + capability/policy | PageGenerationPlan | no qualified/verifiable route |
| W13 | approved graph + route | VisualGenerationContract + model-specific prompt | exact/mandatory/prohibited registers incomplete |
| W14 | contract + route | versioned generated/composited page asset + execution provenance | protected layer mutated |
| W15 | generated page + same contract | PostGenerationQA | mandatory/exact/numeric/relation/visual-semantic failure |
| W16 | RED/exception items | HumanReviewRecord | required human decision missing |
| W17 | approved artifacts | delivery package | draft/rejected/stale asset included |
| W18 | full run history | BenchmarkRecord + lessons/regression candidates | disposition/metrics/issues not recorded |

## State progression

Recommended stage states:

- `NOT_STARTED`
- `IN_PROGRESS`
- `PASS`
- `PASS_WITH_WARNINGS`
- `PARTIAL_PASS`
- `BLOCKED`
- `NEEDS_HUMAN_REVIEW`
- `FAIL`
- `STALE`

A later stage cannot convert an earlier unresolved `BLOCKED/FAIL` into PASS without a new upstream revision and re-verification.

## Issue contract

Every issue should record:

- `issue_id`
- `stage_detected`
- `earliest_responsible_stage`
- `severity`
- `affected_object_ids/versions`
- `description`
- `source_evidence`
- `owner`
- `state`
- `resolution_revision`
- `regression_test_id`

## Verification contract

Verification results should separate:

- what is being verified;
- source/reference used;
- validator mode;
- status;
- exact mismatch/issue;
- required action;
- human-review flag;
- verified object version.

Confidence alone is never an approval basis.
