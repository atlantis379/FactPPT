# 医学可审计演示系统｜DATA_SCHEMA v0.1

> 本文档定义 MVP 的核心数据实体、字段、枚举与校验规则。  
> 当前已固化：Claim Table v0.1 / Information Triage v0.1 / Medical Information Architect v0.1  
> 目标：让 Claim、Node、Edge、来源、审核与最终页面之间形成可追溯链路。

---

## 1. 核心实体关系

```text
Project
  ├── Documents
  │     └── SourceChunks
  ├── Claims
  │     ├── CanonicalClaims
  │     ├── ConflictGroups
  │     └── SourceRefs
  ├── TriageDecisions
  ├── NarrativePlans
  ├── Sections
  ├── Nodes
  ├── Edges
  ├── Pages
  ├── ReviewItems
  ├── ComplianceIssues
  └── AuditLogs
```

---

## 2. Project

```json
{
  "project_id": "PRJ001",
  "name": "GOLD 2026 COPD 更新解读",
  "project_type": "guideline",
  "audience": "resident",
  "presentation_goal": "literature_interpretation",
  "presentation_question": "GOLD 2026 有哪些影响临床管理的重要变化？",
  "duration_minutes": 10,
  "language": "zh-CN",
  "need_web_research": false,
  "output_mode": "full_package",
  "synthetic_case": false,
  "output_channel": "internal_deck",
  "status": "UPLOADED",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

### Enums

`project_type`
- case_discussion
- guideline
- consensus
- journal_club
- conference
- research_defense

`audience`
- specialist
- resident
- medical_student
- researcher
- mixed

`presentation_goal`
- teaching
- decision_communication
- literature_interpretation
- case_review
- research_report

`output_mode`
- presentation
- reference
- notes
- full_package

`output_channel`
- internal_deck
- client_delivery
- public_xiaohongshu

---

## 3. Document

```json
{
  "document_id": "DOC001",
  "project_id": "PRJ001",
  "filename": "source.pdf",
  "file_type": "pdf",
  "file_hash": "sha256...",
  "page_count": 11,
  "source_role": "primary",
  "created_at": "ISO8601"
}
```

`source_role`
- primary
- supplemental
- external_research
- user_note

---

## 4. SourceChunk

用于文本、表格、图注的可检索源片段。

```json
{
  "chunk_id": "CHK001",
  "document_id": "DOC001",
  "page": 4,
  "section": "3.1.1",
  "content_type": "paragraph",
  "text": "...",
  "table_id": null,
  "figure_id": null,
  "bbox": [72, 112, 520, 240],
  "embedding_id": "vec_001"
}
```

`content_type`
- title
- paragraph
- table
- figure_caption
- footnote
- reference
- other

---

## 5. Claim

Claim 是 Source Fact Layer 的最小医学命题单位。v0.1 强制采用 Atomic Claim，并区分原文、标准化表达与 provenance。

### 5.1 最低字段

```json
{
  "claim_id": "C001",
  "project_id": "PRJ001",
  "canonical_claim_id": "CAN001",
  "normalized_claim": "过去一年≥1次中重度急性加重符合GOLD 2026 E组高风险标准",
  "claim_type": "risk_criterion",
  "source_type": "SOURCE",
  "source_quote": "……原文……",
  "source_refs": ["SRC001"],
  "source_chunk_id": "CHK001",
  "population": "COPD患者",
  "condition": "过去一年≥1次中重度急性加重",
  "intervention": null,
  "comparator": null,
  "outcome": "classified_as_E_group",
  "timeframe": "past_12_months",
  "recommendation_class": null,
  "evidence_level": null,
  "risk_level": "RED",
  "locked": true,
  "ambiguity": false,
  "conflict_group_id": null,
  "review_status": "unreviewed"
}
```

### 5.2 Claim Table v0.1 数据约束

1. 一个 Claim 只表达一个可独立验证的医学命题。
2. `source_quote` 与 `normalized_claim` 必须同时存在（SYNTHESIS 可通过多个 SourceRef 支撑）。
3. 数字、阈值、推荐类别、证据等级必须结构化；高风险数字另存 NumericFact。
4. `SOURCE / SUMMARY / SYNTHESIS` 从 Claim 层开始记录。
5. Claim 不存 Clinical Relationship；关系进入 Edge。
6. 多来源同一事实归入同一个 `canonical_claim_id`。
7. 冲突事实保留独立 Claim，通过 `conflict_group_id` 关联，禁止自动融合。
8. 需要外部知识才能补全的内容不得设置 `source_type=SOURCE`。

### 5.3 claim_type

MVP 优先采用：

- definition
- population
- risk_criterion
- diagnostic_criterion
- recommendation
- treatment
- contraindication
- timing
- study_result
- outcome
- mechanism
- limitation
- other

### 5.4 source_type

- SOURCE
- SUMMARY
- SYNTHESIS

定义：

- SOURCE：原文直接明确支持；
- SUMMARY：忠实压缩，不改变边界；
- SYNTHESIS：跨段落 / 表格 / 文献重新组织。

### 5.5 risk_level

- GREEN
- YELLOW
- RED

### 5.6 review_status

- unreviewed
- verified
- needs_human
- rejected

### 5.7 Canonical Claim

同义 / 同事实的多来源 Claim 不重复创建多个事实实体，统一指向 Canonical Claim：

```json
{
  "canonical_claim_id": "CAN001",
  "canonical_text": "过去一年≥1次中重度急性加重符合E组高风险标准",
  "member_claim_ids": ["C001", "C009"],
  "source_refs": ["SRC001", "SRC008"]
}
```

### 5.8 Conflict Group

```json
{
  "conflict_group_id": "CG001",
  "claim_ids": ["C101", "C102"],
  "conflict_type": "threshold_conflict",
  "resolution_status": "needs_human"
}
```

禁止自动平均、折中或合并冲突值。

## 6. NumericFact

建议将高风险数字独立建表。

```json
{
  "numeric_id": "NUM001",
  "claim_id": "C001",
  "value": 48,
  "value_text": "48%",
  "unit": "%",
  "metric": "FEV1 predicted",
  "value_role": "absolute_value",
  "statistic_type": "proportion",
  "numerator": null,
  "denominator": null,
  "population": "COPD patients",
  "subgroup": null,
  "outcome": null,
  "timepoint": null,
  "timeframe": null,
  "intervention": null,
  "comparator": null,
  "value_origin": "SOURCE",
  "missingness": null,
  "source_ref": "DOC001:p6",
  "locked": true,
  "qa_status": "pending"
}
```

适用于：

- 百分比；
- 剂量；
- 阈值；
- 时间；
- 样本量；
- HR；
- OR；
- RR；
- CI；
- P value；
- 推荐等级；
- 证据等级。

---

## 7. SourceRef

```json
{
  "source_ref_id": "SRC001",
  "document_id": "DOC001",
  "page": 18,
  "section": "3.2",
  "table_id": "Table 7",
  "figure_id": null,
  "recommendation_id": "Recommendation 4",
  "chunk_id": "CHK104",
  "quote": "...",
  "pointer_label": "DOC001:p18:recommendation4"
}
```

---

## 8. Semantic Object / Relationship / Binding

### 8.1 SemanticObject

页面语义对象可以来自 Claim、NumericFact、Title、Data Series、Axis、Annotation、Node 等。

```json
{
  "semantic_object_id": "OBJ001",
  "project_id": "PRJ001",
  "page_id": "S05",
  "object_type": "claim",
  "source_entity_type": "claim",
  "source_entity_id": "C022",
  "label": "过去一年≥1次中重度急性加重",
  "risk_level": "RED",
  "locked": true
}
```

`object_type` 示例：

- title
- primary_message
- claim
- numeric
- data_series
- axis
- legend
- annotation
- node
- source
- group
- timepoint
- other

### 8.2 SemanticRelationship

```json
{
  "relationship_id": "REL001",
  "project_id": "PRJ001",
  "page_id": "S05",
  "from_object_id": "OBJ001",
  "to_object_id": "OBJ002",
  "relation_type": "recommended_treatment",
  "relationship_domain": "clinical",
  "direction": "from_to",
  "source_type": "SOURCE",
  "source_refs": ["SRC001"],
  "population": "target_population",
  "conditions": ["C101", "C102"],
  "timeframe": null,
  "exclusions": ["C103"],
  "dose_numeric_id": null,
  "logic_operator": "AND",
  "polarity": "positive",
  "recommendation_strength": "consider",
  "recommendation_class": "IIa",
  "evidence_level": "B",
  "risk_level": "RED",
  "locked": true,
  "needs_human_review": false,
  "review_status": "SUPPORTED"
}
```

`relationship_domain`：

- clinical
- evidence
- title_entailment
- data_semantic
- context
- visual_semantic
- presentation_logic

`relation_type` 可包括：

- leads_to
- requires
- supports
- contradicts
- contraindicates
- associated_with
- causes
- classifies_as
- eligible_for
- excludes
- follows
- reassess
- treated_with
- escalates_to
- title_supported_by
- data_supports_claim
- evidence_supports_recommendation
- belongs_to
- grouped_with
- maps_to
- annotates
- compares_with
- other

规则：

1. SOURCE Relationship 必须有 SourceRef；
2. SUMMARY 必须忠实压缩原文已有关系；
3. SYNTHESIS 必须显式标记；
4. RED + SYNTHESIS 必须 `needs_human_review=true`；
5. Presentation Order 不得自动转换为 Clinical Relationship；
6. Visual Grouping 不得自动转换为 Clinical Relationship。

### 8.3 DataBinding

```json
{
  "binding_id": "DB001",
  "page_id": "S05",
  "numeric_id": "NUM001",
  "value_role": "change_from_baseline",
  "metric": "annualized moderate-to-severe exacerbation rate",
  "outcome": "moderate_to_severe_exacerbation",
  "population": "target_population",
  "subgroup": null,
  "timepoint": null,
  "timeframe": "52_weeks",
  "intervention": "intervention_arm",
  "comparator": "placebo",
  "statistic_type": "rate_ratio",
  "numerator": null,
  "denominator": null,
  "unit": "events/person-year",
  "value_origin": "SOURCE",
  "derived_calculation": null,
  "comparability_status": "comparable",
  "binding_status": "BOUND",
  "source_refs": ["SRC041"],
  "risk_level": "RED",
  "review_status": "verified"
}
```

### 8.4 VisualBinding

```json
{
  "visual_binding_id": "VB001",
  "page_id": "S05",
  "binding_type": "legend_to_series",
  "from_object_id": "LEGEND_A",
  "to_object_id": "SERIES_A",
  "semantic_value": "Intervention",
  "source_refs": ["SRC041"],
  "locked": true
}
```

`binding_type`：

- legend_to_series
- axis_to_metric
- axis_to_unit
- category_to_population
- category_to_timepoint
- annotation_to_comparison
- color_to_semantic
- label_to_numeric
- group_to_meaning
- connector_to_relationship

### 8.5 TitleEntailment

```json
{
  "entailment_id": "TE001",
  "page_id": "S05",
  "title_object_id": "TITLE_S05",
  "supported_by_claim_ids": ["C022", "C023"],
  "source_type": "SUMMARY",
  "entailment_status": "supported",
  "semantic_strength": "association",
  "max_supported_strength": "association",
  "review_status": "verified"
}
```

允许的 `entailment_status`：

- SUPPORTED
- PARTIALLY_SUPPORTED
- UNSUPPORTED
- CONFLICT
- NEEDS_HUMAN_REVIEW

目标：

> 标题语义强度不得超过其 Claims 可支持的最大语义强度。

### 8.6 ContextualImplication

```json
{
  "context_id": "CTX001",
  "page_id": "S06",
  "preceding_page_ids": ["S04", "S05"],
  "implied_relation": "biomarker_guides_drug_selection",
  "source_type": "SYNTHESIS",
  "risk_level": "RED",
  "status": "needs_human"
}
```

用于检测：

- 页面顺序；
- 连续叙事；
- 空间邻近；

是否产生来源外推理暗示。

### 8.7 SemanticRelationship 与 Clinical Edge

原有 `Edge` 概念并未消失，而是收敛为：

> `SemanticRelationship.relationship_domain = clinical`

Decision Map 的箭头只是 Clinical Semantic Relationship 的一种视觉渲染。

---



## 8A. Module 04 Batch 1 数据约束

1. 所有结论型 Title / Primary Message 必须引用底层 Claim。
2. `semantic_strength` 不得高于 `max_supported_strength`。
3. Population / Condition / Timeframe / Exclusion 等必要限定必须参与 Title Entailment。
4. 多 Claim 组合生成的新结论默认不得继承 SOURCE；无直接来源支持时设为 SYNTHESIS。
5. SourceRef 存在不代表 Entailment 通过。
6. TitleEntailment 状态固定为：
   - SUPPORTED
   - PARTIALLY_SUPPORTED
   - UNSUPPORTED
   - CONFLICT
   - NEEDS_HUMAN_REVIEW
7. Narrative Spine / Section Title / Slide Title / Primary Message / Chart Title 必须保存 provenance。
8. 任何可能让合理听众形成语义关系判断的表达，应映射为 SemanticRelationship 或 Binding，而不是仅保留为视觉属性。



## 8B. Module 04 Batch 2 数据约束

1. 医学 DataObject 必须保存 Value 与其必要语义上下文；缺失会改变医学意义的字段时不得标记 BOUND。
2. Numeric value 相同但 Metric / Outcome / Population / Time / Group 不一致时，DataBinding 必须失败。
3. Data 与页面 Claim 的支持关系必须显式记录，推荐 `relation_type = data_supports_claim`。
4. `value_role` 必须区分：
   - baseline_value
   - final_value
   - change_from_baseline
   - absolute_change
   - relative_change
   - absolute_risk
   - relative_risk
   - difference_between_groups
   - other
5. Effect Estimate / CI / P Value / Numerator / Denominator 不能脱离 Comparison / Outcome / Population / Timeframe。
6. `value_origin` 至少支持：
   - SOURCE
   - DERIVED_CALCULATION
   - ESTIMATED_FROM_FIGURE
   - OCR_EXTRACTED
7. `DERIVED_CALCULATION` 必须记录：
   - formula
   - input_numeric_ids
   - calculation_engine_version
8. 自动计算仅允许 `calculation_whitelist` 中的确定性公式。
9. 原始 Value / Unit 永久保留；display value 的换算或舍入必须记录 transformation。
10. `missingness` 必须区分：
   - MISSING
   - NA
   - NR
   - NOT_MEASURED
   - NOT_APPLICABLE
   - UNKNOWN
   禁止自动转换为 0。
11. `comparability_status`：
   - comparable
   - partially_comparable
   - non_comparable
   - unknown
12. `binding_status` 固定为：
   - BOUND
   - PARTIALLY_BOUND
   - UNBOUND
   - CONFLICT
   - NEEDS_HUMAN_REVIEW
13. RED DataBinding 只有 `BOUND` 或存在明确 human approval 时才能进入 Approved Semantic Page Graph。



## 8C. DerivedCalculation

```json
{
  "derived_calculation_id": "CALC001",
  "output_numeric_id": "NUM100",
  "formula": "(NUM001 - NUM002) / NUM001",
  "input_numeric_ids": ["NUM001", "NUM002"],
  "calculation_type": "relative_risk_reduction",
  "whitelisted": true,
  "source_type": "SYNTHESIS",
  "calculation_engine_version": "0.1",
  "review_status": "verified"
}
```

复杂医学统计推导若不在白名单：
- 不自动执行；
- 输出 `NEEDS_HUMAN_REVIEW` 或 `SOURCE_REQUIRED`。



## 8D. Module 04 Batch 3 数据约束

### Clinical Relationship 最低字段

- `relationship_id`
- `from_object_id`
- `to_object_id`
- `relation_type`
- `direction`
- `source_type`
- `source_refs`
- `risk_level`
- `conditions`
- `logic_operator`
- `polarity`
- `review_status`

按关系类型可追加：

- population
- timeframe
- exclusions
- dose_numeric_id
- recommendation_strength
- recommendation_class
- evidence_level

### direction

建议枚举：

- from_to
- to_from
- bidirectional
- none

### logic_operator

- AND
- OR
- NOT
- EXCEPT
- NONE

### polarity

- positive
- negative
- contraindicated
- not_recommended
- excluded
- not_applicable

### review_status

固定为：

- SUPPORTED
- PARTIALLY_SUPPORTED
- UNSUPPORTED
- CONFLICT
- AMBIGUOUS
- NEEDS_HUMAN_REVIEW

### provenance 与推理约束

1. Clinical Relationship provenance 独立于节点 Claim provenance。
2. SOURCE Relationship 必须有直接支持关系类型与方向的 SourceRef。
3. 禁止自动建立 transitive closure：
   - A→B
   - B→C
   - 不自动产生 A→C。
4. 跨来源路径必须保持 Relationship 级 SourceRef。
5. 完整 Path 可单独拥有 SUMMARY / SYNTHESIS provenance。
6. 未连接节点不得被自动补齐关系。
7. RED SYNTHESIS / CONFLICT / 关键 condition 不完整时不得自动 approved。

### Visual Connector Binding

最终具备医学意义的连接器必须存在：

```json
{
  "visual_binding_id": "VB-CONN-001",
  "binding_type": "connector_to_relationship",
  "from_object_id": "VISUAL_LINE_01",
  "to_object_id": "REL001",
  "locked": true
}
```

一个视觉 Connector 可以显式绑定一组 Relationship ID，但不得无底层关系存在。



## 8E. ContextContract

```json
{
  "context_contract_id": "CC001",
  "project_id": "PRJ001",
  "scope_type": "section",
  "scope_ids": ["SEC03"],
  "inherited_context": {
    "population": "severe_asthma",
    "subgroup": null,
    "outcome": "moderate_to_severe_exacerbation",
    "timeframe": "52_weeks",
    "intervention": "drug_x",
    "comparator": "placebo"
  },
  "source_refs": ["SRC101", "SRC102"],
  "inheritance_allowed": true,
  "reset_triggers": [
    "new_study",
    "new_guideline",
    "new_population",
    "new_intervention",
    "new_case",
    "new_section"
  ],
  "overrides": [],
  "status": "active"
}
```

### 规则

1. Context 继承必须显式存在 ContextContract；
2. 相邻页面本身不构成继承；
3. 当前页显式 DataBinding / Claim 限定优先于继承；
4. 触发语义边界时必须 reset 或显式 override；
5. ContextContract 不能产生 Clinical Relationship。

---

## 8F. ContextualImplication

```json
{
  "contextual_implication_id": "CTX001",
  "project_id": "PRJ001",
  "scope_type": "adjacent_pages",
  "scope_ids": ["S05", "S06"],
  "trigger_type": "narrative_sequence",
  "trigger_text": "基于上述特点",
  "implied_relation_type": "biomarker_guides_treatment",
  "implied_from_object_id": "OBJ_BIOMARKER",
  "implied_to_object_id": "OBJ_TREATMENT",
  "source_type": "SYNTHESIS",
  "risk_level": "RED",
  "comparability_required": false,
  "status": "NEEDS_HUMAN_REVIEW",
  "recommended_resolution": "add_qualifier_or_reorder"
}
```

### scope_type

- intra_page
- adjacent_pages
- section

### trigger_type

- transition_phrase
- narrative_sequence
- parallel_comparison
- question_presupposition
- inherited_context
- grouping
- title_carryover
- other

### status

固定为：

- NO_MATERIAL_IMPLICATION
- SUPPORTED
- PARTIALLY_SUPPORTED
- UNSUPPORTED
- CONFLICT
- AMBIGUOUS
- NEEDS_HUMAN_REVIEW

### Risk propagation

如果 implied relationship 属于 RED Clinical Relationship：
- `risk_level = RED`
- 按 RED Gate 处理。



## 8G. MedicalVisual

```json
{
  "medical_visual_id": "MV001",
  "project_id": "PRJ001",
  "page_id": "S09",
  "visual_type": "mechanism_map",
  "visual_origin": "REDRAWN_FROM_EVIDENCE",
  "transformation_type": "SEMANTIC_SYNTHESIS",
  "semantic_object_ids": ["OBJ101", "OBJ102", "OBJ103"],
  "semantic_relationship_ids": ["REL201", "REL202"],
  "medical_semantic_source_refs": ["SRC301", "SRC305"],
  "visual_asset_source_refs": [],
  "node_provenance_coverage": 1.0,
  "relationship_provenance_coverage": 1.0,
  "medical_verified": true,
  "copyright_status": "not_applicable_original_render",
  "license": null,
  "commercial_use": true,
  "adaptation_allowed": true,
  "citation_required": true,
  "review_status": "approved"
}
```

### visual_origin

至少支持：

- SOURCE_FIGURE
- ADAPTED_FROM_SOURCE
- REDRAWN_FROM_EVIDENCE
- MEDICAL_REFERENCE_ASSET
- AI_GENERATED_MEDICAL_VISUAL

### transformation_type

- EXACT_REUSE
- STYLE_ONLY
- LAYOUT_REDESIGN
- SEMANTIC_SIMPLIFICATION
- SEMANTIC_SYNTHESIS
- AI_GENERATED

### provenance

必须分离：

- `medical_semantic_source_refs`
- `visual_asset_source_refs`

### RED Medical Visual Gate

如果 `risk_level=RED`：

- 关键 Node provenance coverage = 100%；
- 关键 Relationship provenance coverage = 100%；
- AI_GENERATED_MEDICAL_VISUAL 必须 `medical_verified=true`；
- Semantic Fidelity QA 必须 PASS；
- 任何关键关系缺失来源 → BLOCK / HUMAN_REVIEW_REQUIRED。

---

## 8H. VisualSemanticBinding

```json
{
  "visual_binding_id": "VB101",
  "page_id": "S09",
  "binding_type": "color_to_semantic",
  "from_object_id": "COLOR_RED",
  "to_object_id": "REL_CONTRAINDICATED",
  "semantic_value": "contraindicated",
  "binding_scope": "page",
  "locked": true,
  "review_status": "verified"
}
```

支持：

- group_to_meaning
- proximity_to_relation
- alignment_to_correspondence
- enclosure_to_membership
- hierarchy_to_priority
- color_to_semantic
- gradient_to_scale
- size_to_magnitude
- thickness_to_strength
- legend_to_series
- axis_to_metric
- axis_to_unit
- category_to_population
- category_to_timepoint
- annotation_to_comparison
- symbol_to_semantic
- connector_to_relationship
- label_to_numeric

### priority_semantics

视觉层级如承担优先级含义，必须标：

- presentation_priority
- clinical_priority
- evidence_priority
- risk_priority
- other

不得通过 Presentation Priority 偷偷表达 Clinical Priority。

---

## 8I. VisualScaleSpec

```json
{
  "visual_scale_id": "VS001",
  "page_id": "S10",
  "chart_id": "CHART01",
  "axis": "y",
  "scale_type": "linear",
  "min": 0,
  "max": 100,
  "unit": "%",
  "truncated": false,
  "reversed": false,
  "misrepresentation_check": "PASS"
}
```

用于检查：
- linear / log；
- truncated axis；
- reversed axis；
- range；
- percentage vs percentage point；
- visual effect exaggeration。


## 9. Node

```json
{
  "node_id": "N001",
  "project_id": "PRJ001",
  "label": "过去一年≥1次中重度急性加重",
  "node_type": "risk_criterion",
  "claim_ids": ["C010"],
  "source_type": "SOURCE",
  "source_refs": ["SRC010"],
  "risk_level": "RED",
  "locked": true,
  "review_status": "verified"
}
```

`node_type`
- clinical_question
- population
- finding
- test
- criterion
- diagnosis
- phenotype
- treatment
- recommendation
- outcome
- follow_up
- evidence
- other

---

## 10. TriageDecision

```json
{
  "triage_id": "TRI001",
  "claim_id": "C001",
  "presentation_question": "GOLD 2026 有哪些影响临床管理的重要变化？",
  "audience": "resident",
  "project_type": "guideline",
  "goal": "literature_interpretation",
  "duration_minutes": 10,
  "bucket": "MUST_INCLUDE",
  "question_relevance": "high",
  "audience_relevance": "high",
  "narrative_necessity": "high",
  "evidence_importance": "medium",
  "source_centrality": "high",
  "risk_level": "RED",
  "presentation_cost": "medium",
  "meaning_preserving_bundle_id": "MPB001",
  "presentation_dependencies": ["C022", "C025"],
  "reasons": [
    "directly_answers_presentation_question",
    "major_guideline_update",
    "required_for_next_section"
  ],
  "user_override": false,
  "override_from": null,
  "override_to": null,
  "override_reason": null,
  "generated_by": "information_triage_agent"
}
```

### 10.1 bucket

固定枚举：

- MUST_INCLUDE
- SHOULD_INCLUDE
- APPENDIX
- EXCLUDED

`EXCLUDED` 仅代表不进入本次汇报，原始 Claim 永不删除。

### 10.2 relevance / necessity

建议 MVP 使用：

- low
- medium
- high

适用字段：

- question_relevance
- audience_relevance
- narrative_necessity
- evidence_importance
- source_centrality

### 10.3 presentation_cost

- low
- medium
- high

MVP 不要求伪精确到秒。

### 10.4 Meaning-Preserving Bundle

```json
{
  "bundle_id": "MPB001",
  "claim_ids": ["C001", "C004", "C007"],
  "reason": "删除其中限定条件将改变推荐的医学意义",
  "risk_level": "RED",
  "split_allowed": false
}
```

### 10.5 Presentation Dependency

Presentation Dependency 是**演示组织依赖**，不代表临床事实关系，不得写入 Edge Table。

```json
{
  "dependency_id": "PD001",
  "from_claim_id": "C002",
  "to_claim_id": "C001",
  "dependency_type": "required_to_explain",
  "reason": "核心变化需要该证据说明为什么发生",
  "source_type": "presentation_logic"
}
```

### 10.6 Override

用户可改变 Bucket，但必须记录原值、新值、理由、操作者与时间；修改后重新计算页面预算。

## 11. NarrativePlan

```json
{
  "narrative_id": "NAR001",
  "project_id": "PRJ001",
  "presentation_question": "GOLD 2026 有哪些影响临床管理的重要变化？",
  "narrative_spine": "从更早识别风险走向动态、精准和连续管理",
  "spine_source_type": "SYNTHESIS",
  "spine_source_refs": ["SRC010", "SRC022", "SRC034"],
  "audience": "resident",
  "project_type": "guideline",
  "duration_minutes": 10,
  "sections": ["SEC01", "SEC02", "SEC03"],
  "user_override": false,
  "version": 1
}
```

### 11.1 Section

```json
{
  "section_id": "SEC01",
  "narrative_id": "NAR001",
  "order": 1,
  "section_question": "为什么管理起点发生变化？",
  "section_title": "高风险识别进一步前移",
  "title_source_type": "SUMMARY",
  "page_ids": ["S02", "S03"]
}
```

Narrative Spine、Section Title 均必须保留 provenance。

---

## 11A. PageSpec

Approved Content Graph 的页面级语义结构。

```json
{
  "page_id": "S05",
  "project_id": "PRJ001",
  "section_id": "SEC02",
  "page_goal": "解释急性加重风险阈值变化",
  "primary_message": "新版风险识别阈值前移",
  "primary_message_source_type": "SUMMARY",
  "primary_message_source_refs": ["SRC022"],
  "primary_claim_ids": ["C022"],
  "supporting_claim_ids": ["C023", "C024"],
  "required_condition_claim_ids": ["C025"],
  "presentation_dependency_ids": ["PD003"],
  "visual_type": "evidence_map",
  "content_depth": "presentation",
  "cognitive_load": "medium",
  "locked_claim_ids": ["C022", "C023", "C024", "C025"],
  "semantic_page_graph_id": "SPG005",
  "semantic_object_ids": ["OBJ010", "OBJ011", "OBJ012"],
  "semantic_relationship_ids": ["REL010", "REL011"],
  "data_binding_ids": ["DB001"],
  "visual_binding_ids": ["VB001", "VB002"],
  "medical_visual_ids": ["MV001"],
  "source_refs": ["SRC022", "SRC023"],
  "risk_level": "RED",
  "design_freedom": [
    "layout",
    "typography",
    "whitespace",
    "color"
  ],
  "content_status": "approved"
}
```

### 11A.1 页面四层信息模型

1. Primary Message；
2. Supporting Claims；
3. Conditions / Data / Caveats；
4. Source。

### 11A.2 visual_type

- decision_map
- evidence_map
- disease_timeline
- mechanism_map
- risk_stratification_map
- outcome_plot
- management_cycle
- trial_evidence_matrix
- comparison
- structured_text
- table
- other

### 11A.3 content_depth

- presentation
- reference
- backup

### 11A.4 cognitive_load

- low
- medium
- high

### 11A.5 Architect 约束

- PageSpec 只能引用既有 Claim；
- Architect 可推荐 visual_type；
- Architect 不得创建未经验证的 Semantic Relationship / Clinical Relationship；
- `primary_message` 若为 SUMMARY / SYNTHESIS 必须保留 provenance；
- Meaning-Preserving Bundle 不得被拆分到改变医学意义；
- Narrative / Page Order Override 必须写 AuditLog。


## 11B. SemanticPageGraph

```json
{
  "semantic_page_graph_id": "SPG005",
  "page_id": "S05",
  "title_object_id": "TITLE_S05",
  "primary_message_object_id": "PM_S05",
  "semantic_object_ids": ["OBJ010", "OBJ011", "OBJ012"],
  "semantic_relationship_ids": ["REL010", "REL011"],
  "data_binding_ids": ["DB001"],
  "visual_binding_ids": ["VB001", "VB002"],
  "medical_visual_ids": ["MV001"],
  "title_entailment_ids": ["TE001"],
  "context_contract_ids": ["CC001"],
  "contextual_implication_ids": ["CTX001"],
  "visual_encoding_contract_id": "VEC005",
  "status": "draft"
}
```

状态：

- draft
- verified
- approved
- blocked

---

## 11C. VisualEncodingContract

```json
{
  "visual_encoding_contract_id": "VEC005",
  "page_id": "S05",
  "allowed_renderer": "evidence_map",
  "locked_bindings": [
    "VB001",
    "VB002"
  ],
  "forbidden_semantic_changes": [
    "new_relationship",
    "relationship_direction_change",
    "legend_series_swap",
    "axis_metric_change",
    "color_semantic_change",
    "group_membership_change"
  ],
  "pure_styling_freedom": [
    "font",
    "font_size",
    "whitespace",
    "non_semantic_background",
    "decorative_line_width"
  ]
}
```



## 12A. VerificationResult

```json
{
  "verification_id": "VER001",
  "project_id": "PRJ001",
  "verification_mode": "SOURCE_FIDELITY",
  "object_type": "clinical_relationship",
  "object_id": "REL021",
  "status": "PARTIALLY_SUPPORTED",
  "risk_level": "RED",
  "supporting_source_refs": ["SRC051"],
  "supporting_spans": [
    {
      "source_ref": "SRC051",
      "chunk_id": "CHK051",
      "page": 6,
      "quote": "source-supported excerpt"
    }
  ],
  "issue_ids": ["ISS001"],
  "explanation": "原文限定为特定高风险患者，生成关系扩大到全部患者。",
  "recommended_action": "RETURN_FOR_REVISION",
  "model_confidence": 0.91,
  "human_review_required": true,
  "verifier_version": "0.1"
}
```

### verification_mode

- SOURCE_FIDELITY
- CROSS_SOURCE_CONSISTENCY
- EXTERNAL_MEDICAL_CHECK

### status

固定为：

- SUPPORTED
- PARTIALLY_SUPPORTED
- UNSUPPORTED
- CONFLICT
- AMBIGUOUS
- NEEDS_HUMAN_REVIEW
- NOT_APPLICABLE

### 约束

- `model_confidence` 不参与 RED 自动批准；
- SOURCE_FIDELITY 与 EXTERNAL_MEDICAL_CHECK 的 Source Pool 必须分离；
- supporting SourceRef 存在不代表 SUPPORTED，仍需语义判断。

---

## 12B. VerificationIssue

```json
{
  "issue_id": "ISS001",
  "verification_id": "VER001",
  "issue_type": "POPULATION_EXPANSION",
  "severity": "critical",
  "responsible_module": "medical_information_architect",
  "object_type": "clinical_relationship",
  "object_id": "REL021",
  "details": "Generated scope is broader than source-supported scope.",
  "recommended_action": "RETURN_FOR_REVISION",
  "resolved": false
}
```

建议 MVP issue_type：

**Claim**
- SOURCE_NOT_FOUND
- SOURCE_MISMATCH
- CONDITION_LOSS
- POPULATION_EXPANSION
- TIMEFRAME_CHANGE
- EXCLUSION_LOSS
- UNCERTAINTY_UPGRADE

**Relationship**
- UNSUPPORTED_RELATIONSHIP
- WRONG_DIRECTION
- RELATIONSHIP_TYPE_UPGRADE
- CAUSALITY_UPGRADE
- RECOMMENDATION_STRENGTH_UPGRADE
- LOGIC_OPERATOR_MISMATCH
- POLARITY_MISMATCH
- TRANSITIVE_INFERENCE

**Data**
- WRONG_METRIC
- WRONG_OUTCOME
- WRONG_POPULATION
- WRONG_TIMEFRAME
- WRONG_COMPARATOR
- VALUE_ROLE_MISMATCH

**Context**
- UNSUPPORTED_CONTEXTUAL_IMPLICATION
- CONTEXT_CONTAMINATION
- UNSUPPORTED_COMPARISON
- QUESTION_PRESUPPOSITION

**Visual**
- VISUAL_RELATIONSHIP_MISMATCH
- SEMANTIC_SIMPLIFICATION_ERROR
- MEDICAL_VISUAL_UNVERIFIED
- VISUAL_PROVENANCE_MISSING

---

## 12C. SourcePriorityPolicy

仅在 CROSS_SOURCE_CONSISTENCY 或 EXTERNAL_MEDICAL_CHECK 需要规则化处理冲突时启用。

```json
{
  "source_priority_policy_id": "SPP001",
  "project_id": "PRJ001",
  "enabled": false,
  "rules": [
    {
      "priority": 1,
      "source_type": "current_official_guideline"
    },
    {
      "priority": 2,
      "source_type": "older_official_guideline"
    }
  ],
  "auto_resolve_allowed": false
}
```

没有明确 SourcePriorityPolicy：
- Conflict 必须保留；
- 不允许模型自行裁决。



## 12D. SemanticFrame

用于 Medical Verifier 对 Source 与 Generated Object 做结构化语义比较。

```json
{
  "semantic_frame_id": "SF001",
  "object_id": "REL021",
  "frame_role": "generated",
  "population": "selected_high_risk_patients",
  "subgroup": null,
  "disease_stage": null,
  "risk_group": "high_risk",
  "setting": null,
  "condition_ids": ["C101", "C102"],
  "logic_operator": "AND",
  "intervention": "drug_x",
  "comparator": null,
  "outcome": "moderate_to_severe_exacerbation",
  "timeframe": "52_weeks",
  "dose_numeric_id": null,
  "threshold_numeric_ids": [],
  "exclusion_ids": ["C103"],
  "polarity": "positive",
  "quantifier": "selected",
  "modality": "may_consider",
  "relation_type": "recommended_treatment",
  "direction": "from_to",
  "recommendation_strength": "consider",
  "recommendation_class": "IIa",
  "evidence_level": "B"
}
```

### Meaning-Critical Slots

至少包括：

- population
- subgroup
- disease_stage
- risk_group
- setting
- conditions
- logic_operator
- intervention
- comparator
- outcome
- timeframe
- dose
- threshold
- exclusions
- polarity
- quantifier
- modality
- relation_type
- direction
- recommendation_strength
- recommendation_class
- evidence_level

---

## 12E. SemanticDiff

```json
{
  "semantic_diff_id": "SD001",
  "verification_id": "VER001",
  "slot": "population",
  "source_value": "selected_high_risk_patients",
  "generated_value": "high_risk_patients",
  "diff_type": "SCOPE_EXPANSION",
  "meaning_critical": true,
  "severity": "critical"
}
```

### diff_type

建议支持：

- SLOT_DELETION
- SLOT_ADDITION
- SLOT_SUBSTITUTION
- SCOPE_EXPANSION
- SCOPE_NARROWING
- QUANTIFIER_UPGRADE
- QUANTIFIER_DOWNGRADE
- MODALITY_UPGRADE
- MODALITY_DOWNGRADE
- POLARITY_FLIP
- CONDITION_LOSS
- CONDITION_ADDITION
- LOGIC_OPERATOR_CHANGE
- RELATIONSHIP_TYPE_CHANGE
- DIRECTION_CHANGE
- RECOMMENDATION_STRENGTH_CHANGE
- CLASS_MISMATCH
- EVIDENCE_LEVEL_MISMATCH
- EXCLUSION_LOSS
- TIMEFRAME_CHANGE

---

## 12F. SourceSpanSupport

```json
{
  "source_span_support_id": "SSS001",
  "verification_id": "VER001",
  "source_ref": "SRC051",
  "chunk_id": "CHK051",
  "page": 6,
  "span_text": "source-supported excerpt",
  "support_scope": [
    "population",
    "condition",
    "recommendation_strength"
  ],
  "sufficiency_status": "SUFFICIENT",
  "rank": 1
}
```

### sufficiency_status

- SUFFICIENT
- PARTIALLY_SUFFICIENT
- INSUFFICIENT
- CONFLICTING

---

## 12G. SourceSetConsistency

```json
{
  "source_set_consistency_id": "SSC001",
  "verification_id": "VER001",
  "source_refs": ["SRC001", "SRC002", "SRC003"],
  "consistency_status": "CONFLICT",
  "conflicting_source_refs": ["SRC002"],
  "priority_policy_applied": false
}
```

用于禁止 Cherry-pick。



## 12H. RevisionSnapshot

```json
{
  "revision_id": "REV001",
  "object_type": "claim",
  "object_id": "C021",
  "new_version": 2,
  "supersedes_version": 1,
  "verification_issue_ids": ["ISS003"],
  "responsible_module": "claim_builder",
  "revision_reason": "restore missing condition",
  "created_at": "ISO8601"
}
```

医学对象修订采用不可变版本：
- 旧版本永久保留；
- 新版本通过 `supersedes_version` 建立链路；
- 不允许覆盖历史。

---

## 12I. ObjectDependency

```json
{
  "dependency_id": "DEP001",
  "upstream_object": "C021:v1",
  "downstream_object": "TITLE_S05:v2",
  "dependency_type": "supports",
  "status": "active"
}
```

上游版本发生实质语义修改时：
- 依赖旧版本的下游对象 → `STALE` / `INVALIDATED`；
- 不得继续进入 Approved Graph。

---

## 12J. ReverificationRun

```json
{
  "reverification_run_id": "RR001",
  "trigger_revision_id": "REV001",
  "target_issue_ids": ["ISS003"],
  "targeted_reverification": {
    "status": "PASS"
  },
  "regression_verification": {
    "status": "PASS",
    "new_issue_ids": []
  },
  "affected_gate_runs": [
    "medical_fidelity",
    "data_binding",
    "context"
  ],
  "final_status": "PASS"
}
```

---

## 12K. VerificationIssue Lifecycle

`issue_status` 固定至少支持：

- OPEN
- ROUTED
- IN_REVISION
- RESOLVED_PENDING_REVERIFY
- VERIFIED_RESOLVED
- UNRESOLVED
- HUMAN_REVIEW_REQUIRED
- WAIVED_BY_HUMAN

约束：
- Responsible Module 只能把 Issue 推进至 `RESOLVED_PENDING_REVERIFY`；
- `VERIFIED_RESOLVED` 只能由独立 Re-verification 写入。

---

## 12L. HumanOverride

```json
{
  "override_id": "HOV001",
  "verification_issue_id": "ISS009",
  "verification_result_id": "VER009",
  "original_status": "UNSUPPORTED",
  "decision": "APPROVED_WITH_OVERRIDE",
  "override_provenance": "HUMAN_SYNTHESIS",
  "reason": "专家明确同意保留该综合判断",
  "reviewer_id": "REVIEWER001",
  "created_at": "ISO8601"
}
```

Human Override：
- 不修改原 VerificationResult；
- 不把 UNSUPPORTED 改写为 SUPPORTED；
- 单独记录人工批准层。

---

## 12M. RetryBudget

```json
{
  "retry_budget_id": "RB001",
  "project_id": "PRJ001",
  "module": "medical_information_architect",
  "max_auto_revision_attempts": 2,
  "current_attempt": 1,
  "recurrent_issue_threshold": 2,
  "status": "active"
}
```

具体次数为配置项，不作为 v0.1 固定常量。

---

## 12N. ApprovedObjectRef

```json
{
  "approved_ref_id": "AOR001",
  "object_type": "claim",
  "object_id": "C021",
  "object_version": 3,
  "immutable_ref": "C021:v3",
  "approved_snapshot_id": "APS001"
}
```

最终 Approved Semantic Page Graph / Export Manifest：
- 必须引用不可变版本；
- 禁止使用动态 `latest`。



## 12O. SourceContextFrame

```json
{
  "source_context_frame_id": "SCF001",
  "source_id": "SRC001",
  "source_type": "guideline",
  "organization": "Example Society",
  "publication_date": "2026-01-01",
  "version": "2026",
  "jurisdiction": "global",
  "population": "severe_asthma",
  "disease_stage": null,
  "setting": "specialist_care",
  "intervention_scope": ["drug_x"],
  "comparator_scope": [],
  "outcome_scope": ["exacerbation"],
  "timeframe_scope": ["52_weeks"],
  "evidence_scope": "guideline_recommendation",
  "intended_use": "clinical_guidance"
}
```

---

## 12P. CrossSourceConflict

```json
{
  "cross_source_conflict_id": "CSC001",
  "object_id": "C101",
  "source_refs": ["SRC001", "SRC002"],
  "comparability_status": "comparable",
  "conflict_type": "VERSION_CHANGE",
  "conflict_status": "CONFIRMED",
  "details": "Recommendation wording changed between versions.",
  "source_priority_policy_id": null,
  "human_review_required": false
}
```

### conflict_type

至少支持：

- DIRECT_CONTRADICTION
- VERSION_CHANGE
- SCOPE_DIFFERENCE
- POPULATION_DIFFERENCE
- CONDITION_DIFFERENCE
- EVIDENCE_EVOLUTION
- RECOMMENDATION_DIFFERENCE
- REGULATORY_DIFFERENCE
- JURISDICTION_DIFFERENCE
- SOURCE_AUTHORITY_DIFFERENCE
- UNRESOLVED_INCONSISTENCY

---

## 12Q. SourceVersionRelation

```json
{
  "source_version_relation_id": "SVR001",
  "older_source_ref": "SRC2024",
  "newer_source_ref": "SRC2026",
  "relation": "SUPERSEDES",
  "evidence_source_ref": "SRC2026",
  "status": "VERIFIED"
}
```

### relation

- SUPERSEDES
- AMENDS
- SUPPLEMENTS
- CORRECTS
- RETRACTS
- UNKNOWN

不得仅凭发布日期自动生成关系。

---

## 12R. ClaimSupersession

```json
{
  "claim_supersession_id": "CSU001",
  "older_claim_ref": "C2024-01:v1",
  "newer_claim_ref": "C2026-04:v1",
  "status": "SUPERSEDED",
  "reason": "explicit_recommendation_change",
  "verified": true
}
```

支持 Claim / Relationship 粒度版本替代。

---

## 12S. SourceQualification

```json
{
  "source_qualification_id": "SQ001",
  "source_ref": "EXT001",
  "source_type": "regulatory_document",
  "organization": "Example Regulator",
  "date_or_version": "2026-05",
  "primary_secondary": "primary",
  "official_status": "official",
  "regulatory_status": "authoritative_for_jurisdiction",
  "jurisdiction": "CN",
  "verifiable_identifier": "ID-001",
  "qualification_status": "QUALIFIED_FOR_HIGH_RISK"
}
```

### qualification_status

- QUALIFIED_FOR_HIGH_RISK
- QUALIFIED_FOR_BACKGROUND
- LEAD_ONLY
- REJECTED

---

## 12T. ExternalVerificationFinding

```json
{
  "external_finding_id": "EVF001",
  "project_id": "PRJ001",
  "target_object_id": "C101:v2",
  "finding_type": "NEWER_GUIDELINE_FOUND",
  "external_source_refs": ["EXT001"],
  "verified_as_of": "2026-09-04",
  "search_scope": "official guideline and regulatory sources",
  "source_versions": ["2026"],
  "finding_status": "NEEDS_HUMAN_REVIEW",
  "provenance": "EXTERNAL_VERIFICATION",
  "auto_modify_source_faithful_content": false
}
```

---

## 12U. RegulatoryVerification

```json
{
  "regulatory_verification_id": "RV001",
  "object_id": "C201",
  "jurisdiction": "CN",
  "indication_status": "not_approved",
  "dose_status": "verified",
  "contraindication_status": "verified",
  "approval_status": "not_approved_for_indication",
  "reimbursement_status": "unknown",
  "regulatory_source_refs": ["REG001"],
  "verified_as_of": "2026-09-04"
}
```

Guideline Recommendation 与 Regulatory Status 分开保存。

---

## 12V. EvidenceSynthesis

```json
{
  "evidence_synthesis_id": "ES001",
  "synthesis_claim": "现有证据支持疗效，但当地尚未批准该适应证。",
  "source_type": "SYNTHESIS",
  "component_bindings": [
    {
      "component": "efficacy_supported",
      "source_refs": ["RCT001", "META001"]
    },
    {
      "component": "not_locally_approved",
      "source_refs": ["REG001"]
    }
  ],
  "risk_level": "RED",
  "review_status": "NEEDS_HUMAN_REVIEW"
}
```


## 12. ReviewItem

```json
{
  "review_item_id": "REV001",
  "project_id": "PRJ001",
  "page_id": "S05",
  "object_type": "semantic_relationship",
  "object_id": "REL010",
  "risk_level": "RED",
  "issue_type": "synthesis_relation",
  "description": "该关键路径为多处资料综合",
  "source_refs": ["SRC022", "SRC023"],
  "auto_result": "needs_human",
  "human_decision": null,
  "human_comment": null,
  "status": "pending"
}
```

`issue_type`
- numeric_mismatch
- missing_source
- synthesis_relation
- recommendation_conflict
- evidence_level_conflict
- missing_condition
- privacy
- compliance
- other

---

## 13. ComplianceIssue

```json
{
  "issue_id": "CMP001",
  "project_id": "PRJ001",
  "page_id": "S09",
  "channel": "public_xiaohongshu",
  "category": "medical_advice_risk",
  "severity": "block",
  "description": "公开页面存在面向普通用户的明确治疗推荐",
  "suggested_action": "改为资料整理与视觉表达示例",
  "status": "open"
}
```

`severity`
- warn
- block

`category`
- patient_privacy
- institution_identifier
- copyright
- citation
- medical_advice_risk
- efficacy_claim
- drug_promotion
- external_contact
- endorsement
- disclaimer
- other

---

## 14. QAResult

```json
{
  "qa_id": "QA001",
  "project_id": "PRJ001",
  "page_id": "S05",
  "qa_type": "numerical",
  "target_id": "NUM001",
  "source_value": "48%",
  "slide_value": "48%",
  "result": "match",
  "severity": "none"
}
```

`qa_type`
- numerical
- semantic
- layout
- citation
- export

`result`
- match
- mismatch
- warning
- pass
- fail

---

## 15. SyntheticCase

仅在用户明确开启时存在。

```json
{
  "synthetic_case_id": "SC001",
  "project_id": "PRJ001",
  "enabled_by_user": true,
  "label": "AI生成模拟病例｜非原文病例｜仅用于教学演示",
  "content": {},
  "validation_source_refs": [],
  "separate_from_source_layer": true
}
```

规则：

- `enabled_by_user` 必须为 true；
- 不允许 Claim `source_type=SOURCE`；
- 页面必须显著标注；
- 默认不创建该实体。

---

## 16. AuditLog

```json
{
  "audit_id": "AUD001",
  "project_id": "PRJ001",
  "event_type": "agent_run",
  "agent_name": "medical_verifier",
  "agent_version": "0.1",
  "model_name": "...",
  "model_version": "...",
  "prompt_version": "verifier_v03",
  "input_version": "claim_graph_v07",
  "output_version": "claim_graph_v08",
  "user_id": null,
  "timestamp": "ISO8601",
  "metadata": {}
}
```

必须记录：

- 文件哈希；
- 模型版本；
- Prompt 版本；
- Agent 版本；
- Claim Graph 版本；
- 用户人工修改；
- 医学审核；
- Compliance；
- 最终导出版本。

---

## 17. 数据一致性约束

1. `locked=true` 的 Claim / Node / Edge 不允许 Design Agent 改值；
2. SOURCE Claim 必须至少有一个 SourceRef；
3. SOURCE Semantic Relationship 必须至少有一个 SourceRef；
4. RED Claim 在进入 DELIVERED 前必须 verified 或 human approved；
5. RED SYNTHESIS Semantic Relationship 必须 human approved；
6. NumericFact mismatch 阻止自动交付；
7. `synthetic_case=false` 时禁止创建 SyntheticCase；
8. public_xiaohongshu 存在 Compliance `block` 时禁止交付公开版本。

---


## 17A. Rule Registry

所有冻结规则必须存在结构化注册记录。

```json
{
  "rule_id": "ARC-007",
  "module": "medical_information_architect",
  "version": "0.1",
  "title": "Architect不得创建SemanticRelationship / ClinicalRelationship",
  "rule_text": "Medical Information Architect不得创建未经验证的Clinical Edge",
  "constraint_type": "HARD",
  "enforced_by": [
    "capability_control",
    "output_schema"
  ],
  "validated_by": [
    "policy_engine"
  ],
  "violation_action": "BLOCK",
  "severity": "critical",
  "enabled": true
}
```

### constraint_type

- HARD
- SEMANTIC
- HUMAN_GOVERNED

### violation_action

- BLOCK
- WARN
- HUMAN_REVIEW_REQUIRED
- RETRY
- FAIL_TASK

### severity

- low
- medium
- high
- critical

---

## 17B. AgentCapability

```json
{
  "capability_id": "CAP-ARCH-001",
  "agent_name": "medical_information_architect",
  "read_resources": [
    "triage_decisions",
    "claims",
    "presentation_dependencies"
  ],
  "write_resources": [
    "narrative_plans",
    "narrative_sections",
    "page_specs"
  ],
  "forbidden_resources": [
    "clinical_edges",
    "numeric_facts"
  ],
  "tool_allowlist": [
    "read_claims",
    "write_narrative_plan",
    "write_page_spec"
  ]
}
```

---

## 17C. PolicyDecision

```json
{
  "policy_decision_id": "POL001",
  "project_id": "PRJ001",
  "object_type": "page_spec",
  "object_id": "S05",
  "workflow_state": "ARCHITECTED",
  "decision": "BLOCK",
  "violated_rule_ids": [
    "ARC-007"
  ],
  "required_review_ids": [],
  "evaluated_at": "ISO8601",
  "policy_engine_version": "0.1"
}
```

`decision`：

- PASS
- BLOCK
- HUMAN_REVIEW_REQUIRED

---

## 17D. ViolationRecord

```json
{
  "violation_id": "VIO001",
  "project_id": "PRJ001",
  "rule_id": "ARC-007",
  "agent_name": "medical_information_architect",
  "object_type": "page_spec",
  "object_id": "S05",
  "violation_type": "unauthorized_semantic_relationship",
  "details": "Architect输出包含未授权Clinical Edge E_TMP_01",
  "action_taken": "BLOCK",
  "created_at": "ISO8601"
}
```

---

## 17E. Policy Gate 数据一致性约束

1. 每条 FROZEN Rule 必须存在 RuleRegistry；
2. Hard Constraint 必须至少指定一个程序化 `enforced_by`；
3. `constraint_type=HUMAN_GOVERNED` 且未审核时，不得进入 DELIVERED；
4. `decision=BLOCK` 时禁止状态推进；
5. `decision=HUMAN_REVIEW_REQUIRED` 时只能进入对应人工审核状态；
6. Agent 写入其 `forbidden_resources` 必须生成 ViolationRecord；
7. PolicyDecision 必须进入 AuditLog。

---

## 18. 推荐数据库表

MVP：

- projects
- documents
- source_chunks
- claims
- canonical_claims
- conflict_groups
- numeric_facts
- source_refs
- nodes
- semantic_objects
- semantic_relationships
- data_bindings
- visual_bindings
- title_entailments
- contextual_implications
- semantic_page_graphs
- visual_encoding_contracts
- triage_decisions
- meaning_preserving_bundles
- presentation_dependencies
- narrative_plans
- narrative_sections
- page_specs
- review_items
- verification_results
- verification_issues
- source_priority_policies
- semantic_frames
- semantic_diffs
- source_span_supports
- source_set_consistency
- revision_snapshots
- object_dependencies
- reverification_runs
- human_overrides
- retry_budgets
- approved_object_refs
- source_context_frames
- cross_source_conflicts
- source_version_relations
- claim_supersessions
- source_qualifications
- external_verification_findings
- regulatory_verifications
- evidence_syntheses
- compliance_issues
- qa_results
- synthetic_cases
- audit_logs
- rule_registry
- agent_capabilities
- policy_decisions
- violation_records


---

## 13A. VisualGenerationContract

```json
{
  "visual_generation_contract_id": "VGC001",
  "project_id": "PRJ001",
  "page_id": "S12",
  "approved_semantic_page_graph_version": "SPG012:v4",
  "page_identity": {
    "section_id": "SEC03",
    "page_type": "evidence_interpretation",
    "project_type": "medical_congress"
  },
  "page_goal": {
    "text": "帮助目标受众理解该页核心医学信息",
    "lock_level": "SEMANTIC_LOCK"
  },
  "audience": {
    "primary": "respiratory_specialists",
    "expertise_level": "specialist",
    "lock_level": "HARD_LOCK"
  },
  "primary_message": {
    "text": "approved primary message",
    "provenance": "SUMMARY",
    "claim_bindings": ["C021:v2"],
    "render_text_lock": "semantic"
  },
  "mandatory_object_ids": ["OBJ001", "OBJ002"],
  "exact_text_register_ids": ["ETR001"],
  "relationship_ids": ["REL001:v2"],
  "logic_contract_ids": ["LOG001"],
  "data_binding_ids": ["DB001"],
  "functional_visual_type": "clinical_decision_map",
  "visual_structure_contract_id": "VSC001",
  "layout_freedom_envelope_id": "LFE001",
  "visual_hierarchy_contract_id": "VHC001",
  "semantic_color_contract_id": "SCC001",
  "medical_visual_asset_contract_ids": ["MVAC001"],
  "generation_mode": "CONTROLLED_COMPOSITION",
  "prohibited_transformations": [
    "invent_medical_objects",
    "alter_numeric_values",
    "change_relation_direction",
    "change_logic_operator",
    "omit_exclusion",
    "add_fake_citation",
    "upgrade_recommendation_strength"
  ],
  "output_spec": {
    "aspect_ratio": "16:9",
    "presentation_slide": true
  },
  "post_generation_verification_contract_id": "PGVC001"
}
```

### lock_level

固定为：

- HARD_LOCK
- SEMANTIC_LOCK
- BOUNDED_CREATIVE
- FREE_CREATIVE

---

## 13B. MandatoryContentObjectRegister

```json
{
  "mandatory_object_register_id": "MCOR001",
  "page_id": "S12",
  "objects": [
    {
      "object_id": "OBJ001",
      "object_type": "biomarker",
      "display_label": "EOS",
      "source_object_ref": "C021:v2",
      "risk_level": "RED",
      "lock_level": "HARD_LOCK",
      "must_render": true
    }
  ]
}
```

---

## 13C. ExactTextRegister

```json
{
  "exact_text_register_id": "ETR001",
  "page_id": "S12",
  "items": [
    {
      "exact_text_id": "TXT001",
      "text": "EOS ≥300 cells/μL",
      "role": "threshold",
      "risk_level": "RED",
      "lock_level": "HARD_LOCK",
      "render_method": "CONTROLLED_COMPOSITION"
    }
  ]
}
```

适用于：
- 药名
- 数字
- 单位
- 阈值
- HR/OR/RR/CI/P
- Recommendation Class
- Evidence Level
- 关键引用

---

## 13D. VisualSemanticContract

```json
{
  "visual_semantic_contract_id": "VSC001",
  "page_id": "S12",
  "relationship_ids": ["REL001:v2"],
  "group_bindings": [],
  "logic_bindings": ["LOG001"],
  "legend_bindings": [],
  "hierarchy_bindings": [],
  "color_semantic_bindings": [],
  "connector_rules": [],
  "status": "LOCKED"
}
```

---

## 13E. LayoutFreedomEnvelope

```json
{
  "layout_freedom_envelope_id": "LFE001",
  "page_id": "S12",
  "reading_flow": "top_to_bottom",
  "title_region": {
    "preferred": "top",
    "max_height_ratio": 0.15
  },
  "main_visual": {
    "preferred_area_ratio_min": 0.55,
    "preferred_area_ratio_max": 0.70
  },
  "source_region": {
    "must_be_bottom": true
  },
  "asymmetry_allowed": true,
  "semantic_overlap_allowed": false
}
```

---

## 13F. VisualHierarchyContract

```json
{
  "visual_hierarchy_contract_id": "VHC001",
  "page_id": "S12",
  "items": [
    {
      "object_id": "PRIMARY_MESSAGE",
      "priority_rank": 1,
      "priority_semantics": "presentation_priority"
    }
  ]
}
```

`priority_semantics` 至少区分：

- presentation_priority
- clinical_priority
- evidence_priority
- risk_priority

---

## 13G. MedicalVisualAssetContract

```json
{
  "medical_visual_asset_contract_id": "MVAC001",
  "page_id": "S12",
  "semantic_role": "anatomical_reference",
  "allowed_origins": [
    "MEDICAL_REFERENCE_ASSET",
    "REDRAWN_FROM_EVIDENCE"
  ],
  "ai_generation_allowed": false,
  "medical_visual_qa_required": true,
  "medical_structure_lock": "SEMANTIC_LOCK",
  "artistic_style_freedom": "BOUNDED_CREATIVE"
}
```

---

## 13H. GenerationModeSpec

支持至少：

- FULL_IMAGE
- CONTROLLED_COMPOSITION

`CONTROLLED_COMPOSITION` 中可进一步声明：

```json
{
  "model_generates": [
    "background",
    "diagram_structure",
    "composition"
  ],
  "post_compositor_adds": [
    "exact_numbers",
    "drug_names",
    "references"
  ]
}
```

---

## 13I. PostGenerationVerificationContract

```json
{
  "post_generation_verification_contract_id": "PGVC001",
  "page_id": "S12",
  "requirements": {
    "mandatory_object_coverage": 1.0,
    "exact_text_fidelity": 1.0,
    "numeric_fidelity": 1.0,
    "relationship_fidelity": 1.0,
    "visual_semantic_fidelity": "PASS",
    "source_visibility": "REQUIRED"
  }
}
```

同一个 Visual Generation Contract 同时用于生成前约束与生成后验收。


---

# Module 06 Batch 2 Draft Schemas｜Visual Strategy Selector（未冻结）

## 13J. VisualTaxonomyRegistry

```json
{
  "visual_type": "CLINICAL_DECISION_MAP",
  "family": "CLINICAL_DECISION_ACTION",
  "supported_intents": [
    "TREATMENT_SELECTION",
    "PATIENT_SELECTION"
  ],
  "supported_relationship_structures": [
    "branching",
    "conditional"
  ],
  "supports_logic": [
    "AND",
    "OR",
    "NOT",
    "EXCEPT"
  ],
  "default_generation_strategies": [
    "DETERMINISTIC_DIAGRAM",
    "HYBRID_COMPOSITION"
  ],
  "hard_exclusions": []
}
```

---

## 13K. InformationStructureProfile

```json
{
  "information_structure_profile_id": "ISP001",
  "page_id": "S12",
  "quantitative": true,
  "categorical": true,
  "granularity": "aggregate",
  "time_dimension": "none",
  "uncertainty": "CI",
  "comparison_structure": "within_study",
  "comparability": "comparable",
  "relationship_structure": "branching",
  "logic": "AND",
  "precision_requirement": "exact",
  "study_context": "RCT",
  "standard_reporting_context": "none",
  "medical_risk": "RED"
}
```

---

## 13L. VisualCandidateScore

```json
{
  "visual_candidate_score_id": "VCS001",
  "visual_strategy_decision_id": "VSD001",
  "visual_type": "CLINICAL_DECISION_MAP",
  "hard_gate_status": "PASS",
  "hard_gate_reasons": [],
  "score_components": {
    "semantic_fit": 0.98,
    "medical_convention_fit": 0.93,
    "data_fidelity": 0.92,
    "auditability": 0.97,
    "audience_fit": 0.90,
    "visual_communication_fit": 0.95
  },
  "penalties": {
    "unsupported_relationship_risk": 0.00,
    "comparability_risk": 0.00,
    "numeric_precision_risk": 0.00,
    "text_density_risk": 0.03,
    "semantic_overload_risk": 0.00,
    "visual_misinterpretation_risk": 0.00
  },
  "total_score": 0.92
}
```

---

## 13M. VisualStrategyDecision

```json
{
  "visual_strategy_decision_id": "VSD001",
  "page_id": "S12",
  "primary_visual_intent": "TREATMENT_SELECTION",
  "secondary_visual_intents": [
    "EVIDENCE_SYNTHESIS"
  ],
  "information_structure_profile_id": "ISP001",
  "standard_override": {
    "applied": false,
    "standard": null
  },
  "candidate_score_ids": [
    "VCS001",
    "VCS002"
  ],
  "rejected_candidates": [
    {
      "visual_type": "GENERIC_CARDS",
      "reason": "cannot_preserve_AND_logic"
    }
  ],
  "selected_primary_visual": "CLINICAL_DECISION_MAP",
  "selected_secondary_visual": "EVIDENCE_CALLOUT",
  "generation_strategy": "HYBRID_COMPOSITION",
  "generation_mode": "CONTROLLED_COMPOSITION",
  "selector_status": "SELECTED",
  "selection_rationale": "conditional treatment selection with AND logic",
  "risk_level": "RED",
  "selector_version": "0.1"
}
```

### selector_status

建议：

- SELECTED
- SELECTABLE_WITH_REVIEW
- AMBIGUOUS
- NO_VALID_VISUAL
- NEEDS_HUMAN_REVIEW

### generation_strategy

建议：

- DETERMINISTIC_CHART
- DETERMINISTIC_DIAGRAM
- PROMPT_DRIVEN_IMAGE
- HYBRID_COMPOSITION

注意：
`generation_strategy` 与 Batch 1 的 `generation_mode` 不同。

- generation_strategy：底层视觉如何实现；
- generation_mode：最终页面是 FULL_IMAGE 还是 CONTROLLED_COMPOSITION。



---

# Module 06 Batch 2 v0.2 Draft Schemas｜Policy & Calibration Separation（未冻结）

## 13N. VisualMappingPolicyRegistry

```json
{
  "policy_id": "VP-QUANT-002",
  "policy_version": "0.1",
  "enabled": true,
  "when": {
    "visual_intent": ["COMPARE", "EFFECT_ESTIMATION"],
    "value_type": ["continuous_summary"],
    "uncertainty": ["CI", "SE"]
  },
  "recommend": [
    "DOT_ESTIMATE_PLOT",
    "FOREST_LIKE_PLOT"
  ],
  "discourage": [
    "BAR_CHART"
  ],
  "strength": "strong",
  "basis": [
    "medical_visual_convention",
    "statistical_semantics"
  ]
}
```

---

## 13O. StandardVisualPolicyRegistry

```json
{
  "standard_visual_policy_id": "SVP-RCT-FLOW-001",
  "policy_version": "0.1",
  "standard": "CONSORT",
  "applicable_when": {
    "study_context": "RCT",
    "visual_intent": "STUDY_FLOW"
  },
  "candidate": "CONSORT_PARTICIPANT_FLOW",
  "default_priority": "STRONGLY_PREFERRED",
  "project_overrides": {
    "formal_reporting": "MANDATORY",
    "conference_summary": "PREFERRED"
  }
}
```

### priority

- MANDATORY
- STRONGLY_PREFERRED
- PREFERRED

---

## 13P. GenerationStrategyPolicyRegistry

```json
{
  "generation_strategy_policy_id": "GSP-FOREST-001",
  "policy_version": "0.1",
  "visual_type": "FOREST_PLOT",
  "allowed_strategies": [
    "DETERMINISTIC_CHART",
    "HYBRID_COMPOSITION"
  ],
  "prohibited_capabilities": [
    "free_image_model_reconstruction_of_data_geometry"
  ],
  "reason": "exact_quantitative_geometry"
}
```

---

## 13Q. SelectorScoringConfig

```json
{
  "selector_scoring_config_id": "SSC-MEDCONGRESS-v0.1",
  "project_type": "medical_congress",
  "weights": {
    "semantic_fit": 0.30,
    "medical_convention_fit": 0.20,
    "data_fidelity": 0.15,
    "auditability": 0.15,
    "audience_fit": 0.10,
    "visual_communication_fit": 0.10
  },
  "status": "CALIBRATION_CONFIG",
  "frozen": false
}
```

---

## 13R. SelectorPenaltyConfig

```json
{
  "selector_penalty_config_id": "SPC-v0.1",
  "weights": {
    "numeric_precision_risk": 0.15,
    "text_density_risk": 0.10,
    "semantic_overload_risk": 0.10,
    "visual_misinterpretation_risk": 0.15
  },
  "hard_fail_categories": [
    "unsupported_medical_relationship",
    "hard_comparability_fail",
    "required_clinical_logic_loss",
    "invented_statistic",
    "prohibited_semantic_transformation"
  ],
  "frozen": false
}
```

---

## 13S. SelectionThresholdConfig

```json
{
  "selection_threshold_config_id": "STC-v0.1",
  "selectable_threshold": 0.80,
  "review_threshold": 0.65,
  "ambiguity_margin": 0.05,
  "calibration_status": "UNVALIDATED_INITIAL_VALUES",
  "frozen": false
}
```

数值仅为 benchmark 前占位，不得视为冻结标准。

---

## 13T. SelectorConstitutionVersion

```json
{
  "selector_constitution_id": "VSS-CONST-v0.1",
  "status": "CANDIDATE_NOT_FROZEN",
  "candidate_rule_count": 12,
  "policy_registry_version": "0.2-draft",
  "calibration_config_version": "0.1-draft"
}
```


---

# Module 06 Batch 3 Draft Schemas｜Generation Strategy Router（未冻结）

## 13X. GenerationComponent

```json
{
  "generation_component_id": "CMP001",
  "page_id": "S12",
  "component_type": "DATA_GEOMETRY",
  "risk_level": "RED",
  "source_bindings": ["DB001"],
  "lock_requirements": [
    "exact_data_binding",
    "geometry_fidelity"
  ],
  "external_processing_allowed": false
}
```

### component_type

- DATA_GEOMETRY
- SEMANTIC_DIAGRAM
- EXACT_TEXT
- MEDICAL_VISUAL_ASSET
- EDITORIAL_COMPOSITION
- DECORATIVE_BACKGROUND

---

## 13Y. GenerationCapabilityRegistry

```json
{
  "engine_id": "chart_engine_v1",
  "engine_type": "DETERMINISTIC_CHART",
  "engine_version": "1.0",
  "status": "QUALIFIED",
  "supported_component_types": [
    "DATA_GEOMETRY"
  ],
  "capabilities": {
    "exact_data_binding": true,
    "deterministic_geometry": true,
    "topology_lock": false,
    "exact_text_rendering": true,
    "external_processing": false,
    "editable_output": true,
    "supported_outputs": ["SVG", "PNG"]
  },
  "benchmark_profile_id": "GBP001"
}
```

---

## 13Z. GenerationRouteDecision

```json
{
  "generation_route_decision_id": "GRD001",
  "generation_component_id": "CMP001",
  "hard_gate_status": "PASS",
  "allowed_strategies": [
    "DETERMINISTIC_CHART",
    "HYBRID_COMPOSITION"
  ],
  "rejected_strategies": [
    {
      "strategy": "PROMPT_DRIVEN_IMAGE",
      "reason": "free_image_model_reconstruction_of_exact_data_geometry"
    }
  ],
  "selected_strategy": "DETERMINISTIC_CHART",
  "selected_engine_id": "chart_engine_v1",
  "fallback_engine_ids": ["chart_engine_v2"],
  "required_validators": [
    "numeric_fidelity",
    "visual_scale_fidelity"
  ]
}
```

---

## 14A. PageGenerationPlan

```json
{
  "page_generation_plan_id": "PGP001",
  "page_id": "S12",
  "visual_strategy_decision_id": "VSD001",
  "generation_mode": "CONTROLLED_COMPOSITION",
  "component_route_ids": [
    "GRD001",
    "GRD002",
    "GRD003"
  ],
  "composition_strategy": "HYBRID_COMPOSITION",
  "merge_order": [
    "editorial_base",
    "semantic_diagram",
    "data_geometry",
    "medical_assets",
    "exact_text",
    "sources"
  ],
  "required_post_generation_validators": [
    "numeric_fidelity",
    "relationship_fidelity",
    "exact_text_fidelity",
    "visual_semantic_fidelity"
  ],
  "routing_status": "ROUTED"
}
```

### routing_status

- ROUTED
- ROUTED_WITH_REVIEW
- UNROUTABLE
- NEEDS_HUMAN_REVIEW
- BLOCKED_BY_DATA_POLICY
- BLOCKED_BY_ASSET_POLICY

---

## 14B. GenerationProvenance

```json
{
  "generation_provenance_id": "GP001",
  "generation_component_id": "CMP003",
  "strategy": "PROMPT_DRIVEN_IMAGE",
  "engine_id": "image_engine_profile_A",
  "engine_version": "2026-08",
  "visual_generation_contract_id": "VGC001",
  "prompt_hash": "sha256:...",
  "parameters": {
    "aspect_ratio": "16:9"
  },
  "generated_at": "2026-09-04T00:00:00+08:00",
  "output_asset_id": "ASSET001"
}
```

---

## 14C. GenerationRouterCalibrationConfig

```json
{
  "router_calibration_config_id": "GRC-v0.1",
  "weights": {
    "fidelity_fit": 0.30,
    "auditability_fit": 0.20,
    "visual_quality_fit": 0.15,
    "editability_fit": 0.10,
    "reliability_fit": 0.10,
    "latency_fit": 0.075,
    "cost_fit": 0.075
  },
  "frozen": false
}
```

权重仅为初始草案，不冻结。


---

# Module 06 Batch 3 v0.2 Draft Schemas｜Router Constitution / Policy Separation（未冻结）

## 14D. ProtectedSemanticLayer

```json
{
  "protected_semantic_layer_id": "PSL001",
  "page_id": "S12",
  "component_ids": [
    "CMP001",
    "CMP002",
    "CMP004"
  ],
  "semantic_roles": [
    "DATA_GEOMETRY",
    "SEMANTIC_DIAGRAM",
    "EXACT_TEXT"
  ],
  "protection_policy": {
    "generative_repaint": "FORBIDDEN",
    "geometry_warp": "FORBIDDEN",
    "internal_relayout": "FORBIDDEN",
    "semantic_crop": "FORBIDDEN",
    "text_rewrite": "FORBIDDEN",
    "relationship_redraw": "FORBIDDEN",
    "occlusion": "BOUNDED_ONLY"
  },
  "status": "PROTECTED"
}
```

---

## 14E. QualifiedCapabilityRecord

```json
{
  "capability_record_id": "QCR001",
  "engine_id": "image_engine_profile_A",
  "engine_version": "2026-09",
  "qualification_status": "QUALIFIED_PARTIAL",
  "qualified_capabilities": {
    "editorial_composition": "PASS",
    "image_edit": "PASS",
    "exact_text_authority": "NOT_QUALIFIED",
    "exact_data_geometry": "NOT_QUALIFIED",
    "semantic_topology_lock": "PARTIAL"
  },
  "qualification_basis": {
    "benchmark_suite": "GEN-CAP-BENCH-v0.1",
    "tested_at": "2026-09-04",
    "evidence_refs": []
  },
  "valid_for_router": true
}
```

---

## 14F. MaterialCapabilityChange

```json
{
  "material_change_id": "MCC001",
  "engine_id": "semantic_svg_renderer",
  "from_version": "1.0",
  "to_version": "2.0",
  "possible_impacts": [
    "topology_lock",
    "layout_order",
    "relationship_geometry"
  ],
  "qualification_invalidated": true,
  "required_actions": [
    "rerun_capability_validation",
    "rerun_affected_route_validation"
  ]
}
```

---

## 14G. GenerationRoutingPolicyRegistry

```json
{
  "routing_policy_id": "GRP-DATA-001",
  "policy_version": "0.2",
  "component_type": "DATA_GEOMETRY",
  "requirements": [
    "exact_data_binding",
    "verifiable_geometry"
  ],
  "allowed_strategy_classes": [
    "DETERMINISTIC_CHART",
    "HYBRID_COMPOSITION"
  ],
  "disallowed_capabilities": [
    "free_reconstruction_of_exact_geometry"
  ],
  "status": "VERSIONED_NOT_FROZEN"
}
```

---

## 14H. FullImageEligibilityPolicy

```json
{
  "full_image_eligibility_policy_id": "FIEP-v0.1",
  "status": "VERSIONED_NOT_FROZEN",
  "eligible_if": {
    "all_critical_components_prompt_authorized": true,
    "exact_geometry_requires_deterministic": false,
    "locked_topology_requires_deterministic": false,
    "exact_text_requires_compositor": false,
    "privacy_gate": "PASS",
    "asset_policy": "PASS",
    "post_generation_verification": "AVAILABLE"
  }
}
```

---

## 14I. RouterOptimizationConfig

```json
{
  "router_optimization_config_id": "ROC-v0.2",
  "status": "CONFIGURABLE_NOT_FROZEN",
  "weights": {
    "visual_quality_fit": 0.30,
    "reliability_fit": 0.25,
    "editability_fit": 0.15,
    "latency_fit": 0.15,
    "cost_fit": 0.10,
    "workflow_fit": 0.05
  },
  "hard_qualification_fields_excluded_from_weighting": [
    "medical_fidelity",
    "clinical_logic_preservation",
    "exact_geometry",
    "exact_text_authority",
    "privacy_data_egress",
    "asset_contract",
    "verification_availability"
  ]
}
```

权重仅为初始草案，不冻结。

---

## 14J. RouterConstitutionVersion

```json
{
  "router_constitution_id": "GSR-CONST-v0.1",
  "status": "FROZEN",
  "rule_count": 14,
  "inherits": [
    "Module06-Batch1-LockModel",
    "Module06-Batch2-VisualStrategySelector"
  ],
  "policy_layer": "VERSIONED_NOT_FROZEN",
  "optimization_layer": "CONFIGURABLE_NOT_FROZEN"
}
```


---

## 14K. GenerationStrategyPreferenceVsEffectiveRoute

用于解决 Module 06 Batch 2 / Batch 3 职责边界：

```json
{
  "visual_strategy_decision_id": "VSD001",
  "preferred_generation_strategy": "HYBRID_COMPOSITION",
  "strategy_requirements": [
    "preserve_visual_type",
    "exact_data_geometry",
    "topology_lock"
  ],
  "page_generation_plan_id": "PGP001",
  "effective_generation_route": {
    "component_routes": [
      "GRD001",
      "GRD002"
    ],
    "composition_strategy": "HYBRID_COMPOSITION"
  },
  "route_deviation_reason": null
}
```

- `preferred_generation_strategy`：Batch 2 语义级偏好；
- `effective_generation_route`：Batch 3 经 capability/policy gate 后的实际执行路线。

---

## 14L. ProtectedSemanticLayerTransformPolicy

```json
{
  "protected_semantic_layer_id": "PSL001",
  "allowed_semantic_invariant_transforms": [
    "format_conversion",
    "whole_layer_uniform_scaling_with_validation",
    "rasterization_at_sufficient_resolution"
  ],
  "conditional_transforms": [
    "crop",
    "resample",
    "occlusion"
  ],
  "forbidden_if_semantic_impact": [
    "geometry_warp",
    "internal_relayout",
    "text_rewrite",
    "edge_redraw",
    "axis_remap",
    "legend_rebinding",
    "color_semantic_remap"
  ]
}
```

---

## 14M. GenerationExecutionProvenance

```json
{
  "generation_execution_provenance_id": "GEP001",
  "generation_component_id": "CMP001",
  "strategy": "DETERMINISTIC_CHART",
  "engine_id": "chart_engine",
  "engine_version": "1.2.0",
  "input_contract_ref": "VGC001:v3",
  "deterministic_spec_ref": "SPEC001",
  "prompt_version": null,
  "prompt_hash": null,
  "secured_prompt_ref": null,
  "operations": [
    "render",
    "compose"
  ],
  "output_asset_ref": "ASSET001:v2",
  "validator_result_refs": [
    "VR-NUM-001",
    "VR-VIS-002"
  ],
  "generated_at": "2026-09-04T02:10:00+08:00"
}
```

说明：
- Generation Execution Provenance 不替代 Medical Semantic Provenance；
- 不替代 Visual Asset Provenance；
- 原始 Prompt 的保存受 Data Minimization / Privacy Policy 约束。


---

## 14N. RouterConstitutionVersion（正式）

```json
{
  "router_constitution_id": "GSR-CONST-v0.1",
  "status": "FROZEN",
  "rule_count": 14,
  "rule_ids": [
    "GSR-HR-001",
    "GSR-HR-002",
    "GSR-HR-003",
    "GSR-HR-004",
    "GSR-HR-005",
    "GSR-HR-006",
    "GSR-HR-007",
    "GSR-HR-008",
    "GSR-HR-009",
    "GSR-HR-010",
    "GSR-HR-011",
    "GSR-HR-012",
    "GSR-HR-013",
    "GSR-HR-014"
  ],
  "inherits": [
    "Module06-Batch1-LockModel",
    "Module06-Batch2-VisualStrategySelector"
  ],
  "routing_policy_layer": {
    "status": "VERSIONED_NOT_FROZEN"
  },
  "optimization_layer": {
    "status": "CONFIGURABLE_NOT_FROZEN"
  }
}
```
