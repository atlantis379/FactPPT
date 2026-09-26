# W01-R Rule Compilation v1.0

**Status:** `STABLE_NOT_FROZEN_SPEC`

**Scope:** the `W01-R` stage — source reading, structure derivation, narrative ordering and page allocation.

**Authority:** `SOURCE_READING_TO_NARRATIVE_DERIVATION_POLICY_v0.2.md` is the normative text. This compilation is the index and the verification record.

**Relationship to the frozen set:** these rules are **not** part of the 178 frozen Module 01–06 rules. `frozen_specs_changed` remains `false`. W01-R is an additive sub-stage; W00–W18 numbering is unchanged.

**Why this document exists:** the rules were added across six skill versions (v0.10.0 → v0.13.0). This compilation is the single authoritative statement of what now stands, what enforces each rule, and what was corrected along the way.

---

## 1. The rule set

Eighteen rules. "Enforced by" names the mechanism that can actually fail; "Reviewed by" names what no mechanism checks.

| ID | Rule | Enforced by | Reviewed by |
|---|---|---|---|
| `REG-READ-001` | The full extracted text must be read. Heading-marker, page or regex splitting may inventory the material but never constitutes the structure. | gate: `reading_pass` completeness + `reading_mode` + `structure_derivation` | whether the reading was adequate |
| `REG-READ-002` | Every extracted block appears exactly once with a coverage status. Silent omission forbidden. | gate: coverage enum, attribution, evidence-only reason | — |
| `REG-READ-003` | Every node states `why_here` as a question answered or a role in the thread. Source headings inadmissible. | gate: `why_here` length + inadmissible-phrase list | whether the answer is a real answer |
| `REG-READ-004` | The thread must be stated in the reader's own words; if it cannot be stated, disposition is `REJECTED`. | schema: `thread` minLength 20 | whether the thread captures the argument |
| `REG-READ-005` | Emphasis declares `emphasis_basis`; `EXTERNAL_AUTHORITY` names the authority and requires a `coverage_declaration`. | gate: basis enum, named authority, declaration presence | whether the emphasis is right |
| `REG-READ-006` | A relation is `EXPLICIT` only when `relation_evidence` quotes the material's marker. | gate: explicit-without-evidence | whether the relation was read correctly |
| `REG-READ-007` | A block with two or more difficulty flags is not rendered as a plain list. | gate: flag validity; difficulty-served on intent-NONE | whether the reasons are sound |
| `REG-READ-008` | Allocation diverging more than 2× from character share requires a `coverage_declaration`; excluded content is retained. | gate: high-signal / high-difficulty without declaration | whether the divergence is justified |
| `REG-READ-009` | All checks report `PASS`/`FAIL`/`NOT_CHECKED` with a stated method. `PASS` without a describable failure mode is invalid. | gate: pass-without-method, fail-without-failures, NOT_CHECKED propagation | — |
| `REG-READ-010` | Failures are recorded; failures may not be cleared by weakening the check. A defective check is corrected, re-run, and recorded with both results. | this compilation, §3 | — |
| `REG-READ-011` | No page may be designed before the artifact is accepted. | process; disposition enum | — |
| `REG-READ-012` | Page-to-block linkage is recorded explicitly. | gate: page without source blocks or declaration | — |
| `REG-READ-013` | Everything material-specific is declared in `profile`. A method that hard-codes a language or domain vocabulary is out of compliance. | gate: profile completeness; roles against core + declared extensions | — |
| `REG-READ-014` | The narrative states how its order differs from source order and what the difference accomplishes. An identical order requires justification. | gate: source-order-without-justification | whether the order works |
| `REG-READ-015` | Every page states `why_this_page` and `figure_intent` before layout. | gate: reason length; intent enum | whether the intent is the right one |
| `REG-READ-016` | The slide surface carries presentation language only: no citation marker, block reference, internal id, audit locator, editorial label, elided quotation, or commentary on the deck's own structure. | gate: seven working-layer mark classes over `on_slide_text` | whether the wording is clear and final |
| `REG-READ-017` | The derived structure must be rendered, not merely declared: a roadmap page, the question at each part boundary, every narrative node exposed by some page, and a consolidation page. | gate: `structure_rendered` — presence, node exposure, page/narrative order agreement | whether the rendered structure helps the reader |
| `REG-READ-018` | **Every generation run reads the source again.** M1–M4 are performed afresh for each deck; a cache, frozen/`authored` answer file, replayed endpoint response or previously accepted artifact may not serve as this run's reading. A prior reading may be a declared comparison baseline, never a substitute. | gate: `reading_pass` freshness — `executed_for_run` vs the run id, `read_from_sha256` vs `source.sha256`, `reused_from` empty. **Requires `--run-id`; omitted, it reports NOT_CHECKED, never PASS.** | whether the reading was genuinely this run's |

