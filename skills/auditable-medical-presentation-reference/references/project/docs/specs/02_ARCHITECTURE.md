# 医学可审计演示系统｜ARCHITECTURE v0.1

> 本文档定义 Agent 架构、系统状态机、模块边界、调用链与工程约束。  
> 已冻结模块：Claim Table v0.1 / Information Triage v0.1 / Medical Information Architect v0.1  
> 核心架构原则：**任何模型不得直接跨越 `Source → Final Deck`。**

---

## 1. 总体架构

```text
用户资料
   │
   ▼
Source Repository
   │
   ▼
Source Extractor
   │
   ▼
Claim Table / Claim Graph
   │
   ├─────────────┬─────────────┐
   ▼             ▼             ▼
Information   Evidence      Clinical
Triage        Mapper        Architect
   │             │             │
   └─────────────┴─────────────┘
                 │
                 ▼
          Medical Verifier
                 │
                 ▼
          Compliance Agent
                 │
                 ▼
        Approved Content Graph
                 │
                 ▼
          Visual Design Agent
                 │
                 ▼
             Draft Deck
                 │
        ┌────────┴────────┐
        ▼                 ▼
 Numerical QA       Semantic QA
        │                 │
        └────────┬────────┘
                 ▼
         Medical Review Sheet
                 │
                 ▼
           Final Delivery
```

---

## 2. 系统组件

### 2.1 Web / Client

核心界面：

1. 项目创建；
2. Source Viewer；
3. Claim Table；
4. Clinical Narrative；
5. Decision / Evidence Map 编辑器；
6. Medical Review Sheet；
7. Compliance Panel；
8. Deck Preview；
9. 导出中心。

### 2.2 Backend API

建议：

- Python；
- FastAPI；
- Pydantic / JSON Schema；
- PostgreSQL；
- pgvector；
- Redis + Celery 或同类任务队列；
- 对象存储保存原文件与渲染结果。

### 2.3 Document Layer

建议：

- PyMuPDF / pdfplumber；
- python-docx；
- openpyxl；
- python-pptx；
- 图片与表格解析使用多模态模型辅助。

MVP 首期可只实现 PDF。

### 2.4 Model Adapter Layer

统一适配：

- Extraction Model；
- Reasoning Model；
- Verification Model；
- Design / Rendering Model。

要求：

- 模型可替换；
- 调用输入/输出结构化；
- 保存 model_id / model_version；
- 保存 prompt_version；
- 不能让 Design Model 直接读取未审核 Source 后自由生成最终内容。

---


### 2.5 Policy / Guardrail Engine

Policy Engine 是系统的确定性规则执行层，不是 LLM Agent。

#### 输入

- Rule Registry；
- 当前对象及其版本；
- Agent Capability；
- Schema Validation Result；
- Numerical QA；
- Semantic QA；
- Medical Verifier Result；
- Compliance Result；
- Human Review State；
- 当前 Workflow State。

#### 输出

- `PASS`；
- `BLOCK`；
- `HUMAN_REVIEW_REQUIRED`；
- Violation Records；
- Next-state eligibility。

#### 核心职责

1. 执行 Hard Constraint；
2. 检查 Agent 是否越权；
3. 对 Semantic / Human-governed 规则汇总判定结果；
4. 负责 Workflow State Gate；
5. 将规则执行结果写入 Audit Log；
6. 保证“禁止”不是单纯 Prompt 约束。

#### 与 Orchestrator 的边界

```text
Orchestrator
决定：下一步调用谁

Policy Engine
决定：当前结果是否有资格进入下一步
```

Policy Engine 不生成医学内容、不修改 Claim、不产生 Clinical Edge。


## 3. Agent 定义

### 3.1 Orchestrator

#### 输入
- Project Config；
- 当前状态；
- 任务结果；
- 人工审核状态。

#### 职责
- 调度 Agent；
- 管理状态；
- 失败重试；
- 人工确认节点；
- 审计日志；
- 版本号。

#### 禁止
- 不直接改医学事实；
- 不直接生成最终诊疗建议。

---

### 3.2 Source Extractor / Claim Builder

#### 目的

把 Source Document 转换为**可审计的 Source Fact Layer**。输出的 Claim Table 不等同于摘要，也不得提前构造临床关系。

#### 输入
- Source Document；
- Extraction Schema；
- Project Context。

#### 输出
- SourceChunk；
- Atomic Claim；
- Canonical Claim；
- SourceRef；
- NumericFact；
- Conflict Group；
- 表格 / 图注 / Figure Region Pointer。

#### Claim Table v0.1 冻结规则

1. 一个 Claim 只表达一个可独立验证的医学命题。
2. 同时保存 `source_quote` 与 `normalized_claim`。
3. 数字、阈值、推荐类别、证据等级单独结构化。
4. `SOURCE / SUMMARY / SYNTHESIS` 从 Claim 层开始标识。
5. Claim 只存事实，关系全部进入 Edge，不在 Claim 阶段偷偷推导。
6. 同一事实多来源合并为 Canonical Claim；冲突来源绝不自动融合。
7. 任何需要外部医学知识才能补全的内容，不得被标记为 SOURCE。

#### 原子化原则

一个 Claim 必须可以独立判断真伪，但不能把会改变医学意义的限定条件拆散。Population、Condition、Timeframe、Dose、Threshold 等属于命题的一部分时必须保留。

#### Canonicalization

- 多个来源表达同一医学命题：合并到同一个 Canonical Claim，并挂接多个 SourceRef；
- 内容相互冲突：保留独立 Claim，并分配同一个 `conflict_group_id`；
- 禁止通过平均、折中、投票自动消除冲突。

#### 必须提取
- 原文片段；
- 上下文；
- 页码；
- 章节；
- 表格编号 / 行 / 列；
- 图编号 / 区域；
- 数字与单位；
- 阈值；
- 推荐类别；
- 证据等级；
- Population；
- Condition；
- Timeframe；
- Limitation。

#### 禁止
- 添加病例；
- 添加来源外医学事实；
- 补全药物信息；
- 补完整诊疗算法；
- 推断推荐等级；
- 修改数字；
- 创建 Clinical Edge；
- 依赖外部医学知识后仍将结果标记为 SOURCE。

#### Human Review Trigger
- 语义不确定；
- 表格 / 图形解析不确定；
- 正文与表格数字冲突；
- 推荐等级不确定；
- 多来源冲突；
- 人群 / 条件不明确；
- 只能依赖外部知识才能补全。

### 3.3 Information Triage

#### 目的

决定 Claim 在**本次演示任务**中的进入层级，而不是判断医学上的绝对重要性。

#### 输入
- Claim Graph；
- `Presentation Question`；
- Audience；
- Project Type；
- Goal；
- Duration；
- Risk Level；
- Claim Metadata。

#### 输出
- TriageDecision；
- `MUST_INCLUDE / SHOULD_INCLUDE / APPENDIX / EXCLUDED`；
- Meaning-Preserving Bundle；
- Presentation Dependency；
- Presentation Cost；
- User Override Record。

#### Information Triage v0.1 冻结规则

1. Triage 的目标是决定“是否进入本次汇报”，而不是判断医学上的绝对重要性。
2. Presentation Question 是最高层筛选条件，必须在 Triage 前明确。
3. Triage 同时考虑 Audience、Project Type、Goal、Duration，而不是只按 Claim 重要度排序。
4. Risk Level 是约束条件而不是简单评分权重；RED 不等于全部必须展示。
5. 删除限定条件会改变医学意义时，相关 Claims 必须作为 Meaning-Preserving Bundle 共同处理。
6. 输出固定为 MUST_INCLUDE / SHOULD_INCLUDE / APPENDIX / EXCLUDED；EXCLUDED 永不删除原始 Claim。
7. 每个 Triage Decision 必须提供可解释 reason，并允许用户 Override，所有 Override 进入审计日志。
8. Triage 只决定内容选择与 Presentation Dependency，不负责创造医学关系，也不负责生成页面。

#### 决策顺序

```text
Presentation Question
    ↓
直接相关 Claims
    ↓
Narrative Prerequisite
    ↓
必要 Evidence
    ↓
Meaning-Preserving Conditions
    ↓
Audience Depth
    ↓
Duration / Presentation Cost
    ↓
Structure Completeness Check
    ↓
Bucket
```

#### 重要约束

- RED 是约束而不是加分项；
- `EXCLUDED != DELETE`；
- Presentation Dependency 是演示组织关系，不等于 Clinical Edge；
- MUST 内容超过时长预算时进入 `NEEDS_USER_INPUT`，不得静默删除。

#### 禁止
- 修改 Claim；
- 修改数字 / 推荐等级；
- 合并冲突 Claim；
- 创建 Clinical Edge；
- 为了叙事顺畅补齐来源外医学逻辑；
- 生成最终页面。

### 3.4 Medical Information Architect

#### 目的

把 Triage 后的 Claim 组织成一条**问题驱动、受众适配、可讲解**的 Narrative，并输出结构化 NarrativePlan / PageSpec。

#### 输入
- Triaged Claims；
- Presentation Question；
- Audience；
- Project Type；
- Goal；
- Duration；
- Presentation Dependencies；
- Meaning-Preserving Bundles。

#### 输出
- Narrative Spine；
- Section；
- Page Goal；
- Primary Message；
- Claim-to-Page Mapping；
- Supporting Claims；
- Required Conditions / Data / Caveats；
- Suggested Functional Visual；
- Cognitive Load；
- Narrative / Page Override Record。

#### Medical Information Architect v0.1 冻结规则

1. Architect 的任务是组织“怎么讲”，不负责决定医学事实是否成立。
2. 每套汇报必须围绕 Presentation Question 建立一个 Narrative Spine，而不是复制源文档目录。
3. Narrative Spine、Section 标题和 Primary Message 均必须保留 SOURCE / SUMMARY / SYNTHESIS provenance。
4. 每页必须有一个明确 Page Goal 和唯一 Primary Message；Supporting Claims 只用于支撑该核心信息。
5. 页面信息固定按 Primary Message → Supporting Claims → Conditions/Data → Source 四层组织。
6. Meaning-Preserving Bundle 不得因排版、页数或时长被拆到足以改变医学意义。
7. Architect 可以建立 Presentation Dependency 和推荐 Functional Visual，但不得创建未经验证的 Clinical Edge。
8. Audience Adaptation 在 Architect 层主要改变认知顺序和叙事深度，而不改变底层 Claim。
9. Architect 只生成 NarrativePlan / PageSpec，不生成最终视觉页面，也不得为了“故事完整”补充原文不存在的医学内容。
10. 用户可以调整 Section/Page 顺序和 Narrative，但所有 Override 必须记录，且 Presentation Order 的变化不得自动改变 Clinical Relationship。

#### 页面语义层级

```text
Level 1  Primary Message
Level 2  Supporting Claims
Level 3  Conditions / Data / Caveats
Level 4  Source
```

#### 权限边界

可以：
- Narrative 分组与排序；
- Section / Page Goal；
- Claim-to-Page Mapping；
- Presentation Dependency；
- Functional Visual 推荐；
- 信息密度 / Cognitive Load 管理。

禁止：
- 创造临床事实；
- 创建未经验证 Clinical Edge；
- 修改 Claim；
- 修改数字 / 推荐等级 / 证据等级；
- 拆散 Meaning-Preserving Bundle 到改变原意；
- 自动生成病例；
- 直接制作最终视觉页面。

#### Human Decision Trigger
- 两套 Narrative 同样合理；
- MUST 内容超过时长；
- Presentation Question 仍过于宽泛；
- 核心 SYNTHESIS 会显著影响整套叙事；
- 必须舍弃重要主题才能满足时长。

### 3.5 Semantic Relationship & Evidence Binding

该模块负责从 `NarrativePlan / PageSpec + Verified Claim Candidates + SourceRef` 构建页面层的语义关系，不等同于 Decision Map Builder。

#### 核心原则

> 演示语义不只由箭头产生。标题、顺序、分组、颜色、图例、坐标轴、注释、位置和线条都可能表达关系，因此都必须进入可验证的 Semantic Binding。

#### 输入

- PageSpec；
- Claim / Canonical Claim；
- NumericFact；
- SourceRef；
- Presentation Dependency；
- Meaning-Preserving Bundle；
- Project / Audience Context。

#### 输出

- SemanticObject；
- SemanticRelationship；
- DataBinding；
- VisualBinding；
- TitleEntailment；
- ContextualImplication；
- SemanticPageGraph Draft；
- Human Review Triggers。

#### Module 04 第一批冻结规则

1. 任何能够让合理听众推断事实、比较、归属、条件、因果、支持、时间或临床关系的页面表达，都属于 Semantic Relationship / Binding，必须可识别、绑定和审计。
2. 所有具有事实或结论性质的 Narrative Spine、Section Title、Slide Title、Primary Message 和 Chart Title 必须显式绑定一个或多个底层 Claim。
3. 标题和 Primary Message 的语义强度不得超过底层 Claim 能支持的最大语义强度。
4. 标题不得通过删除 Population、Condition、Timeframe、Exclusion 等必要限定条件扩大医学适用范围。
5. 多个 SOURCE Claim 组合产生的新判断，不得自动继承 SOURCE provenance；没有来源明确支持该组合关系时必须标记为 SYNTHESIS。
6. 任何为了演示效果进行的标题润色或压缩，都不得删除改变医学含义的限定词，也不得将不确定、相关或弱推荐升级为确定、因果或强推荐。
7. 存在 SourceRef 不等于标题得到支持；Title / Claim Entailment 必须独立判断 SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONFLICT / NEEDS_HUMAN_REVIEW。
8. Narrative Spine、Section Title、Slide Title、Primary Message、Chart Title 必须保存 SOURCE / SUMMARY / SYNTHESIS provenance。

状态：`FROZEN v0.1 / Batch 1`

#### 04A Clinical Relationship Builder

Clinical Relationship 最低结构字段：

- relation_type；
- direction；
- source_type / provenance；
- source_refs；
- risk_level；
- conditions；
- logic_operator；
- polarity；
- recommendation_class（适用时）；
- evidence_level（适用时）；
- review_status。

处理临床语义关系候选，例如：

- `leads_to`
- `requires`
- `supports`
- `contraindicates`
- `associated_with`
- `classifies_as`
- `eligible_for`
- `excludes`
- `follows`
- `reassess`
- `causes`
- `treated_with`
- `escalates_to`

要求：

- SOURCE Relationship 必须有 SourceRef；
- SUMMARY Relationship 必须可回到原文已有关系；
- SYNTHESIS Relationship 必须显式标记；
- RED + SYNTHESIS 必须人工医学确认。

#### Module 04 第三批冻结规则｜Clinical Relationship

1. Clinical Relationship provenance 独立于 Claim provenance；SOURCE Claim 不自动推出 SOURCE Relationship。
2. Clinical Relationship 必须保存 `relation_type / direction / provenance / risk / conditions / review_status`。
3. SOURCE Relationship 必须由来源明确支持关系存在、类型和方向。
4. Relationship direction 独立验证；association / prediction / temporal / causal 不得互换或自动反向。
5. 禁止自动 transitive inference；A→B、B→C 不自动产生 A→C。
6. Population / Condition / Timeframe / Exclusion / Dose 等必要限定与 Relationship 绑定。
7. 多条件关系显式保存 AND / OR / NOT / EXCEPT。
8. 否定、禁忌、不推荐、排除、不适用必须结构化为 relationship type 或 polarity。
9. Recommendation Strength / Class / Evidence Level 绑定到推荐关系。
10. Temporal / Associative / Predictive / Causal 严格区分。
11. 跨来源路径中每个 Relationship 保留自己的 SourceRef，组合路径单独记录 SUMMARY / SYNTHESIS provenance。
12. 来源未连接的节点不得为了叙事或视觉闭环自动补关系。
13. 状态固定为 `SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONFLICT / AMBIGUOUS / NEEDS_HUMAN_REVIEW`；RED SYNTHESIS、冲突或关键条件不完整不得自动进入 Approved Semantic Page Graph。
14. 最终所有医学语义视觉连接必须绑定 Clinical Relationship ID；Renderer / Design 不得自行推理新连接。

状态：`FROZEN v0.1 / Batch 3`

#### 04B Evidence Binding

绑定：

- Recommendation ↔ Evidence；
- Study ↔ Outcome；
- Recommendation ↔ Recommendation Class；
- Recommendation ↔ Evidence Level；
- Result ↔ Limitation；
- Evidence ↔ Source Location。

禁止：

- 原文无 effect size 时自动补数值；
- 把 Recommendation Class 与 Evidence Level 混淆；
- 仅凭研究数量推断推荐强度。

#### 04C Data Binding

任何 NumericFact / DataObject 必须绑定其语义上下文：

- Value；
- Unit；
- Metric；
- Population / Subgroup；
- Outcome；
- Timepoint / Timeframe；
- Intervention / Comparator；
- Statistic Type；
- Numerator / Denominator（适用时）；
- SourceRef。

