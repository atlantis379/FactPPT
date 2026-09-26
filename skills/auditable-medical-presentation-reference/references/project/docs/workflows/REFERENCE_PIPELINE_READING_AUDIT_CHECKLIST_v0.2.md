# Reference Pipeline Reading Audit Checklist v0.2

**Status:** `ACTIVE_SKILL_CHECKLIST`

**Companion to:** `SOURCE_READING_TO_NARRATIVE_DERIVATION_POLICY_v0.2.md`; index: `W01R_RULE_COMPILATION_v1.0.md`

**Supersedes:** `REFERENCE_PIPELINE_READING_AUDIT_CHECKLIST_v0.1.md` (material-bound; retained for the version chain).

**When to run:** after extraction, before structured evidence. Mandatory. No page may be designed before this checklist is complete and the artifact is accepted.

**Applies to:** any material. Language, domain roles and marker lexicons are **declared in `profile`** and checked for declaration here — they are never assumed.

---

## A. Profile declared

| # | Check | Pass condition |
|---|---|---|
| A1 | material kind | `profile.material_kind` declared |
| A2 | language | `profile.language` declared |
| A3 | role vocabulary | every `role` used in blocks is a core role **or** appears in `role_vocabulary.extensions` |
| A4 | signal lexicon | `emphasis_markers` and `fact_pattern` declared; counts reproducible from them |
| A5 | relation lexicon | markers declared per relation type; a relation without a marker is `INFERRED` |
| A6 | no hidden domain binding | no language- or domain-specific vocabulary exists outside `profile` |

## B. Reading happened

| # | Check | Pass condition |
|---|---|---|
| B1 | mode | `reading_mode == FULL_TEXT_READ` |
| B2 | blocks | `blocks_read == blocks_total` |
| B3 | characters | `chars_read / chars_total >= 0.98` |
| B4 | derivation | `structure_derivation == LLM_SEMANTIC_SYNTHESIS` |
| B5 | order | read in source order; relevance decided after reading, never before |
| B6 | **per run** | `executed_for_run` names **this** run. The reading was performed for it, not carried over from an earlier one (`REG-READ-018`) |
| B7 | **from this source** | `read_from_sha256` equals `source.sha256`: the bytes read are the bytes in hand |
| B8 | **not reused** | `reused_from` is empty. No cache keyed by source hash, frozen or `authored` answer file, replayed endpoint response, or previously accepted artifact served as this run's reading. A prior reading used as a **comparison baseline** is recorded as such and is not this run's reading |

## C. Blocks and traceability

| # | Check | Pass condition |
|---|---|---|
| C1 | completeness | block count equals extraction count |
| C2 | no drop | every block has `coverage` in {`in_deck`, `evidence_only`} |
| C3 | attribution | every block has `structure_node_ids` or `orphan_reason` |
| C4 | exclusion retained | every `evidence_only` block has a reason and a retention reference |
| C5 | relations | `EXPLICIT` relations carry `relation_evidence` quoting the declared lexicon |
| C6 | allocation recorded | every `in_deck` block lists the `page_ids` it was allocated to |

## D. Structure

| # | Check | Pass condition |
|---|---|---|
| D1 | thread | stated in the reader's own words, >= 20 chars |
| D2 | motivation | the material's own opening problem/question recorded where it has one |
| D3 | `why_here` | every node names a question answered or a role in the thread; no node cites the material's own heading |
| D4 | not a table of contents | node order differs from source order, **or** the narrative justifies keeping it |
| D5 | grounding | every node has non-empty `source_block_ids` |
| D6 | emphasis basis | every node declares `MATERIAL_SIGNAL` / `EXTERNAL_AUTHORITY` / `BOTH` / `NONE`; external authority is named |

## E. Narrative

| # | Check | Pass condition |
|---|---|---|
| E1 | order declared | `narrative_order` non-empty and every id resolves to a node |
| E2 | difference handled | if order equals source order, `difference_reason` states why that order is correct; otherwise states what the new order accomplishes |
| E3 | audience question | the question the deck answers is stated |
| E4 | step linkage | each step answers the question the previous step raised |

## F. Allocation

