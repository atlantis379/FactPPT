# Source Reading to Narrative Derivation Policy v0.2

**Status:** `STABLE_NOT_FROZEN_SPEC` — verified end to end; see `W01R_RULE_COMPILATION_v1.0.md` for the index, the corrected gate defects and the verification record. Stable means no longer in flux, not frozen: revision follows the same route as any policy, with the correction recorded.

**Stage:** `W01-R` (additive sub-stage of the frozen W00–W18 sequence; W00–W18 numbering unchanged)

**Supersedes:** `SOURCE_READING_AND_STRUCTURE_DERIVATION_POLICY_v0.1.md`, which governed reading and structure only, and whose role vocabulary and marker lists were bound to one material's language and domain. v0.1 was correct in method and wrong in scope; v0.2 keeps the method and removes the binding.

**Applies to:** **any source material** — medical textbooks and guidelines, technical and business reports, research papers, policy documents, existing slide decks, transcripts. The method does not change with the material. What changes is declared, per run, in `profile`.

---

## 1. Purpose

Take a source material from **raw text to an allocated page plan**, with every step traceable, for any material.

The chain this policy governs is the whole of it:

```text
M1  READ      read the full text
M2  STRUCTURE clarify the logic: the thread, the nodes, what each node answers
M3  NARRATIVE order the claims for this audience — not the material's own order
M4  ALLOCATE  assign blocks to pages, each page with a reason and a figure intent
M5  HAND OFF  the artifact is the sole input to page design and generation
```

> **Governing principle**
>
> Reading, structure, narrative and allocation are semantic acts performed by a language model.
> Deterministic code verifies that they happened, that their claims are traceable, and that their
> judgements are declared. Code never produces them; the model never grades itself.

### 1.1 Why this must be a rule and not a habit

A structure produced by splitting the material on its own headings, pages or regular expressions is a **table of contents**, not a reading. It reproduces the material's organisation, carries no argument, cannot say what matters or what is hard, and gives pages nothing to attach to.

This is not hypothetical. A 31-page artifact that had passed every pre-existing gate was measured against a full reading of the same source and produced **129 deterministic failures**; the largest was that the material's actual through-line — a chain repeated in every section but never stated as such — had been lost entirely, because no gate covered reading.

## 2. Scope

| Material kind | The method applies unchanged | What is declared in `profile` |
|---|---|---|
| Medical textbook / guideline | yes | medical role extensions, Chinese clinical markers |
| Technical or business report | yes | business role extensions, the report's own emphasis markers |
| Research paper | yes | paper role extensions (hypothesis, method, result, limitation) |
| Policy document | yes | policy role extensions (obligation, entitlement, procedure) |
| Existing slide deck | yes | slide as the unit; the deck's own emphasis markers |
| Transcript / interview | yes | speaker role extensions |

A run that hard-codes its language or domain into the method rather than declaring it in `profile` is out of compliance with `REG-READ-013`.

## 3. The method

### M1 — Read

Read every extracted block, in source order, in full. Record `reading_mode = FULL_TEXT_READ`, blocks read vs total, characters read vs total. No sampling, no keyword targeting, no skipping sections judged irrelevant before reading them.

Relevance is decided in M4, **after** reading — never before.

### M2 — Structure (clarify the logic)

Derive, from the reading:

- **`thread`** — the reasoning that makes the parts one argument rather than a list of topics, in the reader's own words. If it cannot be stated, the reading is incomplete and the artifact must be rejected.
- **`opening_motivation`** — why the material exists, as the material states it. Many materials open with a problem, a contradiction or a question; that opening is the reason the rest follows.
- **`nodes[]`** — the units of meaning, each with `why_here`: the question the node answers or its role in the thread. A node whose `why_here` is "the material has this heading here" is not admissible.
- **per-block `role`, `relation` + `relation_status`, `signals`, `difficulty`** — the reading's evidence.

A structure whose node order equals the material's own heading order is a table of contents. It may be recorded, but it may not be presented as the derived structure.

### M3 — Narrative

Order the nodes for **this** audience and purpose, and state what the order does:

- `narrative_order` — node ids in presentation order;
- `differs_from_source_order` — boolean;
- `difference_reason` — what the chosen order accomplishes that source order does not (typically: each step answers the question the previous step raised);
- `audience_question` — the question the deck exists to answer.

