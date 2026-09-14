# 可靠 PPT 生成系统
## 开发设计文档 v0.3 · AI Agent 可执行工程规范版

**Phase 1｜Document Intelligence, Verification & Narrative Planning**

> 系统目标不是要求 LLM 一次性正确，而是保证关键输出可验证、可追溯、可拒绝、可修正。

# 0. 文档定位与 v0.3 变更摘要

v0.2 已冻结 Evidence、核心对象 Schema、状态机、Gate、Golden Set 与 Human Review 的工程基础。v0.3 不修改这些已冻结的数据契约，而是在其上增加 AI Agent 开发执行层：把自然语言原则转成 Rule ID、AGENTS.md、Milestone Contract、Change Control、Audit Pass 与 CI Enforcement，使 GPT-5.6 Sol 可以按同一套规则持续开发而不依赖更昂贵模型做常规纠偏。

## 0.1 v0.3 新增的执行边界（不修改 v0.2 Frozen Schema）

- 冻结 SourceSpan、Claim、NumericFact、Relation、SlidePlan 的字段语义、状态字段与版本字段。
- 所有关键对象实行统一生命周期状态机；Approved Semantic Graph 是唯一下游事实输入。
- 所有 Gate 使用统一 GateResult Schema，能够被机器判定、CI 统计和人工复核。
- 关系类型从 20+ 收敛到 10 类核心关系；Embedding 只召回，LLM 分类，Verifier 准入。
- 建立 Golden Set、自动评估 CI 与最小 Human Review 闭环。
- 明确 PostgreSQL/pgvector 持久化与 NetworkX 运行时边界。
- 定义幂等、缓存、重跑、降级、可观测、安全与成本记录。
- 清理 v0.1 中异常编号/转换噪声，本版编号完全由 Word 标题层级生成。

## 0.2 规范关键词

| 关键词 | 含义 |
| --- | --- |
| MUST / 必须 | 违反即视为实现不符合规范。 |
| SHOULD / 应 | 默认实现，只有明确理由才可偏离。 |
| MAY / 可 | 可选能力，不影响 v0.2 主闭环验收。 |

# 1. 产品与系统目标

第一阶段的产品指标不是“能生成 PPTX”，而是“能够可验证地读懂一份长文档，并输出可被下游消费的可靠语义结构”。

## 1.1 系统必须回答的五个问题

1. 原文到底说了什么？——通过 SourceSpan、Claim、NumericFact 回答。
2. 这些事实来自哪里？——通过 document_version、source_span_ids、bbox、offset、provenance 回答。
3. 事实之间是什么关系？——通过受控 Relation 与 Relation Gate 回答。
4. 哪些内容值得进入叙事？——通过 importance、criticality、NarrativeGraph 回答。
5. 哪些内容允许下游使用？——仅 Approved Semantic Graph 与 Approved SlidePlan。

## 1.2 v0.2 不做什么

- 不让 LLM 直接自由输出 PPT 坐标。
- 不在本阶段实现插画生成、复杂视觉合成或最终美化。
- 不把 Neo4j、GraphRAG、复杂 Agent Framework 设为前置依赖。
- 不以单次全文 Prompt 的“看起来不错”作为验收依据。

# 2. 总体架构与唯一下游准入点

```text
PDF / DOCX
    ↓
Document Parsing
    ↓
Source Structure + SourceSpan
    ↓
Semantic Segmentation
    ↓
Candidate Semantic Objects
    ↓
Fact / Numeric / Relation / Coverage Gates
    ↓
Approved Semantic Graph   ← 唯一下游事实输入
    ↓
Narrative Graph
    ↓
Approved SlidePlan JSON
    ↓
[v0.3+] Visual Grammar / Template / Layout / Renderer
```

任何 CANDIDATE、NEEDS_REVIEW、REJECTED 对象都不得绕过 Approved Semantic Graph 直接进入 Narrative 或 SlidePlan。

# 3. 统一对象生命周期状态机

## 3.1 状态枚举

```text
CANDIDATE
VERIFIED
APPROVED
REJECTED
NEEDS_REVIEW
```

## 3.2 状态语义

| 状态 | 定义 | 是否允许进入下游 |
| --- | --- | --- |
| CANDIDATE | Extractor 新生成，尚未完成独立验证。 | 否 |
| VERIFIED | 至少通过机器 Gate，但尚未满足最终准入条件或等待策略决策。 | 否 |
| APPROVED | 满足准入规则；可进入 Approved Semantic Graph / SlidePlan。 | 是 |
| REJECTED | 存在明确不支持、解析错误、数字错误或关系错误。 | 否 |
| NEEDS_REVIEW | 机器无法可靠判定，必须进入人工审核。 | 否，除非人工批准后转 APPROVED |

## 3.3 允许的状态迁移

| From | To | 触发条件 |
| --- | --- | --- |
| CANDIDATE | VERIFIED | 机器 Gate 全部完成且无阻断错误。 |
| CANDIDATE | REJECTED | 出现 UNSUPPORTED、确定性数字错误、非法 schema 等。 |
| CANDIDATE | NEEDS_REVIEW | 证据冲突、OCR 低置信、关系不确定、关键数字无法确定验证。 |
| VERIFIED | APPROVED | 满足对象级准入阈值与文档策略。 |
| VERIFIED | NEEDS_REVIEW | 覆盖/关系/关键性策略要求人工检查。 |
| NEEDS_REVIEW | APPROVED | 人工批准并记录 reviewer 与 revision。 |
| NEEDS_REVIEW | REJECTED | 人工否决。 |
| APPROVED | NEEDS_REVIEW | 新版本解析、模型重跑或冲突检测导致重新审查。 |

## 3.4 所有状态迁移必须记录

- pipeline_run_id
- verifier_model
- prompt_version
- schema_version
- evidence_span_ids
- verification_result_id
- transition_actor（system / human）
- created_at

# 4. 通用元数据协议（Frozen Base Metadata）

所有派生对象 MUST 继承以下元数据。字段名在 v0.2 冻结；后续只能新增兼容字段，不能修改既有语义。

```json
{
  "schema_version": "0.2",
  "pipeline_run_id": "run_...",
  "document_id": "doc_...",
  "document_version": "sha256:...",
  "source_span_ids": [],
  "status": "CANDIDATE",
  "confidence": 0.0,
  "created_at": "2026-09-14T10:00:00+08:00",
  "updated_at": "2026-09-14T10:00:00+08:00"
}
```

## 4.1 版本约束

- document_version = 对规范化原始文件内容计算 SHA-256；同一文件修改后必须生成新版本。
- schema_version 采用语义版本；破坏兼容性的字段语义变更必须升级主版本。
- prompt_version、model_version、extractor_version 必须可从 pipeline_run 追溯。
- 任何对象重跑不得覆盖旧版本记录；使用新 run 生成新 object revision。

# 5. Frozen Schema：SourceSpan

SourceSpan 是系统唯一可审计锚点。所有关键派生对象 MUST 直接或间接引用一个或多个 SourceSpan。

```json
{
  "span_id": "sp_doc01_p023_0007",
  "schema_version": "0.2",
  "pipeline_run_id": "run_...",
  "document_id": "doc_001",
  "document_version": "sha256:...",
  "page_start": 23,
  "page_end": 23,
  "section_id": "sec_4_2",
  "block_ids": ["p23_b07"],
  "span_type": "PARAGRAPH",
  "text": "12个月内急性发作率从1.8降至0.7，下降61%。",
  "text_hash": "sha256:...",
  "start_offset": 1240,
  "end_offset": 1271,
  "offset_basis": "normalized_document_text_v1",
  "bbox_by_page": {"23": [80,210,520,250]},
  "extractor": "docling",
  "extractor_version": "...",
  "verification_status": "VERIFIED",
  "created_at": "...",
  "updated_at": "..."
}
```

