# Generation Runtime Qualification Benchmark Pack v0.1

Status: `ACTIVE_SKILL_BENCHMARK_NOT_FROZEN_SPEC`

Purpose: qualify a new or materially changed execution runtime before W12 may bind abstract legal routes to concrete engines/renderers/compositors. This pack validates execution capability, not medical reasoning.

## 1. Qualification trigger

Run this pack when any of the following is true:

- no current `RuntimeCapabilityProfile` exists;
- an engine/model/renderer/compositor/verifier version is new;
- a material capability change is detected;
- a previously qualified capability is `STALE`;
- the Skill is moved to a new platform/runtime;
- W12 needs a capability not present in the current registry.

The Skill may run only the affected benchmark subset when the material change is scoped and dependencies are unchanged.

## 2. Qualification domains

The v0.1 pack contains five domains:

1. `DETERMINISTIC_DIAGRAM` — node/edge/direction/branch/condition/topology fidelity;
2. `MATRIX_LAYOUT` — row/column/group ownership, non-ranking layout, AND-bundle preservation;
3. `EXACT_CONTENT_COMPOSITOR` — authoritative Chinese/Latin text, operators, units, class/evidence strings;
4. `VERIFIED_MEDICAL_ASSET_RENDERER` — source-asset hash lineage, permitted transforms, crop/scale integrity;
5. `PROMPT_EDITORIAL_BASE` — non-semantic art direction while refusing/avoiding unauthorized medical/textual semantics.

A runtime can qualify for one domain and fail another. Qualification is capability-scoped, not vendor-scoped.

## 3. Required evidence per fixture

Each executed fixture must produce:

- fixture id/version;
- engine/renderer/compositor id and exact version;
- input fixture hash;
- execution settings/config hash;
- output asset/version/hash;
- `GenerationOutputManifest` when the fixture contains meaning-critical content;
- verifier ids/versions;
- expected vs observed result;
- PASS/FAIL/BLOCK;
- issue records for every mismatch.

Pixel similarity is not a primary qualification criterion. Meaning-critical semantics, exact content, geometry/topology, ownership and provenance are.

## 4. Hard-pass criteria

### 4.1 Deterministic Diagram
For RED-authoritative topology qualification:
- 100% required node ids present;
- 100% required edge ids present;
- 100% edge direction correct;
- 100% branch/condition labels correct;
- zero unauthorized meaning-bearing edges;
- zero required logic/operator changes;
- machine-readable semantic manifest required.

Any meaning-critical topology mismatch = FAIL.

### 4.2 Matrix / Layout
For RED-authoritative matrix qualification:
- 100% required row/column/group memberships correct;
- no swapped ownership;
- no omitted required condition;
- explicit AND bundle retained where required;
- no ranking/superiority encoding unless fixture licenses it;
- machine-readable membership/logic manifest required.

Any required membership/logic mismatch = FAIL.

### 4.3 Exact Content
For an authoritative exact-content compositor:
- 100% exact string match for the ExactTextRegister;
- 100% operator/value/unit/class/evidence string match;
- no Unicode-normalization change that changes visible/medical meaning;
- machine-readable rendered-text manifest required.

Approximate wording is not acceptable for ExactText qualification.

### 4.4 Verified Medical Asset Renderer
- input asset identity/hash verified;
- only contract-permitted transforms used;
- output transformation manifest complete;
- derivative lineage complete;
- zero meaning-critical crop/occlusion/repaint;
- prohibited AI redraw as authority must be rejected.

### 4.5 Prompt-driven Editorial Base
This capability is non-authoritative. Qualification tests whether the model can follow a no-semantic-content envelope.

PASS requires the configured run set to avoid unauthorized:
- readable medical text;
- numeric facts;
- diagnostic/treatment arrows;
- rankings/scales;
- invented drug/device names;
- source-looking medical diagrams.

A model may be `QUALIFIED_WITH_RESTRICTIONS` if it is safe only under narrower prompt/envelope conditions. This qualification never authorizes exact text, data geometry or medical topology.

## 5. Adversarial principle

The pack must include negative cases, not only successful render tasks. Examples:

- `≥50%` versus `>50%`;
- `CFR<2.0` versus `CFR≤2.0`;
- edge reversal;
- YES/NO branch swap;
- omitted AND condition;
- `HMR>1.7`, `HMR≥1.9`, `HMR>3` context confusion;
- unlabeled `可参照`/`推荐同` connector;
- non-comparable treatment groups rendered as a ranked heatmap;
- crop removing a source-authority branch;
- image model inventing text/arrows in a decorative background.

A verifier that cannot reject injected negative cases is not qualified for that failure class.

## 6. Capability result

After execution, issue a version-bound `CapabilityRecord` with one of:

- `QUALIFIED`;
- `REFERENCE_QUALIFIED`;
- `QUALIFIED_WITH_RESTRICTIONS`;
- `NOT_QUALIFIED`;
- `BLOCKED`;
- `STALE`.

The record must list the exact benchmark fixture ids passed/failed, scope, limitations, verifier evidence and invalidation triggers.

## 7. Incremental requalification

When a material change affects only one component class, re-run the smallest benchmark subset that covers that capability and its verification dependencies. Examples:

- exact compositor upgrade → Exact Content fixtures + verifier compatibility;
- diagram renderer upgrade → Diagram fixtures + topology/logic verifier compatibility;
- image model upgrade → Editorial Base fixtures;
- manifest schema change → all structured verifier compatibility fixtures.

Do not invalidate upstream W00–W11 medical semantics merely because a renderer capability becomes stale.

## 8. v0.1 fixture inventory

Canonical machine-readable fixtures:

`GENERATION_RUNTIME_QUALIFICATION_FIXTURES_v0.1.json`

Target size: 20 micro-fixtures:
- Diagram: 4
- Matrix/Layout: 4
- Exact Content: 5
- Medical Asset: 4
- Editorial Base: 3

The fixture corpus intentionally reuses failure modes discovered in CMVD Reference Case 001 while remaining synthetic and portable where possible.
