# Model Development Operating Contract v0.3

This file is normative. It supplements `SYSTEM_SPEC_v0.3.md` and does not modify frozen v0.2 business schemas.

## Priority
Frozen Schema / Frozen Contract > Development Contract > Approved ADR / Change Request > Current Milestone > implementation convenience.

## Main model
GPT-5.6 Sol is the default Lead Architect, Main Developer, and Independent Audit model. Developer and Audit passes must use separate task contexts.

## Required workflow
`READ -> PLAN -> IMPLEMENT -> TEST -> AUDIT -> FREEZE`

## Non-negotiable rules
- Only APPROVED objects from Approved Semantic Graph may enter formal downstream.
- Claim, NumericFact, and Relation require SourceSpan provenance.
- Numeric audit truth uses Decimal; deterministic arithmetic is implemented in code, never delegated to LLM output.
- Frozen artifacts cannot change without an APPROVED Change Request.
- Current Milestone `allowed_paths` is the write boundary.
- Do not implement future milestones or unrelated refactors.
- Never delete, weaken, skip tests, or lower thresholds to obtain a pass.
- NEEDS_REVIEW / REJECTED / VERIFIED / CANDIDATE are not downstream-admissible.

## Change control
If a frozen change is required, stop the affected change, create a Change Request, and wait for approval before editing the artifact.

## Definition of Done
A milestone is DONE only after acceptance criteria, required tests, relevant Golden regression, frozen-artifact checks, independent Audit Pass, and Completion Report succeed.

## Rule enforcement
MUST rules should be mapped to `Rule -> Code -> Test -> CI` wherever technically possible. The registry is `config/rule_registry.yaml`.
