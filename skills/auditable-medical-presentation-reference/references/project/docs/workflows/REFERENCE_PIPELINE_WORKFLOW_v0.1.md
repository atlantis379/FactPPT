# Model-first Reference Pipeline Workflow v0.1

**Status:** `PROCESS_FROZEN`

**Purpose:** Establish the canonical end-to-end workflow for validating the Auditable Medical Presentation System with large-model capabilities before cloud engineering and localization.

## 1. Governing principle

The reference pipeline proves product logic first. Large models may perform semantic understanding, structuring, role adaptation, narrative design, verification, visual-strategy selection and prompt compilation; deterministic code remains authoritative for immutable source identity, exact source pointers, schema validation, policy gates, numeric/text exactness checks and persistence.

> Semantic Intelligence → LLM
>
> Deterministic Integrity → Code / Validator

No stage may silently upgrade unsupported content into an authoritative SOURCE fact.

## 2. Canonical workflow

```text
Original PDF
  ↓
W00 Source Registration
  ↓
W01 PDF / Page Extraction
  ↓
W02 Structured Evidence Layer
  ↓
W03 Evidence Verification Gate
  ↓
W04 Presentation Context / Role Profile
  ↓
W05 Information Triage
  ↓
W06 Narrative Spine / Outline
  ↓
W07 PageSpec Construction
  ↓
W08 Semantic Relationship & Evidence Binding
  ↓
W09 Medical / Numeric / Logic Audit
  ↓
W10 Approved Semantic Page Graph
  ↓
W11 Visual Strategy Selection
  ↓
W12 Generation Strategy Routing
  ↓
W13 Visual Generation Contract + Prompt Compilation
  ↓
W14 Page Generation / Controlled Composition
  ↓
W15 Post-generation Visual Audit
  ↓
W16 Human Review Gate
  ↓
W17 Approved Page Images / Delivery Package
  ↓
W18 Benchmark Record + Lessons Learned
```

## 3. Stage contracts

### W00｜Source Registration
Required outputs:
- immutable source identifier;
- SHA256;
- source filename;
- source version;
- page count;
- MIME type;
- storage/reference pointer;
- ingestion timestamp.

Fail if source identity cannot be reproduced.

### W01｜PDF / Page Extraction
Required outputs:
- page-level text;
- rendered-page image;
- page number;
- page extraction status;
- table / figure / flowchart presence markers;
- extraction warnings.

Rule: rendered-page visual evidence is mandatory when text-layer extraction is corrupted, incomplete or layout-dependent.

### W02｜Structured Evidence Layer
Create only source-grounded objects:
- SourceSpan;
- ClaimCandidate;
- Atomic Claim;
- NumericFact;
- RecommendationFact;
- EvidenceGradeFact;
- TableFact / FigureRef;
- SourceRef;
- Provenance;
- RiskLevel.

SOURCE objects must preserve source quote and normalized meaning separately.

### W03｜Evidence Verification Gate
Verify:
- atomicity;
- qualifier preservation;
- population / condition / timeframe;
- operator / threshold / range;
- unit;
- HR / OR / RR / CI / P;
- recommendation class;
- evidence level;
- source location.

Fail states must be explicit. Silent approximation is forbidden.

### W04｜Presentation Context / Role Profile
Must be defined before triage:
- audience;
- presenter role;
- scenario;
- presentation question;
- duration;
- desired depth;
- expected primary / appendix split.

Role adaptation may change selection, order and explanatory depth; it must not change source facts.

### W05｜Information Triage
Allowed outputs only:
- MUST_INCLUDE;
- SHOULD_INCLUDE;
- APPENDIX;
- EXCLUDED.

Every decision requires a reason. Triage does not create clinical relationships.

### W06｜Narrative Spine / Outline
Create:
- narrative spine;
- sections;
- presentation order;
- section goals.

Do not copy the source-document table of contents mechanically.

### W07｜PageSpec Construction
Each page requires:
- page goal;
- one primary message;
- supporting claims;
- conditions / data / caveats;
- source layer;
- risk level.

### W08｜Semantic Relationship & Evidence Binding
Bind approved:
- claim relationships;
- data relationships;
- conditions;
- logical operators;
- recommendation/evidence bindings;
- visual-semantic grammar licenses.

Do not invent missing clinical edges.

### W09｜Medical / Numeric / Logic Audit
Audit at minimum:
- source fidelity;
- numeric exactness;
- title entailment;
- relation direction;
- AND / OR / NOT / EXCEPT;
- comparison validity;
- recommendation strength;
- evidence grade;
- conflicts;
- RED-risk synthesis.

