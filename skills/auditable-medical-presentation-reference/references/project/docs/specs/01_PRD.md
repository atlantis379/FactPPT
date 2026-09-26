# 医学可审计演示系统｜PRD v0.1

> Product Requirement Document  
> 项目暂定名：Auditable Medical Presentation System  
> 当前阶段：MVP 需求冻结  
> 已冻结模块：Claim Table v0.1 / Information Triage v0.1 / Medical Information Architect v0.1  
> 核心定位：把复杂医学材料转化为**可讲、可核验、可追溯、可审阅**的专业演示内容，而不是把 PDF 自动套进漂亮模板。

---

## 1. 产品目标

### 1.1 要解决的核心问题

目标用户在病例讨论、科室讲课、Journal Club、专家共识、指南解读、学术会议与科研答辩中，常见问题包括：

1. 资料过多，不知道应该保留什么。
2. 原始资料顺序不等于汇报逻辑，难以重构成“能讲”的结构。
3. 查文献、找来源、核对数字、推荐等级与阈值耗时。
4. 同一份材料面对不同听众，需要不同深度与叙事方式。
5. 复杂治疗表、推荐段落、病例过程、机制内容难以转成有效图形。
6. AI 容易生成“合理但非原文”的内容，用户难以分辨来源。
7. 流程图中的节点、箭头、因果/先后关系可能被 AI“顺手补全”。
8. 医学材料涉及患者隐私、版权、机构标识和公开渠道合规。
9. 排版与好看仍是基础要求，但不能以牺牲准确性与信息结构为代价。

### 1.2 价值主张

系统不承诺“AI 100%医学正确”，而是提供：

- 关键结论可追溯；
- 数字、单位、阈值可核对；
- 推荐等级与证据等级不由模型擅自推断；
- Clinical Decision Map 的关键关系有来源；
- AI 综合内容显式标识；
- RED 高风险内容进入人工确认；
- 最终输出兼顾演示逻辑、医学准确性与视觉表达。

### 1.3 核心原则

> **排版和好看是基础，真正稀缺的是清晰、准确、可追溯的内容骨架。**

---

## 2. 目标用户与主要场景

### 2.1 用户角色

| 用户 | 主要需求 | 典型痛点 |
|---|---|---|
| 专科医生 | 科室讲课、指南/共识解读 | 时间紧、材料多、证据核对复杂 |
| 规培医生 | 病例讨论、教学汇报 | 不知道如何筛选和组织内容 |
| 医学生 | 课程汇报、学习型演示 | 缺少完整叙事框架和基础解释 |
| 科研人员 | Journal Club、科研答辩 | 证据、方法、结果与局限难以高效表达 |
| 医学内容制作方 | 客户交付 | 既要漂亮，又要尽可能降低医学错误风险 |

### 2.2 项目类型

MVP 支持以下项目类型：

- 病例讨论；
- 指南解读；
- 专家共识；
- Journal Club；
- 学术会议；
- 科研答辩。

---

## 3. 产品输入

每个项目创建时至少收集：

| 字段 | 说明 | 必填 |
|---|---|---|
| Project Type | 病例讨论 / 指南 / 共识 / Journal Club / 学术会议 / 科研答辩 | 是 |
| Audience | 专科专家 / 规培医生 / 医学生 / 科研人员 / 综合听众 | 是 |
| Presentation Goal | 教学 / 决策沟通 / 文献解读 / 病例复盘 / 科研报告 | 是 |
| Presentation Question | 本次汇报必须回答的核心问题；Triage 与 Narrative 的最高层约束 | 是 |
| Duration | 汇报时长 | 是 |
| Language | 中文 / 英文 | 是 |
| Source Files | MVP 首期至少支持 PDF | 是 |
| Need Web Research | 是否允许补充外部权威资料 | 否 |
| Output Mode | Presentation / Reference / Notes / Full Package | 是 |
| Synthetic Case | 默认关闭 | 否 |
| Output Channel | Internal / Client Delivery / Public/Xiaohongshu | 是 |

---

## 4. 默认行为与用户可控项

### 4.1 Source-faithful 默认模式

默认只使用用户提供资料中真实存在的：

- 病例；
- 数据；
- 结论；
- 推荐；
- 阈值；
- 路径。

默认禁止：

- 原文没有病例时主动造病例；
- 原文没有数值时补数值；
- 原文没有完整算法时自动补全；
- 把综合推理伪装成原文结论。

### 4.2 Synthetic Case

仅在用户明确要求“生成模拟病例 / 教学病例 / 演练案例”时启用。

必须：

- 显著标注 `AI生成模拟病例｜非原文病例｜仅用于教学演示`；
- 不进入 Source Fact Layer；
- 不与真实病例混合展示；
- 关键剂量、阈值、路径如用于教学，应回溯权威来源。

若系统判断“加病例会更好讲”，只能提示用户是否需要，不得自动生成。

---

## 5. 核心用户流程

```text
创建项目
  ↓
上传医学资料
  ↓
系统提取 Claim / 数字 / 推荐 / 来源
  ↓
用户确认受众、目标、时长
  ↓
Information Triage
  ↓
生成 Clinical Narrative / PageSpec
  ↓
Semantic Relationship & Evidence Binding
  ↓
Semantic Page Graph
  ↓
Medical Verifier
  ↓
Compliance Check
  ↓
Approved Semantic Page Graph
  ↓
Functional Visual Renderer
  ↓
Visual Design
  ↓
Numerical QA / Semantic QA
  ↓
Medical Review Sheet
  ↓
人工确认 RED 风险项
  ↓
导出演示稿
```

---

## 6. MVP 功能需求

### F01｜项目创建

用户可设置：

- 项目类型；
- 受众；
- 目标；
- 时长；
- 语言；
- 输出类型；
- 输出渠道；
- 是否允许外部资料；
- 是否允许模拟病例。