**A narrative identical to source order requires an explicit justification**, because it forgoes the only thing a narrative is for. For expository sources this is sometimes correct — a procedure taught in sequence must be presented in sequence — but it is a decision, not a default.

### M4 — Allocate

Assign blocks to pages:

- every page declares `source_block_ids`, `why_this_page` (why the page exists, not what it contains) and `action_title` (a sentence stating the takeaway, not a topic label);
- every page declares `figure_intent` — what the reader must *see*: `CAUSAL`, `PROGRESSION`, `COMPARISON`, `TAXONOMY`, `PROCESS`, `SCALE`, `DATA`, `QUOTATION` or `NONE`;
- `figure_intent` is material-agnostic; the concrete figure is chosen later. Deciding the intent here is what stops a page from becoming a list by default;
- every block ends as `in_deck` or `evidence_only`; nothing is dropped;
- allocation follows the material's content distribution unless a `coverage_declaration` says otherwise and why.

### M5 — Hand off

The accepted artifact is the **sole** input to page design. No page may be designed, laid out or generated before acceptance.

## 4. Declared profile

Everything that varies by material is declared, not assumed:

| Field | Why it must be declared |
|---|---|
| `material_kind` | so downstream stages and reviewers know what they are handling |
| `language` | marker matching is language-specific |
| `role_vocabulary.extensions` | the core role set is material-agnostic; domain roles are additions and must be visible as additions |
| `signal_lexicon.emphasis_markers` | the words *this* material uses to mark importance. Counting is code's job; the lexicon is not code's guess |
| `signal_lexicon.fact_pattern` | what counts as one countable fact in this language |
| `relation_lexicon.markers` | the literal markers per relation type. Absence of a marker is what makes a relation `INFERRED` rather than `EXPLICIT` |

**Core roles (fixed, material-agnostic):** `definition`, `claim`, `evidence`, `mechanism`, `classification`, `process`, `comparison`, `problem`, `solution`, `metric`, `risk`, `recommendation`, `example`, `context`, `conclusion`, `other`.

**Declared extension examples:** clinical — `diagnosis`, `treatment`, `prognosis`, `pathology`; business — `market`, `architecture`, `roadmap`, `cost`; paper — `hypothesis`, `method`, `result`, `limitation`.

## 5. Difficulty vocabulary (material-agnostic)

| Flag | Signal in the material |
|---|---|
| `undefined_term` | a term used before it is defined |
| `multi_step` | an ordered chain of three or more steps or conditions |
| `contrastive_pair` | content the material itself contrasts, or warns is easily mistaken |
| `fact_dense` | three or more countable facts in one block |
| `negation_or_exception` | exclusion, exception or explicit negation |
| `long_chain` | a causal chain spanning more than one block |
| `cross_reference` | the material explicitly links this content to content elsewhere |

A passage with two or more flags must receive, at minimum, a structured figure rather than a plain list, and should receive more space than an unflagged passage of equal length.

## 6. Emphasis provenance

Two admissible origins, never conflated:

- **`MATERIAL_SIGNAL`** — the material marks it: its own emphasis markers, repetition, elaboration depth, fact density, position.
- **`EXTERNAL_AUTHORITY`** — an outside authority marks it: a syllabus, a client brief, a standard, an exam specification. `emphasis_authority` must name it.

`EXTERNAL_AUTHORITY` is legitimate and often decisive. But when it changes allocation, the run must record a `coverage_declaration` with `basis = EXTERNAL_AUTHORITY_SPLIT`, state the rationale and confirm excluded content is retained. Without that record a reader cannot distinguish a deliberate choice from an oversight.

## 7. Checks

Seven dimensions. Each must be able to report FAIL. A check whose failure mode cannot be stated is `NOT_CHECKED`, never `PASS`.