## 5.1 SourceSpan 强制规则

- span_id MUST 不可变；对象修订不得复用改变过内容的 span_id。
- document_id + document_version + text_hash SHOULD 可唯一定位原文内容。
- 支持跨页 span：page_start/page_end + bbox_by_page。
- 支持表格：span_type = TABLE_CELL / TABLE_ROW / TABLE_REGION，并保存 block_ids。
- offset_basis 必须固定，避免 PyMuPDF / Docling / DOCX parser 各自 offset 不一致。
- 任何解析器升级导致 normalized text 改变时，必须产生新 document_version 或新的 normalization_version。

# 6. 文档解析与多信号语义分段

## 6.1 解析层输出

- Page
- Section
- Block
- Table
- Figure/Caption
- List
- SourceSpan candidate

## 6.2 分段不得使用单一 embedding 阈值

边界决策 MUST 融合结构、版面与语义三类信号，并保留 boundary_reason。

| 信号 | 示例 | 建议作用 |
| --- | --- | --- |
| 结构 | 标题层级、编号、列表、表格、图注 | 高权重；优先保护文档天然边界 |
| 版面 | 字号、粗体、缩进、column、页间断点 | 高权重；帮助识别标题/栏/跨页 |
| 语义 | 相邻 embedding 相似度突变 | 中权重；用于主题切换候选 |
| 语言 | 然而/因此/如果/综上/相较于 | 中权重；保护转折、条件、总结关系 |

```json
{
  "boundary_after_block_id": "p12_b05",
  "score": 0.84,
  "reasons": [
    {"type":"HEADING_CHANGE","weight":0.35},
    {"type":"SEMANTIC_DROP","value":0.42,"weight":0.25},
    {"type":"DISCOURSE_MARKER","value":"然而","weight":0.20}
  ],
  "overlap_block_ids": ["p12_b05"]
}
```

## 6.3 文档类型配置

医学指南、数字报告、普通业务报告 SHOULD 使用不同 segmentation profile。阈值必须配置化，并通过 Golden Set 校准，不允许硬编码成单一全局常量。

# 7. Frozen Schema：Claim

```json
{
  "claim_id": "clm_023",
  "schema_version": "0.2",
  "pipeline_run_id": "run_...",
  "document_id": "doc_001",
  "document_version": "sha256:...",
  "source_span_ids": ["sp_..."],
  "subject": "升级治疗前的患者",
  "predicate": "应先排除",
  "object": "可纠正因素",
  "text": "升级治疗前应先排除可纠正因素",
  "polarity": "POSITIVE",
  "condition": null,
  "time_window": null,
  "population": "哮喘控制不佳患者",
  "certainty": "RECOMMENDED",
  "importance": 0.92,
  "criticality": "HIGH",
  "extraction_model": "...",
  "prompt_version": "claim_extract_v3",
  "status": "CANDIDATE",
  "confidence": 0.91,
  "created_at": "...",
  "updated_at": "..."
}
```

## 7.1 Claim 约束

- Claim MUST 原子化：尽量只表达一个可验证命题。
- 不能把“相关”升级为“因果”，不能把“可考虑”升级为“必须”。
- certainty、polarity、condition MUST 显式保存，避免摘要时丢失限定语。
- 无 source_span_ids 的关键 Claim MUST 被拒绝。

# 8. Frozen Schema：NumericFact

NumericFact 的数值存储 MUST 使用 Decimal/字符串序列化，不使用二进制 float 作为审计真值。

```json
{
  "numeric_fact_id": "nf_011",
  "schema_version": "0.2",
  "pipeline_run_id": "run_...",
  "document_id": "doc_001",
  "document_version": "sha256:...",
  "source_span_ids": ["sp_..."],
  "raw_text": "从1.8降至0.7，下降61%",
  "metric": "annual_exacerbation_rate",
  "normalized_value": null,
  "unit": "events/year",
  "unit_normalized": "events_per_year",
  "baseline": "1.8",
  "followup": "0.7",
  "change_absolute": "-1.1",
  "change_pct": "-61.1111",
  "comparison_type": "PRE_POST",
  "p_value": null,
  "confidence_interval": null,
  "calculation_formula": "(followup-baseline)/baseline*100",
  "rounding_rule": "HALF_UP_0DP",
  "status": "CANDIDATE",
  "confidence": 0.97,
  "created_at": "...",
  "updated_at": "..."
}
```

## 8.1 数字验证边界

- LLM 仅抽取候选字段，不负责最终算术。
- 单位换算、百分比、差值、四舍五入 MUST 由 Python 确定性实现。
- 若原文数字与可计算结果冲突，保留原文 raw_text，同时标记 NUMERIC_CONFLICT → NEEDS_REVIEW。
- 无法确定单位或量纲的关键数字不得 APPROVED。

# 9. v0.2 关系体系：收敛到 10 类

第一版关系类型必须少而清晰。方向性、跨段能力、from/to 类型约束均在 schema 中固定。

| Relation | 方向性 | 跨段 | 定义 |
| --- | --- | --- | --- |
| SUPPORTS | 有向 | 是 | A 为 B 提供证据或论据。 |
| CONTRADICTS | 有向 | 是 | A 与 B 的命题或结论冲突。 |
| CAUSES | 有向 | 是 | A 被原文明示为 B 的原因。 |
| CONDITION_OF | 有向 | 是 | A 是 B 成立/执行的条件或前置条件。 |
| DEFINES | 有向 | 是 | A 定义 B 的术语、标准或概念。 |
| EXAMPLE_OF | 有向 | 是 | A 是 B 的实例。 |
| CONTRASTS | 对称 | 是 | A 与 B 形成对比/转折。 |
| REFERS_TO | 有向 | 是 | A 指代、回指或依赖 B。 |
| PARENT_CHILD | 有向 | 是 | 章节/概念的层级关系。 |
| SUMMARY_OF | 有向 | 是 | A 是 B 或一组节点的总结。 |

## 9.1 Frozen Schema：Relation

```json
{
  "relation_id": "rel_084",
  "schema_version": "0.2",
  "pipeline_run_id": "run_...",
  "document_id": "doc_001",
  "document_version": "sha256:...",
  "from_type": "CLAIM",
  "from_id": "clm_023",
  "to_type": "CLAIM",
  "to_id": "clm_024",
  "relation_type": "CONDITION_OF",
  "directional": true,
  "cross_block": true,
  "source_span_ids": ["sp_a","sp_b"],
  "extractor_model": "...",
  "prompt_version": "relation_v2",
  "status": "CANDIDATE",
  "confidence": 0.86,
  "created_at": "...",
  "updated_at": "..."
}
```

## 9.2 抽取策略

```text
Current Node
   ↓
pgvector Top-K semantic recall
   ↓
Cross-encoder reranker
   ↓
LLM relation classifier (10-class + NONE)
   ↓
Independent Relation Gate
   ↓
APPROVED / REJECTED / NEEDS_REVIEW
```

训练/评估集 MUST 包含 NONE 负样本，避免“有召回就强行分类”的关系幻觉。

# 10. 统一验证协议：GateResult

五道 Gate 不再返回自由文本。所有 Gate MUST 输出同一结构，便于自动聚合、CI 与人工复核。

```json
{
  "verification_result_id": "vr_...",
  "gate": "FACT_GATE",
  "object_type": "CLAIM",
  "object_id": "clm_023",
  "status": "SUPPORTED",
  "score": 0.97,
  "issues": [],
  "evidence_span_ids": ["sp_..."],
  "verifier_model": "...",
  "prompt_version": "fact_verify_v4",
  "reason_code": "DIRECT_ENTAILMENT",
  "reason": "命题与原文限定条件一致。",
  "created_at": "..."
}
```