验收：
- 项目参数可保存、修改并进入审计日志。

### F02｜PDF 导入

系统支持：

- PDF 文件上传；
- 保存文件哈希；
- 建立 Document ID；
- 解析页码、正文、表格、图注等。

验收：
- 用户可在 Source Viewer 中查看源文档与页码。

### F03｜Claim Table

Claim Table 是系统的 Source Fact Layer，不是摘要表。其职责是把原始医学资料拆成最小可验证的医学命题，并永久绑定原始出处。

**Claim Table v0.1 冻结规则：**

1. 一个 Claim 只表达一个可独立验证的医学命题。
2. 同时保存 `source_quote` 与 `normalized_claim`。
3. 数字、阈值、推荐类别、证据等级必须单独结构化并可锁定。
4. `SOURCE / SUMMARY / SYNTHESIS` 从 Claim 层开始标识。
5. Claim 只存事实；医学关系全部进入 Edge，不在 Claim 阶段偷偷推导。
6. 同一事实多来源合并为 Canonical Claim；冲突来源绝不自动融合。
7. 任何需要外部医学知识才能补全的内容，不得标记为 SOURCE。

**MVP 最低能力：**

- 原子化 Claim；
- SourceRef；
- 原始上下文；
- Canonical Claim；
- Conflict Group；
- NumericFact；
- 推荐类别；
- 证据等级；
- Population / Condition / Timeframe 等关键限定条件；
- RED / YELLOW / GREEN 风险分级。

**验收：**

- 关键 Claim 具备原文页码、source_quote 与 SourceRef；
- 关键数字可从 Claim 文本中独立核对；
- 多来源同义 Claim 不重复堆积；
- 冲突内容不得被自动平均、折中或合并；
- Claim Extractor 不得创建未经来源支持的医学关系。

### F04｜SOURCE / SUMMARY / SYNTHESIS

每个 Claim、Node、Edge 都必须可标记：

- SOURCE；
- SUMMARY；
- SYNTHESIS。

验收：
- 用户可筛选查看三类内容；
- SYNTHESIS 不能静默伪装成 SOURCE。

### F05｜Information Triage

Information Triage 的目标是判断一个 Claim **是否进入本次汇报及进入哪一层**，而不是判断其医学上的绝对重要性。

**Information Triage v0.1 冻结规则：**

1. Triage 的目标是决定“是否进入本次汇报”，而不是判断医学上的绝对重要性。
2. `Presentation Question` 是最高层筛选条件，必须在 Triage 前明确。
3. Triage 同时考虑 Audience、Project Type、Goal、Duration，而不是只按 Claim 重要度排序。
4. Risk Level 是约束条件而不是简单评分权重；RED 不等于全部必须展示。
5. 删除限定条件会改变医学意义时，相关 Claims 必须作为 `Meaning-Preserving Bundle` 共同处理。
6. 输出固定为 `MUST_INCLUDE / SHOULD_INCLUDE / APPENDIX / EXCLUDED`；EXCLUDED 永不删除原始 Claim。
7. 每个 Triage Decision 必须提供可解释 reason，并允许用户 Override，所有 Override 进入审计日志。
8. Triage 只决定内容选择与 `Presentation Dependency`，不负责创造医学关系，也不负责生成页面。

**Triage 决策至少考虑：**

- Question Relevance；
- Audience Relevance；
- Narrative Necessity；
- Evidence Importance；
- Source Centrality；
- Risk Constraint；
- Presentation Cost。

**验收：**

- 同一材料面对不同 Audience 时 MUST/SHOULD/APPENDIX 应明显不同；
- 同一 Audience 面对不同 Presentation Question 时结果应明显不同；
- MUST 内容超过时长预算时必须请求用户收窄范围，而不是静默删除关键内容。

### F06｜Clinical Narrative / Medical Information Architect

Medical Information Architect 负责“怎么讲”，不负责判断医学事实是否成立。它接收 Triage 后的内容，生成 NarrativePlan 与 PageSpec，但不直接制作最终视觉页面。

**Medical Information Architect v0.1 冻结规则：**

1. Architect 的任务是组织“怎么讲”，不负责决定医学事实是否成立。
2. 每套汇报必须围绕 Presentation Question 建立一个 Narrative Spine，而不是复制源文档目录。
3. Narrative Spine、Section 标题和 Primary Message 均必须保留 `SOURCE / SUMMARY / SYNTHESIS` provenance。
4. 每页必须有一个明确 Page Goal 和唯一 Primary Message；Supporting Claims 只用于支撑该核心信息。
5. 页面信息固定按 `Primary Message → Supporting Claims → Conditions/Data → Source` 四层组织。
6. Meaning-Preserving Bundle 不得因排版、页数或时长被拆到足以改变医学意义。
7. Architect 可以建立 Presentation Dependency 和推荐 Functional Visual，但不得创建未经验证的 Clinical Edge。
8. Audience Adaptation 在 Architect 层主要改变认知顺序和叙事深度，而不改变底层 Claim。
9. Architect 只生成 NarrativePlan / PageSpec，不生成最终视觉页面，也不得为了“故事完整”补充原文不存在的医学内容。
10. 用户可以调整 Section/Page 顺序和 Narrative，但所有 Override 必须记录，且 Presentation Order 的变化不得自动改变 Clinical Relationship。

**页面结构：**

- Level 1：Primary Message；
- Level 2：Supporting Claims；
- Level 3：Conditions / Data / Caveats；
- Level 4：Source。

**验收：**

- Narrative 应由 Presentation Question 驱动，而不是复刻原文目录；
- 同一 Claim Pool 面对不同受众时，叙事顺序与深度应发生合理变化；
- Architect 可建议 Decision Map / Evidence Map，但不得自行新增临床箭头。