| # | Check | Fails when |
|---|---|---|
| 1 | `thread` | reading incomplete; a block has neither node nor orphan reason; node order equals source heading order **and** no node's `why_here` refers to another node; `thread` absent or restating section titles |
| 2 | `emphasis` | a node claims importance with basis `NONE`; external authority used without `emphasis_authority`; a key node has no block meeting the signal floor; **counter-example:** a high-signal block sits in `evidence_only` without declaration |
| 3 | `difficulty` | a block with ≥2 flags has no page or only a plain-list page; an `undefined_term` is nowhere resolved |
| 4 | `summary` | a unit over 10% of characters has under half its share of pages without declaration; a summary assertion has no source block |
| 5 | `logic` | a causal / progressive / staged page rests only on `INFERRED` relations; an explicit contrast marker is rendered as parallel enumeration |
| 6 | `narrative` | `narrative_order` equals source order with no justification; `difference_reason` absent or trivial; a step does not answer the prior step's question |
| 7 | `allocation` | a page lacks blocks, `why_this_page` or `figure_intent`; a high-difficulty block is allocated to a page whose `figure_intent` is `NONE` or a list |
| `surface` | any `on_slide_text` string contains a working-layer mark: citation marker, block reference, internal id, audit locator, editorial label, elided quotation, or commentary on the deck's own structure |
| `structure_rendered` | no roadmap page; no section-question page; no consolidation page; a narrative node exposed by no page; or page order contradicting the declared narrative order |

## 8. Rules

| ID | Rule |
|---|---|
| `REG-READ-001` | The full extracted text must be read. Heading-marker, page or regex splitting may inventory the material but never constitutes the structure. |
| `REG-READ-002` | Every extracted block appears exactly once, with a coverage status. Silent omission is forbidden. |
| `REG-READ-003` | Every node states `why_here` as a question answered or a role in the thread. Source headings are not admissible. |
| `REG-READ-004` | The thread must be stated in the reader's own words. If it cannot be stated, disposition is `READING_STRUCTURE_REJECTED`. |
| `REG-READ-005` | Emphasis declares `emphasis_basis`; `EXTERNAL_AUTHORITY` names the authority and is accompanied by a `coverage_declaration`. |
| `REG-READ-006` | A relation is `EXPLICIT` only when `relation_evidence` quotes the material's marker from the declared lexicon. `INFERRED` relations may not be presented to the audience as the material's own. |
| `REG-READ-007` | A block with two or more difficulty flags is not rendered as a plain list. |
| `REG-READ-008` | Allocation diverging by more than 2× from character share requires a `coverage_declaration`, and excluded content is retained. |
| `REG-READ-009` | All checks report `PASS`, `FAIL` or `NOT_CHECKED` with a stated method. `PASS` without a describable failure mode is invalid. |
| `REG-READ-010` | A failing check is recorded with its failures. Failures may not be cleared by weakening the check: a defective check is corrected, re-run, and the correction recorded with both results. |
| `REG-READ-011` | No page may be designed before the artifact is accepted. |
| `REG-READ-012` | Page-to-block linkage is recorded explicitly. A page whose blocks are unrecorded cannot be audited later. |
| `REG-READ-013` | Everything material-specific is declared in `profile`. A method that hard-codes a language, domain vocabulary or marker list is out of compliance, because it cannot serve the next material. |
| `REG-READ-014` | The narrative must state how its order differs from source order and what the difference accomplishes. An identical order requires justification, not silence. |
| `REG-READ-017` | **The derived structure must be rendered, not merely declared.** The thread, the parts, the question each part answers and the narrative order are audience-facing content: the deck must expose them through a roadmap page, a question at each part boundary, and a consolidation page, and every narrative node must be visible on some page. A structure that exists only in the artifact does not exist for the reader. |
| `REG-READ-016` | **The slide surface carries presentation language only.** Citation markers, block or line references, internal ids, editorial labels, elided quotations and the author's commentary about the deck's own structure are working-layer content: they belong in `speaker_notes` and the audit artifact, never on a slide. A page declares its `on_slide_text`, and that text is checked. |
| `REG-READ-015` | Every page states `why_this_page` and `figure_intent` before layout. A page whose intent is undecided becomes a list by default. |
| `REG-READ-018` | **Every generation run reads the source again.** M1–M4 are performed afresh for each deck, from the material in hand. A reading, structure, narrative or page plan produced by an earlier run — a cache keyed by source hash, a frozen or `authored` answer file, a replayed endpoint response, or a previously accepted artifact — may not serve as this run's reading, however well it scored. The reading declares the run it was performed for (`executed_for_run`), the bytes it was read from (`read_from_sha256`), and leaves `reused_from` empty. A prior reading may be used as a **comparison baseline** — two readers compared against each other — and that use is recorded as such; it is never substituted for this run's reading. |

