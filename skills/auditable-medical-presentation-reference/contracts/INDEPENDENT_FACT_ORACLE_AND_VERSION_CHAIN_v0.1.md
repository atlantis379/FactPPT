# Independent Fact Oracle and Version Chain v0.1

Status: `ACTIVE_SKILL_CONTRACT_NOT_FROZEN_SPEC`

This contract operationalizes independent truth review and explicit correction/version handling without changing frozen rules or stage numbers.

## W02-FSC-O independent oracle sub-gate

The extractor cannot certify its own denominator. Before W02-FSC can PASS, create a `FactOracleReview` with:

- exact source SHA-256 and actual page denominator;
- extraction run/identity and different review run/identity;
- one review record for every page, including confirmed blank/non-substantive pages;
- anchored fact inventory, with all RED facts explicitly approved;
- disagreement and resolution records;
- reviewer attestation and time.

The deterministic gate proves agreement with this reviewed oracle only. It does not prove that a reviewer made a clinically correct judgment. If the denominator is UNKNOWN/PARTIAL, any disagreement is unresolved, or independence cannot be established, the result is not PASS.

## W00-VC source version and correction sub-gate

Record document nodes, explicit `CORRECTED_BY | AMENDED_BY | SUPERSEDED_BY` edges, correction-notice anchors, effective source IDs and claim-level old/effective fact pairs. Publication date or perceived authority alone cannot create a supersession edge.

Each correction preserves:

- the old fact as `SUPERSEDED`;
- a distinct new claim/version as `EFFECTIVE`;
- the correction notice anchor;
- the effective source identity;
- exclusion of the old claim from the effective claim index.

Cycles, unanchored edges, non-versioned fact IDs or superseded facts remaining effective block downstream authority. A whole document can remain historically relevant while a specific claim is superseded.

Run:

```text
python scripts/skill_tool.py fact-oracle FACT_ORACLE_REVIEW.json
python scripts/skill_tool.py source-chain SOURCE_VERSION_CHAIN.json
```