### F07｜Semantic Relationship & Evidence Binding

该模块不是“画箭头模块”，而是负责验证并绑定**任何会让听众产生语义关系理解的演示表达**。

系统需要处理的关系包括但不限于：

1. Claim ↔ Claim；
2. Title / Primary Message ↔ Claim；
3. Data / NumericFact ↔ Claim；
4. Data ↔ Metric / Outcome / Population / Timeframe；
5. Legend ↔ Data Series；
6. Axis ↔ Metric / Unit；
7. Annotation ↔ Data Comparison；
8. Section / Page ↔ Context；
9. Visual Group ↔ Meaning；
10. Node ↔ Node / Clinical Relationship。

核心目标：

> 最终页面中任何被标题、顺序、分组、位置、颜色、线条、图例、坐标轴、注释或箭头表达出的“关系”，都必须存在明确的语义绑定与 provenance。

#### 关系 provenance

所有关键 Semantic Relationship 均使用：

- `SOURCE`：原文明确表达该关系；
- `SUMMARY`：对原文已有关系进行忠实压缩；
- `SYNTHESIS`：由多个 Claim / Source 组合形成的关系。

RED + SYNTHESIS 关系必须进入人工医学审核。

#### 六类核心子模块

- **04A Clinical Relationship Builder**：诊断、分型、治疗、时间、因果、条件等临床关系候选；
- **04B Evidence Binding**：推荐、研究、结局、证据等级、局限的绑定；
- **04C Data Binding**：NumericFact 与 Metric / Outcome / Population / Timeframe 的绑定；
- **04D Title / Claim Entailment**：标题、Primary Message、Section Title 是否被 Claim 充分支持；
- **04E Contextual Relationship Checker**：页面顺序、上下文是否产生来源外推理暗示；
- **04F Visual Semantic Binding**：Legend / Series / Axis / Color / Grouping / Annotation 等视觉语义绑定。

#### 验收

- 页面标题必须能明确映射到支持它的 Claim；
- 数字不仅要“数值正确”，还必须绑定正确的 Metric / Outcome / Population / Timeframe；
- 图例必须绑定正确数据系列；
- 颜色若表达风险 / 推荐 / 禁忌等语义，则必须纳入 Semantic Binding；
- 页面相邻或视觉分组不得自动升级为 Clinical Relationship；
- Design Agent 不得新增任何 Semantic Relationship；
- 所有关键关系必须有 provenance；
- RED SYNTHESIS 关系不得自动批准。

### Module 04 第一批冻结规则｜Semantic Assertion & Title Entailment

以下 8 条已正式冻结：

1. **任何能够让合理听众推断事实、比较、归属、条件、因果、支持、时间或临床关系的页面表达，都属于 Semantic Relationship / Binding，必须可识别、绑定和审计。**
2. **所有具有事实或结论性质的 Narrative Spine、Section Title、Slide Title、Primary Message 和 Chart Title 必须显式绑定一个或多个底层 Claim。**
3. **标题和 Primary Message 的语义强度不得超过底层 Claim 能支持的最大语义强度。**
4. **标题不得通过删除 Population、Condition、Timeframe、Exclusion 等必要限定条件扩大医学适用范围。**
5. **多个 SOURCE Claim 组合产生的新判断，不得自动继承 SOURCE provenance；没有来源明确支持该组合关系时必须标记为 SYNTHESIS。**
6. **任何为了演示效果进行的标题润色或压缩，都不得删除改变医学含义的限定词，也不得将不确定、相关或弱推荐升级为确定、因果或强推荐。**
7. **存在 SourceRef 不等于标题得到支持；Title / Claim Entailment 必须独立判断 `SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONFLICT / NEEDS_HUMAN_REVIEW`。**
8. **Narrative Spine、Section Title、Slide Title、Primary Message、Chart Title 必须保存 `SOURCE / SUMMARY / SYNTHESIS` provenance。**

状态：`FROZEN v0.1 / Batch 1`


### Module 04 第二批冻结规则｜Data ↔ Claim / Data Binding

以下 12 条已正式冻结：

1. **任何进入演示的医学数据都必须同时绑定 Value 与其必要语义上下文，包括 Metric、Unit、Population/Subgroup、Outcome、Timepoint/Timeframe、Intervention/Comparator、Statistic Type 和 Source；缺失会改变医学意义的关键维度时不得视为完整绑定。**
2. **数值一致不等于 Data Binding 正确；Value、Metric、Outcome、Population、Time、Group 等任一关键语义绑定错误，都必须判定失败。**
3. **任何用于支持页面 Claim 的数据都必须显式建立 `DATA_SUPPORTS_CLAIM` 或等价绑定；空间邻近、同页展示或视觉分组不得自动视为证据支持。**
4. **Baseline、Final Value、Change from Baseline、Absolute Change、Relative Change、Absolute Risk、Relative Risk 等数据角色必须显式区分，禁止相互替代。**
5. **Effect Estimate、CI、P Value、Numerator/Denominator 等统计对象必须绑定到其准确的 Comparison、Outcome、Population 和 Timeframe，不能作为脱离语境的独立数字使用。**
6. **由系统计算得到但原文未明确给出的数值不得继承 SOURCE provenance；必须记录输入数据、公式和 `DERIVED_CALCULATION`，并按 SYNTHESIS 管理。**
7. **自动衍生只允许白名单内的确定性计算；复杂医学统计推导、跨研究标准化或可能改变临床解释的计算不得自动生成，必须使用来源结果或进入人工审核。**
8. **单位换算、格式化和舍入必须保留原始 Value/Unit 与转换记录；不得因自动舍入、单位转换或格式统一跨越诊断阈值、剂量或其他临床边界。**
9. **0、Missing、NA、NR、Not Measured、Not Applicable 和 Unknown 必须明确区分；系统不得将缺失数据自动转换为0，也不得自行插补来源未提供的值。**
10. **从图形、OCR或不确定来源估算的数据必须显式标记估算来源与置信状态，不得作为精确 SOURCE 数据呈现。**
11. **跨研究、跨人群、跨Endpoint或跨时间窗口的数据在进入直接比较图前必须具有明确的 Comparability 状态；未证明可比的数据不得因并排视觉呈现而暗示直接优劣关系。**
12. **Data Binding 状态固定为 `BOUND / PARTIALLY_BOUND / UNBOUND / CONFLICT / NEEDS_HUMAN_REVIEW`；RED 数据只有 BOUND 或经人工明确批准后才允许进入 Approved Semantic Page Graph。**