还必须显式记录：

- `value_role`：baseline / final / change_from_baseline / absolute_change / relative_change / absolute_risk / relative_risk 等；
- `value_origin`：SOURCE / DERIVED_CALCULATION / ESTIMATED_FROM_FIGURE / OCR_EXTRACTED；
- `comparability_status`：comparable / partially_comparable / non_comparable / unknown；
- `binding_status`：BOUND / PARTIALLY_BOUND / UNBOUND / CONFLICT / NEEDS_HUMAN_REVIEW。

目的：

> Numerical QA 不仅检查“数字有没有抄错”，还检查“这个数字是不是属于这个指标、这个人群、这个时间和这个结局”。

#### Module 04 第二批冻结规则｜Data Binding

1. 任何进入演示的医学数据都必须绑定 Value 与必要语义上下文（Metric、Unit、Population/Subgroup、Outcome、Timepoint/Timeframe、Intervention/Comparator、Statistic Type、Source）。
2. 数值一致不等于 Data Binding 正确；关键语义绑定错误必须失败。
3. 用于支持 Claim 的数据必须显式建立 `DATA_SUPPORTS_CLAIM` 或等价绑定；同页、邻近、分组不自动代表支持。
4. Baseline、Final Value、Change from Baseline、Absolute/Relative Change、Absolute/Relative Risk 等 value role 必须显式区分。
5. Effect Estimate、CI、P Value、Numerator/Denominator 必须绑定准确 Comparison、Outcome、Population、Timeframe。
6. 系统衍生但原文未给出的数值必须记录输入、公式、`DERIVED_CALCULATION`，并按 SYNTHESIS 管理。
7. 自动衍生仅限白名单中的确定性计算；复杂医学统计推导不得自动生成。
8. 单位换算、格式化、舍入必须保留原始值与转换记录，且不得跨越临床边界。
9. 0 / Missing / NA / NR / Not Measured / Not Applicable / Unknown 必须区分，禁止自动插补。
10. 从图形、OCR 或不确定来源估算的数据必须标记估算来源与置信状态，不得作为精确 SOURCE 数据。
11. 跨研究/人群/Endpoint/时间的数据在直接比较前必须具有 Comparability 状态。
12. Data Binding 状态固定为 `BOUND / PARTIALLY_BOUND / UNBOUND / CONFLICT / NEEDS_HUMAN_REVIEW`；RED 仅 BOUND 或人工批准后可进入 Approved Semantic Page Graph。

状态：`FROZEN v0.1 / Batch 2`

#### 04D Title / Claim Entailment

验证：

- Narrative Spine；
- Section Title；
- Slide Title；
- Primary Message；
- Chart Title；

是否被其绑定 Claims 充分支持。

规则：

> 标题语义强度不得超过底层 Claim 可支持的语义强度。

例如：

- “相关”不得通过标题升级为“导致”；
- “可考虑”不得通过标题升级为“推荐”；
- “部分人群”不得通过标题扩展为“全部患者”。

#### 04E Contextual Relationship Checker

区分：

- Presentation Order；
- Presentation Dependency；
- Clinical Relationship；
- Contextual Implication。

页面相邻、连续出现或上下文铺垫本身不等于 Clinical Relationship，但系统必须检测其是否形成来源外强烈推理暗示。

#### Module 04 第四批冻结规则｜Contextual Relationship

1. Contextual Relationship 是由页面/跨页/Section 上下文让目标受众合理推断出的 Semantic Relationship，必须审核隐含语义。
2. Presentation Order、Presentation Dependency、Contextual Implication、Clinical Relationship 分离建模。
3. 检测范围至少覆盖 Intra-page / Adjacent-page / Section。
4. 因此、所以、基于上述、下一步、相比之下、优先、随后等作为 Semantic Trigger。
5. Population / Subgroup / Outcome / Timeframe / Intervention / Comparator 不因相邻页面自动继承；需要省略时使用 Context Contract。
6. 新研究、新指南、新 Population、新 Intervention、新病例、新 Section 或其他语义边界必须 Context Reset / Override。
7. 隐含比较必须调用 Comparability；不可比数据不得通过叙事并列暗示直接优劣。
8. Clinical Implication / Practice Impact / Take-home / Conclusion 必须单独做 Contextual Entailment。
9. 问句、反问句与标题预设同样属于 Semantic Assertion。
10. 状态固定为 `NO_MATERIAL_IMPLICATION / SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONFLICT / AMBIGUOUS / NEEDS_HUMAN_REVIEW`；隐含 RED Clinical Relationship 时继承 RED 风险。
11. Contextual Relationship Checker 只检测、定位和描述，不自行创造医学关系或修改 Claim。

状态：`FROZEN v0.1 / Batch 4`

#### Context Contract

用于在不重复展示全部限定条件的前提下，安全管理跨页上下文。

最小字段：

- `context_contract_id`
- `scope_type`: page / page_range / section
- `scope_ids`
- `population`
- `subgroup`
- `outcome`
- `timeframe`
- `intervention`
- `comparator`
- `source_refs`
- `inheritance_allowed`
- `reset_triggers`
- `override_log`

原则：

- 继承必须显式；
- 语义边界默认 reset；
- 当前页显式 Binding 优先于继承；
- Context Contract 不得创造 Clinical Relationship。

#### 04F Visual Semantic Binding

管理：

- Legend ↔ Series；
- Axis ↔ Metric / Unit；
- Category ↔ Population / Timepoint / Group；
- Annotation ↔ Data Comparison；
- Color ↔ Semantic Meaning；
- Grouping ↔ Meaning；
- Label ↔ Numeric / Claim；
- Connector ↔ Relationship。

区分：

**Pure Styling**
- 字体；
- 留白；
- 非语义背景；
- 非语义装饰色；
- 纯美术细节。

**Semantic Layout / Encoding**
- 分组；
- 层级；
- 连线；
- 图例；
- 轴；
- 颜色语义；
- 标签归属；
- 空间邻近所表达的意义。

Semantic Layout 必须进入 Visual Encoding Contract，Design Agent 不得自由重写。

#### Module 04 第五批冻结规则｜Visual Semantic Binding & Medical Visual Provenance

1. Visual Semantic Binding 严格区分 Pure Styling 与 Semantic Visual Encoding。
2. Grouping / proximity / alignment / enclosure / position / hierarchy 若表达语义，必须显式绑定。
3. Color / gradient / size / thickness / emphasis 一旦承担风险、疗效、证据、推荐、禁忌或优先级含义，必须结构化绑定。
4. Visual Hierarchy 必须区分 Presentation Priority 与 Clinical Priority。
5. Legend / Series / Axis / Metric / Unit / Category / Annotation / Comparison / Symbol 必须显式绑定。
6. 坐标范围、尺度、截断轴等不得制造与真实效应不相称的视觉结论。
7. Connector / Arrow / Inhibition / Activation / Up-Down Indicator 必须绑定已批准 Relationship。
8. Medical Semantic Provenance 与 Visual Asset Provenance 分离保存。
9. Visual Origin 至少支持 `SOURCE_FIGURE / ADAPTED_FROM_SOURCE / REDRAWN_FROM_EVIDENCE / MEDICAL_REFERENCE_ASSET / AI_GENERATED_MEDICAL_VISUAL`。
10. Adaptation / Semantic Simplification / Redrawn from Evidence 必须做 Semantic Fidelity QA。
11. AI Generated Medical Visual 默认 `medical_verified=false`。
12. 承担医学语义的图优先保存 Semantic Objects + Relationships + Bindings，而非仅保存静态图。
13. RED Medical Visual 的关键 Node / Relationship provenance coverage 必须100%。
14. 图内文字、数字、阈值、推荐、标签、结论继续经过原有 QA。
15. 医学有效性与版权许可分离管理；版权状态未知不得默认可用于商业交付或公开传播。

状态：`FROZEN v0.1 / Batch 5`

#### 04G Medical Visual Provenance

所有医学专用图必须维护两条独立 Provenance：

**Medical Semantic Provenance**
- 医学节点、关系、标签、路径、机制依据什么来源成立。

**Visual Asset Provenance**
- 视觉资产本身来自哪里，如何变换，版权/许可状态如何。

Visual Origin：

- SOURCE_FIGURE
- ADAPTED_FROM_SOURCE
- REDRAWN_FROM_EVIDENCE
- MEDICAL_REFERENCE_ASSET
- AI_GENERATED_MEDICAL_VISUAL

Transformation：

- EXACT_REUSE
- STYLE_ONLY
- LAYOUT_REDESIGN
- SEMANTIC_SIMPLIFICATION
- SEMANTIC_SYNTHESIS
- AI_GENERATED

SOURCE_FIGURE / 外部 Asset 还必须记录：
- copyright_status
- license
- commercial_use
- adaptation_allowed
- citation_required

AI_GENERATED_MEDICAL_VISUAL：
- 默认 `medical_verified=false`
- 未通过 Medical Visual QA 不得作为已验证医学事实图交付。

#### 风险分级

Semantic Relationship 同样采用：

- GREEN；
- YELLOW；
- RED。

典型 RED：

- 诊断标准 → 诊断；
- 条件 → 治疗；
- 生物标志物 → 药物选择；
- 药物 → 剂量；
- 症状 → 临床处理；
- 因果关系；
- 升级 / 降阶关系；
- 禁忌 / 排除关系。

#### Provenance

每个关键关系必须记录：

- SOURCE；
- SUMMARY；
- SYNTHESIS。

RED + SYNTHESIS → `HUMAN_REVIEW_REQUIRED`。

#### 禁止

- 因页面顺序自动生成 Clinical Relationship；
- 因视觉分组自动生成临床归属；
- 因同色自动解释为同一治疗类别；
- 仅为了页面美观添加语义连线；
- 让 Functional Visual Renderer 重新推理医学关系。

---

### 3.5A Semantic Page Graph

通过 Medical Verifier 后形成 `Approved Semantic Page Graph`。

至少包含：

```text
Title / Primary Message
Claim Objects
Numeric / Data Objects
Source Objects
Validated Semantic Relationships
Validated Data Bindings
Validated Visual Bindings
Risk / Provenance
Visual Encoding Contract
```

下游所有 Functional Visual Renderer 必须消费该对象，而不是重新读取原始 PDF 自由理解。

---

### 3.5B Functional Visual Renderer

Renderer 是语义图的表现层，不是医学推理层。

可渲染：

- Clinical Decision Map；
- Evidence Map；
- Disease Timeline；
- Mechanism Map；
- Risk Stratification Map；
- Outcome Plot；
- Management Cycle；
- Trial Evidence Matrix；
- Comparison；
- Structured Text。

约束：

- 不创建新 Semantic Relationship；
- 不改变已批准关系方向；
- 不交换 Data Series / Legend；
- 不修改 Axis / Unit 绑定；
- 不改变颜色语义绑定；
- 不改变对象分组所表达的临床含义。

---


### 3.6 Medical Verifier

#### 输入
- Claim Graph；
- Semantic Page Graph Draft；
- SemanticRelationship；
- DataBinding；
- VisualBinding；
- TitleEntailment；
- Source Repository。

#### 检查
- Claim 是否被原文支持；
- Semantic Relationship 是否被原文或已批准综合支持；
- Title / Primary Message 是否被底层 Claims 支持；
- Data 是否绑定正确 Metric / Outcome / Population / Timeframe；
- Legend / Series / Axis / Annotation 是否绑定正确；
- 数字、单位、阈值是否一致；
- 推荐等级是否一致；
- 压缩后是否遗漏限定条件；
- 是否把相关性写成因果；
- 是否把“可考虑”写成“推荐”；
- 是否通过顺序、分组、颜色、空间位置暗示未经验证关系。

#### 输出
- Verified Claims；
- Conflict List；
- Risk Level；
- Human Review Required。

---


### Module 05 第一批冻结规则｜Verifier Role & Source Fidelity

以下 10 条已正式冻结：

1. **Medical Verifier 的默认职责是验证 Generated Medical Meaning 是否忠实于指定 Source，而不是依据模型自身医学知识重新判断、补全或改写来源内容。**
2. **Source Fidelity 与 Clinical Correctness 必须作为两个独立概念管理；默认 `SOURCE_FIDELITY` 模式通过，不代表内容已通过最新临床实践验证。**
3. **Medical Verifier 必须支持至少 `SOURCE_FIDELITY / CROSS_SOURCE_CONSISTENCY / EXTERNAL_MEDICAL_CHECK` 三种 Verification Mode；外部医学验证只有在项目明确启用时才能介入，且外部来源必须与用户指定 Source 分离记录。**
4. **Medical Verifier 是只读验证角色；原则上不得直接修改 Claim、NumericFact、SemanticRelationship、PageSpec 或 Source，发现问题必须输出结构化 VerificationIssue 并退回责任模块修正后重新验证。**
5. **Verifier 必须分别验证 Claim、Title/Primary Message、Data Binding、Clinical Relationship、Contextual Implication 和 Medical Visual Semantic Fidelity，不得只做文本级事实核对。**
6. **每个 VerificationResult 必须记录被验证对象、status、risk、supporting SourceRef/Source Span、issue type、解释和 recommended action；只有 SourceRef 而无语义支持判断不能视为验证完成。**
7. **Verification Status 固定为 `SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONFLICT / AMBIGUOUS / NEEDS_HUMAN_REVIEW / NOT_APPLICABLE`；系统必须允许“不明确”和“无法安全裁定”，不得强迫所有对象得到二元真假结果。**
8. **来源不存在、来源冲突或来源表述不明确时，Verifier 不得使用模型常识静默补全；冲突只有在存在明确 Source Priority Policy 时才能按规则处理，否则必须保留 Conflict 或进入人工审核。**
9. **Verification Gate 必须同时考虑 `verification_status + risk_level + object_type`；RED 的 PARTIALLY_SUPPORTED、AMBIGUOUS、CONFLICT 或 NEEDS_HUMAN_REVIEW 不得自动进入 Approved Semantic Page Graph，RED UNSUPPORTED 必须 BLOCK。**
10. **Verifier 的模型置信度只能用于复核排序和不确定性提示，不能替代 Source Evidence、Provenance 或 Human Review，也不能单独作为 RED 内容自动通过的依据。**

状态：`FROZEN v0.1 / Batch 1`


### 3.7 Compliance Agent

与 Medical Verifier 独立。

#### 输入
- Approved Medical Content；
- Output Channel；
- Source Metadata。

#### 检查
- 患者隐私；
- 医院/医生/机构标识；
- 版权；
- 引用；
- 医疗效果承诺；
- 药品推广倾向；
- 未授权背书；
- 联系方式与站外导流；
- 免责声明。

#### 输出
- compliance_status；
- issues；
- block / warn / pass。

---

### 3.8 Visual Design Agent

#### 输入
仅接收：

- `Approved Semantic Page Graph`；
- `Visual Encoding Contract`；
- Renderer Output。

#### 可以自由修改：Pure Styling
- 字号；
- 字体层级；
- 留白；
- 非语义背景；
- 非语义装饰色；
- 纯视觉线宽与美术细节。

#### 不允许修改：Semantic Layout / Encoding
- 对象分组；
- 标题与内容归属；
- Semantic Relationship；
- Clinical Relationship；
- Legend / Series Binding；
- Axis / Metric / Unit Binding；
- Annotation / Data Binding；
- Color / Risk / Recommendation Binding；
- Label / Numeric Binding；
- 已批准 Node / Relationship；
- 来源标识。

#### 禁止
- 新增任何 Semantic Relationship；
- 通过线条、位置、同色、分组暗示未经批准关系；
- 为版面顺畅改变数据系列归属；
- 新增医学事实；
- 未经批准主动补充临床图形关系。

---

### 3.9 Numerical QA

强制比较：

- number_value；
- unit；
- threshold；
- dose；
- duration；
- sample_size；
- HR / OR / RR / CI / P；
- recommendation_class；
- evidence_level。

任一关键项 mismatch：
- 标记 `QA_BLOCKED`；
- 不进入自动交付。

---

### 3.10 Semantic QA

检查：

- 人群限定是否丢失；
- 排除条件是否丢失；
- 是否出现语气升级；
- 是否出现因果升级；
- 是否把推断写成事实；
- 是否把 Summary / Synthesis 错标为 Source。

---


## 3A. Agent Capability Matrix

所有 Agent 权限采用“最小能力原则”。禁止事项优先通过 API / Schema / 数据库写权限实现，而不是只依赖 Prompt。

