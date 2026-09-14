# Independent Audit Checklist

- [ ] No unauthorized frozen artifact diff.
- [ ] No illegal state transition (especially CANDIDATE -> APPROVED).
- [ ] Only APPROVED objects can enter Narrative / SlidePlan.
- [ ] All Claims / NumericFacts / Relations have SourceSpan provenance.
- [ ] Numeric audit values use Decimal and deterministic arithmetic.
- [ ] Relations do not bypass retrieval / classification / verifier.
- [ ] Stage reruns are idempotent and preserve history.
- [ ] DB migration, Pydantic/JSON Schema, and API are consistent.
- [ ] Failure, conflict, and low-confidence paths have tests.
- [ ] No tests were deleted/weakened/skipped to obtain a pass.
- [ ] No changes outside Current Milestone allowed paths.
- [ ] Golden labels were not modified by Developer Pass.
- [ ] Sensitive data is not exposed in logs, fixtures, prompt dumps, or unauthorized services.
- [ ] Completion Report records limitations and open risks accurately.