状态：`FROZEN v0.1 / Batch 2`


### Module 04 第三批冻结规则｜Clinical Relationship

以下 14 条已正式冻结：

1. **Clinical Relationship 的 provenance 必须独立于组成它的 Claim provenance；两个 SOURCE Claim 并不自动产生 SOURCE Relationship。**
2. **任何 Clinical Relationship 必须结构化记录 `relation_type`、`direction`、`source/provenance`、`risk`、`conditions` 和 `review status`，不能只保存无语义的 A→B。**
3. **SOURCE Clinical Relationship 必须由来源明确支持关系的存在、类型和方向；来源只分别支持两个节点时不得标记为 SOURCE Relationship。**
4. **Clinical Relationship 的方向必须独立验证；关联、预测、时间先后和因果不得相互替代，也不得自动反向。**
5. **Clinical Relationship 默认禁止自动传递推理；即使 A→B 和 B→C 均成立，也不得自动生成 A→C。**
6. **任何会改变关系医学意义的 Population、Condition、Timeframe、Exclusion、Dose 等限定必须与关系共同绑定；不得为了简化图形删除必要条件。**
7. **多条件关系必须显式保存 AND / OR / NOT / EXCEPT 等逻辑；视觉布局不得改变原始逻辑运算。**
8. **否定、禁忌、不推荐、排除和不适用必须作为明确 Clinical Relationship 类型或 polarity 保存，不得仅依赖视觉小字表达。**
9. **推荐强度、Recommendation Class 和 Evidence Level 必须绑定到对应的推荐关系，不能只附着在药物或治疗节点上。**
10. **Temporal、Associative、Predictive 和 Causal Relationship 必须严格区分；时间顺序或统计关联不得自动升级为因果。**
11. **多个来源组合形成完整临床路径时，单个关系仍保留各自 SourceRef，整个组合路径必须按 SUMMARY/SYNTHESIS 独立标记，不得伪装成某单一来源的完整算法。**
12. **来源未明确连接的临床节点不得因叙事完整、版面美观或流程闭环需求被自动补齐；系统必须允许不完整路径。**
13. **Clinical Relationship 状态固定为 `SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONFLICT / AMBIGUOUS / NEEDS_HUMAN_REVIEW`；RED SYNTHESIS、关系冲突或关键条件不完整不得自动进入 Approved Semantic Page Graph。**
14. **任何最终具有医学含义的视觉连接必须绑定唯一或明确的一组 Clinical Relationship ID；Design/Renderer 不得显示来源于其自身推理的新临床连接。**

状态：`FROZEN v0.1 / Batch 3`


### Module 04 第四批冻结规则｜Contextual Relationship

以下 11 条已正式冻结：

1. **Contextual Relationship 指由同页上下文、相邻页面、Section 结构、叙事顺序或承接表达使目标受众合理推断出的 Semantic Relationship；系统必须审核实际产生的隐含语义，而不能只审核显式文字和箭头。**
2. **Presentation Order、Presentation Dependency、Contextual Implication 和 Clinical Relationship 必须作为不同对象保存；演示顺序或解释依赖不得自动转换为临床关系。**
3. **Contextual Relationship 检测至少覆盖 Intra-page、Adjacent-page 和 Section 三个范围；关键医学关系不得只做单页孤立审核。**
4. **“因此、所以、基于上述、下一步、相比之下、优先、随后”等能够建立因果、条件、决策、比较或时间关系的承接表达必须作为 Semantic Trigger 接受关系验证，不能仅按普通文案处理。**
5. **Population、Subgroup、Outcome、Timeframe、Intervention、Comparator 等医学上下文不得因页面相邻而自动跨页继承；需要跨页省略时必须通过显式 Context Contract 记录继承范围和来源。**
6. **Context Contract 在新研究、新指南、新 Population、新 Intervention、新病例、新 Section 或其他实质语义边界出现时必须 Reset 或显式 Override，禁止旧上下文静默污染新内容。**
7. **相邻页面或连续结构形成隐含比较时，必须调用 Comparability 信息；未证明可比的跨研究、跨人群、跨 Endpoint 或跨时间数据不得通过叙事并列暗示直接优劣。**
8. **Clinical Implication、Practice Impact、Take-home、Conclusion 等从 Evidence 向临床意义过渡的内容必须单独进行 Contextual Entailment；研究结果不得因进入“临床意义”页面而自动升级为诊断、治疗或决策关系。**
9. **问句、反问句和标题中的预设同样属于 Semantic Assertion；如果问题本身预设了未经验证的临床关系，必须按该隐含关系接受审核。**
10. **Contextual Implication 的状态固定为 `NO_MATERIAL_IMPLICATION / SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONFLICT / AMBIGUOUS / NEEDS_HUMAN_REVIEW`；若隐含的是 RED Clinical Relationship，则继承 RED 风险规则。**
11. **Contextual Relationship Checker 只负责检测、描述和定位隐含关系及风险，不得自行补充医学关系或修改底层 Claim；发现 unsupported implication 时应通过调整叙事、增加限定、Context Reset、分隔内容或人工审核解决。**

状态：`FROZEN v0.1 / Batch 4`