| Module | READ | WRITE | Hard Forbidden |
|---|---|---|---|
| Source Extractor | Source Document | Claim / SourceRef / NumericFact | Edge / PageSpec / Deck |
| Information Triage | Claim / Project Config | TriageDecision / PresentationDependency | Claim / ClinicalEdge / Deck |
| Medical Information Architect | Triaged Claim / PresentationDependency | NarrativePlan / PageSpec | Claim / ClinicalEdge / NumericFact |
| Semantic Relationship Engine | Claim / NumericFact / SourceRef / PageSpec | SemanticRelationship / DataBinding / VisualBinding / SemanticPageGraph Draft | Claim mutation / final approval |
| Functional Visual Renderer | Approved Semantic Page Graph | Visual Structure | New SemanticRelationship / Claim mutation |
| Medical Verifier | Claim / SemanticRelationship / Binding / Source | VerificationResult | Source mutation / visual styling |
| Compliance Agent | Approved Medical Content / Channel | ComplianceIssue | Medical fact mutation |
| Visual Design Agent | Approved Semantic Page Graph / Visual Encoding Contract | Styling / LayoutSpec | Claim / NumericFact / SemanticRelationship / VisualBinding |
| Numerical QA | Source Numeric / Slide Numeric | QAResult | Content rewrite |
| Semantic QA | Source / Claim / Page Text | QAResult | Claim mutation |

### Capability enforcement

建议实现：

- 独立 service account / role；
- API endpoint allowlist；
- Pydantic / JSON Schema 限制输出字段；
- 数据库表级 / 字段级写权限；
- Tool allowlist；
- Policy Gate 二次校验。

原则：

> **如果某模块“没有资格修改 Claim”，优先让它在技术上没有 Claim write capability。**

---

## 3B. Rule Enforcement Model

每条冻结规则必须注册为结构化 Rule，而不是只存在于 Markdown。

示例：

```yaml
rule_id: ARC-007
module: medical_information_architect
rule:
  Architect不得创建Clinical Edge
constraint_type: HARD
enforced_by:
  - capability_control
  - output_schema
validated_by:
  - policy_engine
violation_action: BLOCK
severity: critical
```

语义规则示例：

```yaml
rule_id: SEM-004
module: semantic_qa
rule:
  SUMMARY不得把“可考虑”升级为“推荐”
constraint_type: SEMANTIC
enforced_by:
  - semantic_qa
validated_by:
  - medical_verifier
violation_action: HUMAN_REVIEW_REQUIRED
severity: high
```

人工规则示例：

```yaml
rule_id: MED-021
module: medical_review
rule:
  RED SYNTHESIS Semantic Relationship必须人工确认
constraint_type: HUMAN_GOVERNED
enforced_by:
  - policy_engine
validated_by:
  - human_medical_reviewer
violation_action: HUMAN_REVIEW_REQUIRED
severity: critical
```

---

## 3C. Policy Gate

每个阶段完成后都经过 Gate：

```text
Agent Output
   ↓
Schema Validator
   ↓
Capability Violation Check
   ↓
Deterministic QA
   ↓
Semantic / Medical Verification
   ↓
Policy Engine
   ├─ PASS
   ├─ BLOCK
   └─ HUMAN_REVIEW_REQUIRED
```

未经 Gate 通过不得进入下一 Workflow State。



### Module 05 第二批冻结规则｜Semantic Fidelity Verification

以下 12 条已正式冻结：

1. **每个医学语义验证必须优先基于能够完整支持该对象的最小充分 Source Span，而不是仅依赖文档级、章节级或主题相关引用；来源相关不等于来源支持。**
2. **Verifier 必须比较 Source Semantic Frame 与 Generated Semantic Frame 中所有会改变医学意义的关键槽位；任何 Meaning-Critical Slot 的删除、替换、扩大、缩小或错配都必须生成明确 VerificationIssue。**
3. **SUMMARY 可以减少文字长度和重复信息，但不得删除会改变医学边界的必要内容；是否忠实以 Meaning Preservation 而不是字数或词面相似度为标准。**
4. **Generated Scope 不得在无来源支持的情况下扩大或缩小 Source Scope；Population、Subgroup、Disease Stage、Risk Group、Setting 等范围变化必须显式识别并重新验证。**
5. **数量范围和集合强度属于医学语义的一部分；some / selected / many / most / all 等量词不得被静默升级、弱化或删除。**
6. **来源中的不确定性、可能性、证据强度和推荐语气必须保留；不得将可能/提示/相关/可考虑升级为确定/证明/导致/推荐/必须，也不得无依据弱化来源明确的强结论。**
7. **否定、禁忌、不推荐、排除、不适用、无证据及证据否定必须保持原始 polarity；absence of evidence 不得改写为 evidence of absence，关键 polarity 翻转视为 Critical Failure。**
8. **Verifier 必须验证条件集合及 AND / OR / NOT / EXCEPT 等逻辑；会改变适用条件的条件遗漏、增加或逻辑运算符变化均属于 Fidelity Failure。**
9. **Clinical Relationship 的存在、relation_type、direction 和 polarity 必须分别验证；Associative、Predictive、Temporal、Conditional、Causal、Recommendation 等关系不得相互替代。**
10. **诊疗推荐必须作为完整语义单元验证，包括 Population、Condition、Action、Recommendation Strength、Recommendation Class、Evidence Level、Exclusion/Exception；任一关键字段错绑不得判为完整 SUPPORTED。**
11. **多个 Source Span 可以共同支持 SUMMARY/SYNTHESIS，但多个来源分别兼容不能自动等于来源明确支持新的组合结论；不存在直接组合关系证据时必须保留 SYNTHESIS provenance。**
12. **一个对象绑定多个有效 SourceRef 时必须检查所有直接相关来源，不得 Cherry-pick 支持性证据而忽略冲突或限制性来源；实质冲突必须输出 CONFLICT，除非有明确 Source Priority Policy 合法解决。**

状态：`FROZEN v0.1 / Batch 2`


### Module 05 第三批冻结规则｜Verification Issue Resolution & Re-verification Loop

以下 14 条已正式冻结：

1. **每个 VerificationIssue 必须依据 issue_type 路由到明确 Responsible Module，禁止统一交给通用 Rewrite Agent。**
2. **任何因 VerificationIssue 产生的医学内容修订必须创建新版本或不可变 Revision Snapshot，禁止覆盖原对象；旧版本、修改原因和 Issue ID 必须可追溯。**
3. **上游医学对象发生实质语义修改时，所有依赖旧版本的下游对象必须自动标记 STALE/INVALIDATED，并在重建和重新验证前不得继续使用。**
4. **每次修订后必须同时执行 Targeted Re-verification 和 Regression Verification，不得只检查原问题是否消失。**
5. **删除或隐藏问题内容不能自动视为修复完成；必须重新检查 Page Goal、MUST_INCLUDE、Meaning-Preserving Bundle 与 Narrative Integrity，防止通过删内容规避验证。**
6. **Revision Mode 不得提升模块 Capability；责任模块只能在原有 Write Scope 内修复，跨对象类型问题必须继续路由。**
7. **涉及多个模块的问题必须优先定位最上游 Root Cause，并按依赖拓扑顺序修复，禁止多个下游模块对同一上游错误各自打补丁。**
8. **VerificationIssue 状态固定至少包含 `OPEN / ROUTED / IN_REVISION / RESOLVED_PENDING_REVERIFY / VERIFIED_RESOLVED / UNRESOLVED / HUMAN_REVIEW_REQUIRED / WAIVED_BY_HUMAN`；责任模块无权直接将 Issue 标记 VERIFIED_RESOLVED。**
9. **自动 Revision / Re-verification 必须具有有限且可配置的 Retry Budget；超过预算、重复 Critical Issue 或无法收敛时必须升级人工审核。**
10. **连续修订中重复出现相同或等价 Issue 必须识别为 Recurrent Issue；重复 Critical Issue 应进入人工审核并成为模型/规则改进信号。**
11. **Human Override 可以允许内容继续使用，但不得改变原始 VerificationResult；来源未支持的内容即使被人工接受，也必须保留原验证状态，并单独记录 Override provenance。**
12. **医学对象发生实质语义修订后，旧 VerificationResult 自动失效；新版本必须重新建立 Minimum Sufficient Source Span Support 并重新验证，不能继承旧 SUPPORTED 状态。**
13. **所有进入 Approved Semantic Page Graph 和最终交付的医学对象必须绑定不可变的明确版本，不得使用动态 `latest` 引用作为最终审计依据。**
14. **修订影响到的 Data、Context、Visual、Compliance、Copyright 等 Gate 必须依据 Dependency Graph 重新执行；局部医学修复不得绕过其他已冻结约束。**

状态：`FROZEN v0.1 / Batch 3`


### Module 05 第四批冻结规则｜Cross-source Conflict & External Medical Verification

以下 16 条已正式冻结：

1. **跨来源一致性判断前必须先比较 Source Context，包括 Population、Disease Stage、Setting、Intervention、Comparator、Outcome、Timeframe、Jurisdiction 和 Intended Use；语境不等价的来源不得仅因结论不同而自动判 Conflict。**
2. **跨来源不一致必须进行 Conflict Typing，至少区分直接矛盾、版本更新、范围/人群差异、条件差异、证据演进、推荐差异、监管/地域差异和无法解释的不一致；不得用单一 CONFLICT 丢失原因。**
3. **来源之间的版本关系必须显式建模；`SUPERSEDES / AMENDS / SUPPLEMENTS / CORRECTS / RETRACTS / UNKNOWN` 等关系不得仅凭发布时间推断。**
4. **版本更新应尽可能在 Claim / Relationship 粒度判断 Supersession；新版本文件存在不得自动使旧版本全部失效。**
5. **Source Priority Policy 只定义项目中的来源使用或冲突处理规则，不得成为医学真实性绝对排序；Presentation Priority、Evidence Authority、Regulatory Authority 和 Conflict Resolution Priority 必须分离。**
6. **Guideline、RCT、Meta-analysis、Consensus、Drug Label、Regulatory Document、Textbook、Review 等 Source Type 必须保留不同功能语义；研究证据、指南推荐和监管授权不得互相替代。**
7. **多个研究或 Meta-analysis 可以支持疗效/安全性结论，但不得自动形成 Guideline Recommendation、Approved Indication 或 Standard-of-Care 判断；这些语义必须由相应来源直接支持或标记 SYNTHESIS。**
8. **涉及 Indication、Dose、Contraindication、Approval Status、Reimbursement/Regulatory Limitation 等监管属性时必须进行独立 Regulatory Verification；指南推荐和监管状态不得互相覆盖。**
9. **External Medical Verification 必须显式启用；SOURCE_FIDELITY 模式不得因为发现外部更新而静默纠正或替换用户指定来源。**
10. **用户指定 Source 与 External Verification Source 必须逻辑隔离；外部来源产生的修改、提示和综合结论必须保留 EXTERNAL_VERIFICATION provenance，不得回写成原始 SOURCE。**
11. **External Medical Check 来源必须通过 Source Qualification，至少记录 Source Type、Organization、Date/Version、Primary/Secondary、Official/Regulatory Status、Jurisdiction 和可验证标识；资格不足的来源只能作为线索。**
12. **External Medical Check 发现更新、撤回或冲突时默认生成独立 External Verification Finding；除非项目明确要求更新，否则不得自动修改 Source-faithful Presentation。**
13. **任何 External Medical Verification 必须记录 `verified_as_of`、检索范围及使用的 Source Version；外部验证结果不得被视为无时间边界永久有效。**
14. **外部来源选择必须综合 Recency、Authority、Jurisdiction、Population 和 Project Purpose；最新来源不得自动等价于当前项目最适用来源。**
15. **External Medical Verification 应检查来源撤稿、勘误、替代和有效状态；Retracted 来源不得作为有效高风险支持证据，Corrected/Amended 来源必须使用有效版本并保留版本链。**
16. **跨来源形成的综合判断必须保存为 Evidence Synthesis，并对组成结论逐项绑定来源；不得把多来源综合结果伪装成任何单一来源直接支持的 SOURCE Claim。**

状态：`FROZEN v0.1 / Batch 4`


## 3D. Module 05 Rule Implementation Ownership

Module 05 采用“LLM Semantic Verifier + Deterministic Validators + Policy Engine + Human Review”的组合实现，不由单一 Agent 包办。

| Frozen Rule Area | Primary Implementer | Secondary Validator / Gate |
|---|---|---|
| Verification Mode / Source Pool separation | Backend / Project Config / Source Registry | Policy Engine |
| Verifier read-only | Capability Control / RBAC / API Schema | Policy Engine |
| Claim semantic fidelity | Medical Verifier LLM | Semantic QA |
| Title / Primary Message entailment | Medical Verifier LLM | Title Entailment Validator |
| Data semantic binding | Data Binding Validator + Medical Verifier | Numerical QA + Policy Engine |
| Clinical Relationship fidelity | Medical Verifier LLM | Relationship Validator + Human Review for RED |
| Contextual implication fidelity | Contextual Checker + Medical Verifier | Policy Engine |
| Medical Visual semantic fidelity | Medical Visual QA + Medical Verifier | Policy Engine / Human Review |
| Verification status enum / required fields | JSON Schema / Backend Validator | Policy Engine |
| RED verification gate | Policy Engine / State Machine | Human Medical Review |
| Confidence usage restriction | Backend Policy | Policy Engine |

### 实现原则

1. 能确定性执行的规则不交给 LLM；
2. 语义忠实度由独立 Medical Verifier 判断；
3. RED / 冲突 / 模糊项由 Policy Engine 强制进入 Human Review；
4. Verifier 无写权限，只能写 VerificationResult / VerificationIssue；
5. 修订必须由责任模块重新生成或由用户/人工审核者显式修改；
6. 生成上下文与验证上下文逻辑隔离，避免 self-justification。



### Batch 2 Implementation Ownership

| Frozen Rule | Primary Mechanism | Medical Verifier Role | Final Gate |
|---|---|---|---|
| 05-011 Minimum Sufficient Source Span | Source Retriever / Span Ranker | 判断候选 Span 是否足以支持完整对象 | Policy Engine |
| 05-012 Meaning-Critical Slots | Structured Semantic Comparator | 处理自然语言等价与隐含限定 | Policy Engine |
| 05-013 Meaning Preservation | Meaning-Preserving Bundle Validator | 判断压缩是否改变医学边界 | Policy Engine |
| 05-014 Scope Change | Scope Comparator | 判断 Population / Subgroup 等范围变化 | Policy Engine |
| 05-015 Quantifier | Quantifier Lexicon + Parser | 复杂量词语义判断 | Semantic QA |
| 05-016 Modality / Strength | Modality & Strength Lexicon | 判断语义升级或弱化 | Medical Verifier + Policy Engine |
| 05-017 Negation / Polarity | Negation Parser | 处理复杂否定、无证据 vs 证据否定 | Critical Policy Gate |
| 05-018 Condition Logic | Logic Comparator | 判断复杂条件表达是否等价 | Medical Verifier |
| 05-019 Relationship Type / Direction | Relationship Validator | 判断关系类型、方向与 polarity | RED Policy Gate |
| 05-020 Recommendation Unit | Recommendation Object Validator | 综合推荐语义判断 | RED Policy Gate |
| 05-021 Multi-source Synthesis | Provenance Engine / Source Aggregator | 判断是否为来源外组合推理 | Policy Engine |
| 05-022 Conflict / Cherry-pick | Conflict Detector / Source Registry | 判断实质冲突 | Source Priority Policy / Human Review |

#### Batch 2 实现原则

1. Verifier 比较的是 `Source Semantic Frame` 与 `Generated Semantic Frame`，而不是字符串相似度。
2. 已结构化字段优先使用确定性 Comparator；难以结构化的语义差异由 Medical Verifier 处理。
3. `source_ref != null` 不能直接推出 `SUPPORTED`。
4. Verifier 检索时优先寻找 Minimum Sufficient Source Span。
5. 多 SourceRef 对象必须执行 conflict-aware retrieval，不允许只取支持性证据。
6. 修订仍由责任模块完成，Verifier 不直接改医学对象。



### Batch 3 Implementation Ownership

| Frozen Rule | Primary Mechanism | Secondary Validator / Gate |
|---|---|---|
| 05-023 Issue Routing | Issue Routing Table / Orchestrator | Policy Engine |
| 05-024 Immutable Revision | Versioned Object Store / Audit Log | Backend Integrity Check |
| 05-025 Downstream Invalidation | Dependency Graph / Version Resolver | Policy Engine |
| 05-026 Targeted + Regression Reverify | Semantic Diff Engine / Medical Verifier | Regression Rule Set |
| 05-027 Anti-delete Evasion | Triage Integrity Validator / Architect Validator | Policy Engine |
| 05-028 Revision Capability | Capability Control / Revision API | Policy Engine |
| 05-029 Root Cause First | Root Cause Resolver / Dependency Graph | Orchestrator |
| 05-030 Issue State Machine | Issue Workflow State Machine | Policy Engine |
| 05-031 Retry Budget | Orchestrator Retry Counter | Policy Engine |
| 05-032 Recurrent Issue | Issue Fingerprint / QA Analytics | Human Review Escalation |
| 05-033 Human Override Integrity | Human Review Layer / Immutable VerificationResult | Audit Log |
| 05-034 Version-aware Reverification | Verification Store / Source Span Resolver | Policy Engine |
| 05-035 Immutable Approved Versions | Approved Snapshot / Export Manifest | Delivery Gate |
| 05-036 Dependency-aware Gate Re-run | Gate Runner / Dependency Graph | Policy Engine |