## 2. The nine checks

| Check | Deterministic part (gate) | Judgement part (reviewer) |
|---|---|---|
| `thread` | reading completeness, attribution, order-vs-source | thread quality |
| `emphasis` | basis declared, signal floor, counter-example | whether the emphasis is right |
| `difficulty` | flag validity, hard block allocation | whether the reasons are sound |
| `summary` | distribution vs character share | whether the summary is faithful |
| `logic` | `EXPLICIT` evidence for causal/staged pages | whether the relation is read correctly |
| `narrative` | order non-empty, difference or justification | whether the order works |
| `allocation` | blocks, reason, intent present | whether the intent is right |
| `surface` | seven working-layer mark classes | whether the wording is clear |
| `structure_rendered` | roadmap / section-question / consolidation presence, node exposure, order agreement | whether it helps the reader |

**The gate declares its own scope.** Every result carries `gate_scope` and `not_assessed_by_this_gate`. A passing gate means the reading was complete and traceable; it does not mean it was good.

## 3. Corrected gate defects

Four defects were found in the gate itself while applying it. Each was corrected and re-run, both states retained, and no criterion was relaxed. This is the record `REG-READ-010` requires.

| # | Defect | Symptom | Correction |
|---|---|---|---|
| 1 | Relation detection scanned only `text[:60]` | a block whose causal marker sits later was recorded `unmarked`; check `logic` failed 3 pages that did have explicit evidence | scan the whole block |
| 2 | Attribution test used "has a structural marker" | 226 ordinary body blocks were reported as unattributed | test attribution to a section instead |
| 3a | `page_plan[].source_block_ids` required at least one item | cover / section-divider / closing pages have no source block and were reported as errors — a defect of the criterion, not of the plan | allow empty **only** with `synthesised_reason`; a silently empty page still fails |
| 3b | `page_plan[].action_title` required ≥6 characters of every page | a section divider has a **label**, not a takeaway ("肺炎概述" = 4 characters) | content pages require `action_title`; structure pages declare `section_label` |
| 4 | `structure_rendered` / `surface` enforcement ignored the check's own `NOT_CHECKED` status | an artifact that declared a check out of scope was still failed on it | `NOT_CHECKED` propagates to `not_assessed_by_this_gate`, not to errors |

**Pattern.** Three of the four were the same mistake: a criterion written for one page or check kind applied to all of them. When a rule fails on work that satisfies it, suspect the rule before the work — and record which it was.

**Initial measurement on the first application:** 431 reported failures, of which 302 were these defects. After correction: 129 real failures. A gate that reports three times the truth is worse than no gate, because it teaches its operators to ignore it.

## 3a. Addition: a reading belongs to a run (`REG-READ-018`)

**Defect that forced it.** The pipeline was tested by running different drivers over one material and observing that they produced the same deck. The observation was true and empty: the content lived in frozen `authored` answer files, so the drivers were runners, not readers. Every completeness criterion was satisfied — `reading_mode`, `blocks_read == blocks_total`, `chars_read / chars_total >= 0.98`, `structure_derivation` — while no reader had met the material. The comparison had measured a fixture's stability and reported it as reader agreement.

**What was added.**

| Layer | Addition |
|---|---|
| Policy | `REG-READ-018` (rule) and §9c (the failure mode, the three reuse forms, what reuse remains legitimate) |
| Schema | `reading_pass.executed_for_run`, `reading_pass.read_from_sha256`, `reading_pass.reused_from` |
| Gate | `reading_pass:NOT_READ_FOR_THIS_RUN`, `reading_pass:READ_FROM_A_DIFFERENT_SOURCE`, `reading_pass:READING_REUSED_FROM_PRIOR_ARTIFACT`; CLI `--run-id` |
| Checklist | B6 per run, B7 from this source, B8 not reused |