| # | Check | Pass condition |
|---|---|---|
| F1 | every page grounded | each page has `source_block_ids` |
| F2 | every page reasoned | `why_this_page` states why the page exists, not what it contains |
| F3 | action titles | `action_title` is a sentence stating a takeaway, not a topic label |
| F4 | figure intent | `figure_intent` declared for every page before layout |
| F5 | difficulty served | a block with >= 2 difficulty flags is not allocated to a page whose intent is `NONE` |
| F6 | distribution | allocation follows content distribution, or a `coverage_declaration` explains it |
| F7 | **surface layer** | every `on_slide_text` string is presentation language: no citation marker, block reference, internal id, audit locator, editorial label, elided quotation, or commentary on the deck's own structure |
| F8 | layer separation | `speaker_notes` carries the working layer (why the page exists, source ids, quoted source, difficulty notes) |
| F9 | **structure rendered** | a roadmap page states the thread and the parts; each part boundary carries the question that part answers; every narrative node is exposed by some page; a consolidation page closes the argument; page order follows the declared narrative order |

## G. Seven checks

Each must report `PASS` / `FAIL` / `NOT_CHECKED` **with a stated method**. `PASS` without a describable failure mode is invalid.

| # | Dimension | Machine-checked by the gate | Reviewer-assessed |
|---|---|---|---|
| G1 | thread | completeness, attribution, order-vs-source | thread quality |
| G2 | emphasis | basis declared; signal floor; counter-example | whether the emphasis is right |
| G3 | difficulty | flags valid; hard blocks not unallocated | whether the reasons are sound |
| G4 | summary | distribution vs character share | whether the summary is faithful |
| G5 | logic | `EXPLICIT` evidence present for causal/staged pages | whether the relation is correctly read |
| G6 | narrative | order non-empty; difference or justification | whether the order actually works |
| G7 | allocation | blocks, reason, intent present; intent not `NONE` for hard blocks | whether the intent is the right one |
| G8 | surface | no working-layer mark found in `on_slide_text` | whether the on-slide wording is clear and final |
| G9 | structure_rendered | roadmap / section-question / consolidation pages exist; all narrative nodes exposed; page order monotone with narrative order | whether the rendered structure actually helps the reader |

## H. Check integrity and disposition

| # | Check | Pass condition |
|---|---|---|
| H1 | no silent pass | no check reports `PASS` without a method |
| H2 | failures recorded | each failing check lists failures with locators |
| H3 | defective checks corrected, not weakened | each correction records the defect and the corrected test, with both results |
| H4 | disposition | one of the three accepted values |
| H5 | gaps declared | `ACCEPTED_WITH_DECLARED_GAPS` only when every open failure carries a declaration or remediation |
| H6 | downstream validity | no page designed before acceptance |

---

## Machine check

```bash
python scripts/skill_tool.py reading-structure READING_STRUCTURE_ARTIFACT.json --run-id RUN_ID
```

Validates against `schemas/reading_structure_artifact.v0.2.schema.json` and applies the deterministic subset of A–H: profile declaration, reading completeness, **reading freshness against the run id (B6–B8)**, block presence and attribution, role admissibility against core + declared extensions, relation evidence, difficulty-to-intent, narrative declaration, page allocation completeness, and check integrity. The gate reports the judgement fields it did **not** assess.

**`--run-id` and honesty about freshness.** Supplied, the gate fails a reading whose `executed_for_run` is not that run, whose `read_from_sha256` is not the source's hash, or whose `reused_from` is set (B6–B8). Omitted, the gate **cannot** exercise that failure mode, so it reports `reading_pass:FRESHNESS_NOT_VERIFIED` under `not_assessed_by_this_gate` — never PASS. A run that wants B6–B8 certified passes its run id; a run that omits it has certified completeness only.

## Portability

The same gate, unchanged, has been run on:

| Material | Kind | Units | Blocks | Result |
|---|---|---|---|---|
| clinical textbook chapter (zh-CN) | `MEDICAL_SOURCE` | 25 pages | 298 | PASS |
| technical R&D report (zh-CN) | `TECHNICAL_REPORT` | 20 slides | 20 | PASS |

Only `profile` differed. A checklist item that cannot be satisfied without editing the method is a signal that `profile` is missing a field — not that the material needs a special case.

## Not to be claimed

- A passing gate does not mean the reading was good; it means the reading was complete and traceable.
- A passing gate does not mean **this run** read the source. B6–B8 are established only when `--run-id` is supplied; without it the gate reports `NOT_CHECKED` and states so. A reading carried over from an earlier run can pass every other criterion. **If you did not pass a run id, you have certified completeness only — say that, do not say "the source was re-read".**
- A passing gate does not mean the structure or narrative is correct. Only the counter-example tests begin to probe that, and they are necessary, not sufficient.
- This checklist does not verify domain content. It verifies that a reading happened, that its claims are traceable, and that its judgements are declared.