### Module 04 第五批冻结规则｜Visual Semantic Binding & Medical Visual Provenance

以下 15 条已正式冻结：

1. **Visual Semantic Binding 必须区分 Pure Styling 与 Semantic Visual Encoding；任何会改变听众对医学事实、关系、比较、层级、风险、推荐、时间或归属理解的视觉属性都属于 Semantic Encoding，不得由 Design Agent 自由决定。**
2. **Grouping、proximity、alignment、enclosure、position、hierarchy 等空间布局如果会表达归属、对应、先后或临床关系，必须存在显式 Visual Binding；“只是排版”不能作为绕过审核的理由。**
3. **颜色、深浅、渐变、大小、粗细、字体强调等只有在不承担医学含义时才属于 Pure Styling；一旦用于表达风险、疗效、证据、推荐、禁忌、优先级或程度，就必须结构化绑定其 Semantic Meaning。**
4. **Visual Hierarchy 必须区分 Presentation Priority 与 Clinical Priority；为了讲述顺序进行的强调不得被系统或视觉呈现解释为医学重要性、推荐强度或证据等级。**
5. **Legend、Data Series、Axis、Metric、Unit、Category、Annotation、Comparison 和 Symbol 必须建立显式绑定；任何 Legend/Series、Axis/Metric、Annotation/Comparison 或医学符号映射错误都必须判定失败。**
6. **坐标范围、比例尺、线性/对数尺度、截断轴和其他视觉尺度设置不得造成与真实数据差异或效应大小明显不相称的视觉结论；Visual QA 必须检查 Statistical/Visual Misrepresentation。**
7. **任何具有医学含义的 Connector、Arrow、Inhibition Symbol、Activation Symbol、Up/Down Indicator 等必须绑定已批准 Semantic/Clinical Relationship，不得由 Renderer 或 Design Agent新增或改变关系类型。**
8. **所有医学专用图必须分别记录 Medical Semantic Provenance 与 Visual Asset Provenance；“医学内容依据什么”与“视觉资产从哪里来”不得混为同一个来源字段。**
9. **医学图 Visual Origin 固定至少支持 `SOURCE_FIGURE / ADAPTED_FROM_SOURCE / REDRAWN_FROM_EVIDENCE / MEDICAL_REFERENCE_ASSET / AI_GENERATED_MEDICAL_VISUAL`，不同来源类型必须使用对应的 QA 与风险策略。**
10. **ADAPTED_FROM_SOURCE、SEMANTIC_SIMPLIFICATION 和 REDRAWN_FROM_EVIDENCE 必须进行 Semantic Fidelity QA；重绘、简化或重新布局不得改变原始节点、方向、条件、AND/OR逻辑、限定或关系强度。**
11. **AI_GENERATED_MEDICAL_VISUAL 默认 `medical_verified=false`；视觉真实感、专业风格或科学风格不能替代医学验证，未经 Medical Visual QA 的AI医学图不得作为已验证医学事实图交付。**
12. **承担医学语义的专用图应尽可能保存为可审计的 Semantic Objects + Relationships + Bindings，而不是仅保存为不可解析的 PNG/SVG；最终图像是 Renderer Output，不是医学事实的唯一载体。**
13. **医学专用图必须计算关键 Node 与 Relationship Provenance Coverage；RED Medical Visual 的关键节点和关键关系必须达到100% provenance coverage，无法溯源部分不得静默保留。**
14. **嵌入图片中的文字、数字、阈值、推荐、标签和结论仍必须经过 Claim、Data Binding、Clinical Relationship 和 Semantic QA；内容进入图像后不得逃逸既有审核体系。**
15. **Visual Asset 的医学有效性与版权许可必须分离管理；SOURCE_FIGURE、参考图库和外部资产必须保存 copyright/license/commercial_use/adaptation_allowed/citation_required 状态，版权状态不明确时不得默认可用于商业交付或公开传播。**

状态：`FROZEN v0.1 / Batch 5`


### F08｜Semantic Page Graph & Functional Visual Rendering

Medical Information Architect 输出 PageSpec 后，系统先构建并验证 `Semantic Page Graph`，再进入 Functional Visual Renderer。

`Semantic Page Graph` 至少包含：

- Title / Primary Message；
- Claim Objects；
- Numeric / Data Objects；
- Source Objects；
- Semantic Relationships；
- Visual Encoding Contract；
- Risk / Provenance；
- Allowed / Forbidden Bindings。

Functional Visual Renderer 只能将已批准 Semantic Page Graph 渲染为：

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

原则：

> Decision Map、Evidence Map 等不再各自重新“理解医学关系”，而只是同一 Approved Semantic Page Graph 的不同渲染形式。

验收：

- Renderer 不得创建新医学关系；
- Renderer 不得改变 Legend / Series / Axis / Grouping 的既定语义绑定；
- Pure Styling 与 Semantic Layout 必须区分；
- Semantic Layout 只能依据已批准 Visual Encoding Contract。

### F09｜Numerical Check

强制核对：

- 数字；
- 百分比；
- 单位；
- 剂量；
- 阈值；
- 时间；
- 样本量；
- HR / OR / RR / CI / P；
- 推荐类别；
- 证据等级。

验收：
- 任一关键数字不一致时阻止自动交付。

### F10｜Medical Review Sheet

聚合：

- RED 高风险项；
- 未验证 Semantic Relationship；
- 数字冲突；
- 来源不足；
- SYNTHESIS 关键语义关系。

验收：
- 医生无需逐页重审，可集中确认高风险项目。

### F11｜Compliance Check

按渠道执行：

- 患者隐私；
- 医院/医生/机构标识；
- 版权与引用；
- 医疗效果承诺；
- 药品推广倾向；
- 未授权背书；
- 站外导流；
- 免责声明。

### F12｜Visual Design

