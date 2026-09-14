# M0 Completion Report — Draft

**status:** DRAFT; independent Audit Pass and CI result pending.

## Scope
Agent governance bootstrap only. No business modules or frozen normative artifacts changed.

## Acceptance evidence
- Current Milestone: ACTIVE, bounded to governance paths.
- Frozen manifest: populated with existing normative artifacts; v0.2 inventory currently absent and future additions must be enumerated.
- Rule registry: M0 frozen-contract and path rules mapped to executable checks; business rules remain unmapped until their milestone.
- Test results: governance unit tests pass locally, including root-commit scope, executable skip detection without string/comment false positives, test deletion/rename, controlled manifest change, assertion inventory, and FROZEN evidence negatives. The actual root-commit CLI gate passes locally.
- CI results: pending GitHub run.
- Independent audit: pending separate context.

## Known limitations and open risks
- This is a CI skeleton, not the business schema, Golden, migration, or downstream admission gate implementation.
- Initial push checks every tracked path against an explicit bootstrap allowlist plus the M0 allowed paths; it is valid only for a single root commit. Later pushes compare against the push event's `before` SHA, including multi-commit pushes.
- A new non-default branch with a zero `before` SHA compares against the default branch. A non-root new default branch fails closed and requires a PR with a known base.
- `.gitattributes` pins governed text files to LF so frozen hashes remain stable on Windows checkouts with `core.autocrlf=true`.
- FROZEN admission requires checked acceptance criteria, an M0 final report with `status: PASS`, positive passed test count and zero failures, passing CI/frozen-hash gates, `golden_regression: NOT_APPLICABLE` only because the Golden subset is `none`, and a clean PASS independent audit record. Those final artifacts are not yet present.
- A post-bootstrap manifest update requires an APPROVED Change Request already present in the base revision, unchanged in the update, naming each changed artifact with approver and approval time. Initial M1 schema registration therefore needs prior approval for the manifest update even though the new schema files themselves did not previously exist as frozen artifacts. Create and approve the CR in a separate earlier change, then register the schemas and manifest in M1.
- Test edits may strengthen existing tests, but the gate rejects removed test functions, lower assertion counts, skips, and deleted/renamed test files. Assertion counts cannot prove semantic equivalence; independent audit must review changed assertions and fixtures.
- Freeze is blocked until independent audit and CI pass.