RED content requires human-review eligibility before final delivery.

### W10｜Approved Semantic Page Graph
Only audited objects may become approved semantic content for visual generation.

### W11｜Visual Strategy Selection
Decision basis:
- page goal;
- visual intent;
- information structure;
- approved relationships;
- precision requirement.

Hard constraints precede scoring. `NO_VALID_VISUAL` is legal.

### W12｜Generation Strategy Routing
Create effective generation route by component:
- deterministic chart;
- deterministic diagram;
- exact text compositor;
- verified medical asset renderer;
- prompt-driven image;
- hybrid composition.

Router cannot change the selected visual type or medical semantics.

### W13｜Visual Generation Contract + Prompt Compilation
Required:
- lock levels;
- mandatory content register;
- exact text register;
- visual semantic contract;
- layout freedom envelope;
- prohibited transformations;
- post-generation verification contract;
- model-specific prompt.

### W14｜Page Generation / Controlled Composition
Default for RED/high-precision pages:

```text
Prompt-driven Editorial Base
  ↓
Deterministic Semantic Diagram
  ↓
Deterministic Data Geometry
  ↓
Exact Content Overlay
  ↓
Source / Citation Overlay
  ↓
Flatten
```

Protected Semantic Layers must not be repainted by a later free generative pass.

### W15｜Post-generation Visual Audit
Check:
- mandatory object coverage;
- exact text;
- numeric fidelity;
- relationship fidelity;
- visual-semantic fidelity;
- citations;
- crop / occlusion / warp;
- label / axis / legend integrity.

### W16｜Human Review Gate
Required for:
- RED medical content;
- contested interpretations;
- high-risk synthesis;
- unresolved conflicts;
- uncertain source extraction;
- generation QA failures that cannot be deterministically resolved.

### W17｜Approved Delivery
Possible outputs:
- Presentation Deck;
- Reference / Appendix Deck;
- Speaker Notes;
- Backup Slides;
- Evidence Traceability Sheet;
- Medical Review Sheet;
- approved page images.

### W18｜Benchmark Record
Every reference test must record:
- source hash;
- role profile;
- output artifacts;
- failed gates;
- human corrections;
- generation retries;
- page pass rate;
- numeric mutation count;
- source-traceability coverage;
- unresolved issues;
- lessons learned.

## 4. Non-negotiable gates

A downstream stage must not proceed when any of these conditions is unresolved:

- SOURCE fact has no SourceRef;
- NumericFact has no exact source binding;
- RED threshold / dose / recommendation / evidence level is unverified;
- clinical relationship direction is unsupported;
- comparison lacks comparability clearance;
- source text extraction is visibly corrupted and rendered-page evidence has not been checked;
- exact text cannot be rendered and verified;
- generation route lacks an executable verifier;
- Protected Semantic Layer would be repainted by a generative model.

## 5. Workflow change control

This workflow is frozen as a process baseline, not as a medical-spec replacement.

### Recorded addition: W01-R (additive sub-stage, W00–W18 numbering unchanged)

| Field | Value |
|---|---|
| Change | Insert `W01-R Source Reading and Structure Derivation` between W01 and W02 |
| Reason | Structure was being derived by splitting the source on its own heading markers, which reproduces the source's table of contents, carries no argument, and cannot state emphasis or difficulty. Pages designed on such a structure inherit its errors. |
| Affected stages | W01 (unchanged), **W01-R (new)**, W02 (now requires an accepted W01-R artifact), W05–W11 (consume the structure), W07 (page-to-block linkage becomes mandatory) |
| Frozen module rules affected | None weakened. W01-R adds a gate; it removes no existing rule. |
| Backward compatibility | Additive. Runs that predate this policy are `NOT_CHECKED` for W01-R and may not claim `APPROVED_REFERENCE_OUTPUT`. |
| Benchmark impact | A first application recorded 129 deterministic failures against a 31-page artifact that had passed every pre-existing gate — evidence that the earlier gates did not cover structure derivation. |
| Authority | `SOURCE_READING_AND_STRUCTURE_DERIVATION_POLICY_v0.1.md` |
| Approval status | `ACTIVE_SKILL_POLICY_NOT_FROZEN_SPEC` |

Any further proposed workflow change must record:
- reason;
- affected stages;
- affected frozen module rules;
- backward compatibility;
- benchmark impact;
- approval status.

No change may silently weaken a frozen Module 01–06 rule.