## 10.1 Gate 状态枚举

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONFLICT
INDETERMINATE
```

## 10.2 Gate 与对象准入

| Gate | 阻断规则 |
| --- | --- |
| Parsing Gate | 关键页/表格/阅读顺序不可恢复 → 文档或区域 NEEDS_REVIEW。 |
| Evidence Gate | 关键对象无 SourceSpan / span 不完整 → REJECTED。 |
| Fact Gate | PARTIALLY_SUPPORTED / UNSUPPORTED → 不得进入 Approved Graph。 |
| Numeric Gate | 确定性计算不一致或单位不可判定 → REJECTED / NEEDS_REVIEW。 |
| Relation Gate | CAUSES/CONDITION_OF 等高风险关系低于阈值 → NEEDS_REVIEW。 |
| Coverage Gate | critical claim 加权召回低于文档类型阈值 → 阻断 Narrative finalize。 |

## 10.3 Fact Gate issue taxonomy

- ADDED_CONTENT
- MISSING_QUALIFIER
- POLARITY_CHANGED
- CONDITION_DROPPED
- POPULATION_CHANGED
- TIME_WINDOW_CHANGED
- CAUSALITY_UPGRADED
- MODALITY_CHANGED

# 11. Coverage Gate 与“漏了什么”的可操作定义

Coverage 不能直接对模型自身抽取结果计算。Golden Set 中必须存在人工标注的 critical items，才能形成可解释分母。

## 11.1 Golden critical item

```json
{
  "gold_id": "g_001",
  "type": "CLAIM",
  "source_span_ids": ["sp_..."],
  "criticality": "HIGH",
  "weight": 3,
  "label": "启动治疗前必须评估吸入技术"
}
```

## 11.2 指标

```text
Critical Coverage = Σ(hit_i * weight_i) / Σ(weight_i)
Unweighted Recall = matched_gold_items / total_gold_items
```

v0.2 首版 SHOULD 同时报告普通召回与 weighted critical coverage；不能只报告一个“coverage 92%”而不说明分母。

# 12. Verifier 独立性与 Human Review 闭环

## 12.1 独立性规则

- Extractor 与 Verifier SHOULD 使用不同 prompt；高风险场景 SHOULD 使用不同模型或不同供应商。
- Verifier 输入必须包含原始 evidence，而不是只看 Extractor 的解释。
- Verifier 不得读取 Extractor 的 chain-of-thought；只读取候选结构化对象与 SourceSpan。

## 12.2 Review Queue 优先级

```text
review_priority = importance × uncertainty × criticality_weight
```

| 字段 | 说明 |
| --- | --- |
| importance | 内容对全文/叙事的重要度 0–1。 |
| uncertainty | 1 - machine confidence，或冲突规则加权。 |
| criticality_weight | LOW=1, MEDIUM=2, HIGH=3, SAFETY_CRITICAL=5。 |

## 12.3 审核结果必须回流

- 人工 APPROVE / REJECT / EDIT 生成独立 revision，不覆盖机器原始输出。
- 审核样本自动加入 evaluation candidate pool。
- 错误原因写入 taxonomy，用于 prompt/model/rule 回归分析。
- 记录 reviewer_id、reviewed_at、before/after、reason_code。

# 13. SemanticGraph 与 NarrativeGraph 接口

## 13.1 持久化边界

| 组件 | 职责 |
| --- | --- |
| PostgreSQL | 持久化文档、对象、关系、验证结果、版本、审核记录。 |
| pgvector | 持久化 embedding；召回跨段候选。 |
| NetworkX MultiDiGraph | 运行时图算法、路径分析、局部子图操作；不作为持久化真值源。 |

## 13.2 SemanticGraph

SemanticGraph MUST 只表达“原文能支持的事实与关系”。节点/边只从 APPROVED 对象加载。

## 13.3 NarrativeGraph

NarrativeGraph 表达“为了讲清楚，应该按什么顺序组织”。它可以重排，但不能创造新的事实节点。每个 NarrativeNode MUST 可回溯到一个或多个 SemanticNode。

## 13.4 Narrative 重建策略

- 第一版优先采用规则/模板（BACKGROUND → PROBLEM → EVIDENCE → DECISION → ACTION）+ LLM 辅助排序。
- LLM 只能在已批准节点范围内选取、聚合、排序，不得新增事实。
- Narrative Spine 必须可人工编辑，并保存 edit revision。

# 14. Frozen Schema：SlidePlan JSON

SlidePlan 是内容引擎与视觉引擎之间的唯一 Handoff Contract。v0.2 只冻结契约，不实现最终视觉渲染。

```json
{
  "slide_plan_id": "spn_008",
  "schema_version": "0.2",
  "pipeline_run_id": "run_...",
  "slide_id": "s_008",
  "intent": "DECIDE",
  "message": "升级治疗前，应首先排除5类可纠正因素",
  "narrative_role": "DECISION",
  "claims": ["clm_023","clm_024"],
  "source_refs": ["sp_a","sp_b"],
  "must_show_numeric_fact_ids": ["nf_011"],
  "evidence_display_policy": "SHOW_FOOTNOTE",
  "text_budget": {"title_chars": 26, "body_chars": 90},
  "visual_hint": {
    "grammar": "DECISION_FLOW",
    "layout": "HORIZONTAL_PROCESS",
    "node_count": 5
  },
  "status": "APPROVED",
  "created_at": "...",
  "updated_at": "..."
}
```

## 14.1 受控枚举

- intent：INTRODUCE / EXPLAIN / COMPARE / DECIDE / PROVE / WARN / SUMMARIZE / TRANSITION。
- visual grammar：FLOW / TIMELINE / COMPARISON / MATRIX / DATA_INSIGHT / HIERARCHY / EVIDENCE / SUMMARY。
- layout：TITLE_BODY / TWO_COLUMN / HORIZONTAL_PROCESS / VERTICAL_PROCESS / GRID / CHART_PLUS_INSIGHT / FULL_BLEED_VISUAL。

## 14.2 SlidePlan 准入

- 关键 Claim 无 source_refs → 禁止 APPROVED。
- must_show_numeric_fact_ids 中所有数字必须已通过 Numeric Gate。
- claims 必须来自 Approved Semantic Graph。
- SlidePlan 下游可以不重新读取全文，但必须能通过 source_refs 回到原文。

# 15. 数据库与版本化设计

## 15.1 核心表

```text
documents
document_versions
pages
sections
blocks
source_spans
semantic_blocks
claims
numeric_facts
relations
embeddings
verification_results
human_reviews
narrative_nodes
narrative_edges
slide_plans
pipeline_runs
artifacts
```

## 15.2 所有核心业务表统一字段

```text
id
schema_version
pipeline_run_id
document_id
document_version
status
created_at
updated_at
```

## 15.3 图版本

Approved Semantic Graph 与 Narrative Graph SHOULD 支持 graph_snapshot_id。Snapshot 指向具体 object revision 集合，用于重现任意一次 SlidePlan。

# 16. 工程目录与模块边界

```text
src/
├── ingestion/
├── parsing/
├── segmentation/
├── evidence/
├── schemas/
├── extraction/
├── retrieval/
├── verification/
├── human_review/
├── graph/
├── narrative/
├── slide_contract/
├── prompts/
├── config/
├── evaluation/
├── observability/
├── security/
├── db/
├── api/
└── tests/
```

每个 stage MUST 可独立重跑；禁止把所有处理封装为一个不可观察的大 Prompt。

# 17. Pipeline、幂等、缓存与重跑

## 17.1 Stage 接口

```text
parse_document(file) -> DocumentStructure
segment_document(document_version) -> SemanticBlock[]
materialize_source_spans(blocks) -> SourceSpan[]
extract_claims(blocks) -> Claim[]
extract_numeric_facts(blocks) -> NumericFact[]
verify_objects(objects) -> GateResult[]
retrieve_relation_candidates(node) -> CandidateNode[]
extract_relations(candidates) -> Relation[]
verify_relations(relations) -> GateResult[]
build_semantic_graph(approved_revision_set) -> SemanticGraphSnapshot
build_narrative_graph(snapshot) -> NarrativeGraphSnapshot
build_slide_plans(narrative_snapshot) -> SlidePlan[]
```

## 17.2 幂等键

```text
idempotency_key = hash(
  document_version + stage + model_version +
  prompt_version + schema_version + config_version
)
```

## 17.3 Artifact 策略

- 每个 stage 输出原始 JSON artifact 到对象存储或文件存储；DB 保存元数据与引用。
- embedding、解析结果、LLM 结构化输出 SHOULD 缓存。
- 重跑使用新 pipeline_run_id，但允许复用命中相同幂等键的 artifact。
- 所有下游对象必须可追溯到输入 artifact 和 run。

# 18. 失败降级与阻断策略

| 故障 | 动作 |
| --- | --- |
| 解析失败 | 标记 DOCUMENT_UNUSABLE 或局部区域 NEEDS_REVIEW；禁止静默继续。 |
| OCR 低置信 | SourceSpan 标记 LOW_CONFIDENCE；关键对象进入 Review Queue。 |
| 关键数字无法验证 | NumericFact NEEDS_REVIEW/REJECTED；依赖它的 Claim 不得 APPROVED。 |
| 关系冲突 | 保留候选与证据，标记 CONFLICT/NEEDS_REVIEW，不强行二选一。 |
| 模型超时/失败 | 重试有上限；超过后 stage FAILED，可从该 stage 独立重跑。 |
| Coverage 不达标 | 阻断 Narrative finalize，但保留已有 Approved Graph 供人工分析。 |

# 19. 可观测性与成本

## 19.1 每个调用至少记录

- run_id
- stage
- object_ids
- model/provider
- prompt_version
- schema_version
- latency_ms
- input_tokens
- output_tokens
- estimated_cost
- retry_count
- cache_hit
- status
- error_code

## 19.2 推荐指标面板

- Parsing success rate
- Gate rejection/review rate
- Numeric conflict rate
- Relation precision sample
- Critical coverage
- Human correction time
- Tokens / page
- Cost / page
- P50/P95 latency
- Cache hit rate

# 20. Golden Set 与评估规范

## 20.1 分层样本集

| 类型 | 首版建议数量 | 重点 |
| --- | --- | --- |
| 普通业务报告 | 5–8 | 章节、列表、常规叙事 |
| 医学指南/共识 | 5–8 | 条件、推荐级别、禁忌、证据 |
| 数字密集型 | 5–8 | 数值、单位、表格、变化率 |
| 表格密集型 | 3–5 | 跨行列、脚注、表头 |
| 长文档 | 3–5 | 跨章节引用、覆盖率 |
| 复杂逻辑文档 | 3–5 | 转折、条件、对比、否定 |

## 20.2 标注内容

- 关键 SourceSpan
- Atomic Claim
- NumericFact
- 10 类 Relation + NONE
- criticality/importance
- Narrative role（少量）
- unsupported / partially supported 负样本

## 20.3 标注质量

关键评估集 SHOULD 双人标注；至少对 Claim/Relation 子集计算 inter-annotator agreement。无法一致的样本进入 adjudication，不直接计入自动阈值校准。

# 21. 指标定义与验收口径

| 指标 | 定义 | v0.2 建议目标 |
| --- | --- | --- |
| Parsing completeness | 人工标注可解析 block 中，被正确恢复文本+顺序的比例。 | ≥ 98% 数字 PDF |
| Claim precision | 抽取 Claim 中被人工判定忠实的比例。 | ≥ 95% critical 子集 |
| Claim critical recall | critical Claim 加权召回。 | ≥ 95% |
| Numeric extraction accuracy | 字段值/单位抽取完全正确。 | ≥ 98% |
| Numeric deterministic consistency | 可计算数字通过程序复算。 | 100% 已 APPROVED 项 |
| Relation precision | APPROVED relation 中正确关系比例。 | ≥ 92% high-confidence |
| Traceability | 关键对象能定位到有效 SourceSpan。 | 100% APPROVED 项 |
| Hallucination rate | APPROVED 对象中无原文支持的比例。 | ≤ 0.5%，critical=0 |
| Human correction time | 每文档人工审核耗时。 | 记录基线，持续下降 |
| Cost / page | 完整 Phase 1 每页平均成本。 | 建立基线，不先设产品承诺 |

所有阈值都是工程首版目标，必须通过 Golden Set 数据校准。不得把目标值当作模型能力宣称。

# 22. 自动评估 CI

每次发生以下变化时 MUST 自动重跑 Golden Set：prompt、model、schema、segmentation profile、reranker、numeric rule、relation threshold。

```text
PR / config change
   ↓