设计 Agent 只能处理 `Approved Semantic Page Graph + Visual Encoding Contract`。

可自由决定的 **Pure Styling**：

- 字体与字号；
- 留白；
- 非语义装饰色；
- 背景；
- 非语义线宽；
- 纯视觉间距与美术细节。

不得自由改变的 **Semantic Layout / Encoding**：

- 哪些对象属于同一组；
- 哪个标题对应哪些内容；
- 哪条线连接哪些对象；
- Legend 对应哪个 Data Series；
- Axis 对应哪个 Metric / Unit；
- Annotation 对应哪个数据比较；
- 哪个颜色代表哪个风险 / 推荐 / 禁忌语义；
- 哪个标签属于哪个数字；
- 临床节点之间的先后、条件、因果或治疗关系。

不可修改：

- Locked Fields；
- 关键医学事实；
- NumericFact；
- 推荐等级；
- 证据等级；
- 已批准 Semantic Relationship；
- 已批准 Visual Binding。

原则：

> Visual Design Agent 不得新增任何 Semantic Relationship，即使没有使用箭头。

### F13｜双层交付

至少支持：

1. Presentation Deck；
2. Reference Layer。

后续扩展：

- Speaker Notes；
- Backup Slides。

### F14｜Source Traceability

最终页关键结论应可回到：

- 文档；
- 页码；
- 推荐条目；
- 证据等级；
- 参考文献。

---

## 7. 医学图形语言

系统优先采用 Functional Visual：

| 原始内容 | 输出图形 |
|---|---|
| 复杂治疗表 | Clinical Decision Map |
| 推荐段落 | Evidence Map |
| 病例经过 | Disease Timeline |
| 发病机制 | Mechanism Map |
| 风险分层 | Risk Stratification Map |
| 疗效结果 | Outcome Plot |
| 随访管理 | Management Cycle |
| 研究证据 | Trial Evidence Matrix |

默认弱化：

- 医生照片；
- 药瓶；
- 听诊器；
- 泛用医疗图标；
- 与内容无关的人体剪影；
- 装饰性图库图片。

---

## 8. Audience Adaptation

系统在 Information Triage 之前必须确认 Audience。

### 专科专家
保留：

- FEV1；
- EOS；
- ABE；
- Evidence Grade；
- Treatment Algorithm。

### 规培医生
强调：

- 如何识别；
- 如何分层；
- 如何处理；
- 什么时候升级。

### 医学生
强调：

- 疾病是什么；
- 为什么发生；
- 怎么判断；
- 核心治疗原则。

---

## 9. 风险分级

### GREEN
允许自动压缩：

- 历史背景；
- 重复性描述；
- 非关键定义补充；
- 低风险背景信息。

### YELLOW
可总结但保留来源：

- 机制；
- 研究结果；
- 技术特点；
- 适用场景；
- 一般性管理建议。

### RED
不得擅自删减或改变：

- 诊断阈值；
- 药物剂量；
- 禁忌证；
- 特殊人群；
- 推荐类别；
- 证据等级；
- 时间节点；
- 排除条件；
- 风险提示；
- 适应证。

---



### F15｜Rule Enforcement / Policy Engine

系统中的“允许 / 禁止 / 必须 / 不得”不能只依赖 Prompt。所有冻结规则必须明确：

- 谁负责执行；
- 谁负责验证；
- 违反后采取什么动作；
- 是否需要人工确认。

规则统一分为三类：

#### A｜Hard Constraint

由确定性系统执行，例如：

- JSON Schema；
- API Capability；
- RBAC / Agent Permission；
- State Machine；
- Deterministic Validator。

典型规则：

- Architect 不得写 Claim；
- Triage 不得创建 Clinical Edge；
- `source_type=SOURCE` 时必须存在 SourceRef；
- `synthetic_case=false` 时不得创建 SyntheticCase；
- Numeric mismatch 不得进入 Delivered。

违反动作：`BLOCK`。

#### B｜Semantic Constraint

需要语义判断，例如：

- SUMMARY 是否改变原文语气；
- 是否遗漏适用人群；
- 是否把相关性写成因果；
- 是否通过文字暗示了不存在的 Clinical Edge。

执行者：

- Semantic QA；
- Medical Verifier。

违反动作：

- `BLOCK`；
- 或 `HUMAN_REVIEW`。

#### C｜Human-governed Constraint

系统能够识别风险，但不应自行做最终临床裁决，例如：

- 多个权威来源冲突；
- RED SYNTHESIS Edge；
- 指南边界存在合理争议；
- 需要医生确认的关键医学解释。

违反 / 未决动作：`HUMAN_REVIEW_REQUIRED`。

#### Policy Engine

Policy Engine 是确定性的规则执行与状态门控层，不是普通 LLM Agent。

职责：

1. 读取 Rule Registry；
2. 验证 Agent 是否越权；
3. 汇总 Schema / Permission / QA / Medical Review 结果；
4. 决定对象是否可进入下一状态；
5. 输出 PASS / BLOCK / HUMAN_REVIEW_REQUIRED；
6. 将违规记录写入 Audit Log。

Policy Engine 与 Orchestrator 分工：

- **Orchestrator**：决定下一步调用哪个模块；
- **Policy Engine**：决定当前结果是否有资格进入下一步。

验收：

- 每条冻结规则都有唯一 `rule_id`；
- 每条规则均有 `constraint_type / enforced_by / validated_by / violation_action`；
- Agent 越权不能仅依赖 Prompt 检测；
- Hard Constraint 必须存在程序级阻断；
- 未通过 Policy Gate 的对象不得进入下一状态。


## Module 05｜Medical Verifier & Source Fidelity Gate

Medical Verifier 是从“已建模医学语义”进入“可批准内容”的来源忠实度验证层。默认不承担临床决策，也不以模型常识替代来源。

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