## 9. Portability evidence

The policy is only as general as its instantiations. Two materials of different kinds and languages have been run through this contract:

| Material | Kind | Units | Blocks | Chars | Thread found |
|---|---|---|---|---|---|
| 第六章 肺部感染性疾病 (scanned clinical textbook chapter) | `MEDICAL_SOURCE` | 25 pages | 298 | 37,393 | pathogen property → pathology → imaging → drug choice, repeated per section but never stated |
| 附件2 基于多模态语义分析的业务热点区域研究 (technical R&D report) | `TECHNICAL_REPORT` | 20 slides | 20 | 7,080 | pain points → platform capability → model/resource → measured effect → rollout |

Neither run needed a change to the method. What differed between them — language markers, role extensions, unit label — is exactly the content of `profile`.

## 9a. Presentation layer and working layer

A run produces two kinds of text and they must not mix.

| | Presentation layer | Working layer |
|---|---|---|
| What | the takeaway, the supporting content, figure labels, footer source | why the page exists, source block ids, quoted原文, difficulty notes, the author's reasoning about the structure |
| Where | the slide | `speaker_notes`, the artifact, the review sheet |
| Language | final, audience-facing, no markers | may quote, cite and reason freely |

**Failure mode this prevents.** On a first run, a page's on-slide prose read:

> 原文：在抗菌药物应用以前…曾一度使肺炎病死率明显下降。但近年来…甚至有所上升。这是全章的问题起点。

Three separate working-layer leaks in one line: the citation marker `原文：`, an elided quotation, and a sentence describing **the author's own structure** rather than the subject. The audience is being shown the workshop. The same run put `块 35-45` in subtitles and `（原文块 1–2）` in table headers.

The corrected line states the result instead:

> 抗菌药物出现后肺炎病死率曾一度明显下降；但近年来，尽管有强力的抗菌药物和有效的疫苗，病死率并未进一步降低，甚至有所上升。

The test is not stylistic. Ask of every visible string: **would this be on the slide if the reader never knew the deck had a plan?** If no, it is working layer.

## 9b. Structure must be rendered

`REG-READ-016` forbids the working layer on slides. `REG-READ-017` requires the opposite error to be caught too: the **legitimate scaffolding** must be on the slides.

Two failure modes, opposite in direction, both real:

| | Wrongly on the slide | Wrongly absent from the slide |
|---|---|---|
| Content | citation markers, block ids, the author's commentary on the deck's own plan | the thread, the parts, the question each part answers, the narrative order |
| Rule | `REG-READ-016` | `REG-READ-017` |
| Symptom | the audience sees the workshop | the audience sees 59 unrelated pages |

**Recorded instance.** A deck satisfied `REG-READ-016` after cleanup and still failed this rule: a 59-page version had no roadmap page, no section dividers at all (the cover, the one section marker and the closing page had no declared figure and degraded into single-item lists), and the through-line appeared only on the last content page. The artifact had carried the thread, the 17 nodes with `why_here`, and the narrative order the whole time — none of it was rendered.

The distinction is not "put more on the slide". It is: **the reader must be able to see the argument's shape.** The author's process is working layer; the argument's shape is presentation layer. The first is forbidden on the surface; the second is required on it.

## 9c. A reading belongs to a run, not to a document

`REG-READ-018`. A reading is **evidence about a run**. It says: on this occasion, a reader met this material and this is what it made of it. Nothing else in the chain can be checked if that is not true, because every downstream claim is traceable to the reading rather than to the source.

A reading reused from an earlier run stops being evidence and becomes a **fixture**. The artifact keeps its shape — blocks, nodes, `why_here`, narrative order all still present and all still passing — while no longer answering the question it exists to answer. This is the more dangerous failure of the two, because nothing about the output looks wrong. `REG-READ-016` leaks the workshop onto the slide; reuse leaves the audience reading a deck whose argument was never derived from the material in front of it.

**Recorded instance.** The pipeline was tested by running different drivers over the same material and observing that they produced the same deck. That observation was true and it was empty: the content lived in frozen authored answer files, so the drivers were runners, not readers. The comparison had measured the fixture's stability, not the readers' agreement. The same structure is what makes a cache look like a speed-up rather than a substitution.

