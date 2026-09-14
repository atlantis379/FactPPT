# Milestone M0 — Agent Governance Bootstrap

**status:** ACTIVE

## Goal
Establish enforceable development governance before business implementation.

## Allowed paths
- AGENTS.md
- README.md
- .gitignore
- .gitattributes
- docs/milestones/**
- docs/change_requests/**
- docs/audit/**
- docs/milestone_reports/**
- config/rule_registry.yaml
- schemas/frozen_manifest.json
- tools/governance/**
- tests/governance/**
- .github/workflows/**
- pyproject.toml

## Forbidden paths
- src/**
- schemas/v0_2/**
- docs/specs/**
- docs/decisions/**
- evaluation/**
- reference/**

## Frozen dependencies
- docs/specs/DEVELOPMENT_CONTRACT.md
- docs/specs/SYSTEM_SPEC_v0.3.md
- docs/decisions/ADR-006-sol-mainline.md

## Inputs / outputs
- Input: v0.3 development contract and System Spec sections 31–43.
- Output: active milestone contract, frozen manifest, rule enforcement, CI gates, templates, draft report.

## Acceptance criteria
- [ ] Current Milestone is machine-readable and constrains changed paths.
- [ ] Frozen manifest hashes every existing normative artifact and rejects unlisted future v0.2 schema files.
- [ ] Rule registry identifies implemented M0 gates and defers business rules honestly.
- [ ] Blocking CI runs governance checks and unit tests, including negative cases.
- [ ] Independent Audit Pass and completion report precede FROZEN status.

## Required tests
- governance unit tests
- frozen hash and manifest completeness
- milestone path admission
- rule registry consistency
- CI gate execution

## Golden subset
none; no Golden Set exists in M0.

## Change policy
Any frozen dependency change requires an APPROVED Change Request.

## Completion report
Required before FREEZE.