## Module 06｜Prompt-driven Medical Visual Generation

定位：以 `Approved Semantic Page Graph` 为唯一医学语义输入，先生成 `Visual Generation Contract`，再由模型特定 Prompt Compiler 编译为图像生成提示词。PPT 仅作为最终交付容器，不作为视觉生成引擎。

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



### Module 06 Batch 2 架构草案｜Visual Strategy Selector v0.2（未冻结）

#### 目标

Visual Strategy Selector 不负责“画得漂亮”，而负责把已审核医学信息结构映射到最合适的功能视觉，并同时决定该视觉应使用何种生成策略。

核心输出不是单一 `visual_type`，而是结构化 `VisualStrategyDecision`：

```text
Approved Semantic Page Graph
        ↓
Visual Intent Classifier
        ↓
Standard Override Resolver
        ↓
Information Structure / Data Shape Analyzer
        ↓
Hard Constraint & Exclusion Engine
        ↓
Candidate Generator
        ↓
Visual Strategy Scoring
        ↓
Generation Strategy Router
        ↓
VisualStrategyDecision
        ↓
Visual Generation Contract
```

#### 核心原则

- 先判断医学/统计信息结构，再选图；
- Hard Rule 与标准化医学图形优先于审美偏好；
- Invalid Candidate 先排除，再评分；
- Visual Strategy 与 Generation Strategy 分离；
- Table / Matrix 是正式视觉策略，不是失败兜底；
- 无合适图形结构时允许“不强行画图”。

状态：`FROZEN v0.1 / Batch 2`


#### 反向审查结论：三层治理结构

Batch 2 不把具体图形映射、评分权重和阈值全部冻结，而分为：

1. **Layer 1｜Frozen Selector Constitution（待冻结候选）**
   - 只定义长期稳定的医学、统计、逻辑与审计边界。
2. **Layer 2｜Versioned Visual Policy Registry（版本化策略库）**
   - 维护 Taxonomy、Information→Visual Mapping、标准化视觉惯例、Visual Type 可用生成策略等。
3. **Layer 3｜Calibration Config（可调参数）**
   - 维护评分权重、Penalty 权重、选择阈值、Ambiguity Margin、Audience / Project 偏好。


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

说明：
- 冻结的是 Selector 的长期稳定边界与决策宪法；
- `MedicalVisualTaxonomyRegistry / VisualMappingPolicyRegistry / StandardVisualPolicyRegistry / GenerationStrategyPolicyRegistry` 保持版本化、非冻结；
- `SelectorScoringConfig / PenaltyConfig / SelectionThresholdConfig / AmbiguityMargin / Audience & Project weighting` 保持可校准、非冻结。


#### 不冻结的部分

- Medical Visual Taxonomy 具体成员；
- Information → Visual 的推荐映射；
- 标准图形优先级强度；
- Scoring 权重；
- Penalty 权重；
- 选择阈值；
- Ambiguity Margin；
- Audience / Project-specific weighting；
- 具体 Visual Type → Generation Strategy 的永久一一映射。

这些内容通过版本化 Registry / Config 演进。


### Module 06 Batch 3｜Generation Strategy Router v0.1 — FORMALLY FROZEN

#### 定位

Generation Strategy Router 不决定“医学上应该画什么”，只决定**已经选定的 Visual Strategy 应该通过什么技术路径实现**。

关键原则：

```text
Visual Strategy Decision
        ↓
Decompose into Generation Components
        ↓
Hard Routing Gates
        ↓
Capability Registry
        ↓
Valid Engine Candidates
        ↓
Soft Optimization
        ↓
PageGenerationPlan
```

Router 采用**组件级路由**，而不是强迫整页只使用一种生成方式。

典型组件：

- DATA_GEOMETRY
- SEMANTIC_DIAGRAM
- EXACT_TEXT
- MEDICAL_VISUAL_ASSET
- EDITORIAL_COMPOSITION
- DECORATIVE_BACKGROUND

典型执行器：

- DETERMINISTIC_CHART
- DETERMINISTIC_DIAGRAM
- EXACT_CONTENT_COMPOSITOR
- VERIFIED_MEDICAL_ASSET_RENDERER
- PROMPT_DRIVEN_IMAGE
- HYBRID_COMPOSITION

页面只要存在精确数据几何、Meaning-Critical Clinical Logic 或高风险 Exact Text，通常进入 `CONTROLLED_COMPOSITION`；只有所有关键内容均允许自由图像生成时，才可能进入 `FULL_IMAGE`。

状态：`FROZEN v0.1 / Batch 3`

#### Batch 3 第二轮反向审查结论


#### Batch 3 最终冲突审查摘要

- Batch 2 与 Batch 3 的 Generation Strategy 归属已拆分为：`preferred_generation_strategy` vs `effective_generation_route`；
- Batch 1 的 `generation_mode` 改由 Batch 3 Router + FullImageEligibilityPolicy 计算后写入 VisualGenerationContract；
- Router 不重做 Module 05 的 Source Fidelity / Clinical Correctness 判断；
- Exact Geometry、Topology、Exact Text、Asset Rule 在 Batch 3 只作为 Engine/Route Capability Gate，不重复定义上游医学语义；
- Protected Semantic Layer 允许 semantic-invariant 的格式转换/整体缩放，但禁止会改变几何、绑定、可读性或医学含义的生成式重绘；
- Generation Execution Provenance 与 Medical Semantic Provenance / Visual Asset Provenance 分离；
- 14 条规则已完成冲突审查并正式冻结。

Batch 3 不冻结具体 Engine、Provider、FULL_IMAGE 判定阈值或软评分权重，而采用三层治理：

1. **Frozen Router Constitution（待冻结候选）**
   - 14 条长期稳定的实现边界。
