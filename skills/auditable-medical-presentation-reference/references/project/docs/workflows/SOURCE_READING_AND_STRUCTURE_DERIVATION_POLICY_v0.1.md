# Source Reading and Structure Derivation Policy v0.1

> **STATUS: SUPERSEDED by `SOURCE_READING_TO_NARRATIVE_DERIVATION_POLICY_v0.2.md`.**
>
> v0.1 is retained for the version chain only. Its method was correct and is carried forward
> unchanged; its **scope was bound to one material** — the role vocabulary, marker lists and
> difficulty names served a single language and domain, while the header claimed applicability to
> "textbooks, guidelines, papers, reports, slide sources". A rule that only fits the material in
> front of it is a habit, not a rule.
>
> Do not start a run from this file. Runs built on v0.1 may not claim `APPROVED_REFERENCE_OUTPUT`.
> Reason for supersession: portability (`REG-READ-013` in v0.2).

**Status:** `SUPERSEDED_NOT_ACTIVE`

**Stage:** `W01-R` (additive sub-stage of the frozen W00–W18 sequence; the W-numbers of W00–W18 are unchanged)

**Applies to:** every run that derives structure from a source document — textbooks, guidelines, papers, reports, slide sources.

---

## 1. Purpose

Establish structure from a reading of the source, and make that reading auditable, before any page is designed.

Page design is downstream of structure. If the structure is wrong, every page inherits the error and no amount of visual work repairs it. The failure mode this policy exists to prevent is specific and common:

> A structure produced by splitting the source on its own heading markers, page boundaries or regular expressions is a **table of contents**, not a reading. It reproduces the source's organisation, carries no argument, cannot say what matters or what is hard, and provides no basis for ordering pages.

### Governing principle

> **Structure is derived by reading. Code verifies that the reading happened and that its claims are traceable — code does not produce structure.**

Reading, thread derivation, emphasis judgement, difficulty judgement and relationship assignment are semantic acts. Block inventory, character accounting, signal counting, traceability and coverage accounting are deterministic and belong to code. Neither may do the other's job:

- code must not be asked to infer a thread, a relationship or a difficulty;
- a language model's assertion that it "read and understood" is not evidence, and must be replaced by a traceable per-block record plus checks that can fail.

## 2. Required execution order

```text
W01  source extraction (page text, page images, block inventory)
  ↓
W01-R  SOURCE READING AND STRUCTURE DERIVATION        <-- this policy
  R1  full-text read pass over every extracted block
  R2  per-block record: role, relation + status, signals, difficulty, coverage
  R3  semantic structure synthesis: thread, opening motivation, nodes with why_here
  R4  five falsifiable checks (thread / emphasis / difficulty / summary / logic)
  R5  coverage declaration when page share diverges from character share
  ↓
W02  structured evidence layer
  ↓
W03+ (unchanged)
```

`W01-R` must complete before `W02`. Evidence objects built on an unreviewed structure propagate the structure's errors into every later stage.

A run that reaches `W07 PageSpec` without a `W01-R` artifact is invalid, regardless of how the pages look.

## 3. Object model

The artifact is `reading_structure_artifact.v0.1` (schema in `schemas/`). Required parts:

| Part | Content | Owner |
|---|---|---|
| `source` | filename, SHA256, page count | code |
| `reading_pass` | `reading_mode`, blocks/chars read vs total, `structure_derivation` | code |
| `blocks[]` | one record per extracted block (see 3.1) | code for counts, model for judgement |
| `structure` | `thread`, `opening_motivation`, `nodes[]` with `why_here` | model |
| `checks` | five check results with method and failures | code applies, model supplies judgements |
| `coverage_declaration` | required when page share diverges from character share | model |
| `disposition` | one of the three accepted values | model |

### 3.1 Required fields per block

| Field | Rule |
|---|---|
| `block_id`, `page`, `chars` | stable identity; a block may never be dropped |
| `role` | from the closed set: definition, mechanism, classification, diagnosis, treatment, prognosis, prevention, pathology, epidemiology, other |
| `relation` | from the closed set: causal, progressive, contrast, example, exception, whole_part, unmarked |
| `relation_status` | `EXPLICIT` (with `relation_evidence` quoting the marker) or `INFERRED` |
| `signals` | `emphasis_terms`, `numeric_facts` — counted by code, not asserted |
| `difficulty[]` | from the closed set in §5 |
| `coverage` | `in_deck` or `evidence_only`; `evidence_only` requires `evidence_only_reason` |
| `structure_node_ids` | the structure nodes this block supports; empty requires `orphan_reason` |

### 3.2 Required fields per structure node

| Field | Rule |
|---|---|
| `node_id`, `label` | stable identity |
| `why_here` | **the question this node answers, or its role in the thread.** "Because the source has this heading" is not an acceptable value and must be rejected |
| `source_block_ids` | non-empty; the blocks that ground the node |
| `emphasis_basis` | `SYLLABUS`, `SOURCE_SIGNAL`, `BOTH` or `NONE` — declared, never implied |
| `difficulty_basis` | the difficulty this node exists to resolve, if any |