Golden Set regression run
   ↓
metrics.json
   ↓
compare against baseline
   ↓
PASS / WARN / BLOCK
   ↓
store artifacts + diff report
```

## 22.1 默认阻断条件

- critical hallucination > 0。
- Numeric deterministic consistency < 100% for APPROVED items。
- Claim critical recall 较基线下降超过 2 个百分点。
- Relation precision 较基线下降超过 3 个百分点。
- Schema validation failure > 0。

# 23. 最小 Human Review UI

```text
┌──────────────┬────────────────────┬──────────────────┐
│ 原文 / Span   │ Candidate / Approved │ Gate / Relation   │
│ PDF page      │ Claim / NumericFact  │ issue / confidence│
└──────────────┴────────────────────┴──────────────────┘
             ↓ Narrative Path / Review Actions
```

## 23.1 必需操作

- Approve
- Reject
- Edit with revision
- Jump to SourceSpan
- View all GateResults
- View conflicting relations
- Compare machine vs human revision

Review UI 的目标不是“做一个完整后台”，而是让所有 NEEDS_REVIEW 对象都有清晰入口，且人工修改能形成可训练/可评估数据。

# 24. 安全与合规

- 文档访问必须绑定用户/项目权限；所有 SourceSpan 与 artifact 继承权限。
- 敏感医疗/企业材料需要可配置的数据保留期与删除策略。
- 调用外部模型供应商时记录 provider、region、retention policy；高敏场景支持本地模型或脱敏后调用。
- 日志禁止直接记录整段敏感原文；默认记录 object id / span id，需要调试时受权限控制读取。
- 删除文档时必须能级联删除/失效 embedding、artifact、graph snapshot 与 SlidePlan。

# 25. MVP 实施顺序（重新排序）

## P0｜必须先完成

1. 冻结 Base Metadata、SourceSpan、Claim、NumericFact、Relation、SlidePlan Schema。
2. 实现统一状态机与 GateResult。
3. 完成 Source/Evidence pipeline 与稳定 hash/version。
4. 实现 NumericFact Decimal + deterministic verifier。
5. 建立 Golden Set v1 + 自动评估脚本/CI。
6. 关系收敛为 10 类 + NONE，并实现 Relation Gate。
7. 实现最小 Human Review Queue/UI。

## P1｜形成工程闭环

1. 多信号 segmentation profile 与边界理由。
2. PostgreSQL + pgvector 持久化；NetworkX runtime snapshot。
3. Extractor/Verifier 独立化。
4. Narrative Graph + 可编辑 Narrative Spine。
5. SlidePlan JSON Schema validator。
6. 幂等、缓存、Artifact、重跑、可观测。

## P2｜上游稳定后再扩展

1. 多文档类型深度适配。
2. Narrative Planner 优化与专用 NLI/Relation 模型评估。
3. Visual Grammar / Template Selector / Flex/Grid / PptxGenJS。
4. 视觉输出 OCR / 数字回验 / Layout Quality Score。
5. 按实际规模再评估 Neo4j / GraphRAG。

# 26. 建议代码交付物与 Definition of Done

| 里程碑 | 交付物 | DoD |
| --- | --- | --- |
| M1 Evidence | document_version.json, source_spans.json | 任意 Approved 对象可定位原文；span_id 稳定。 |
| M2 Facts | claims.json, numeric_facts.json, gate_results.json | unsupported 不入 Approved；数字可复算。 |
| M3 Relations | relations.json, semantic_graph_snapshot.json | 10 类+NONE 可评估；跨段关系有证据。 |
| M4 Review | review_queue API/UI, revisions | NEEDS_REVIEW 有闭环，人工修正可回流。 |
| M5 Evaluation | golden_set, metrics, CI report | 关键回归可自动阻断。 |
| M6 Narrative/SlidePlan | narrative_snapshot.json, slide_plans.json | SlidePlan 仅引用 Approved nodes，schema 100% valid。 |

# 27. v0.2 正式架构决策记录（ADR 摘要）

1. Approved Semantic Graph 是唯一允许进入 Narrative/SlidePlan 的事实输入。
2. SourceSpan 是不可变审计锚点；所有关键对象必须有 provenance。
3. Claim、NumericFact、Relation 是独立一等对象，各自验证。
4. NumericFact 的算术与单位校验由确定性代码负责。
5. 关系首版只允许 10 类 + NONE；Embedding 不直接决定关系。
6. Extractor 与 Verifier 解耦；高风险对象支持异源模型复核。
7. Coverage 以人工 Golden critical items 为分母。
8. PostgreSQL/pgvector 是持久化真值；NetworkX 仅为运行时图。
9. NarrativeGraph 可以重排但不得创造事实；必须能回溯 SemanticGraph。
10. SlidePlan 是内容层与视觉层的正式版本化契约。
11. 所有 stage 支持幂等、缓存、独立重跑、artifact 追溯。
12. Prompt/model/schema/config 的每次变更必须触发 Golden Set 回归。

# 28. 下一步开发任务拆分（建议 2 个 Sprint 起步）

## Sprint A｜Schema + Evidence + Numeric

- Pydantic/JSON Schema：BaseMetadata、SourceSpan、Claim、NumericFact、GateResult。
- document hash/version + normalized offset basis。
- PyMuPDF/Docling parser adapter；SourceSpan materializer。
- Numeric Decimal parser + unit normalization + deterministic calculator。
- 状态机 transition service。
- Golden Set 文件格式与最小 5 份样本。
- 单元测试：schema、hash、offset、numeric、state transition。

## Sprint B｜Relation + Review + CI

- Relation 10-class + NONE Schema / classifier / verifier。
- pgvector candidate retrieval + reranker adapter。
- Approved Graph snapshot builder。
- Review Queue API + 简易三栏 UI。
- Golden Set 扩展到 15–20 份，加入 Relation/negative samples。
- CI metrics + baseline diff + block rules。

完成 Sprint A/B 后再进入 Narrative Planner 与 SlidePlan，能最大程度避免在不稳定语义层之上继续堆功能。

# 29. 结论

v0.2 的核心变化不是增加更多 AI 模块，而是把“可靠”变成工程上可判定的属性：对象有状态、状态有迁移、准入有 Gate、Gate 有结构化证据、错误有人工闭环、版本变更有 CI 回归。只要这一层稳定，下游 Narrative 与 PPT 视觉生成就能建立在可重复、可审计的数据基础上。


# 30. v0.3 AI Agent 开发执行总则

本章及其后续章节构成 Model Development Operating Contract。它是规范性要求，不是建议性说明。GPT-5.6 Sol 可以同时承担 Lead Architect、Main Developer 与独立 Audit Pass，但项目正确性不得依赖模型“记得规则”，而必须通过 Frozen Contract、Rule Registry、Schema、测试、Golden Set 与 CI 共同强制。

## 30.1 规范优先级

```text
Frozen Schema / Frozen Contract
        ↓