**Beyond completeness this cannot go.** The gate cannot discover which run it is validating, so the run id is supplied by the caller. Supplied, the three failure modes above are exercised. **Omitted, freshness is `NOT_CHECKED` — never PASS** — and the gate says so in `not_assessed_by_this_gate`. That is the honest status, but it is a real limit: a caller that omits `--run-id` has certified completeness only. A run that wants B6–B8 certified passes its run id.

**Why the new fields are optional to the schema.** The gate pins `schema_version == reading_structure_artifact.v0.2`. Making the fields required would fail every artifact already accepted under that version — the two portability runs among them — for a reason unrelated to their content. The rule is new; the contract is extended, not replaced.

**Historical artifacts.** `out/reading_v02/artifact_medical.json` and `artifact_business.json` predate `REG-READ-018` and declare no freshness fields. The gate reports `FRESHNESS_NOT_VERIFIED` for them, exactly as those two runs already declare `surface` and `structure_rendered` `NOT_CHECKED` because their slides were never generated. Stated rather than grandfathered silently.

## 4. Two opposite errors the rule set holds apart

| | Wrongly on the slide | Wrongly absent from the slide |
|---|---|---|
| Content | citation markers, block ids, the author's commentary on the deck's own plan | the thread, the parts, the question each part answers, the narrative order |
| Rule | `REG-READ-016` | `REG-READ-017` |
| Symptom | the audience sees the workshop | the audience sees unrelated pages |

Both were observed in the same run, in that order. The first correction removed the working layer and, in doing so, removed the legitimate scaffolding too; the second restored the scaffolding without reintroducing the working layer. **The distinction is not how much goes on the slide but which layer it belongs to.**

## 5. Portability evidence

The same gate, unchanged, run on two materials of different kinds:

| Material | Kind | Units | Blocks | Chars | Result |
|---|---|---|---|---|---|
| 第六章 肺部感染性疾病 (scanned clinical textbook) | `MEDICAL_SOURCE` | 25 pages | 298 | 37,393 | PASS |
| 附件2 基于多模态语义分析的业务热点区域研究 (technical R&D deck) | `TECHNICAL_REPORT` | 20 slides | 20 | 7,080 | PASS |

Only `profile` differed. Both were produced before `surface` and `structure_rendered` existed and declare those two `NOT_CHECKED` with a reason — which is the honest status for an artifact whose slides were never generated.

**A material that appears to need a method change most likely needs a `profile` field instead.**

## 6. Verification record

| Item | Result |
|---|---|
| `reading-structure` on the chapter artifact (59 pages, structure rendered) | PASS |
| `reading-structure` on the clinical evidence artifact | PASS (two checks `NOT_CHECKED`, declared) |
| `reading-structure` on the technical evidence artifact | PASS (two checks `NOT_CHECKED`, declared) |
| Reverse test: strip the structural pages | FAIL with 4 specific errors |
| Reverse test: inject working-layer text into `on_slide_text` | FAIL with 4 leak classes named |
| Reverse test: remove `coverage_declaration` | FAIL with the signal and difficulty errors |
| Reverse test: accepted artifact re-validated **with** a run id | FAIL — `reading_pass:NOT_READ_FOR_THIS_RUN:expected=…:declared=(none declared)` |
| Reverse test: `reused_from` naming a frozen authored answer file | FAIL — schema `is not of type 'null'` **and** `reading_pass:READING_REUSED_FROM_PRIOR_ARTIFACT:…` |
| Reverse test: `read_from_sha256` set to a different source | FAIL — `reading_pass:READ_FROM_A_DIFFERENT_SOURCE:declared=000000000000:source=75e3724ab625` |
| Positive test: reading declaring this run and this source, with the run id | PASS |
| Accepted artifact re-validated **without** a run id | PASS, with `reading_pass:FRESHNESS_NOT_VERIFIED` reported under `not_assessed_by_this_gate` |
| `python scripts/verify_read_freshness_rule.py` | 5/5 cases behave as required |
| `verify-package` | PASS |
| Existing six `VALIDATORS` | unchanged |

## 7. Not to be claimed

- A passing gate does not mean the reading was good, the structure correct, the narrative effective, or the rendered structure helpful.
- A passing gate does not mean **this run** read the source. Freshness under `REG-READ-018` is established only when a run id is supplied; without it the gate reports `NOT_CHECKED`, and a reading could have been carried over from an earlier run while every other criterion passes.
- This compilation does not verify medical content.
- These rules are stable but not frozen; they may be revised by the same route, with the correction recorded.
