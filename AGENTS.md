# Reliable PPT System — Agent Instructions

## Required reading
Before modifying code, read:
1. `docs/specs/DEVELOPMENT_CONTRACT.md`
2. `docs/specs/SYSTEM_SPEC_v0.3.md`
3. `docs/milestones/CURRENT.md`
4. Referenced ADRs
5. Referenced frozen schemas
6. Existing tests for affected modules

## Non-negotiable rules
- Approved Semantic Graph is the only formal downstream factual input.
- Never modify frozen artifacts without an APPROVED Change Request.
- NumericFact audit values use Decimal; LLMs never perform deterministic arithmetic.
- Every Claim, NumericFact and Relation requires SourceSpan provenance.
- CANDIDATE / VERIFIED / NEEDS_REVIEW / REJECTED never enter formal downstream.
- Do not implement future milestones or unrelated refactors.
- Do not delete, weaken, skip tests, or lower thresholds to obtain a pass.

## Workflow
`READ -> PLAN -> IMPLEMENT -> TEST -> AUDIT -> FREEZE`

## Before coding
Report current milestone, allowed paths, forbidden paths, frozen dependencies, acceptance criteria, and implementation plan.

## Stop condition
If implementation requires a frozen change, a specification conflicts, or acceptance criteria cannot be met, stop the affected change, record the blocker, and create a Change Request where applicable. Do not silently work around the contract.

## Output contract
Report the implementation plan, test results, independent audit result, and Milestone Completion Report. Do not label a milestone FROZEN before all gates pass.

## Completion
A milestone is not complete until required tests, relevant Golden regression, CI gates, and independent Audit Pass succeed.

## Cursor Cloud specific instructions
- M0 is a Python 3.12 standard-library CLI. There is no lockfile, third-party package, or long-running service.
- GitHub Actions provides `python`. On the default Cloud Agent image only `python3` is present; link it to `/usr/local/bin/python` before the commands below.
- From the repository root: `python -m unittest discover -s tests/governance -v`
- Local gate: `python tools/governance/check.py --changed-file <path>` for a path on the current milestone allow-list. A forbidden path must fail closed.