#### Batch 3 修复闭环

```text
VerificationIssue
      ↓
Issue Router
      ↓
Root Cause Resolver
      ↓
Responsible Module
      ↓
New Version / Revision Snapshot
      ↓
Invalidate downstream dependents
      ↓
Rebuild affected objects
      ↓
Targeted Re-verification
      ↓
Regression Verification
      ↓
Re-run affected Gates
      ↓
Policy Engine
      ├─ PASS
      ├─ RETURN_FOR_REVISION
      ├─ HUMAN_REVIEW_REQUIRED
      └─ BLOCK
```

#### 关键实现原则

1. Verifier 不能直接修内容；
2. Issue 必须路由到有权限的责任模块；
3. 修订生成新版本，不覆盖旧版本；
4. 上游变更必须使依赖旧版本的下游对象失效；
5. 修复后不仅复查原 Issue，还要做回归验证；
6. 自动修复必须有限重试并可升级人工；
7. Human Override 不得篡改原 VerificationResult；
8. 最终交付只引用不可变版本。



### Batch 4 Implementation Ownership

| Frozen Rule Area | Primary Mechanism | Medical Verifier Role | Final Gate |
|---|---|---|---|
| Source Context / Comparability | Source Context Comparator + Comparability Engine | 判断医学语境是否真正等价 | Policy Engine |
| Conflict Typing | Conflict Classifier | 处理无法确定的语义差异 | Human Review if needed |
| Version Relation | Source Version Registry | 验证版本关系的医学含义 | Policy Engine |
| Claim-level Supersession | Version Diff Engine + Claim Alignment | 判断是否实质替代 | Policy Engine |
| Source Priority | Project Config + SourcePriorityPolicy | 不负责自行建立权威等级 | Policy Engine |
| Source Type Functional Semantics | Source Taxonomy Registry | 验证 Recommendation / Evidence / Regulatory 语义是否错位 | Semantic QA |
| Regulatory Verification | Regulatory Verification Adapter | 判断指南建议与监管状态是否被混用 | RED Policy Gate |
| External Verification Enablement | Project Config / Verification Mode | 仅在显式启用时使用外部来源 | Policy Engine |
| Source Pool Isolation | Source Registry | 分离 USER_SOURCE 与 EXTERNAL_VERIFICATION | Backend / Policy Engine |
| External Source Qualification | Source Qualification Engine | 处理边界来源是否足够支撑医学判断 | Policy Engine |
| Retraction / Correction Status | Source Status Resolver | 处理有效版本语义 | Policy Engine |
| External Finding | External Verification Engine | 输出独立 Finding，不静默改 Source-faithful 内容 | Human Review when RED |
| Evidence Synthesis | Evidence Synthesis Engine + Provenance Engine | 判断综合结论是否超出来源 | Policy Engine |

#### External Verification Pipeline

```text
External Search / Retrieval
        ↓
Source Qualification
        ↓
Source Registry
        ↓
Source Context / Version / Status Check
        ↓
Claim Extraction
        ↓
Cross-source Verification
        ↓
External Verification Finding
        ↓
Evidence Synthesis (if needed)
        ↓
Policy Engine / Human Review
```

#### Batch 4 实现原则

1. “不同”先做 Context / Comparability 分析，再做 Conflict 判定；
2. 新年份来源不能自动覆盖旧来源；
3. Source Type 的功能语义必须保留：Evidence ≠ Recommendation ≠ Regulatory Approval；
4. External Verification 必须显式启用；
5. 用户来源和外部验证来源逻辑隔离；
6. 外部来源先 Qualification，再进入高风险验证；
7. 外部更新默认形成 Finding，而不是直接修改 Source-faithful 内容；
8. 所有外部验证均有时间边界；
9. Cross-source Synthesis 必须保持逐项 provenance。


## 4. Source-faithful 生成路径

```text
Source
  ↓
Extraction
  ↓
Atomic / Canonical Claim Graph
  ↓
Information Triage
  ↓
NarrativePlan / PageSpec
  ↓
Semantic Relationship & Evidence Binding
  ↓
Semantic Page Graph Draft
  ↓
Medical Verification
  ↓
Approved Semantic Page Graph
  ↓
Functional Visual Rendering
```

### 4.1 Synthetic Case 支路

仅当 `synthetic_case=true`：

```text
User Explicit Request
  ↓
Synthetic Case Generator
  ↓
External / Source Validation of key medical facts
  ↓
Label: AI-generated teaching case
  ↓
Separate Synthetic Layer
```

默认 `false`。

---

## 5. Approved Semantic Page Graph

Functional Visual Renderer 与 Visual Design Agent 的唯一页面语义输入。

至少包含：

```text
PAGE_GOAL
PRIMARY_MESSAGE
LOCKED_CLAIMS
SEMANTIC_OBJECTS
SEMANTIC_RELATIONSHIPS
DATA_BINDINGS
VISUAL_BINDINGS
EVIDENCE
SOURCE_REFS
RISK_LEVELS
VISUAL_TYPE
VISUAL_ENCODING_CONTRACT
DESIGN_FREEDOM
```

示例：

```yaml
page_goal: 解释某临床分型与治疗选择
primary_claim: 功能检测后按表型组织治疗策略
locked_claims:
  - C001
  - C004
nodes:
  - N01
  - N02
edges:
  - E001
evidence:
  - claim_id: C004
    recommendation_class: IIa
    evidence_level: B
design_freedom:
  - layout
  - typography
  - whitespace
  - color
```

---

## 6. 产品状态机

```text
UPLOADED
  ↓
EXTRACTED
  ↓
CLAIMS_READY
  ↓
ARCHITECTED
  ↓
VERIFIED
  ↓
COMPLIANCE_CHECKED
  ↓
CONTENT_APPROVED
  ↓
POLICY_GATE
  ↓
DESIGNED
  ↓
QA_PASSED
  ↓
MEDICAL_REVIEWED
  ↓
DELIVERED
```

### 6.1 状态约束

| 当前状态 | 可进入 | 阻断条件 |
|---|---|---|
| UPLOADED | EXTRACTED | 解析失败 |
| EXTRACTED | CLAIMS_READY | Source Pointer 不完整 |
| CLAIMS_READY | ARCHITECTED | Audience / Goal / Duration 缺失 |
| ARCHITECTED | VERIFIED | 无 |
| VERIFIED | COMPLIANCE_CHECKED | 关键 Claim 无来源 |
| COMPLIANCE_CHECKED | CONTENT_APPROVED | 存在 BLOCK 合规项 |
| CONTENT_APPROVED | DESIGNED | 无 |
| DESIGNED | QA_PASSED | Numerical / Semantic QA 失败 |
| QA_PASSED | MEDICAL_REVIEWED | RED 未审核 |
| MEDICAL_REVIEWED | DELIVERED | RED 未通过 |

规则：

> 任一 RED 风险未确认时不得进入 `DELIVERED`。

---

## 7. 任务队列设计

建议每个 Agent 为独立 Task：

- `extract_source`
- `build_claim_table`
- `triage_claims`
- `build_narrative`
- `build_decision_map`
- `build_evidence_map`
- `verify_medical_content`
- `check_compliance`
- `render_deck`
- `run_numerical_qa`
- `run_semantic_qa`
- `build_review_sheet`
- `export_delivery`

每个 Task 保存：

- task_id；
- project_id；
- input_version；
- output_version；
- agent_version；
- model_version；
- prompt_version；
- started_at；
- completed_at；
- status；
- error。

---

## 8. 失败与重试

### 8.1 自动重试
可用于：

- 文档解析失败；
- 模型超时；
- JSON Schema 失败；
- 临时存储错误。

### 8.2 不自动重试
应进入人工处理：

- Claim 与来源冲突；
- RED Edge 无依据；
- 数字冲突；
- 推荐等级冲突；
- 合规 BLOCK；
- Source 无法解析但内容属于高风险。

---

## 9. 数据存储

### PostgreSQL
保存：

- Project；
- Document；
- Claim；
- Edge；
- Review；
- Audit Log；
- Deck Metadata。

### pgvector
用于：

- Source Chunk Retrieval；
- Claim-source semantic matching；
- Duplicate claim detection。

### Object Storage
保存：

- 原始文件；
- 页面截图；
- 中间渲染；
- 最终 PPTX / PDF / PNG。

---

## 10. Audit Log

每次生成记录：

- input_file_hash；
- model_version；
- prompt_version；
- agent_version；
- claim_graph_version；
- user_edit；
- medical_review；
- compliance_result；
- export_version。

要求：

> 任一最终页面都可回到“使用了哪些来源、经过哪些 Agent、哪些地方由用户/医生确认”。

---

## 11. MVP 部署建议

第一版可采用：

```text
Web Frontend
   ↓
FastAPI
   ↓
PostgreSQL + pgvector
   ↓
Redis/Celery
   ↓
Object Storage
   ↓
Model Adapter Layer
```

MVP 首期优先实现单租户或简单用户隔离，不在第一阶段引入复杂机构权限与知识库。


## Module 06｜Prompt-driven Medical Visual Generation

### Module 06 第一批冻结规则｜Visual Generation Contract & Prompt Compiler

以下 14 条已正式冻结：

1. **页面视觉生成不得直接从原始文档或自由文本 Prompt 开始，必须以通过上游审核的 Approved Semantic Page Graph 为输入，并先生成结构化 Visual Generation Contract。**
2. **Visual Generation Contract 必须明确区分 `HARD_LOCK / SEMANTIC_LOCK / BOUNDED_CREATIVE / FREE_CREATIVE` 四级控制范围；模型不得将未授权字段从锁定区转入创意区。**
3. **Claim、NumericFact、Threshold、Unit、Drug Name、Population、Condition、Exclusion、Recommendation Class、Evidence Level、Clinical Relationship、Logic Operator 和 Source Binding 等关键医学事实默认属于 HARD_LOCK 或 SEMANTIC_LOCK，不由视觉模型重新推理或生成。**
4. **每页必须存在唯一 Page Goal 和 Primary Message；视觉模型可以优化其呈现方式，但不得改变页面目标或生成语义强于已批准 Primary Message 的新结论。**
5. **所有必须出现的医学对象必须通过 Mandatory Content Object Register 显式声明；视觉模型不得静默删除、合并或新增具有医学语义的对象。**
6. **需要逐字准确的药名、数字、单位、阈值、统计值、推荐等级、证据等级和引用必须进入 Exact Text Register；高风险页面优先通过 Controlled Composition 实现，不得仅依赖图像模型文字生成能力。**
7. **Clinical Relationship、Condition Logic、Grouping、Hierarchy、Legend、Color Semantic 和其他会产生医学含义的视觉关系必须作为 Visual Semantic Contract 输入，视觉模型只能表现已批准关系，不能新增医学推断。**
8. **Functional Visual Type 由 Visual Strategy Selector 基于 Page Goal、Information Structure 和 Approved Semantic Graph 选择；视觉模型不得为了美观擅自把功能图降级为通用卡片、列表或其他改变信息关系的形式。**
9. **Layout 应通过 Layout Freedom Envelope 规定必须满足的区域、阅读流、层级和限制，同时保留足够构图自由；系统不应以固定模板或逐元素坐标作为主要视觉生成方式。**
10. **Visual Hierarchy 必须显式区分 Presentation Priority 与 Clinical/Evidence/Risk Priority；模型可以优化视觉强调，但不得通过大小、位置、颜色或留白创造未经授权的医学优先级。**
11. **Medical Visual Asset 必须声明允许的来源类型、医学语义角色、是否允许 AI 生成及是否需要 Medical Visual QA；医学结构锁定与艺术表现自由必须分离。**
12. **每个页面必须显式声明 Generation Mode，至少支持 `FULL_IMAGE / CONTROLLED_COMPOSITION`；高风险精确文本和数据密集页应优先采用受控合成，而不是完全自由整页生成。**
13. **Visual Generation Contract 必须包含 Prohibited Transformations，明确禁止新增医学对象、修改数值、改变关系方向、改变逻辑、删除限定、伪造引用或升级推荐强度等行为。**
14. **Visual Generation Contract 同时是 Post-generation Verification Contract；最终图片必须重新对照同一 Contract 检查 Mandatory Object Coverage、Exact Text、Numeric Fidelity、Relationship Fidelity 和 Visual Semantic Fidelity，通过后方可进入 Presentation Packaging。**

状态：`FROZEN v0.1 / Batch 1`


### Module 06 Batch 1 Implementation Ownership

| Frozen Rule Area | Primary Implementer | Secondary Validator / Gate |
|---|---|---|
| Approved Semantic Page Graph as sole upstream input | Orchestrator + Contract Builder | Policy Engine |
| Four-level lock model | Visual Generation Contract Schema | Policy Engine |
| Medical truth lock | Contract Builder from approved objects | Medical Verifier / Semantic QA |
| Page Goal / Primary Message lock | Medical Information Architect output adapter | Title/Primary Message Validator |
| Mandatory Content Objects | Mandatory Object Register Builder | Post-generation Visual Verifier |
| Exact Text Register | Exact Content Registry + Controlled Compositor | Text/Numeric QA |
| Visual Semantic Contract | Semantic Binding Exporter | Visual Semantic QA |
| Functional Visual Type | Visual Strategy Selector | Policy Engine |
| Layout Freedom Envelope | Visual Layout Spec Builder | Visual QA |
| Priority semantics | Visual Hierarchy Contract Builder | Semantic QA |
| Medical Visual Asset rules | Medical Asset Policy Resolver | Medical Visual QA |
| Generation Mode | Generation Mode Selector | Policy Engine |
| Prohibited Transformations | Contract Rule Compiler | Policy Engine |
| Contract reuse for QA | Generated Visual Verifier | Delivery Gate |

#### Module 06 v0.1 关键实现原则

1. `Visual Generation Contract` 是产品资产，具体 Prompt 只是面向某个图像模型的编译结果。
2. Prompt Compiler 不拥有医学推理权限，只把已批准内容与视觉规则转换成模型可理解的指令。
3. 锁定字段由结构化数据注入，不能由 Visual Creative Agent 重写。
4. Visual Creative Agent 仅在 `BOUNDED_CREATIVE / FREE_CREATIVE` 范围内工作。
5. `FULL_IMAGE` 与 `CONTROLLED_COMPOSITION` 是两条正式生成路径。
6. Exact Text / NumericFact 等高风险内容优先由确定性 Compositor 写入最终图像。
7. 生成后的视觉必须使用同一个 Contract 进行反向验收。

#### Module 06 生成链路

```text
Approved Semantic Page Graph
        ↓
Visual Strategy Selector
        ↓
Visual Generation Contract Builder
        ↓
Model-specific Prompt Compiler
        ↓
Image Generation API
        ↓
[optional] Exact Content Compositor
        ↓
Generated Visual Verifier
        ↓
Visual Revision Controller
        ↓
Approved Slide Image
        ↓
Presentation Packager
```


### Module 06 Batch 2 架构草案｜Visual Strategy Selector v0.2（未冻结）

> 本节为设计草案，不改变 Module 06 Batch 1 已冻结状态；Batch 2 规则需用户后续明确确认后才能进入 FROZEN。

## A. Module 06 架构调整

原链路：

```text
Approved Semantic Page Graph
        ↓
Visual Strategy Selector
        ↓
Visual Generation Contract
        ↓
Prompt Compiler
        ↓
Image Generation API
```

调整为：

```text
Approved Semantic Page Graph
        ↓
[06A] Visual Intent Classifier
        ↓
[06B] Standard Override Resolver
        ↓
[06C] Information Structure & Data Shape Analyzer
        ↓
[06D] Hard Constraint / Exclusion Engine
        ↓
[06E] Visual Candidate Generator
        ↓
[06F] Visual Strategy Scoring Engine
        ↓
[06G] Generation Strategy Router
        ↓
VisualStrategyDecision
        ↓
Visual Generation Contract Builder
        ↓
        ├─ Prompt-driven Image
        ├─ Deterministic Chart
        ├─ Deterministic Diagram
        └─ Hybrid Composition
        ↓
Generated Slide Image
        ↓
Post-generation Verification
```

### 调整后的职责边界

- **Visual Intent Classifier**：判定用户需要完成的认知任务。
- **Standard Override Resolver**：识别 CONSORT / PRISMA / STARD 等标准化视觉场景。
- **Information Structure Analyzer**：识别数据形态、关系结构、时间结构、逻辑结构。
- **Hard Constraint Engine**：先排除医学/统计上不适用或可能误导的视觉类型。
- **Candidate Generator**：从 Taxonomy Registry 中生成可用候选集。
- **Scoring Engine**：只对通过 Hard Gate 的候选评分。
- **Generation Strategy Router**：独立决定该视觉由 Image Model、确定性 Renderer 或 Hybrid 路径实现。
- **Visual Generation Contract Builder**：把最终 Visual Strategy 再编译成 Batch 1 已冻结的 Contract。