| Reuse | Looks like | Why it is not this run's reading |
|---|---|---|
| Cache keyed by source hash | the same document was read before; the bytes are unchanged | the source is unchanged, the reader is not. A model, a prompt, a lexicon or a `profile` that moved makes the cached reading another run's judgement |
| Frozen / `authored` answer file | reproducible, deterministic, reviewable | determinism obtained by not reading. Its provenance is a fixture, not an observation |
| Replayed endpoint response | the model "answered" the same way as last time | the answer was authored and replayed; no model met the material |
| Previously accepted artifact | it already passed the gate | the gate certifies completeness and traceability **of the run that produced it**. Passing is not transitive across runs |

**What reuse is legitimate.** A prior reading may be loaded as a *comparison baseline*: two independent readings of one source are compared paragraph by paragraph to see where readers diverge. That is a use of a past reading as a second opinion, and the artifact under test is still read afresh. The distinction is whether the prior reading **substitutes for** this run's reading or **is measured against** it.

**Correction and re-run is not reuse.** When a defective check is corrected, `REG-READ-010` requires the check to be re-run and both results recorded. If the correction reaches M1, M1 is performed again — a re-run is a new reading, and it is recorded as one.

**Cost is not a defence.** Reading a long source on every run is expensive; that is a real cost and it does not make a frozen reading admissible. The remedy for an expensive reader is a cheaper reader, a declared `profile` that fits the material, or an explicit reduction in what is read for a stated purpose — each of which still reads. A frozen reading is not a cheaper read; it is no read.

## 10. Change record

| | v0.1 | v0.2 |
|---|---|---|
| Scope | reading + structure | reading + structure + **narrative** + **page allocation** + handoff |
| Role vocabulary | medical enum baked into schema | material-agnostic core + declared extensions |
| Marker lists | hard-coded Chinese clinical words | `signal_lexicon` / `relation_lexicon` declared per run |
| Difficulty flags | medical-flavoured names | material-neutral names |
| Emphasis basis | `SYLLABUS` | `MATERIAL_SIGNAL` / `EXTERNAL_AUTHORITY` + named authority |
| Checks | 5 | 7 (+ `narrative`, + `allocation`) |
| Rules | 12 | 15 (+ `REG-READ-013` portability, `+014` narrative, `+015` page intent) |
| Defect that forced v0.2 | — | v0.1 declared itself applicable to "textbooks, guidelines, papers, reports" while its vocabulary served one material. A rule that only fits the material in front of it is a habit, not a rule. |

### Additive revision within v0.2 — `REG-READ-018`

| | Before | After |
|---|---|---|
| Rules | 17 | 18 (+ `REG-READ-018` reading is per run) |
| `reading_pass` | reads completeness only | completeness **and** run binding: `executed_for_run`, `read_from_sha256`, `reused_from` |
| Gate | certifies the reading happened | certifies the reading happened **for this run**, when a run id is supplied |
| Defect that forced it | — | A comparison of "different drivers" had measured a frozen fixture: the content lived in authored answer files, so the drivers were runners, not readers. Reading completeness was fully certified while no reader had met the material. |

**Why the version string is unchanged.** The gate pins `schema_version == reading_structure_artifact.v0.2`, and the new `reading_pass` fields are optional to the schema and enforced by the gate when a run id is supplied. Bumping the schema version would invalidate every artifact already accepted under it for a reason unrelated to their content. The rule is new; the contract is extended, not replaced.

## 11. Audit record minimum

Artifact identity and SHA256; the declared `profile`; reading completeness; **the run the reading was performed for and the source bytes it was read from (`executed_for_run`, `read_from_sha256`), with `reused_from` recorded empty**; the thread statement; per check: status, method, failure count; every `coverage_declaration` with basis and authority; every check correction with defect and corrected test; the narrative order and its difference reason; the page plan with per-page reason and intent; disposition.

## 12. Disposition

`READING_STRUCTURE_ACCEPTED` · `READING_STRUCTURE_ACCEPTED_WITH_DECLARED_GAPS` · `READING_STRUCTURE_REJECTED`.

`ACCEPTED_WITH_DECLARED_GAPS` requires every open failure to carry a declaration or recorded remediation. An undeclared gap is a rejection.

A structure-, narrative- or allocation-changing correction returns to M1 and rebuilds M2–M5. Downstream stages consuming the artifact are invalidated to their dependent scope.