Model Development Operating Contract (本章)
        ↓
Approved ADR / Change Request
        ↓
Current Milestone Specification
        ↓
Architecture / Implementation Notes
        ↓
Implementation Convenience
```

- 低优先级规则 MUST NOT 覆盖高优先级规则。
- 实现便利、性能优化、减少代码量、缩短开发时间均不能作为违反 Frozen Contract 的理由。
- 规范冲突无法自动解决时，当前受影响实现 MUST 停止并生成 Change Request；未受影响的任务可继续。
- v0.3 文档版本升级不等于 v0.2 Frozen Schema 自动升级。

## 30.2 主开发模型与成本策略

| 任务类型 | 默认模型/推理强度 | 说明 |
| --- | --- | --- |
| Schema、状态机、Relation、Narrative、跨模块集成 | GPT-5.6 Sol / High | 高风险结构性工作。 |
| 常规 CRUD、API、migration、fixture、普通单测 | GPT-5.6 Sol / Medium | 控制成本；仍需遵守全部规范。 |
| Milestone Audit / failure-path review | GPT-5.6 Sol / High，新上下文 | 必须与 Developer Pass 上下文隔离。 |
| 格式化、lint、确定性脚本 | 工具链优先 | 能由程序完成的任务不消耗高推理模型。 |

## 30.3 Agent 不得拥有的隐含权限

- 不得自行修改 Frozen Schema、Frozen State Machine、Relation Taxonomy、API Contract 或 Gate Contract。
- 不得通过删除测试、降低阈值、改变 Golden Set 标注或绕过 Gate 使 CI 通过。
- 不得顺手实现未来 Milestone，也不得跨越 current milestone 的 allowed_paths。
- 不得用自由文本解释代替机器可验证的 Schema、测试或状态迁移记录。

# 31. Rule ID 与机器可追踪规则注册表

所有真正影响系统正确性、下游准入、冻结契约或开发流程的规则 MUST 拥有稳定 Rule ID。Rule ID 使“开发文档的一句话”可以一路追踪到代码约束、测试与 CI Gate。

## 31.1 Rule 命名空间

| 前缀 | 范围 |
| --- | --- |
| CORE | 系统级不可变原则与唯一下游入口 |
| SCHEMA | Frozen Schema 与兼容性 |
| STATE | 对象生命周期与状态迁移 |
| EVID | SourceSpan / provenance |
| NUM | NumericFact 与确定性验证 |
| REL | Relation 抽取与验证 |
| REVIEW | Human Review |
| MILESTONE | Agent 开发范围与流程 |
| CHANGE | Change Control |
| TEST | 测试行为 |
| CI | 持续集成阻断 |
| AUDIT | 独立审计 |
| TRACE | 版本、run、provenance |
| IDEMP | 幂等与重跑 |
| SEC | 安全与敏感数据 |

## 31.2 Rule Registry Schema

```yaml
id: CORE-001
title: Approved Graph is the only downstream factual input
level: MUST
scope: [narrative, slideplan]
statement: Only APPROVED objects loaded from Approved Semantic Graph may enter downstream.
enforcement:
  code: src/graph/admission.py
  tests:
    - tests/integration/test_downstream_admission.py
  ci_gate: downstream-admission
