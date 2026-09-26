# Test 001｜CMVD Benchmark Lessons Compiled into Skill v0.1

## Source identity

- `test_id`: `REFERENCE_PIPELINE_TEST_001_CMVD`
- source: `冠状动脉微血管疾病诊断和治疗中国专家共识（2023版）`
- publication: `中华心血管病杂志, 2024, 52(5): 460-492`
- DOI: `10.3760/cma.j.cn112148-20231222-00521`
- source SHA256: `d9719aa7364f269fe82015a67d807387c2ef0188cf1a63fae1f2555454351201`
- page count: 33

## Main role profile used

- presenter: 心内科住院医 / 主治医师
- audience: 心内科临床医生
- scenario: 科室专家共识解读
- presentation question: `CMVD如何从临床怀疑走向分型诊断，并依据表型选择治疗策略？`
- duration: 20 min
- external research: false
- synthetic case: false

## What this benchmark proved

### 1. PDF text extraction alone is insufficient

The diagnostic flowchart page had corrupted/garbled text extraction while the rendered page remained legible. Therefore layout-sensitive source evidence must support multimodal page inspection before approval.

Permanent rule: `REG-PDF-001`.

### 2. Numeric semantics must survive extraction

Thresholds such as CFR / IMR / FFR, operators, units, recommendation classes and evidence levels are meaning-critical. A number without statistic/metric/operator/context is not an authoritative NumericFact.

Permanent rules: `REG-NUM-001`, `REG-REC-001`.

### 3. Image models can violate PageSpec even on YELLOW pages

Generation attempt for S01 (intended cover) expanded into a dense definition/classification/epidemiology page and introduced unbound medical numeric labels. It was rejected as semantic overreach.

Generation attempt for S02 (intended single phenotype map) expanded into a multi-slide sheet and introduced unrelated recommendation/diagnostic content. It was rejected as Page Contract violation.

Corrective regeneration still failed: the model again expanded S01/S02 beyond the approved semantic contract.

### 4. Edition year and publication year must not be conflated

The source is `2023版` but was published in 2024. A generator must not relabel it `2024版` simply because of publication year.

Permanent rule: `REG-GEN-004`.

### 5. FULL_IMAGE eligibility needs semantic-density/capability evidence

Two consecutive contract-compliance failures showed that YELLOW medical risk alone does not justify authoritative FULL_IMAGE generation.

Full-image eligibility must consider semantic density, exact-object count, topology constraints, exact/source-label requirements and engine/visual-type contract-compliance benchmark.

Two consecutive PageSpec fidelity failures for the same engine/visual-type trigger capability downgrade for authoritative rendering in the current benchmark.

### 6. Routing lesson

Current benchmark routing lesson:
- S01: deterministic/editorial composition; optional nonsemantic generated background only;
- S02: deterministic phenotype map + exact text overlay;
- S03: image assistance only if no exact evidence geometry is required;
- S04: controlled semantic diagram when directional/causal grammar is present;
- S05–S09: CONTROLLED_COMPOSITION / HYBRID;
- S10: editorial generation only if source-defined research gaps are exact/controlled text.

## Regression rule set

- `REG-PDF-001`: corrupted layout-dependent text → rendered-page visual inspection.
- `REG-NUM-001`: diagnostic thresholds preserve operator/value/unit/context.
- `REG-REC-001`: recommendation class/evidence level remain bound to the correct row/recommendation.
- `REG-VIS-001`: RED decision pages use protected topology/exact-text layers.
- `REG-ROLE-001`: role adaptation never changes facts.
- `REG-GEN-001`: one PageSpec → one page image.
- `REG-GEN-002`: cover PageSpec cannot gain unrequested medical facts.
- `REG-GEN-003`: image model cannot invent exact medical numeric labels.
- `REG-GEN-004`: source edition and publication year remain distinct.
- `REG-GEN-005`: YELLOW does not authorize semantic expansion.
- `REG-GEN-006`: two consecutive fidelity failures → capability downgrade.
- `REG-GEN-007`: YELLOW alone is insufficient for FULL_IMAGE eligibility.
- `REG-GEN-008`: semantic density/exact-object count participate in FULL_IMAGE eligibility.
- `REG-GEN-009`: noncompliant model may still provide nonsemantic art direction/background, not authoritative content.

## Current status of Test 001

`PARTIAL_WITH_BLOCKERS`

The pre-generation reference pipeline was completed, but the benchmark has not yet reached approved final page generation + post-generation QA + RED human review for the full deck. Therefore Test 001 is a regression/lesson benchmark, not a complete gold-standard delivery set.
