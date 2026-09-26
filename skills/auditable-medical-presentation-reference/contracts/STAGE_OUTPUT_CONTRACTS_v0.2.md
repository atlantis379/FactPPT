# Stage Output Contracts v0.2

This file supersedes `STAGE_OUTPUT_CONTRACTS.md` for active Skill v0.2 runs. Frozen specs remain authoritative.

| Stage | Required input | Required output | Blocking failure |
|---|---|---|---|
| W00 | source file(s) | SourceManifest with immutable id/hash/version/retrieval pointer | source identity not reproducible |
| W01 | SourceManifest | ExtractedPage records + rendered-page refs + warnings | silent page omission / unresolved layout corruption |
| W02 | ExtractedPage | SourceSpan, ClaimCandidate, AtomicClaim, NumericFact, SourceRef, provenance | SOURCE object lacks source binding |
| W03 | evidence objects | VerificationResult per meaning-critical object | unresolved RED fact / numeric semantics uncertain |
| W04 | verified evidence + presentation context | PresentationContextProfile + AdaptationContract + ContextIntegrityCheck | presenter/audience/subject population conflated; context mutates source fact |
| W05 | PresentationContextProfile + AdaptationContract + evidence | TriageDecision set | unclassified required evidence / meaning bundle broken |
| W06 | Triage set + AdaptationContract | NarrativePlan | unsupported narrative fact added / audience adaptation mutates medical meaning |
| W07 | NarrativePlan + AdaptationContract | PageSpec[] | page lacks unique PrimaryMessage/source layer |
| W08 | PageSpec + approved evidence | SemanticRelationship/DataBinding/ContextBinding/VisualSemantic licenses | unsupported edge or invalid comparison |
| W09 | semantic page graph candidate | Issue/Verification results | source/numeric/logic failure unresolved |
| W10 | verified current objects | ApprovedSemanticPageGraph | stale/unapproved version included |
| W11 | approved graph + AdaptationContract | VisualStrategyDecision | no valid visual and selector fabricates one |
| W12 | strategy + capability/policy | PageGenerationPlan | no qualified/verifiable route |
| W13 | approved graph + route | VisualGenerationContract + model-specific prompt | exact/mandatory/prohibited registers incomplete |
| W14 | contract + route | versioned generated/composited page asset + execution provenance | protected layer mutated |
| W15 | generated page + same contract | PostGenerationQA | mandatory/exact/numeric/relation/visual-semantic failure |
| W16 | RED/exception items | HumanReviewRecord | required human decision missing |
| W17 | approved artifacts | delivery package | draft/rejected/stale asset included |
| W18 | full run history | BenchmarkRecord + lessons/regression candidates | disposition/metrics/issues not recorded |

## W04 mandatory contract

`PresentationContextProfile` must contain independently modeled:

- `PresenterProfile`;
- `AudienceProfile`;
- `SubjectPopulationProfile`;
- `ScenarioProfile`;
- `GoalProfile`;
- `DurationProfile`;
- `AdaptationContract`;
- `ContextIntegrityCheck` result.

The downstream modules consume the AdaptationContract, not a rewritten evidence layer.

### Context invariants

The following identifiers/values may not be mutated by W04:

- authoritative Claim identity and proposition;
- NumericFact identity/value/operator/unit/range/statistic type;
- population/subgroup/condition/exclusion scope;
- recommendation class;
- evidence level;
- approved clinical relationship direction/logical operator;
- source provenance.

If an audience does not need an exact RED detail in the main deck, W04 may recommend `APPENDIX`, `SPEAKER_NOTE`, or omission from the current page; it may not rewrite the detail into a weaker or broader medical proposition.

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