status: ACTIVE
introduced_in: v0.3
related_specs: [SYSTEM_SPEC_v0.2]
related_adrs: []
```

## 31.3 v0.3 初始强制规则集

| Rule ID | 规范陈述 | 级别 |
| --- | --- | --- |
| CORE-001 | APPROVED Semantic Graph 是 Narrative/SlidePlan 的唯一事实入口。 | MUST |
| EVID-001 | 关键 Claim/NumericFact/Relation 必须可追溯到至少一个 SourceSpan。 | MUST |
| TRACE-001 | 所有派生对象必须保存 schema_version、pipeline_run_id、document_version 与 revision 元数据。 | MUST |
| NUM-001 | NumericFact 审计真值必须使用 Decimal/字符串序列化，不使用二进制 float。 | MUST |
| NUM-002 | LLM 只能抽取数字候选，百分比、差值、单位换算和四舍五入由确定性代码完成。 | MUST |
| REL-001 | Embedding 只负责 Relation 候选召回，Relation 类型必须经分类与独立 Gate。 | MUST |
| STATE-001 | 禁止 CANDIDATE→APPROVED 直接跳转。 | MUST |
| STATE-002 | NEEDS_REVIEW / REJECTED / VERIFIED 对象不得进入正式下游。 | MUST |
| SCHEMA-001 | Frozen Artifact 未经 Approved Change Request 不得修改。 | MUST |
| MILESTONE-001 | Agent 只能修改 Current Milestone 明确允许的路径。 | MUST |
| MILESTONE-002 | 每个 Milestone 按 READ→PLAN→IMPLEMENT→TEST→AUDIT→FREEZE 执行。 | MUST |
| CHANGE-001 | 实现若需要破坏 Frozen Contract，必须先生成 Change Request 并停止相关修改。 | MUST |
| TEST-001 | 不得删除、弱化或跳过失败测试以使实现通过。 | MUST NOT |
| CI-001 | 关键 Gate、Schema、Golden Set 或 Frozen Hash 失败时禁止标记 Milestone DONE。 | MUST |
| AUDIT-001 | 每个 Milestone 必须在新上下文中执行独立 Audit Pass。 | MUST |
| REVIEW-001 | 关键数字不可验证、OCR 低置信、关系冲突等情况进入 Human Review。 | MUST |
| IDEMP-001 | 每个 stage 必须支持基于幂等键安全重跑，不覆盖历史审计记录。 | MUST |
| SEC-001 | 敏感材料不得写入日志、fixture 或未授权外部服务。 | MUST |

# 32. AGENTS.md：模型的仓库级入口契约

长开发文档不应成为 Agent 每次执行时唯一的信息入口。仓库根目录 MUST 存在简短 AGENTS.md，负责告诉 Sol：先读什么、什么不可违反、当前任务如何执行。完整规范仍以 docs/specs/ 为 System of Record。

## 32.1 AGENTS.md 必须包含

- Required Reading：Development Contract、System Spec、Current Milestone、相关 ADR 与 Frozen Schemas。
- Non-negotiable Rules：Approved Graph、Frozen Schema、Decimal、SourceSpan、状态机与禁止未来 Milestone。
- Workflow：READ → PLAN → IMPLEMENT → TEST → AUDIT → FREEZE。
- Stop Conditions：需要修改 Frozen Artifact、发现规范冲突、无法满足 Acceptance Criteria。
- Output Contract：Implementation Plan、Test Result、Audit Result、Milestone Completion Report。

## 32.2 根目录 AGENTS.md 模板

```markdown
# Reliable PPT System — Agent Instructions

## Required reading
Before modifying code, read:
1. docs/specs/DEVELOPMENT_CONTRACT.md
2. docs/specs/SYSTEM_SPEC_v0.3.md
3. docs/milestones/CURRENT.md
4. Referenced ADRs
5. Referenced frozen schemas

## Non-negotiable rules
- Approved Semantic Graph is the only valid downstream factual input.
- Never modify frozen artifacts without an APPROVED Change Request.
- NumericFact audit values use Decimal; LLMs never perform deterministic arithmetic.
- Every Claim/NumericFact/Relation requires SourceSpan provenance.
- CANDIDATE/VERIFIED/NEEDS_REVIEW/REJECTED never enter formal downstream.
- Do not implement future milestones.
- Do not weaken tests or thresholds to make CI pass.

## Workflow
READ -> PLAN -> IMPLEMENT -> TEST -> AUDIT -> FREEZE

If implementation conflicts with a frozen specification:
STOP the affected change and create a Change Request.
```

## 32.3 嵌套 AGENTS.md

只有当某个目录存在额外局部规则时 SHOULD 使用嵌套 AGENTS.md，例如 schemas/ 禁止非兼容字段修改、evaluation/ 禁止直接篡改 Golden Label。局部 AGENTS.md 可以增加约束，但 MUST NOT 放宽根目录规则。

# 33. Milestone Contract 与 Agent 执行状态机

Current Milestone 是 Agent 的唯一合法实施范围。一个模型任务可以很大，但不能是“把整个系统开发完”。每个 Milestone 都必须形成独立、可冻结、可回归的工程增量。

## 33.1 Milestone 生命周期

```text
NOT_STARTED
   ↓
READ
   ↓
PLANNED
   ↓
IMPLEMENTING
   ↓
TESTING
   ↓
AUDITING
   ↓