---

## B. Medical Visual Taxonomy Registry v0.1

### Family A｜Study & Evidence Flow

- CONSORT_PARTICIPANT_FLOW
- PRISMA_FLOW
- STARD_FLOW
- TRIAL_SCHEMA
- STUDY_DESIGN_SCHEMA
- EVIDENCE_ACQUISITION_FLOW

### Family B｜Quantitative Clinical Data

- BAR_CHART
- LINE_CHART
- DOT_ESTIMATE_PLOT
- BOX_PLOT
- SCATTERPLOT
- KAPLAN_MEIER
- FOREST_PLOT
- FUNNEL_PLOT
- ROC_CURVE
- CALIBRATION_PLOT
- WATERFALL_PLOT
- SWIMMER_PLOT
- SPIDER_PLOT
- TABLE
- MATRIX

### Family C｜Effect & Evidence Synthesis

- FOREST_PLOT
- SUBGROUP_FOREST
- NON_POOLED_FOREST
- EVIDENCE_MATRIX
- TRIAL_EVIDENCE_MATRIX
- NETWORK_DIAGRAM
- CONTRIBUTION_MATRIX
- RANKOGRAM
- RECOMMENDATION_MATRIX
- EVIDENCE_MAP

### Family D｜Clinical Decision & Action

- DIAGNOSTIC_ALGORITHM
- CLINICAL_DECISION_MAP
- TREATMENT_ALGORITHM
- TREATMENT_PATHWAY
- CARE_PATHWAY
- RISK_STRATIFICATION_MAP
- PATIENT_SELECTION_MAP
- ESCALATION_DEESCALATION_PATHWAY
- MONITORING_PATHWAY
- MANAGEMENT_CYCLE
- REFERRAL_PATHWAY

### Family E｜Mechanism & Medical Concept

- MECHANISM_MAP
- PATHOPHYSIOLOGY_MAP
- DRUG_MECHANISM_DIAGRAM
- MECHANISM_TO_OUTCOME_MAP
- ANATOMY_ILLUSTRATION
- PROCEDURE_ILLUSTRATION
- IMAGING_ORIENTATION_DIAGRAM
- DISEASE_MODEL

### Family F｜Time, Course & Patient Experience

- DISEASE_TIMELINE
- TREATMENT_TIMELINE
- PATIENT_JOURNEY
- PATIENT_TIMELINE
- CLINICAL_COURSE
- SWIMMER_PLOT
- LONGITUDINAL_OUTCOME_PLOT
- MANAGEMENT_TIMELINE

### Family G｜Diagnostic & Prediction Performance

- ROC_CURVE
- CALIBRATION_PLOT
- STARD_FLOW
- THRESHOLD_DECISION_MAP
- DIAGNOSTIC_PERFORMANCE_MATRIX
- DECISION_CURVE

`DECISION_CURVE` 仅在底层存在合法的原始分析结果时可用，不允许 Visual Strategy Selector 自行推导。

### Family H｜Summary & Editorial Visual

- CENTRAL_ILLUSTRATION
- VISUAL_ABSTRACT
- GRAPHICAL_ABSTRACT
- EDITORIAL_SUMMARY
- EVIDENCE_TO_PRACTICE_SUMMARY
- TAKE_HOME_MAP

---

## C. Visual Intent Taxonomy

一级 `visual_intent` 至少支持：

### 通用信息任务

- COMPARE
- CHANGE_OVER_TIME
- DISTRIBUTION
- ASSOCIATION
- EFFECT_ESTIMATION
- SURVIVAL
- PROCESS
- SEQUENCE
- MECHANISM
- EVIDENCE_SYNTHESIS
- SUMMARY
- EXACT_LOOKUP

### 医学专用任务

- DIAGNOSIS
- PATIENT_SELECTION
- RISK_STRATIFICATION
- TREATMENT_SELECTION
- TREATMENT_SEQUENCING
- TREATMENT_ESCALATION
- MONITORING
- REFERRAL
- STUDY_FLOW
- STUDY_DESIGN
- DIAGNOSTIC_PERFORMANCE
- PREDICTION_PERFORMANCE

一个页面允许：
- 1 个 `primary_visual_intent`
- 0..N 个 `secondary_visual_intents`

主视觉由 primary intent 决定，secondary intent 只能形成辅助视觉，不能反客为主。

---

## D. Information Structure Profile

Selector 在选图前必须形成 `InformationStructureProfile`：

```yaml
quantitative: true|false
categorical: true|false

granularity:
  aggregate | individual | mixed

time_dimension:
  none | discrete | continuous | time_to_event

uncertainty:
  none | SD | SE | CI | credible_interval | mixed

comparison_structure:
  none | within_study | cross_study | multi_arm | paired

comparability:
  comparable | partially_comparable | non_comparable | unknown

relationship_structure:
  none | sequence | branching | hierarchy | network | cycle |
  associative | predictive | causal | conditional

logic:
  NONE | AND | OR | NOT | EXCEPT | MIXED

precision_requirement:
  low | medium | high | exact

study_context:
  none | RCT | systematic_review | diagnostic_accuracy |
  observational | meta_analysis | network_meta_analysis

standard_reporting_context:
  none | CONSORT | PRISMA | STARD | other

medical_risk:
  GREEN | YELLOW | RED
```

---

# E. 可执行 IF / THEN 决策树 v0.1

决策树采用**严格优先级**。前序 Hard Rule 命中后，后序规则不能用审美评分覆盖。

## Stage 0｜Standard Override

```text
IF standard_reporting_context == CONSORT
AND visual_intent == STUDY_FLOW
THEN
    primary_candidate = CONSORT_PARTICIPANT_FLOW
    standard_priority = HIGH
    exclude = generic_process_flow

IF standard_reporting_context == PRISMA
AND visual_intent == STUDY_FLOW
THEN
    primary_candidate = PRISMA_FLOW
    standard_priority = HIGH

IF standard_reporting_context == STARD
AND visual_intent == STUDY_FLOW
THEN
    primary_candidate = STARD_FLOW
    standard_priority = HIGH
```

Standard Override 默认是“强优先”，是否升级为项目级 Hard Requirement 由 Project Policy 决定。

---

## Stage 1｜Study / Evidence Specific Rules

```text
IF study_context == meta_analysis
AND contains_effect_estimate == true
AND uncertainty in [CI, credible_interval]
THEN candidate += FOREST_PLOT

IF study_context == meta_analysis
AND pooling_allowed == false
THEN candidate += NON_POOLED_FOREST
AND prohibit = pooled_summary_visual

IF study_context == network_meta_analysis
THEN
    candidate += NETWORK_DIAGRAM
    IF intent == EFFECT_ESTIMATION:
        candidate += FOREST_PLOT
    IF valid_ranking_data == true:
        candidate += RANKOGRAM

IF visual_intent == STUDY_DESIGN
AND has_trial_arms == true
THEN candidate += TRIAL_SCHEMA
```

---

## Stage 2｜Time-related Rules

```text
IF time_dimension == time_to_event
THEN
    candidate += KAPLAN_MEIER
    prohibit += ordinary_line_chart_as_survival_substitute

IF visual_intent == CHANGE_OVER_TIME
AND granularity == aggregate
AND time_dimension in [discrete, continuous]
THEN candidate += LINE_CHART

IF visual_intent == CHANGE_OVER_TIME
AND granularity == individual
AND oncology_best_change_over_time == true
THEN candidate += SPIDER_PLOT

IF visual_intent == SEQUENCE
AND single_patient_events == true
THEN candidate += PATIENT_TIMELINE

IF multiple_individual_durations == true
THEN candidate += SWIMMER_PLOT

IF visual_intent == SEQUENCE
AND semantic_domain == disease_evolution
THEN candidate += DISEASE_TIMELINE

IF visual_intent == SEQUENCE
AND semantic_domain == care_experience
THEN candidate += PATIENT_JOURNEY
```

---

## Stage 3｜Quantitative Data Rules

```text
IF visual_intent == COMPARE
AND value_type in [count, frequency, category_percentage]
AND uncertainty == none
THEN candidate += BAR_CHART

IF visual_intent in [COMPARE, EFFECT_ESTIMATION]
AND value_type == continuous_summary
AND uncertainty != none
THEN
    candidate += DOT_ESTIMATE_PLOT
    prohibit += bar_chart_for_summary_estimate

IF visual_intent == DISTRIBUTION
THEN candidate += BOX_PLOT

IF visual_intent == ASSOCIATION
AND x_type == continuous
AND y_type == continuous
THEN candidate += SCATTERPLOT

IF visual_intent == EXACT_LOOKUP
OR precision_requirement == exact
AND dimensions >= 2
THEN candidate += TABLE, MATRIX
```

---

## Stage 4｜Diagnostic / Prediction Rules

```text
IF visual_intent == DIAGNOSTIC_PERFORMANCE
AND threshold_sweep_data_available == true
THEN candidate += ROC_CURVE

IF visual_intent == PREDICTION_PERFORMANCE
AND predicted_vs_observed_available == true
THEN candidate += CALIBRATION_PLOT

IF visual_intent == DIAGNOSIS
AND relationship_structure == branching
THEN candidate += DIAGNOSTIC_ALGORITHM

IF visual_intent == DIAGNOSIS
AND threshold_based_decision == true
THEN candidate += THRESHOLD_DECISION_MAP
```

---

## Stage 5｜Clinical Decision Rules

```text
IF visual_intent in [TREATMENT_SELECTION, PATIENT_SELECTION]
AND relationship_structure == branching
THEN candidate += CLINICAL_DECISION_MAP

IF visual_intent == TREATMENT_SELECTION
AND logic in [AND, OR, NOT, EXCEPT, MIXED]
THEN
    candidate += CLINICAL_DECISION_MAP
    prohibit += generic_cards_without_logic

IF visual_intent == TREATMENT_SEQUENCING
AND relationship_structure == sequence
THEN candidate += TREATMENT_PATHWAY

IF visual_intent == TREATMENT_ESCALATION
THEN candidate += ESCALATION_DEESCALATION_PATHWAY

IF visual_intent == MONITORING
AND relationship_structure == cycle
THEN candidate += MANAGEMENT_CYCLE

IF visual_intent == MONITORING
AND relationship_structure == branching
THEN candidate += MONITORING_PATHWAY

IF visual_intent == RISK_STRATIFICATION
THEN candidate += RISK_STRATIFICATION_MAP

IF visual_intent == REFERRAL
THEN candidate += REFERRAL_PATHWAY, CARE_PATHWAY
```

---

## Stage 6｜Mechanism / Medical Concept Rules

```text
IF visual_intent == MECHANISM
AND relationship_structure in [causal, associative, network]
AND semantic_domain in [molecular, cellular, pathophysiology]
THEN candidate += MECHANISM_MAP

IF mechanism_has_target_intervention_effect_chain == true
THEN candidate += DRUG_MECHANISM_DIAGRAM

IF mechanism_extends_to_clinical_outcome == true
THEN candidate += MECHANISM_TO_OUTCOME_MAP

IF primary_information == anatomy
THEN candidate += ANATOMY_ILLUSTRATION

IF primary_information == procedure
THEN candidate += PROCEDURE_ILLUSTRATION
```

---

## Stage 7｜Evidence / Comparison Structures

```text
IF visual_intent == EVIDENCE_SYNTHESIS
AND multiple_trials == true
AND multiple_endpoints == true
THEN candidate += TRIAL_EVIDENCE_MATRIX

IF visual_intent == EVIDENCE_SYNTHESIS
AND primary_structure == claim_to_source_relationship
THEN candidate += EVIDENCE_MAP

IF multiple_therapies == true
AND multiple_precise_attributes == true
THEN candidate += COMPARISON_MATRIX

IF recommendation_class_and_evidence_level_are_primary == true
THEN candidate += RECOMMENDATION_MATRIX
```

---

## Stage 8｜Summary / Editorial Rules

```text
IF visual_intent == SUMMARY
AND content_has_single_coherent_conceptual_structure == true
THEN candidate += CENTRAL_ILLUSTRATION

IF page_goal == summarize_study_method_and_main_findings
THEN candidate += VISUAL_ABSTRACT

IF page_goal == summarize_entire_document
THEN candidate += GRAPHICAL_ABSTRACT

IF page_goal == evidence_to_clinical_meaning
THEN candidate += EVIDENCE_TO_PRACTICE_SUMMARY

IF page_goal == final_take_home
AND approved_messages_count between 3 and 5
THEN candidate += TAKE_HOME_MAP
```

---

## Stage 9｜No-forced-visual Fallback

```text
IF valid_candidate_set == empty
THEN
    IF precision_requirement == exact:
        candidate += TABLE_OR_MATRIX
    ELSE:
        candidate += EDITORIAL_SUMMARY

IF no_visual_adds_information_value == true
THEN
    allow = TEXT_FORWARD_EDITORIAL_PAGE
```

原则：
**“没有合适图”是合法结果。不得为了视觉丰富强行制造流程、关系或卡片。**

---

# F. Hard Exclusion Rules

Candidate Scoring 之前必须先执行：

```text
IF time_dimension == time_to_event
THEN exclude ordinary LINE as substitute for KM

IF continuous_summary_with_uncertainty == true
THEN exclude BAR as primary estimate display

IF comparability in [non_comparable, unknown]
AND visual_implies_direct_superiority == true
THEN exclude candidate

IF relationship_logic in [AND, OR, NOT, EXCEPT]
AND candidate_cannot_encode_logic == true
THEN exclude candidate

IF medical_relationship_required == true
AND candidate_would_require_new_unapproved_relationship == true
THEN exclude candidate

IF precision_requirement == exact
AND candidate_obscures_exact_values == true
THEN penalize heavily or exclude

IF source_data_insufficient_for_visual == true
THEN exclude candidate

IF candidate_requires_derived_statistic_not_in_approved_data == true
THEN exclude candidate
```

---

# G. Visual Strategy Scoring Schema v0.1

只有通过 Hard Gate 的候选才能进入评分。

## Base score

```text
VisualStrategyScore =
  0.30 × SemanticFit
+ 0.20 × MedicalConventionFit
+ 0.15 × DataFidelity
+ 0.15 × Auditability
+ 0.10 × AudienceFit
+ 0.10 × VisualCommunicationFit
- Penalties
```

每项归一到 `0..1`。

### 1. SemanticFit｜30%

检查候选是否准确承载：
- visual intent；
- relationship structure；
- condition logic；
- time structure；
- comparison structure。

### 2. MedicalConventionFit｜20%

检查该视觉是否符合：
- 标准化研究报告习惯；
- 医学/科研领域成熟图形语法；
- 对应 clinical use case 的惯例。

### 3. DataFidelity｜15%

检查：
- 是否保持原始 metric / unit；
- 是否可表达 uncertainty；
- 是否保留 precision；
- 是否避免视觉夸大。

### 4. Auditability｜15%

检查：
- 图中对象是否易绑定 Claim/Data/Relationship ID；
- 是否易做 Post-generation QA；
- 是否能明确定位数据、关系和来源。

### 5. AudienceFit｜10%

检查：
- 专家/普通听众所需信息密度；
- 阅读成本；
- 认知负担。

### 6. VisualCommunicationFit｜10%

检查：
- 模式识别效率；
- 一页内的视觉清晰度；
- 信息压缩收益；
- 是否优于表格/纯文字。

---

# H. Penalty Schema

Penalty 只在通过 Hard Gate 的候选间进行细分。

建议：

```text
UnsupportedRelationshipRisk: 0.00 .. 0.30
ComparabilityRisk:           0.00 .. 0.25
NumericPrecisionRisk:        0.00 .. 0.20
TextDensityRisk:             0.00 .. 0.15
SemanticOverloadRisk:        0.00 .. 0.20
VisualMisinterpretationRisk: 0.00 .. 0.25
```

如果某风险已经达到 Hard Exclusion 条件，则不再扣分，而是直接 `INVALID_CANDIDATE`。

---

# I. Selection Thresholds（草案，不冻结数值）

为了 MVP 可执行，建议先采用可配置阈值：

```text
score >= HIGH_THRESHOLD:
    SELECTABLE

score between REVIEW_THRESHOLD and HIGH_THRESHOLD:
    SELECTABLE_WITH_REVIEW

score < REVIEW_THRESHOLD:
    REJECT
```

具体阈值暂不冻结，在测试集上标定。

如果 Top1 与 Top2 分差很小：

```text
IF top1_score - top2_score < ambiguity_margin
THEN selector_status = AMBIGUOUS
AND expose top_2_candidates
```

不要为了系统“看起来聪明”强迫唯一答案。

---

# J. Generation Strategy Router

Visual Type 选择与“怎么生成”彻底分离。

## Strategy 1｜DETERMINISTIC_CHART

优先用于：
- FOREST_PLOT
- KM / SURVIVAL
- ROC
- CALIBRATION
- BOX
- SCATTER
- DOT ESTIMATE
- 精确 BAR / LINE
- WATERFALL / SWIMMER / SPIDER
- FUNNEL