2. **Versioned Routing Policy Registry**
   - 组件分类、Strategy、Engine Capability、FULL_IMAGE Eligibility、Fallback、Data Egress、Asset Generation 等策略。
3. **Calibration / Optimization Config**
   - 仅用于已经通过 Hard Qualification 的合法执行器之间优化视觉质量、可靠性、可编辑性、延迟与成本。

#### 14 条 Hard Rule 冻结候选（当前未冻结）

1. Implementation-only Authority Rule
2. Semantic-granularity Routing Rule
3. Hard Fidelity Gate Before Optimization Rule
4. Exact Quantitative Geometry Rule
5. Semantic Topology Lock Rule
6. Exact Text Authority Rule
7. Asset-contract Binding Rule
8. Protected Semantic Layer Rule
9. Data Boundary / Egress Rule
10. Qualified Capability Rule
11. No Semantic Degradation Fallback Rule
12. Material Capability Change Invalidation Rule
13. Generation Provenance Rule
14. Verification-aware Routing Rule

其中：
- Batch 1 的 Lock Model 直接继承，不在 Batch 3 重复冻结；
- `FULL_IMAGE Eligibility` 改为版本化 Routing Policy，不作为独立宪法规则；
- Capability Registry 的具体能力值不冻结；
- Soft Optimization 只对 Qualified Engine Set 生效。



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


## 9A. 核心功能冻结状态

| 模块 | 版本 | 状态 | 关键产物 |
|---|---|---|---|
| Claim Table | v0.1 | FROZEN | Atomic Claim / Canonical Claim / SourceRef / NumericFact |
| Information Triage | v0.1 | FROZEN | TriageDecision / Meaning-Preserving Bundle / Presentation Dependency |
| Medical Information Architect | v0.1 | FROZEN | NarrativePlan / Section / PageSpec / Primary Message |
| Rule Enforcement / Policy Engine | v0.1 | FROZEN | Rule Registry / Policy Gate / Violation Record |
| Semantic Relationship & Evidence Binding | v0.1 | FROZEN | Batch 1：Semantic Assertion / Title Entailment 8条；Batch 2：Data Binding 12条；Batch 3：Clinical Relationship 14条；Batch 4：Contextual Relationship 11条；Batch 5：Visual Semantic Binding & Medical Visual Provenance 15条，共60条 |
| Medical Verifier & Source Fidelity Gate | v0.1 | PARTIALLY_FROZEN | Batch 1：Verifier Role & Source Fidelity 10条；Batch 2：Semantic Fidelity Verification 12条；Batch 3：Issue Resolution & Re-verification 14条；Batch 4：Cross-source Conflict & External Medical Verification 16条 |
| Prompt-driven Medical Visual Generation | v0.1 | PARTIALLY_FROZEN | Batch 1：Visual Generation Contract 14条；Batch 2：Visual Strategy Selector 13条；Batch 3：Generation Strategy Router 14条 |

后续模块不得绕过以上冻结规则。若需要改变行为，必须升版并记录变更理由、影响范围与回归测试结果。

---

## 10. 非功能需求

### 10.1 可审计
任何最终页面都可回溯：

- 来源；
- Agent；
- 模型版本；
- Prompt 版本；
- 用户修改；
- 医学审核；
- 合规结果。

### 10.2 可编辑
最终 PPT 初稿应尽量保持可编辑结构。

### 10.3 可阻断
当出现以下情况时必须阻止自动交付：

- RED 项未确认；
- 关键数字不一致；
- 关键 Semantic Relationship 无来源且未人工确认；
- 隐私泄漏；
- 合规阻断项。

---

## 11. MVP 不做

- 自动诊断；
- 自动处方；
- 无人工确认的完整临床决策支持；
- 全自动公开发布；
- 自建完整文献搜索引擎；
- 复杂机构级知识库。

---

## 12. MVP 固定测试集

首个固定测试集：GOLD 2026 COPD 更新材料。

必须生成：

1. Management Paradigm Map；
2. Case Finding Clinical Decision Map；
3. Exacerbation Risk Evidence Map；
4. Disease Activity Framework；
5. Biologic Evidence Map；
6. COPD Management Cycle。

必须满足：

- 不主动虚构病例；
- 不补原文没有的疗效数字；
- 不擅自补完整诊疗算法；
- 关键节点有来源；
- 关键箭头有来源或 SYNTHESIS；
- 数字自动核验；
- 高风险内容进入 Medical Review Sheet。

---

## 13. 产品指标

### Source Fidelity
- Claim Source Match Rate；
- Number Match Rate；
- Recommendation Class Match Rate；
- Evidence Level Match Rate；
- Semantic Relationship Provenance Coverage。

### Presentation Quality
- One-slide-one-message rate；
- Audience Fit Score；
- Text Density；
- Functional Visual Ratio；
- Visual Clutter Score。

### Workflow Efficiency
- 上传到初稿时间；
- 医生人工审核项数量；
- 医生审核时间；
- 自动通过率；
- 人工返工率。

### Risk
- Unsupported Claim Rate；
- Unsupported Semantic Relationship Rate；
- Hallucinated Numeric Rate；
- Privacy Leakage Rate；
- Compliance Block Rate。

---

## 14. 第一阶段验收标准

MVP 通过必须满足：

1. 可导入一份医学 PDF；
2. 可输出结构化 Claim Table；
3. 关键 Claim 有页码与原文出处；
4. 关键数字自动比对；
5. 可构建一份 Semantic Page Graph 并渲染 Clinical Decision Map；
6. 可生成一张 Evidence Map；
7. 关键 Semantic Relationship 有 provenance，RED SYNTHESIS 可进入人工确认；
8. 未要求时不生成模拟病例；
9. RED 项进入 Medical Review Sheet；
10. 可输出演示稿初稿；
11. 最终页保留 Source Traceability；
12. 任一关键数字不一致时阻止自动交付。