FROZEN / BLOCKED
```

## 33.2 固定六步开发协议

| 阶段 | Agent 必须做什么 | 不得做什么 |
| --- | --- | --- |
| READ | 读取 AGENTS、Current Milestone、Frozen Schema、ADR、现有测试。 | 不得立即修改代码。 |
| PLAN | 输出 files_to_create/modify、schema/db impact、test plan、risks。 | 不得隐藏 Frozen Contract 影响。 |
| IMPLEMENT | 只修改 allowed_paths；实现本 Milestone。 | 不得跨范围重构或实现未来功能。 |
| TEST | 运行 unit/integration/schema/migration/相关 Golden regression。 | 不得跳过失败项。 |
| AUDIT | 使用新上下文按规范找缺陷与绕过路径。 | 不得为 Developer Pass 辩护。 |
| FREEZE | 输出 Completion Report，并冻结达到条件的 artifact。 | 未通过 DoD 不得宣称完成。 |

## 33.3 Current Milestone Schema

```yaml
milestone_id: M1
title: Frozen Core Schema and Lifecycle
status: ACTIVE
goal: Implement frozen Pydantic/JSON Schemas and lifecycle state machine.
allowed_paths:
  - src/schemas/**
  - src/state/**
  - tests/unit/schemas/**
  - tests/unit/state/**
forbidden_paths:
  - src/narrative/**
  - src/slide_contract/**
frozen_dependencies:
  - docs/specs/SYSTEM_SPEC_v0.3.md
  - schemas/v0_2/**
acceptance_criteria:
  - all schema validation tests pass
  - illegal state transitions are rejected
  - no frozen artifact diff without approved CR
required_tests:
  - unit
  - schema
  - frozen_hash
golden_subset: none
```

# 34. Frozen Artifact 与 Change Control

## 34.1 Frozen Artifact 类型

- JSON Schema / Pydantic Schema
- State Machine
- Relation Taxonomy
- Gate Contract
- Database Contract
- API Contract
- SlidePlan Contract
- Golden Set label schema

## 34.2 Change Request 生命周期

```text
PROPOSED → UNDER_REVIEW → APPROVED → IMPLEMENTED → VERIFIED
                 ↘ REJECTED
```

## 34.3 Change Request 最小字段

```yaml
change_id: CR-YYYYMMDD-001
affected_artifact: schemas/v0_2/numeric_fact.json
reason: ...
current_limitation: ...
proposed_change: ...
compatibility: BACKWARD_COMPATIBLE | BREAKING
affected_modules: []
db_migration_required: false
golden_set_impact: ...
risk: ...
rollback_plan: ...
status: PROPOSED
approved_by: null
```

## 34.4 Agent 遇到 Frozen 冲突时的行为

1. 停止受影响的代码修改，不擅自“临时兼容”。
2. 生成 Change Request，并标记被阻塞的 Acceptance Criterion。
3. 继续当前 Milestone 中与该冲突无关且不会制造返工的任务。
4. Change Request 未 APPROVED 前，MUST NOT 修改 Frozen Artifact。

# 35. Same-model Independent Audit：用 Sol 审核 Sol

由于成本策略以 GPT-5.6 Sol 为主，Reviewer 不要求更昂贵模型，但必须通过上下文隔离、输入最小化和固定审计清单降低同源错误。

## 35.1 Developer Pass 与 Audit Pass 的上下文隔离

| Developer Pass | Audit Pass |
| --- | --- |
| 读取完整开发上下文，可修改代码。 | 新任务/新上下文；默认只读。 |
| 目标：完成 Milestone。 | 目标：主动寻找规范违反、失败路径和隐含耦合。 |
| 允许看到 Implementation Plan。 | 不读取 Developer 的解释性 reasoning。 |
| 可修复测试。 | 先输出 Findings，再由后续修复任务处理。 |

## 35.2 Audit Pass 最小输入

- AGENTS.md
- Development Contract / Frozen Spec
- Current Milestone
- git diff / changed files
- test & CI results
- 相关 schema / migration

## 35.3 审计严重度

| Severity | 定义 | 是否阻断 Freeze |
| --- | --- | --- |
| CRITICAL | 可能绕过 Approved Graph、破坏数据正确性/审计性或泄露敏感数据。 | 是 |
| HIGH | 违反 MUST 规则、Frozen Contract、状态机或确定性验证。 | 是 |
| MEDIUM | 违反 SHOULD、缺测试或存在可维护性/性能风险。 | 按 Milestone 策略 |
| LOW | 非阻断改进。 | 否 |

## 35.4 Audit 输出 Schema

```yaml
audit_id: audit_M1_003
milestone_id: M1
model: gpt-5.6-sol
findings:
  - finding_id: F-001
    severity: HIGH
    rule_id: STATE-001
    file: src/state/transitions.py
    evidence: "CANDIDATE can transition directly to APPROVED"
    remediation: "remove transition and add negative unit test"
result: FAIL
```

# 36. Rule → Code → Test → CI Enforcement Matrix

任何 MUST 级规则如果可以用代码表达，就 SHOULD 从纯文档规则升级为程序约束。以下矩阵定义第一批必须落地的 Enforcement。

| Rule | Code Enforcement | Required Test | CI Gate | Policy |
| --- | --- | --- | --- | --- |
| CORE-001 | Admission guard：仅 status=APPROVED | test_downstream_admission | downstream-admission | BLOCK |
| EVID-001 | Pydantic validator + DB FK/constraint | test_missing_source_span_rejected | evidence-integrity | BLOCK |
| NUM-001 | Decimal field type / JSON string | test_float_not_accepted_as_audit_value | numeric-schema | BLOCK |
| NUM-002 | Deterministic NumericVerifier | test_percentage_and_rounding | numeric-verification | BLOCK |
| STATE-001 | Explicit transition table | test_candidate_cannot_approve_directly | state-machine | BLOCK |
| STATE-002 | Downstream admission policy | test_nonapproved_never_downstream | downstream-admission | BLOCK |
| SCHEMA-001 | Frozen artifact hash manifest | test_frozen_hashes_unchanged | frozen-contract | BLOCK |
| TEST-001 | CI policy + test inventory diff | test suite protection | test-integrity | BLOCK |
| IDEMP-001 | Idempotency key + uniqueness constraints | test_stage_rerun_is_idempotent | pipeline-idempotency | BLOCK |
| TRACE-001 | Base metadata validator | test_provenance_required | traceability | BLOCK |

# 37. CI / Merge / Freeze Gate

## 37.1 v0.3 默认 CI 阶段

```text
lint
→ unit
→ schema_validation
→ migration_check
→ frozen_artifact_hash
→ integration
→ relevant_golden_regression
→ security_checks
→ rule_enforcement_report
→ milestone_dod
```

## 37.2 BLOCKING 条件

- 任何 required test 失败。
- 未经 Approved CR 出现 Frozen Artifact hash 变化。
- 关键 schema validation、migration compatibility 或状态机检查失败。
- Golden Set 的 critical item 出现已定义的不可接受回归。
- 存在未关闭的 CRITICAL/HIGH Audit finding。
- Current Milestone allowed_paths 之外出现未经批准的实现改动。
- 存在关键对象无 provenance、Numeric Gate 失败却进入 APPROVED、或任何下游准入绕过。

## 37.3 Golden Set 阈值管理

具体数值阈值 MUST 由 config/evaluation_thresholds.yaml 版本化管理，不写死在 Agent Prompt 中。第一阶段采用“已有基线不退化 + critical errors=0”的保守策略；阈值调整属于评估策略变更，必须记录 ADR 或 Change Request。

# 38. Developer Pass、Audit Pass 与 Completion Report 模板

## 38.1 Developer Pass 任务头

```text
ROLE: Main Developer
MODEL: GPT-5.6 Sol
CURRENT MILESTONE: <M#>

Before coding:
1. Read AGENTS.md and required specs.
2. Report allowed_paths, forbidden_paths, frozen dependencies.
3. Produce Implementation Plan.
4. If a frozen change is required, do not modify it; create a Change Request.

Implement only this milestone. Run all required tests before reporting completion.
```

## 38.2 Audit Pass 任务头

```text
ROLE: Independent Specification Auditor
MODEL: GPT-5.6 Sol
MODE: READ-ONLY FIRST PASS

Assume the implementation contains hidden defects.
Check each changed path against Rule Registry and Current Milestone.
Prioritize: schema drift, state-machine bypass, missing provenance, numeric nondeterminism, downstream admission, idempotency, failure paths, tests weakened to pass.
Output findings only; do not rationalize Developer decisions.
```

## 38.3 Milestone Completion Report

```yaml
milestone_id: M1
status: PASS | FAIL | BLOCKED
implemented: []
not_implemented: []
files_changed: []
frozen_artifacts_changed: []
change_requests: []
tests:
  passed: 0
  failed: 0
golden_regression: NOT_APPLICABLE | PASS | FAIL
audit_result: PASS | FAIL
known_limitations: []
open_risks: []
artifacts_frozen: []
```

# 39. Repository Layout v0.3

```text
AGENTS.md

docs/
├── specs/
│   ├── SYSTEM_SPEC_v0.3.md
│   ├── DEVELOPMENT_CONTRACT.md
│   ├── STATE_MACHINE.md
│   └── SLIDEPLAN_CONTRACT.md
├── decisions/
│   └── ADR-*.md
├── milestones/
│   ├── CURRENT.md
│   └── M*.md
├── change_requests/
│   └── CR-*.md
└── milestone_reports/
    └── M*-completion.md

schemas/
├── v0_2/                  # Frozen business schemas
└── frozen_manifest.json

src/
├── ingestion/
├── parsing/
├── segmentation/
├── evidence/
├── schemas/
├── extraction/
├── retrieval/
├── verification/
├── human_review/
├── graph/
├── narrative/
├── slide_contract/
├── observability/
├── security/
└── db/

prompts/
├── extraction/
├── verification/
└── narrative/

evaluation/
├── golden_set/
├── metrics/
└── evaluation_thresholds.yaml

tests/
├── unit/
├── integration/
└── regression/

config/
rule_registry.yaml
```

## 39.1 目录权限原则

- Current Milestone 的 allowed_paths 决定 Coding Agent 可写目录。
- schemas/v0_2/ 默认只读；如需变更必须 CR APPROVED。
- evaluation/golden_set/ 默认只读给 Developer；标注更改只能走 evaluation review。
- docs/decisions/ 与 change_requests/ 允许 Agent 提案，但 APPROVED 状态由项目 owner 决定。

# 40. v0.3 Milestone 路线：先建立“约束系统”，再继续业务实现

| Milestone | 目标 | Freeze 输出 |
| --- | --- | --- |
| M0 | Agent Governance Bootstrap：AGENTS、Rule Registry、CI 骨架、Frozen Manifest、Milestone/CR 模板。 | 开发执行规则与自动阻断骨架 |
| M1 | 核心 Schema + 生命周期状态机。 | Pydantic/JSON Schema、transition table |
| M2 | DocumentVersion + SourceSpan + Evidence Layer。 | 可追溯 Evidence contract |
| M3 | Claim + NumericFact + Deterministic NumericVerifier。 | 数字可靠性闭环 |
| M4 | GateResult + Human Review 最小闭环。 | 机器验证到人工决策 |
| M5 | Relation retrieval/classification/verification + Approved SemanticGraph。 | 可靠图结构 |
| M6 | Semantic Segmentation + Coverage Evaluation。 | 全文分段与漏项评估 |
| M7 | NarrativeGraph。 | 可解释叙事主线 |
| M8 | SlidePlan Contract implementation。 | 内容→视觉 Handoff |
| M9+ | Visual Grammar / Layout / Renderer。 | 进入 v0.4+ 视觉系统 |

## 40.1 M0 是 v0.3 的第一项实际开发

在编写业务模块前，先把“模型如何开发这个项目”本身做成代码资产。M0 完成后，后续 M1–M9 都在相同的规则、CI、审计和变更控制下推进。

# 41. Definition of Done v0.3

任何 Milestone 只有同时满足以下条件才可以标记 DONE / FROZEN。

- Acceptance Criteria 全部 PASS。
- 所有 required tests PASS；无通过删除/弱化测试获得的假通过。
- Schema validation 与 migration check PASS。
- 不存在未授权 Frozen Artifact diff。
- 相关 Golden Set regression 满足版本化阈值。
- 不存在 BLOCKING Gate failure。
- Independent Audit Pass 已完成，CRITICAL/HIGH finding 为 0。
- Known limitations 与 Open risks 已记录。
- Milestone Completion Report 已生成。
- 新增/修改规则已更新 Rule Registry 与 Enforcement Matrix。

# 42. v0.3 新增 ADR 决策摘要

| ADR | 决策 |
| --- | --- |
| ADR-006 | GPT-5.6 Sol 为项目默认 Lead Architect / Main Developer；高成本模型不是常规依赖。 |
| ADR-007 | 开发正确性由规则、Schema、测试、Golden Set 与 CI 保证，不依赖模型自觉。 |
| ADR-008 | AGENTS.md 只做短入口与导航，完整规范以 docs/specs 为 System of Record。 |
| ADR-009 | 所有 MUST 规则逐步映射 Rule → Code → Test → CI。 |
| ADR-010 | 同模型 Review 必须使用独立上下文与固定 Audit Protocol。 |
| ADR-011 | Frozen Schema v0.2 不因 System Spec v0.3 自动升级。 |

# 43. v0.3 结论与立即执行项

v0.3 的本质不是增加更多业务模块，而是把“如何让 GPT-5.6 Sol 长期、低成本、可控地开发整个项目”本身做成工程系统。模型负责推理与实现，仓库规则负责记忆，Schema/状态机负责边界，测试与 Golden Set 负责回归，CI 负责阻断，Human Review 负责最终不确定性。

1. 先实施 M0：创建 AGENTS.md、Rule Registry、Frozen Manifest、Milestone/CR/Audit 模板与最小 CI Gate。
2. 再实施 M1：冻结核心 Pydantic/JSON Schema 与对象状态机。
3. 从 M1 起，任何 Sol 开发任务都必须使用 Current Milestone + Developer Pass + Independent Audit Pass。

# 附录 A｜仓库根目录 AGENTS.md 完整模板

```markdown
# Reliable PPT System — Agent Instructions

## 1. Required reading
Before modifying code, read in this order:
1. docs/specs/DEVELOPMENT_CONTRACT.md
2. docs/specs/SYSTEM_SPEC_v0.3.md
3. docs/milestones/CURRENT.md
4. ADRs referenced by CURRENT.md
5. Frozen schemas referenced by CURRENT.md
6. Existing tests in the affected modules

## 2. Non-negotiable rules
- Approved Semantic Graph is the only formal downstream factual input.
- Never change a frozen artifact without an APPROVED Change Request.
- NumericFact audit values use Decimal; LLMs do not perform deterministic arithmetic.
- Every Claim, NumericFact and Relation requires SourceSpan provenance.
- CANDIDATE, VERIFIED, NEEDS_REVIEW and REJECTED never enter formal downstream.
- Do not implement future milestones or unrelated refactors.
- Do not delete, weaken or skip failing tests to obtain a pass.
- Do not lower evaluation thresholds without an approved policy change.

## 3. Required workflow
READ -> PLAN -> IMPLEMENT -> TEST -> AUDIT -> FREEZE

## 4. Before coding
Report:
- current milestone
- allowed paths
- forbidden paths
- frozen dependencies
- acceptance criteria
- implementation plan

## 5. Stop condition
If the implementation requires a frozen change, stop the affected change and create a Change Request.
Do not silently work around the contract.

## 6. Completion
A milestone is not complete until required tests, CI gates, relevant Golden regression and independent audit pass.
```

# 附录 B｜rule_registry.yaml 最小模板

```yaml
registry_version: "0.3"
rules:
  - id: CORE-001
    title: Approved Graph only
    level: MUST
    statement: Only APPROVED semantic objects may enter formal downstream.
    enforcement:
      code: src/graph/admission.py
      tests:
        - tests/integration/test_downstream_admission.py
      ci_gate: downstream-admission
    status: ACTIVE

  - id: NUM-002
    title: Deterministic numeric verification
    level: MUST
    statement: LLMs may extract numeric candidates but never provide audit arithmetic.
    enforcement:
      code: src/verification/numeric.py
      tests:
        - tests/unit/verification/test_numeric.py
      ci_gate: numeric-verification
    status: ACTIVE
```

# 附录 C｜Milestone Specification 模板

```markdown
# Milestone <ID> — <Title>

status: DRAFT | ACTIVE | BLOCKED | FROZEN
owner: project

## Goal
<one bounded engineering outcome>

## Allowed paths
- ...

## Forbidden paths
- ...

## Frozen dependencies
- ...

## Inputs / Outputs
- input: ...
- output: ...

## Acceptance criteria
- [ ] ...

## Required tests
- unit
- integration
- schema
- golden subset

## Change policy
Any frozen dependency change requires an APPROVED Change Request.

## Completion report
Required before FREEZE.
```

# 附录 D｜Change Request 模板

```markdown
# Change Request <CR-ID>

status: PROPOSED
affected_artifact: ...
rule_ids: []

## Reason
...

## Current limitation
...

## Proposed change
...

## Compatibility
BACKWARD_COMPATIBLE | BREAKING

## Affected modules
- ...

## Migration / Golden Set impact
...

## Risk / rollback
...

## Approval
approved_by: null
approved_at: null
```

# 附录 E｜Independent Audit Checklist

- Frozen Schema 是否有未经批准的 diff？
- 是否存在 CANDIDATE→APPROVED 或其他非法状态迁移？
- 非 APPROVED 对象是否可能进入 Narrative / SlidePlan？
- Claim/NumericFact/Relation 是否存在缺 SourceSpan 或缺 provenance？
- NumericFact 是否出现 float 审计真值或 LLM 算术？
- Relation 是否绕过 retrieval/classification/verifier 任一层？
- 幂等重跑是否覆盖旧 revision 或生成重复业务对象？
- DB migration、Pydantic/JSON Schema 与 API 是否一致？
- 失败路径、冲突路径、低置信路径是否有测试？
- 是否删除、弱化、跳过测试或降低阈值以获得 PASS？
- 是否修改 Current Milestone allowed_paths 外的代码？
- Golden Set 是否被 Developer 直接改标签？
- 敏感数据是否进入日志、fixture、prompt dump 或未授权服务？
- Completion Report 是否真实反映未完成项、限制与风险？