特点：
- 数据几何必须由确定性代码生成；
- Image Model 不得自由重画数据关系。

## Strategy 2｜DETERMINISTIC_DIAGRAM

优先用于：
- CONSORT
- PRISMA
- STARD
- 高风险 Clinical Decision Map
- 带 AND/OR/NOT/EXCEPT 的路径
- 高风险 Treatment Algorithm

特点：
- Node / Edge / Logic 由 Semantic Graph 编译；
- 可允许后续 AI 做非语义视觉包装。

## Strategy 3｜PROMPT_DRIVEN_IMAGE

适用于：
- CENTRAL_ILLUSTRATION
- EDITORIAL_SUMMARY
- 低精度、低数字密度的概念型视觉
- 已锁定医学结构的视觉叙事

仅当：
- 不承担高风险精确数据几何；
- Exact Text 风险可控；
- Medical Visual Asset Policy 允许。

## Strategy 4｜HYBRID_COMPOSITION

推荐作为医学PPT主力路径：

```text
Deterministic Chart / Diagram
        +
Prompt-driven overall art direction
        +
Exact Content Compositor
        ↓
Flatten to final slide image
```

适用于：
- 医学大会数据页；
- Trial结果页；
- 高风险决策页；
- Evidence + Editorial composition 混合页。

---

# K. VisualStrategyDecision Schema

Selector 必须输出完整决策对象，而不是单一图名。

```yaml
visual_strategy_decision_id: VSD001
page_id: S12

primary_visual_intent:
  TREATMENT_SELECTION

secondary_visual_intents:
  - EVIDENCE_SYNTHESIS

information_structure_profile_id:
  ISP001

standard_override:
  applied: false

candidate_scores:
  - visual_type: CLINICAL_DECISION_MAP
    hard_gate: PASS
    semantic_fit: 0.98
    medical_convention_fit: 0.93
    data_fidelity: 0.92
    auditability: 0.97
    audience_fit: 0.90
    visual_communication_fit: 0.95
    penalty: 0.03
    total_score: 0.92

  - visual_type: TREATMENT_PATHWAY
    hard_gate: PASS
    total_score: 0.74

  - visual_type: GENERIC_CARDS
    hard_gate: FAIL
    exclusion_reason:
      - cannot_preserve_AND_logic

selected_primary_visual:
  CLINICAL_DECISION_MAP

selected_secondary_visual:
  EVIDENCE_CALLOUT

generation_strategy:
  HYBRID_COMPOSITION

generation_mode:
  CONTROLLED_COMPOSITION

selector_status:
  SELECTED

selection_rationale:
  "页面核心任务为条件性治疗选择，底层存在 AND 逻辑与 RED Clinical Relationships，需保留决策分支并使用确定性关系结构。"

prohibited_visual_types:
  - GENERIC_CARDS
  - DECORATIVE_TIMELINE

risk_level:
  RED

selector_version:
  0.1
```

---

# L. Selector 决策伪代码

```python
def select_visual_strategy(page_graph, project_policy):
    intent = classify_visual_intent(page_graph)
    profile = build_information_structure_profile(page_graph)

    standard = resolve_standard_override(profile, project_policy)

    candidates = set()

    if standard:
        candidates.add(standard.visual_type)

    candidates |= apply_study_rules(profile)
    candidates |= apply_time_rules(profile)
    candidates |= apply_quant_rules(profile)
    candidates |= apply_diagnostic_rules(profile)
    candidates |= apply_clinical_decision_rules(profile)
    candidates |= apply_mechanism_rules(profile)
    candidates |= apply_evidence_rules(profile)
    candidates |= apply_summary_rules(profile)

    if not candidates:
        candidates |= fallback_candidates(profile)

    valid_candidates = []
    rejected_candidates = []

    for candidate in candidates:
        gate = hard_constraint_check(candidate, profile, page_graph)
        if gate.pass:
            valid_candidates.append(candidate)
        else:
            rejected_candidates.append((candidate, gate.reasons))

    scores = [
        score_visual_candidate(candidate, intent, profile, page_graph)
        for candidate in valid_candidates
    ]

    ranked = rank(scores)

    selection = resolve_ambiguity(ranked)

    generation_strategy = route_generation_strategy(
        selection,
        profile,
        page_graph.risk_level
    )

    return VisualStrategyDecision(
        intent=intent,
        profile=profile,
        ranked_candidates=ranked,
        rejected_candidates=rejected_candidates,
        selected_visual=selection,
        generation_strategy=generation_strategy
    )
```

---

## M. 决策原则

Visual Strategy Selector 自身没有权限：

- 创建新 Claim；
- 创建 Clinical Relationship；
- 推导缺失统计值；
- 宣布研究可比；
- 改变 Recommendation Strength；
- 因为“视觉需要”改变 Page Goal。

它只允许：

1. 分类；
2. 生成候选；
3. 排除不合法视觉；
4. 排序合法候选；
5. 选择 Generation Strategy；
6. 输出解释。

状态：`DRAFT v0.2 / NOT_FROZEN`


---

## N. Batch 2 反向审查重构｜Constitution vs Policy vs Calibration

### N1. 三层治理结构

```text
LAYER 1
FROZEN SELECTOR CONSTITUTION
───────────────────────────
长期稳定 Hard Rules
医学 / 统计 / 逻辑 / 审计边界
        ↓
LAYER 2
VERSIONED VISUAL POLICY REGISTRY
────────────────────────────────
MedicalVisualTaxonomyRegistry
VisualMappingPolicyRegistry
StandardVisualPolicyRegistry
GenerationStrategyPolicyRegistry
        ↓
LAYER 3
CALIBRATION CONFIG
──────────────────
Scoring weights
Penalty weights
Selection thresholds
Ambiguity margin
Audience / Project adjustments
```

### N2. Batch 2｜13 条 Hard Rules — FROZEN v0.1

以下内容以 PRD 与 Manifest 中已冻结版本为准；此处同步消除旧的“12条候选”残留。

### Module 06 Batch 2｜Visual Strategy Selector v0.1 — FORMALLY FROZEN

以下 13 条 Hard Rules 已正式冻结：

1. **Decision Basis Rule**  
   Visual Strategy 必须基于 `Page Goal + Visual Intent + Information Structure + Approved Semantic Relationships + Precision Requirement` 选择，不得仅依据对象数量、文字长度、页面空间或审美偏好决定视觉类型。

2. **Hard Gate Before Scoring Rule**  
   医学、统计、逻辑、来源、Comparability 或其他语义约束不满足的 Visual Candidate 必须直接标记为 `INVALID_CANDIDATE`；Scoring 不得通过高审美分、高沟通分或其他软指标重新激活 Hard-Fail Candidate。

3. **Standard-aware Rule**  
   当页面任务属于 CONSORT、PRISMA、STARD 等已有标准化医学报告视觉覆盖范围时，Selector 必须识别对应 Standard Visual 并纳入标准候选；若最终不用标准视觉，必须记录明确的任务差异或选择理由。冻结的是 `standard-aware`，而不是 `standard-always-wins`。

4. **Data Shape Compatibility Rule**  
   统计视觉必须兼容底层 Data Shape，包括变量类型、个体/聚合粒度、时间结构、不确定性、比较结构和精度需求；不得为了视觉效果改变、弱化或掩盖统计含义。

5. **Temporal Structure Separation Rule**  
   `Time Series / Time-to-event / Individual Longitudinal Course / Event Sequence / Duration` 必须作为不同 Information Structure 管理，不得作为普通“时间数据”相互替代。

6. **Clinical Logic Preservation Rule**  
   当底层 Semantic Graph 含 `AND / OR / NOT / EXCEPT`、条件分支、排除、禁忌、方向或其他 Meaning-Critical Clinical Logic 时，所选 Visual Type 必须能够显式保留该逻辑；不能表达该逻辑的视觉候选必须排除。

7. **Comparability-before-Comparison Rule**  
   任何跨研究、跨人群、跨 Endpoint 或跨时间的直接视觉比较必须先通过 Comparability Gate；`non_comparable / unknown` 数据不得通过长度、面积、位置、排名、颜色强弱或并列布局暗示直接 superiority。

8. **No New Medical Semantics Rule**  
   Visual Strategy Selector 只允许分类 Information Structure、生成候选、排除不合法候选、排序合法候选及选择 Generation Strategy；不得为了适配某个 Visual Type 创建新的 Claim、Clinical Relationship、比较关系、统计量或缺失数据。

9. **Precision-preserving Representation Rule**  
   Visual Strategy 不得为了图形化或视觉冲击牺牲页面要求的精确查阅能力；当任务核心是精确多维查阅、属性对应、完整比较或逐项核验时，任何无法保留必要精度和对应关系的候选必须降级或排除；Table / Matrix 必须作为合法一级候选，而非失败兜底。

10. **No Forced Visual Rule**  
    系统必须允许 `NO_VALID_VISUAL` 或 Text-forward Editorial Page 作为合法 Selector 结果；不得为了提高“每页有图率”强制制造流程、层级、比较或医学关系。

11. **Visual Strategy ≠ Generation Strategy Rule**  
    “医学信息最适合用什么视觉表达”与“该视觉应通过什么技术生成”必须分别决策；Image Model 或其他生成工具的能力限制不得迫使系统选择医学表达更差的 Visual Type，应切换 Generation Strategy 而不是牺牲 Visual Strategy。

12. **Explainability & Ambiguity Rule**  
    Visual Strategy Selector 必须保存候选集、Hard Exclusion 理由、最终选择理由和 Generation Strategy；当多个合法候选无法可靠区分时，必须允许 `AMBIGUOUS / NEEDS_HUMAN_REVIEW`，不得为了输出唯一答案强制选择。

13. **Visual Grammar Licensing Rule**  
    任何 Visual Type 所固有的空间、形状、方向、顺序、层级、循环、收敛、分支、面积、颜色梯度或其他视觉语法，只能在 Approved Semantic Page Graph 明确支持对应语义时使用；若 Visual Type 本身会诱导目标受众推断出未经批准的医学关系、比较、顺序、等级、因果或程度，则该候选必须标记为 `INVALID_CANDIDATE`。

状态：`FROZEN v0.1 / Batch 2`

### N3. Versioned Policy Registry

#### VisualMappingPolicyRegistry

示例：

```yaml
policy_id: VP-QUANT-002
policy_version: 0.1

when:
  visual_intent:
    - COMPARE
    - EFFECT_ESTIMATION
  value_type:
    - continuous_summary
  uncertainty:
    - CI
    - SE

recommend:
  - DOT_ESTIMATE_PLOT
  - FOREST_LIKE_PLOT

discourage:
  - BAR_CHART

strength:
  strong

basis:
  - medical_visual_convention
  - statistical_semantics
```

注意：
- Mapping 是版本化策略，不是 Frozen Constitution；
- 同一 Information Structure 可以有多个合法候选；
- Policy 可根据 benchmark、期刊规范、医学领域或产品版本更新。

#### StandardVisualPolicyRegistry

```yaml
policy_id: SVP-RCT-FLOW-001
standard: CONSORT
applicable_when:
  study_context: RCT
  visual_intent: STUDY_FLOW

candidate:
  CONSORT_PARTICIPANT_FLOW

priority:
  STRONGLY_PREFERRED

project_overrides:
  formal_reporting: MANDATORY
  conference_summary: PREFERRED
```

`priority` 可配置：
- MANDATORY
- STRONGLY_PREFERRED
- PREFERRED

#### GenerationStrategyPolicyRegistry

```yaml
visual_type: FOREST_PLOT

allowed:
  - DETERMINISTIC_CHART
  - HYBRID_COMPOSITION

prohibited_capabilities:
  - free_image_model_reconstruction_of_data_geometry

reason:
  exact_quantitative_geometry
```

冻结原则不是“Forest 永远 Python 画”，而是：
**承担精确数值几何的视觉不得由自由 Image Model 重新解释其几何关系。**

### N4. Calibration Config

#### SelectorScoringConfig

```yaml
config_id: SSC-MEDCONGRESS-v0.1

weights:
  semantic_fit: 0.30
  medical_convention_fit: 0.20
  data_fidelity: 0.15
  auditability: 0.15
  audience_fit: 0.10
  visual_communication_fit: 0.10
```

以上仅为初始值，**不冻结**。

允许：
- 全局校准；
- Project Type 校准；
- Audience 校准；
- benchmark 后版本升级。

#### PenaltyConfig

Penalty 仅用于**未达到 Hard Fail**的轻度风险。

可配置：
- numeric_precision_risk
- text_density_risk
- semantic_overload_risk
- visual_misinterpretation_risk
- mild_comparability_uncertainty

以下不得作为 penalty：
- unsupported medical relationship
- hard comparability fail
- required clinical logic loss
- invented statistic
- prohibited semantic transformation

这些必须直接 `INVALID_CANDIDATE`。

#### SelectionThresholdConfig

```yaml
selectable_threshold: CONFIGURABLE
review_threshold: CONFIGURABLE
ambiguity_margin: CONFIGURABLE
```

具体数值通过 benchmark 标定，不进入冻结规则。

### N5. Selector 执行顺序 v0.2

```text
Approved Semantic Page Graph
        ↓
Build Visual Intent + Information Structure Profile
        ↓
Apply Frozen Constitution
        ↓
Load Versioned Visual Policy Registry
        ↓
Generate Candidate Set
        ↓
Hard Gate
   ↙             ↘
INVALID         VALID
                  ↓
          Calibration Scoring
                  ↓
           Candidate Ranking
                  ↓
          Ambiguity Resolution
             ↙          ↘
         SELECTED     AMBIGUOUS
             ↓
      Generation Strategy Router
             ↓
      VisualStrategyDecision
             ↓
      Visual Generation Contract
```

### N6. 关键架构修正

- Scoring 是“合法候选之间的偏好排序”，不是医学正确性裁判。
- Taxonomy 是 Registry，不是 Constitution。
- IF/THEN Mapping 是 Versioned Policy，不是 Frozen Rule。
- Threshold 是 Calibration，不是产品真理。
- Generation Router 可以随着底层模型能力升级而更新。
- Hard Rule 只冻结长期稳定且一旦违反就会产生医学/统计/审计风险的边界。

状态：`DRAFT v0.2 / NOT_FROZEN`


---

### Module 06 Batch 3｜Generation Strategy Router v0.1（FORMALLY FROZEN）

## A. 核心问题

Batch 2 已决定：

> “医学上应该画什么。”

Batch 3 只回答：

> “这个已批准的 Visual Strategy 应通过何种技术路线生成，哪些部分由确定性引擎负责，哪些部分允许图像模型创造，最后如何合成。”

因此：

```text
Visual Strategy
≠
Generation Strategy
```

Generation Strategy Router **没有权限改变 Visual Type**。

---

## B. 组件级 Generation Architecture

不再把整页简单标记成：

```text
FOREST_PLOT → DETERMINISTIC
```

而是先拆页：

```text
Page
├─ Title / Exact Text
├─ Quantitative Geometry
├─ Semantic Diagram
├─ Medical Visual Asset
├─ Editorial Composition
├─ Decorative Background
└─ Sources / Footnotes
```

再分别路由。

### Generation Component Types

#### 1. DATA_GEOMETRY

包括：
- bar / line / dot
- forest
- KM
- ROC
- calibration
- waterfall / swimmer / spider
- axis / legend / scale / CI

默认承担精确数值几何。

#### 2. SEMANTIC_DIAGRAM

包括：
- Clinical Decision Map
- Treatment Pathway
- Mechanism Map
- Risk Stratification
- Evidence Map
- CONSORT / PRISMA / STARD flow
- AND / OR / NOT / EXCEPT 结构

承担 Node / Edge / Direction / Group / Logic。

#### 3. EXACT_TEXT

包括：
- Drug Name
- Dose
- Threshold
- Unit
- HR / OR / RR / CI / P
- Recommendation Class
- Evidence Level
- Citation / Source
- RED Exact Text

#### 4. MEDICAL_VISUAL_ASSET

包括：
- anatomy
- procedure
- pathology
- organ / cell / molecular structure
- medical iconography with semantic role

#### 5. EDITORIAL_COMPOSITION

负责：
- overall visual balance
- whitespace
- composition
- non-semantic shape language
- title positioning
- section emphasis
- art direction

#### 6. DECORATIVE_BACKGROUND

只允许：
- non-semantic texture
- light / shadow
- atmosphere
- visual polish

---

## C. 执行器分类

### Strategy A｜DETERMINISTIC_CHART

用于精确 Data Geometry。

要求：
- 原始数值绑定；
- deterministic coordinate calculation；
- axis/legend/data series 显式绑定；
- 不允许 Image Model 重解释数据几何。

### Strategy B｜DETERMINISTIC_DIAGRAM

用于 Meaning-Critical Semantic Graph。

要求：
- nodes 来自 approved objects；
- edges 来自 approved relationships；
- AND/OR/NOT/EXCEPT 显式编译；
- Image Model 不得新增、删除、改向。

