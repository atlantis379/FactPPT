# Reference Pipeline Reading Audit Checklist v0.1

> **STATUS: SUPERSEDED by `REFERENCE_PIPELINE_READING_AUDIT_CHECKLIST_v0.2.md`.**
> Retained for the version chain. Its checks were bound to one material's language and domain.


**Status:** `ACTIVE_SKILL_CHECKLIST`

**Companion to:** `SOURCE_READING_AND_STRUCTURE_DERIVATION_POLICY_v0.1.md`

**When to run:** after `W01` extraction, before `W02` structured evidence. Mandatory. A run may not proceed to `W07 PageSpec` without a completed instance of this checklist.

---

## A. Reading actually happened

| # | Check | Pass condition | Record |
|---|---|---|---|
| A1 | `reading_mode` | `FULL_TEXT_READ` | — |
| A2 | blocks read | `blocks_read == blocks_total` | numbers |
| A3 | characters read | `chars_read / chars_total >= 0.98` | ratio |
| A4 | structure derivation | `LLM_SEMANTIC_SYNTHESIS` | — |
| A5 | reading order | blocks were read in source order, not sampled by keyword | statement |

## B. Block inventory and traceability

| # | Check | Pass condition | Record |
|---|---|---|---|
| B1 | every block present | block count equals extraction block count | numbers |
| B2 | no block dropped | every block has `coverage` in {`in_deck`, `evidence_only`} | count |
| B3 | attribution | every block has `structure_node_ids`, or `orphan_reason` | orphan count |
| B4 | exclusion retention | every `evidence_only` block has `evidence_only_reason` and a retention reference | count |
| B5 | per-block judgement | every block has `role`; `relation` with `relation_status`; `signals` counted by code | — |

## C. Structure quality

| # | Check | Pass condition | Record |
|---|---|---|---|
| C1 | thread stated | `structure.thread` present, in the reader's own words, >= 20 chars | quote |
| C2 | motivation stated | `opening_motivation` recorded where the source provides one | quote |
| C3 | `why_here` usable | every node's `why_here` names a question answered or a role in the thread; no node says "because the source has this heading" | failures |
| C4 | **not the source's TOC** | node order differs from the source's heading order, **or** at least one node's `why_here` references another node | statement |
| C5 | node grounding | every node has non-empty `source_block_ids` | — |
| C6 | emphasis declared | every node has `emphasis_basis` | counts by basis |

## D. Five falsifiable checks

Each row must report `PASS`, `FAIL` or `NOT_CHECKED`, **with the method stated**. `PASS` without a describable failure mode is invalid.

| # | Dimension | Fails when | Result |
|---|---|---|---|
| D1 | thread | §4.1 of the policy | |
| D2 | emphasis | a key node has no block with `emphasis_terms >= 2` or `numeric_facts >= 3`; **or** a block with `emphasis_terms >= 3` / `numeric_facts >= 4` sits in `evidence_only` without declaration | |
| D3 | difficulty | a block with >= 2 difficulty flags has no page or only a plain-list page; **or** an `assumed_concept` is nowhere resolved | |
| D4 | summary | a unit over 10% of source characters has less than half its share of pages without `coverage_declaration`; **or** a summary assertion has no source block | |
| D5 | logic | a causal / staged page rests only on `INFERRED` relations; **or** an explicit contrast marker is rendered as parallel enumeration | |

## E. Coverage declaration

| # | Check | Pass condition |
|---|---|---|
| E1 | divergence declared | any >2× divergence between character share and page share has `coverage_declaration` |
| E2 | basis recorded | `coverage_declaration.basis` is one of the enumerated values |
| E3 | exclusion retained | `excluded_content_retained` is true and an evidence store reference exists |
| E4 | homework / objective reverse test | the source's own questions or stated objectives can be answered from declared coverage |

## F. Check integrity

| # | Check | Pass condition |
|---|---|---|
| F1 | no silent pass | no check reported `PASS` without a method |
| F2 | failures recorded | every failing check lists its failures with locators |
| F3 | **defective checks corrected, not weakened** | every check correction records the defect and the corrected test |
| F4 | rerun after correction | corrected checks were re-run and the new result recorded, with both counts |

## G. Page linkage

| # | Check | Pass condition |
|---|---|---|
| G1 | page-to-block link exists | every page carries `source_block_ids` |
| G2 | link is checkable | the link was produced by a stated method, not asserted |
| G3 | unlinked pages declared | a page with no source block (e.g. a synthesised conclusion) is marked as synthesised rather than left blank |

## H. Disposition

| # | Check | Pass condition |
|---|---|---|
| H1 | disposition | one of `READING_STRUCTURE_ACCEPTED`, `READING_STRUCTURE_ACCEPTED_WITH_DECLARED_GAPS`, `READING_STRUCTURE_REJECTED` |
| H2 | gaps declared | `ACCEPTED_WITH_DECLARED_GAPS` only when every open failure has a declaration or a recorded remediation |
| H3 | downstream validity | no page was designed before acceptance |

---

## Machine check

```bash
python scripts/skill_tool.py reading-structure READING_STRUCTURE_ARTIFACT.json
```

The gate validates the artifact against `schemas/reading_structure_artifact.v0.1.schema.json` and applies the deterministic subset of the checks above: reading completeness, block presence and attribution, `why_here` admissibility, `EXPLICIT` relation evidence, difficulty-to-figure, coverage declaration, check-integrity, and page linkage. Judgement fields (`thread` quality, `why_here` usefulness, difficulty reasons) remain reviewer-assessed; the gate records that it did not assess them.

## Not to be claimed

- A passing gate does not mean the reading was good; it means the reading was complete and traceable.
- A passing gate does not mean the structure is correct. Only `C4` and `D1`'s counter-example test begin to probe that, and they are necessary, not sufficient.
- This checklist does not verify medical content. It verifies that a reading happened, that its claims are traceable, and that its judgements are declared.