## 4. Mandatory audit dimensions

Five dimensions, each with a check that **must be able to report FAIL**. A check whose failure mode cannot be stated is recorded `NOT_CHECKED`, never `PASS`.

### 4.1 Thread (`checks.thread`)

Fails when any of the following holds:

- `reading_mode` is not `FULL_TEXT_READ`, or `blocks_read < blocks_total`, or `chars_read / chars_total < 0.98`;
- any block has neither `structure_node_ids` nor `orphan_reason`;
- the node order equals the source's own heading order **and** no node supplies a `why_here` that refers to another node (i.e. the "structure" is the source's table of contents);
- `structure.thread` is absent, shorter than 20 characters, or restates the source's section titles.

### 4.2 Emphasis (`checks.emphasis`)

Fails when any of the following holds:

- a node claims importance with `emphasis_basis = NONE`;
- a node claims importance with `emphasis_basis = SYLLABUS` but the run does not declare that the basis is external;
- a node marked important contains no block with `emphasis_terms >= 2` or `numeric_facts >= 3`;
- **counter-example test:** a block with `emphasis_terms >= 3` or `numeric_facts >= 4` is in `evidence_only` and no `coverage_declaration` explains it.

### 4.3 Difficulty (`checks.difficulty`)

Fails when any of the following holds:

- a block carrying two or more difficulty flags receives no page, or receives a page whose figure is a plain list;
- any block flagged `assumed_concept` has no place in the deck or evidence store where the concept is resolved;
- the difficulty vocabulary is used without a per-block reason.

### 4.4 Summary (`checks.summary`)

Fails when any of the following holds:

- for any unit whose character share exceeds 10% of the source, its page share is less than half its character share, and no `coverage_declaration` explains the divergence;
- a summary or conclusion asserts content with no source block behind it (checks against `structure_node_ids`);
- **reverse test:** the source's own end-of-unit questions or stated objectives cannot be answered from the deck's declared coverage.

### 4.5 Logic (`checks.logic`)

Fails when any of the following holds:

- a page presents a causal, sequential or staged relationship while every block behind that page has `relation_status = INFERRED` — the relationship is the reader's, and presenting it as the source's is a fabrication;
- a block whose `relation = unmarked` is rendered as cause, sequence or progression without an `INFERRED` declaration;
- **counter-example test:** a block containing an explicit contrast marker (`但`, `然而`, `不过`) is presented as a parallel enumeration.

## 5. Difficulty vocabulary

Difficulty is judged from the text, with a reason recorded per block:

| Flag | Signal in the source |
|---|---|
| `assumed_concept` | a technical term used without definition at first use |
| `multi_step_mechanism` | a mechanism with three or more ordered steps or conditions |
| `confusable_pair` | content the source itself contrasts, or warns is easily mistaken |
| `numeric_dense` | three or more numeric facts in one block |
| `negation_or_exception` | "不…", "除外", "不包括", "无…征象" |
| `long_causal_chain` | a causal chain spanning more than one block |
| `cross_section_link` | the source explicitly links this content to content elsewhere |

A passage carrying two or more flags must receive, at minimum, a structured figure rather than a plain list, and should receive more space than an unflagged passage of equal length.

## 6. Emphasis provenance

Importance has exactly two admissible origins and they must not be conflated:

- **`SOURCE_SIGNAL`** — the source itself marks it: emphasis terms, repetition, elaboration depth, numeric density, position.
- **`SYLLABUS`** — an external authority (teaching outline, exam syllabus, scope document) marks it.

`SYLLABUS` is legitimate and often decisive for teaching material, but it is **external**. A run that lets syllabus-driven selection change page allocation must record `coverage_declaration.basis = SYLLABUS_MASTERY_SPLIT`, state the rationale, and confirm excluded content is retained in an evidence store. Without this record, a reader cannot distinguish a deliberate pedagogical choice from an oversight.

## 7. Coverage and exclusion

- No block may vanish. Every block ends as `in_deck` or `evidence_only`.
- `evidence_only` is a **retention** status, not a deletion. Excluded content must remain retrievable, per the full-source coverage policy.
- Page allocation follows the source's content distribution unless a `coverage_declaration` says otherwise. Divergence without declaration is a failure of §4.4.

## 8. Relationship to other policies