### Strategy C｜EXACT_CONTENT_COMPOSITOR

用于 Exact Text / citation / high-risk numeric labels。

要求：
- 文本从 Exact Text Register 注入；
- 字符串不可由 Image Model 重写；
- position/layout 可在授权范围内调整。

### Strategy D｜VERIFIED_MEDICAL_ASSET_RENDERER

用于经过 MedicalVisualAssetContract 授权的素材。

来源可包括：
- verified source figure；
- licensed medical asset；
- deterministic vector asset；
- AI-generated medical asset（仅当 contract 明确允许且需 QA）。

### Strategy E｜PROMPT_DRIVEN_IMAGE

负责：
- editorial composition；
- non-semantic styling；
- atmosphere；
- concept illustration；
- approved low-risk visual narrative。

不得负责：
- exact quantitative geometry；
- locked clinical topology；
- authoritative exact RED text。

### Strategy F｜HYBRID_COMPOSITION

将上述多条路径合成完整页面。

推荐流程：

```text
Deterministic Chart / Diagram
        +
Verified Medical Asset
        +
Prompt-driven Editorial Art
        +
Exact Content Compositor
        ↓
Layered Composition
        ↓
Flattened Final Slide Image
```

---

# D. Generation Strategy Router｜IF / THEN 决策树 v0.1

## Stage 0｜Data Egress / Privacy Gate

```text
IF component contains data not permitted for external processing
THEN
    external_prompt_image = FORBIDDEN

    route to:
      LOCAL_DETERMINISTIC
      LOCAL_VERIFIED_ASSET
      LOCAL_COMPOSITION
      OR BLOCK
```

Router 不得因为外部模型视觉更好而绕过数据治理规则。

---

## Stage 1｜Component Classification

```text
IF visual encodes numeric magnitude / uncertainty / axis / scale
THEN component_type = DATA_GEOMETRY

IF visual encodes node-edge-direction / AND-OR / branch / exclusion
THEN component_type = SEMANTIC_DIAGRAM

IF text must match approved exact string
THEN component_type = EXACT_TEXT

IF visual contains anatomy / procedure / pathology / medical structure
THEN component_type = MEDICAL_VISUAL_ASSET

IF element is primarily overall composition and non-semantic styling
THEN component_type = EDITORIAL_COMPOSITION

IF element has no medical or quantitative semantic role
THEN component_type = DECORATIVE_BACKGROUND
```

---

## Stage 2｜Hard Routing

### Exact Quantitative Geometry

```text
IF component_type == DATA_GEOMETRY
AND geometry_is_meaning_critical == true
THEN
    require capability:
      exact_data_binding
      deterministic_or_equivalently_constrained_geometry

    disallow:
      free_prompt_image_geometry
```

### Meaning-Critical Semantic Diagram

```text
IF component_type == SEMANTIC_DIAGRAM
AND relationship_risk in [YELLOW, RED]
THEN
    require:
      topology_lock
      node_lock
      edge_lock
      logic_lock

    preferred:
      DETERMINISTIC_DIAGRAM
      HYBRID_COMPOSITION
```

### Exact Text

```text
IF component_type == EXACT_TEXT
AND exactness_required == true
THEN
    require:
      exact_string_rendering

    preferred:
      EXACT_CONTENT_COMPOSITOR
```

### Medical Visual Asset

```text
IF component_type == MEDICAL_VISUAL_ASSET
THEN
    read MedicalVisualAssetContract

IF ai_generation_allowed == false
THEN
    PROMPT_DRIVEN_MEDICAL_ASSET = FORBIDDEN

IF ai_generation_allowed == true
THEN
    medical_visual_qa_required = true
```

### Editorial / Decorative

```text
IF component_type in [EDITORIAL_COMPOSITION, DECORATIVE_BACKGROUND]
AND no_locked_semantics_are_modified
THEN
    PROMPT_DRIVEN_IMAGE = ALLOWED
```

---

## Stage 3｜Page-level Mode

```text
IF any component requires:
    deterministic data geometry
    OR locked topology
    OR exact content compositor
THEN
    generation_mode = CONTROLLED_COMPOSITION

ELSE IF all meaning-critical components are approved for prompt generation
AND privacy gate passes
THEN
    generation_mode = FULL_IMAGE
```

`FULL_IMAGE` 不是默认模式。

---

## Stage 4｜Capability Gate

Router 不允许按模型名称硬编码能力。

必须读取：

```text
GenerationCapabilityRegistry
```

例如：

```yaml
engine_id: image_model_x
engine_version: 2026-08
capabilities:
  prompt_image: true
  image_edit: true
  exact_text_reliability: benchmarked
  data_geometry_lock: false
  topology_lock: partial
  external_processing: true
```

Router 只能使用**已注册、已验证**的能力。

---

## Stage 5｜Valid Engine Candidate Set

通过 Hard Gate 后形成：

```text
component
    ↓
allowed engines
    ↓
capability-qualified engines
```

例如：

```text
FOREST DATA_GEOMETRY

allowed:
- deterministic_chart_engine_A
- deterministic_chart_engine_B

not allowed:
- free image model reconstruction
```

---

## Stage 6｜Soft Optimization

仅在合法执行器之间评分。

候选评分维度建议：

```text
GenerationFitScore =
  FidelityFit
+ AuditabilityFit
+ VisualQualityFit
+ EditabilityFit
+ ReliabilityFit
+ LatencyFit
+ CostFit
```

权重全部配置化，不冻结。

注意：

> 成本、速度、审美永远不能重新激活被 Hard Gate 禁止的执行器。

---

## Stage 7｜Fallback

```text
IF selected engine unavailable / fails
THEN
    choose next valid implementation strategy

IF no valid implementation remains
THEN
    ROUTING_STATUS = UNROUTABLE
    OR NEEDS_HUMAN_REVIEW
```

Fallback 只能改变：
- engine；
- rendering technique；
- non-semantic visual polish。

不得改变：
- Visual Type；
- Claim；
- data；
- relationship；
- clinical logic。

---

# E. PageGenerationPlan

最终不是输出一个字符串：

```text
generation_strategy = HYBRID
```

而是：

```yaml
page_generation_plan_id: PGP001
page_id: S12

visual_strategy_decision_id: VSD001

generation_mode:
  CONTROLLED_COMPOSITION

components:

  - component_id: CMP001
    type: DATA_GEOMETRY
    source_bindings:
      - DB001
    route:
      strategy: DETERMINISTIC_CHART
      engine: chart_engine_v1

  - component_id: CMP002
    type: SEMANTIC_DIAGRAM
    source_bindings:
      - REL001
      - REL002
    route:
      strategy: DETERMINISTIC_DIAGRAM
      engine: semantic_svg_renderer_v1

  - component_id: CMP003
    type: EDITORIAL_COMPOSITION
    route:
      strategy: PROMPT_DRIVEN_IMAGE
      engine: image_model_profile_A

  - component_id: CMP004
    type: EXACT_TEXT
    source_bindings:
      - ETR001
    route:
      strategy: EXACT_CONTENT_COMPOSITOR
      engine: compositor_v1

composition:
  strategy:
    HYBRID_COMPOSITION

  merge_order:
    - editorial_base
    - semantic_diagram
    - data_geometry
    - exact_text
    - sources

verification:
  - numeric_fidelity
  - relationship_fidelity
  - exact_text_fidelity
  - visual_semantic_fidelity
```

---

# F. Router 不拥有的权限

Generation Strategy Router 不得：

- 更换 Visual Type；
- 修改 Page Goal；
- 修改 Claim；
- 修改 NumericFact；
- 修改 Clinical Relationship；
- 创建新医学对象；
- 推导新统计量；
- 因成本更低而降低医学表达准确性；
- 因 Image Model 更漂亮而把 deterministic component 改成 free generation。

---

# G. Batch 3｜14 条 Hard Rules — FORMALLY FROZEN v0.1

本轮已逐条对照：
- Module 04｜Semantic Relationship & Evidence Binding，特别是 Visual Semantic Binding & Medical Visual Provenance；
- Module 05｜Medical Verifier & Source Fidelity Gate；
- Module 06 Batch 1｜Visual Generation Contract & Prompt Compiler；
- Module 06 Batch 2｜Visual Strategy Selector。

结论：**不存在必须删除 Batch 3 的结构性冲突，但有 6 处需要收窄职责或改写，以避免重复冻结和跨模块越权。**

---

1. **Route-resolution Authority Rule**  
   Router 的职责是把已批准的 `VisualStrategyDecision` 解析为可执行 `Generation Route / PageGenerationPlan`。  
   - Router 不得修改 Visual Type、Page Goal、Claim、NumericFact、Clinical Relationship 或其他上游医学语义。  
   - Batch 2 可以输出 `preferred_generation_strategy / strategy_requirements`；Batch 3 负责 Capability Qualification、组件路由与最终 `effective_generation_route`。  
   - 当首选 Generation Strategy 不可执行时，Router 可以在不改变 Visual Strategy 的前提下切换到另一个**合法实现策略**，并记录 `route_deviation_reason`。  
   - 若不存在合法路线，必须返回 `UNROUTABLE / NEEDS_HUMAN_REVIEW`。

   **边界说明：**解决 Batch 2 “选择 Generation Strategy” 与 Batch 3 “决定路由”的职责重叠：Batch 2 决定语义层面的偏好/要求，Batch 3 决定经能力验证后的实际执行路线。

2. **Semantic-granularity & Binding-preservation Routing Rule**  
   Router 必须能够在满足语义和风险要求的最小必要粒度上独立路由 Generation Components。  
   - 当不同内容具有不同 Fidelity、Privacy、Exactness、Asset 或 Verification 要求时必须拆分路由；  
   - 组件拆分不得切断 `Meaning-Preserving Bundle`、Data Binding、Relationship Binding、Label Ownership、Legend/Series Binding 或其他 Meaning-Critical Binding；  
   - 只有约束同质、语义绑定完整且均允许同一路径时，才可整页采用单一路由。

   **边界说明：**继承 Module 02 的 Meaning-Preserving Bundle 和 Module 04 的 Binding，不重新定义医学关系。

3. **Hard Route Qualification Before Optimization Rule**  
   Router 在任何视觉质量、可靠性、可编辑性、延迟、成本或工作流优化之前，必须先验证：
   - 上游对象/版本仍为 Approved / Current；
   - 所需医学语义与 Binding 已由上游冻结模块确定；
   - Data Precision / Topology / Exact Text / Asset / Privacy / Verification Requirements 可被候选路线满足。  

   Router **不重新裁定 Source Fidelity 或 Clinical Correctness**；这仍属于 Module 05。Router 只消费其有效验证/批准状态。

4. **Exact Quantitative Geometry Routing Rule**  
   对承担数值大小、位置、比例、区间、坐标轴、尺度、误差范围或其他 Meaning-Critical Data Geometry 的组件，Router 只能选择具有已 qualification 的：
   - exact data binding；
   - geometry fidelity；
   - scale/axis fidelity；
   - post-generation numeric/visual verification  
   能力的执行路径。  

   未经约束或未 qualification 的自由生成式图像路径不得作为权威 Data Geometry Renderer。

   **边界说明：**Module 04 定义“数据视觉语义必须正确”；Batch 3 只定义“什么能力的执行器有资格实现它”。

5. **Semantic Topology Capability Rule**  
   当组件承担 Node / Edge / Direction / Branch / Group / AND / OR / NOT / EXCEPT、禁忌、排除或其他 Meaning-Critical Relationship 时，Router 只能选择能够：
   - 锁定 approved topology；
   - 保留 approved relationship IDs；
   - 验证 node/edge/direction/logic  
   的执行路径。  

   Router 不重新创建或验证医学关系本身；关系真实性与支持性仍由 Module 04/05 负责。

6. **Exact Text Routing Authority Rule**  
   当 `VisualGenerationContract` 中存在 `ExactTextRegister` 项时，Router 必须选择支持：
   - authoritative string injection；
   - exact rendering；
   - post-render text verification  
   的路线。  

   图像模型自行生成的近似文字可以作为非权威草图，但不能履行 Exact Text 义务。  
   **不在 Batch 3 重新定义哪些医学字段属于 Exact Text**；字段分类沿用 Batch 1。

7. **Asset-contract Binding Rule**  
   Router 对 Medical Visual Asset 的生成、选择和调用必须严格服从对应 `MedicalVisualAssetContract`。  
   Router 只执行 Contract，不重新判定医学资产的医学有效性、版权状态或许可结论；这些由 Module 04 的 Medical Visual Provenance / Asset Governance 与相应 QA 决定。

8. **Protected Semantic Layer Rule**  
   任何由 qualified Renderer / Compositor / Verified Asset Pipeline 生成并承担锁定医学或统计语义的组件，一旦成为 `Protected Semantic Layer`：  
   - 下游生成式操作不得改变其内部数据几何、文字、Node/Edge、Direction、Grouping、Legend、Axis、Color Semantics 或其他 Meaning-Critical Encoding；  
   - 不禁止纯技术性的 rasterization、format conversion、整体缩放或其他**已证明 semantic-invariant** 的处理；  
   - 任何裁切、遮挡、缩放、重采样、风格化或重布局，只要可能影响可读性、几何比例、绑定或医学含义，就必须禁止或重新验证；  
   - 最安全默认路径是：Prompt-driven Editorial Base 先生成，Protected Semantic Layers 后叠加。

   **边界说明：**这是 Module 04 Visual Semantic Binding 在“生成/合成阶段”的执行保护机制，不重复定义视觉语义本身。

9. **Data Boundary / Egress Enforcement Rule**  
   Router 必须消费并执行项目级 `DataEgressPolicy / PrivacyDecision`。  
   - Router 无权自行放宽隐私或数据出域政策；  
   - 不允许外发的内容必须路由至合法本地/受控路径或阻断；  
   - 外部模型视觉质量、成本或速度不得覆盖数据边界。  

   **边界说明：**数据政策由 Data Governance / Compliance 定义，Batch 3 只负责路由执行。

10. **Qualified Capability Evidence Rule**  
    Router 只能依据与具体 Engine / Model / Renderer / Compositor Version 绑定、经过项目定义 benchmark / qualification 的 `CapabilityRecord` 做 Hard Routing。  
    厂商名称、营销声明、模型家族、历史版本能力或未经验证经验不得作为 Hard Capability Evidence。  
    Capability Registry 本身版本化、非冻结。

11. **No Semantic Degradation Fallback Rule**  
    Tool / Engine 失败时，Fallback 只能改变：
    - Engine / Renderer；
    - implementation technique；
    - non-semantic visual polish。  

    不得改变：
    - Visual Type；
    -医学语义；
    - Data Precision；
    - Clinical Logic；
    - Exact Text requirement；
    - Asset Contract；
    - Verification requirement。  

    没有合法 fallback 时必须 `UNROUTABLE / HUMAN_REVIEW_REQUIRED`。

12. **Material Capability Change Invalidation Rule**  
    Engine、Model、Renderer、Prompt Compiler、Compositor 或其版本发生可能影响：
    - locked semantics；
    - data geometry；
    - topology；
    - exact text；
    - asset integrity；
    - privacy behavior；
    - verifier compatibility  
    的 Material Change 时，相关 Capability Qualification 与受影响 Generation Route 必须标记 STALE / INVALIDATED 并重新验证。  

    **边界说明：**复用 Module 05 的版本化/失效思想，但对象是“生成能力与路线”，不是医学 Claim/Relationship。

13. **Generation Execution Provenance Rule**  
    每个 Generation Component 必须保存独立的 **Generation Execution Provenance**，至少能够追溯：
    - strategy；
    - Engine / Model / Renderer / Compositor version；
    - input contract/version；
    - deterministic spec 或 prompt version/hash；
    - 受数据政策允许时的安全 prompt reference；
    - generation/edit operation；
    - output asset/version；
    - relevant validator result IDs。  

    Generation Execution Provenance 必须与：
    - Medical Semantic Provenance；
    - Visual Asset Provenance  
    分离管理，不能互相替代。  

    原始 Prompt 若含敏感信息，不因审计要求强制明文保存；记录方式必须服从数据最小化与安全策略。

14. **Verification-aware Route Eligibility Rule**  
    Router 只能选择存在**注册且可执行** Post-generation Verification Path 的路线。  
    对每个 Meaning-Critical Component 必须明确：
    - validator type；
    - validator capability/version；
    - verification target；
    - failure action。  

    Router 不负责篡改或“通过” VerificationResult；实际 Numeric / Semantic / Medical Visual Verification 仍由相应 QA / Module 05 Verifier 执行。  
    如果锁定内容无法被可靠验证，该路线不得进入最终合法候选。

状态：`FROZEN v0.1 / Batch 3`


# H. Batch 3 三层治理结构