| Policy | Relationship |
|---|---|
| `FULL_SOURCE_EVIDENCE_COVERAGE_POLICY_v0.1` | W01-R supplies the block inventory that policy's coverage accounting presupposes |
| `NARRATIVE_RATIONALITY_AUDIT_POLICY_v0.1` | W06-NR audits the narrative; W01-R supplies the thread it audits. A W06-NR pass on a heading-scan structure is meaningless |
| `NARRATIVE_TO_PAGE_DECOMPOSITION_AUDIT_POLICY_v0.1` | W06-NP allocates pages; W01-R's emphasis and difficulty judgements are its input |
| `PAGESPEC_VISUAL_STRATEGY_DERIVATION_POLICY_v0.1` | W11 derives visual strategy from page purpose; W01-R's `relation` and `difficulty` fields state that purpose |
| `REFERENCE_PIPELINE_WORKFLOW_v0.1` | this policy adds stage `W01-R`; W00–W18 numbering is unchanged |

## 9. Rules

| ID | Rule |
|---|---|
| `REG-READ-001` | Structure must be derived by reading the full extracted text. Heading-marker splitting, page splitting and regex segmentation may inventory the source but may never constitute the structure. |
| `REG-READ-002` | Every extracted block must appear in the artifact exactly once, with a coverage status. Silent omission is forbidden. |
| `REG-READ-003` | Every structure node must state `why_here` as the question it answers or its role in the thread. Source headings are not admissible. |
| `REG-READ-004` | The structure must declare `thread` in the reader's own words. If the thread cannot be stated, the reading is incomplete and the artifact must be `READING_STRUCTURE_REJECTED`. |
| `REG-READ-005` | Importance must declare `emphasis_basis`. `SYLLABUS` is external and must be accompanied by a `coverage_declaration`. |
| `REG-READ-006` | Relationships are `EXPLICIT` only when `relation_evidence` quotes the source marker. `INFERRED` relationships may not be presented to the audience as the source's own. |
| `REG-READ-007` | A passage with two or more difficulty flags must not be rendered as a plain list. |
| `REG-READ-008` | Page allocation diverging by more than 2× from character share requires `coverage_declaration`, and excluded content must be retained. |
| `REG-READ-009` | All five checks must report `PASS`, `FAIL` or `NOT_CHECKED` with a stated method. A check may not be reported `PASS` without a describable failure mode. |
| `REG-READ-010` | A check that fails must be recorded with its failures; failures may not be cleared by weakening the check. A defective check is corrected and the check re-run, and the correction is recorded. |
| `REG-READ-011` | No page may be designed before `W01-R` reaches `READING_STRUCTURE_ACCEPTED` or `READING_STRUCTURE_ACCEPTED_WITH_DECLARED_GAPS`. |
| `REG-READ-012` | Page-to-source linkage must be recorded explicitly (`source_block_ids` per page). A page whose source blocks are not recorded cannot be audited later. |

## 10. Regression case (recorded from the first application of this policy)

The first application, to a 25-page scanned textbook chapter (298 blocks / 37,393 characters), produced these results. They are recorded because each demonstrates a distinct failure this policy must catch.

| Observation | Meaning |
|---|---|
| A regex structure tree localised only 226/298 blocks to a section and no block to anything finer — 76% of content had no node below "somewhere in this section". | §4.1. The "structure" gave pages nothing to attach to. |
| The node order was identical to the textbook's own section order. | §4.1. A table of contents, not a reading. |
| A full read then revealed a through-line the source never states: pathogen property → pathology → imaging → drug choice, repeated in every section. The earlier structure had rendered the sections as six parallel knowledge groups and lost it entirely. | `REG-READ-004`. This is the specific loss the policy exists to prevent. |
| The source's own opening contradiction, its explicit reason for preferring one classification axis, and its causal argument that poor pathogen detection is why empirical therapy dominates were all absent from the deck. | Structure without a reading loses the argument while keeping the facts. |
| Page allocation gave 10% of pages to a section holding 27% of the source's characters, and 0% to one holding 13%, with no record of the choice. | §4.4 / `REG-READ-005`. The choice was legitimate (it followed the external syllabus) but undocumented. |
| Three of the ten initial checks were later found defective: a relation detector that scanned only the first 60 characters, an attribution test that mislabelled ordinary body blocks, and pages with no link to source blocks at all. Correcting them moved the reported failure count from 431 to 129. | `REG-READ-010`. A failing check is as likely to be a defective check as a defective artifact; both must be recorded, and neither may be cleared by weakening the test. |

## 11. Audit record minimum

Record, per run:

- artifact identity and SHA256;
- `reading_mode`, blocks read / total, characters read / total;
- the thread statement;
- per dimension: status, method, failure count;
- every `coverage_declaration` with its basis;
- every check correction, with the defect and the corrected test;
- disposition.

## 12. Failure and disposition

Dispositions: `READING_STRUCTURE_ACCEPTED`, `READING_STRUCTURE_ACCEPTED_WITH_DECLARED_GAPS`, `READING_STRUCTURE_REJECTED`.

`ACCEPTED_WITH_DECLARED_GAPS` is available only when every open failure carries a `coverage_declaration` or a recorded remediation. An undeclared gap is a rejection.

A structure-changing correction returns to `R1` and rebuilds `R2`–`R5`. Downstream stages that consumed the structure are invalidated to their dependent scope.