```text
LAYER 1
ROUTER CONSTITUTION
───────────────────
14 Hard Rule candidates
长期稳定实现边界

        ↓

LAYER 2
VERSIONED ROUTING POLICY REGISTRY
─────────────────────────────────
GenerationComponentRegistry
GenerationStrategyRegistry
GenerationCapabilityRegistry
GenerationRoutingPolicyRegistry
FullImageEligibilityPolicy
FallbackPolicyRegistry
DataEgressPolicyRegistry
AssetGenerationPolicyRegistry

        ↓

LAYER 3
CALIBRATION / OPTIMIZATION CONFIG
─────────────────────────────────
VisualQuality weighting
Reliability weighting
Editability weighting
Latency weighting
Cost weighting
Project-specific preferences
```

---

# I. Protected Semantic Layer Architecture

推荐正式执行顺序：

```text
Prompt-driven Editorial Base
        ↓
[optional verified medical asset background]
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
        ↓
Post-generation Verification
```

禁止：

```text
Accurate Chart / Diagram / Exact Text
        ↓
Final free generative "beautification"
        ↓
Repainted semantic layer
```

Protected Semantic Layer 必须具有：

```yaml
protected_layer_id: PSL001
contains:
  - DATA_GEOMETRY
  - SEMANTIC_DIAGRAM
  - EXACT_TEXT
protection:
  repaint: forbidden
  semantic_crop: forbidden
  geometry_warp: forbidden
  occlusion_over_threshold: forbidden
  internal_relayout: forbidden
```

---

# J. FULL_IMAGE Eligibility 改为 Policy

`FULL_IMAGE` 不作为独立 Hard Rule。

由以下约束动态推导：

```text
Batch 1 Lock Requirements
+ Exact Geometry Requirements
+ Topology Requirements
+ Exact Text Requirements
+ Asset Contract
+ Privacy / Data Egress
+ Qualified Capability
+ Verification Coverage
        ↓
FullImageEligibilityPolicy
```

例如：

```yaml
policy_id: FIEP-v0.1

eligible_if:
  all_critical_components_prompt_authorized: true
  exact_geometry_requires_deterministic: false
  locked_topology_requires_deterministic: false
  exact_text_requires_compositor: false
  privacy_gate: PASS
  asset_policy: PASS
  post_generation_verification: AVAILABLE
```

未来模型能力提升时更新 Policy / Capability Registry，不修改 Constitution。

---

# K. Soft Optimization 重新定义

Hard Qualification 之后才能进入优化：

```text
Qualified Engines Only
        ↓
Soft Optimization
```

建议优化维度：

- VisualQualityFit
- ReliabilityFit
- EditabilityFit
- LatencyFit
- CostFit
- WorkflowFit

以下不再作为“可被权重平均掉”的软评分项：
- Hard Fidelity
- Clinical Logic preservation
- Exact geometry requirement
- Exact text authority
- Privacy/Data Egress
- Asset contract
- Verification availability

这些均属于 Gate。

权重全部配置化，不冻结。

---

# L. Batch 1 继承关系

Batch 3 不重复冻结 Batch 1 的：

```text
HARD_LOCK
SEMANTIC_LOCK
BOUNDED_CREATIVE
FREE_CREATIVE
```

Router 直接读取 `VisualGenerationContract.lock_level`。

如果某 Engine 的行为会越过授权 Lock Level：
- Candidate Engine = INVALID。




---

# M. Batch 3 最终跨模块冲突审查

## M1. 实质性冲突

### Conflict C1｜Batch 2 与 Batch 3 对 Generation Strategy 的归属

**发现：**
- Batch 2 Frozen Rule 8/12 已包含“选择/记录 Generation Strategy”；
- Batch 3 若再声明“Router 决定 Generation Strategy”，会造成双写权限。

**解决：**
- Batch 2：输出 `preferred_generation_strategy / strategy_requirements`，属于 Visual Strategy Decision 的语义级偏好；
- Batch 3：输出 `effective_generation_route / PageGenerationPlan`，依据 Capability、Privacy、Asset、Verification Gate 解析具体执行路线；
- 两者不一致时必须记录 `route_deviation_reason`；
- Batch 3 不得改变 Visual Type。

**状态：RESOLVED_BY_SCOPE_SPLIT**

### Conflict C2｜Batch 1 Generation Mode 与 Batch 3 Routing 顺序

**发现：**
Batch 1 要求每页在 `VisualGenerationContract` 中声明 `FULL_IMAGE / CONTROLLED_COMPOSITION`；旧实现责任表将其交给 Generation Mode Selector。

**解决：**
- Batch 3 Router 先形成经 Hard Qualification 的 `PageGenerationPlan`；
- `FullImageEligibilityPolicy` 计算有效 `generation_mode`；
- Contract Builder 将该结果写入 Batch 1 的 VisualGenerationContract；
- Batch 1 冻结规则不需修改，仅更新实现责任。

**状态：RESOLVED_BY_IMPLEMENTATION_ORDER**

---

## M2. 高重叠但不冲突

| Batch 3 Rule | 上游相近规则 | 结论 |
|---|---|---|
| Rule 3 Hard Route Qualification | Batch 2 Hard Gate / Module 05 Gate | 不重复裁定医学正确性，只检查 Route eligibility |
| Rule 4 Exact Geometry | Module 04 Data/Visual Binding | Module 04 定义正确语义；Batch 3 限制可用 Renderer capability |
| Rule 5 Topology Capability | Module 04 Clinical/Visual Relationship | Module 04 定义 relation；Batch 3 只锁执行器 topology |
| Rule 6 Exact Text Routing | Batch 1 Exact Text Register | Batch 1 定义 exact content；Batch 3 决定 authoritative render path |
| Rule 7 Asset Contract | Module 04 Medical Visual Provenance / Batch 1 Asset Contract | 上游定义资产规则；Batch 3 仅执行 |
| Rule 8 Protected Layer | Module 04 Visual Semantic Fidelity / Batch 1 Lock Model | 新增的是生成后保护机制，非重复语义规则 |
| Rule 12 Capability Change Invalidation | Module 05 Re-verification Loop | 复用失效机制，作用对象不同 |
| Rule 13 Generation Execution Provenance | Module 04 Provenance / 全局 AuditLog | 新增执行链 provenance，并明确三类 provenance 分离 |
| Rule 14 Verification-aware Route | Module 05 Verifier / Batch 1 Post-generation Contract | Router 只要求 verifier path 存在，不执行医学裁定 |

---

## M3. 职责越界检查

### Router 明确不得做

- Source Fidelity judgement；
- Clinical Correctness judgement；
- Claim / NumericFact / Relationship revision；
- Comparability medical adjudication；
- Copyright / license legal adjudication；
- Privacy policy definition；
- Medical Visual validation conclusion；
- Visual Type reselection；
- Human Review override。

### Router 可以做

- 读取上游批准状态；
- 读取 VisualGenerationContract / VisualStrategyDecision；
- 读取 Capability / Privacy / Asset / Verification Policy；
- 拆分合法 Generation Components；
- Hard-qualify Engine/Route；
- 选择 effective implementation route；
- 构建 PageGenerationPlan；
- 标记 UNROUTABLE / STALE / INVALID route；
- 记录 Generation Execution Provenance。

---

## M4. 文档一致性发现

发现 `02_ARCHITECTURE.md` 中仍残留旧的：
`Batch 2｜12 条 Hard Rule 冻结候选（未冻结）`

但：
- PRD 已记录 Batch 2 正式冻结 13 条；
- Manifest 已记录 Batch 2 = 13 条 FROZEN。

本次已同步修复 Architecture，统一以 **13 条 FROZEN v0.1** 为准。

---

## M5. 最终审查结论

经过冲突收敛后，Batch 3 的 14 条候选：
- **0 条需要删除**；
- **6 条需要职责收窄或精确改写**；
- **2 个跨 Batch 实质性职责冲突已通过 Scope Split / Implementation Order 解决**；
- 未发现需要修改 Module 04、Module 05、Module 06 Batch 1 的冻结医学原则；
- Batch 2 的冻结文本不修改，只通过 `preferred strategy` vs `effective route` 的数据语义区分解决归属冲突。

最终状态：
`FROZEN v0.1 / Batch 3`


---


### Module 06 Batch 3｜Generation Strategy Router v0.1 — FORMALLY FROZEN

以下 14 条 Hard Rules 已正式冻结：

1. **Route-resolution Authority Rule**  
   Router 的职责是把已批准的 `VisualStrategyDecision` 解析为可执行 `Generation Route / PageGenerationPlan`。Router 不得修改 Visual Type、Page Goal、Claim、NumericFact、Clinical Relationship 或其他上游医学语义。Batch 2 可以输出 `preferred_generation_strategy / strategy_requirements`；Batch 3 负责 Capability Qualification、组件路由与最终 `effective_generation_route`。当首选 Generation Strategy 不可执行时，Router 可以在不改变 Visual Strategy 的前提下切换到另一个合法实现策略，并记录 `route_deviation_reason`；若不存在合法路线，必须返回 `UNROUTABLE / NEEDS_HUMAN_REVIEW`。

2. **Semantic-granularity & Binding-preservation Routing Rule**  
   Router 必须能够在满足语义和风险要求的最小必要粒度上独立路由 Generation Components。当不同内容具有不同 Fidelity、Privacy、Exactness、Asset 或 Verification 要求时必须拆分路由；组件拆分不得切断 `Meaning-Preserving Bundle`、Data Binding、Relationship Binding、Label Ownership、Legend/Series Binding 或其他 Meaning-Critical Binding；只有约束同质、语义绑定完整且均允许同一路径时，才可整页采用单一路由。

3. **Hard Route Qualification Before Optimization Rule**  
   Router 在任何视觉质量、可靠性、可编辑性、延迟、成本或工作流优化之前，必须先验证：上游对象/版本仍为 Approved / Current；所需医学语义与 Binding 已由上游冻结模块确定；Data Precision / Topology / Exact Text / Asset / Privacy / Verification Requirements 可被候选路线满足。Router 不重新裁定 Source Fidelity 或 Clinical Correctness，这仍属于 Module 05；Router 只消费其有效验证/批准状态。

4. **Exact Quantitative Geometry Routing Rule**  
   对承担数值大小、位置、比例、区间、坐标轴、尺度、误差范围或其他 Meaning-Critical Data Geometry 的组件，Router 只能选择具有已 qualification 的 `exact data binding / geometry fidelity / scale-axis fidelity / post-generation numeric-visual verification` 能力的执行路径。未经约束或未 qualification 的自由生成式图像路径不得作为权威 Data Geometry Renderer。

5. **Semantic Topology Capability Rule**  
   当组件承担 Node / Edge / Direction / Branch / Group / AND / OR / NOT / EXCEPT、禁忌、排除或其他 Meaning-Critical Relationship 时，Router 只能选择能够锁定 approved topology、保留 approved relationship IDs，并验证 node / edge / direction / logic 的执行路径。Router 不重新创建或验证医学关系本身；关系真实性与支持性仍由 Module 04/05 负责。

6. **Exact Text Routing Authority Rule**  
   当 `VisualGenerationContract` 中存在 `ExactTextRegister` 项时，Router 必须选择支持 authoritative string injection、exact rendering 和 post-render text verification 的路线。图像模型自行生成的近似文字可以作为非权威草图，但不能履行 Exact Text 义务。Batch 3 不重新定义哪些医学字段属于 Exact Text，字段分类沿用 Batch 1。

7. **Asset-contract Binding Rule**  
   Router 对 Medical Visual Asset 的生成、选择和调用必须严格服从对应 `MedicalVisualAssetContract`。Router 只执行 Contract，不重新判定医学资产的医学有效性、版权状态或许可结论；这些由 Module 04 的 Medical Visual Provenance / Asset Governance 与相应 QA 决定。

8. **Protected Semantic Layer Rule**  
   任何由 qualified Renderer / Compositor / Verified Asset Pipeline 生成并承担锁定医学或统计语义的组件，一旦成为 `Protected Semantic Layer`，下游生成式操作不得改变其内部数据几何、文字、Node/Edge、Direction、Grouping、Legend、Axis、Color Semantics 或其他 Meaning-Critical Encoding。允许纯技术性的 rasterization、format conversion、整体缩放或其他已证明 semantic-invariant 的处理；任何裁切、遮挡、缩放、重采样、风格化或重布局，只要可能影响可读性、几何比例、绑定或医学含义，就必须禁止或重新验证。默认推荐路径为：Prompt-driven Editorial Base 先生成，Protected Semantic Layers 后叠加。

9. **Data Boundary / Egress Enforcement Rule**  
   Router 必须消费并执行项目级 `DataEgressPolicy / PrivacyDecision`。Router 无权自行放宽隐私或数据出域政策；不允许外发的内容必须路由至合法本地/受控路径或阻断；外部模型视觉质量、成本或速度不得覆盖数据边界。

10. **Qualified Capability Evidence Rule**  
    Router 只能依据与具体 Engine / Model / Renderer / Compositor Version 绑定、经过项目定义 benchmark / qualification 的 `CapabilityRecord` 做 Hard Routing。厂商名称、营销声明、模型家族、历史版本能力或未经验证经验不得作为 Hard Capability Evidence。Capability Registry 本身版本化、非冻结。

11. **No Semantic Degradation Fallback Rule**  
    Tool / Engine 失败时，Fallback 只能改变 Engine / Renderer、implementation technique 或 non-semantic visual polish；不得改变 Visual Type、医学语义、Data Precision、Clinical Logic、Exact Text requirement、Asset Contract 或 Verification requirement。没有合法 fallback 时必须 `UNROUTABLE / HUMAN_REVIEW_REQUIRED`。

12. **Material Capability Change Invalidation Rule**  
    Engine、Model、Renderer、Prompt Compiler、Compositor 或其版本发生可能影响 locked semantics、data geometry、topology、exact text、asset integrity、privacy behavior 或 verifier compatibility 的 Material Change 时，相关 Capability Qualification 与受影响 Generation Route 必须标记 `STALE / INVALIDATED` 并重新验证。复用 Module 05 的版本化/失效思想，但作用对象是“生成能力与路线”，不是医学 Claim / Relationship。

13. **Generation Execution Provenance Rule**  
    每个 Generation Component 必须保存独立的 `Generation Execution Provenance`，至少能够追溯 strategy、Engine / Model / Renderer / Compositor version、input contract/version、deterministic spec 或 prompt version/hash、受数据政策允许时的安全 prompt reference、generation/edit operation、output asset/version、relevant validator result IDs。Generation Execution Provenance 必须与 Medical Semantic Provenance、Visual Asset Provenance 分离管理，不能互相替代。原始 Prompt 若含敏感信息，不因审计要求强制明文保存；记录方式必须服从数据最小化与安全策略。

14. **Verification-aware Route Eligibility Rule**  
    Router 只能选择存在注册且可执行 Post-generation Verification Path 的路线。对每个 Meaning-Critical Component 必须明确 validator type、validator capability/version、verification target 和 failure action。Router 不负责篡改或“通过” VerificationResult；实际 Numeric / Semantic / Medical Visual Verification 仍由相应 QA / Module 05 Verifier 执行。如果锁定内容无法被可靠验证，该路线不得进入最终合法候选。

状态：`FROZEN v0.1 / Batch 3`

治理说明：
- Batch 1 的 `HARD_LOCK / SEMANTIC_LOCK / BOUNDED_CREATIVE / FREE_CREATIVE` 直接继承，不重复冻结；
- `GenerationComponentRegistry / GenerationStrategyRegistry / GenerationCapabilityRegistry / GenerationRoutingPolicyRegistry / FullImageEligibilityPolicy / FallbackPolicyRegistry / DataEgressPolicyRegistry / AssetGenerationPolicyRegistry` 保持版本化、非冻结；
- Soft Optimization 仅对通过 Hard Qualification 的 Qualified Engine Set 生效；
- Visual Quality / Reliability / Editability / Latency / Cost / Workflow 等权重保持可配置、非冻结。


### Module 06 Batch 3 Implementation Ownership

| Frozen Rule Area | Primary Implementer | Validator / Gate |
|---|---|---|
| Route resolution | Generation Strategy Router | Policy Engine |
| Semantic-granularity routing | Component Decomposer + Binding Resolver | Semantic QA |
| Hard qualification | Route Qualification Engine | Policy Engine |
| Exact data geometry | GenerationCapabilityRegistry + deterministic/controlled renderer | Numeric / Visual QA |
| Semantic topology | Topology-capable renderer route | Semantic QA |
| Exact text | Exact Content Compositor route | Exact Text QA |
| Medical asset binding | Asset Policy Adapter | Medical Visual QA |
| Protected Semantic Layer | Composition Engine | Visual Semantic QA |
| Data boundary / egress | DataEgressPolicy Adapter | Privacy / Compliance Gate |
| Qualified capability evidence | Capability Qualification Service | Benchmark / Policy Gate |
| Fallback | Fallback Resolver | Policy Engine |
| Material change invalidation | Version / Capability Resolver | Requalification Gate |
| Generation execution provenance | Generation Audit Logger | Audit QA |
| Verification-aware routing | Verification Path Registry | Delivery Gate |
