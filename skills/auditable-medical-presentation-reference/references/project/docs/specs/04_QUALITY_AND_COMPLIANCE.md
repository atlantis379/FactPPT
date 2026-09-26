# 医学可审计演示系统｜QUALITY_AND_COMPLIANCE v0.1

> 本文档定义医学准确性、内容风险、隐私、渠道合规与人工审核机制。  
> 本文档同时作为已冻结 Claim / Triage / Architect 规则的质量守门规范。  
> 核心原则：**准确性依靠流程、来源与审计，而不是依赖模型“自信”。**

---

## 1. 两类“准确”

### 1.1 Source Fidelity

回答：

> 最终内容是否忠实于原始资料？

包括：

- 数字；
- 单位；
- 阈值；
- 推荐类别；
- 证据等级；
- 人群；
- 限定条件；
- 排除条件；
- 原文语气。

### 1.2 Clinical Correctness

回答：

> 这是否是对患者的正确临床判断？

系统不承担最终临床判断。

产品定位：

- 忠实整理资料；
- 辅助构建表达逻辑；
- 提示风险；
- 让医生确认高风险医学内容。

---

## 2. Source / Summary / Synthesis

### SOURCE
原文直接明确支持。

要求：
- source_quote；
- 页码；
- 章节 / 表格 / 推荐条目。

### SUMMARY
忠实压缩。

要求：
- 不改变语气；
- 不丢失关键条件；
- 保留来源。

### SYNTHESIS
跨段落、表格、文献重新组织。

要求：
- 显式标注；
- 关键关系必须验证；
- RED 医学关系进入人工确认。

---

## 3. 医学风险分级

### GREEN

可自动压缩：

- 历史背景；
- 重复描述；
- 非关键定义；
- 低风险背景信息。

### YELLOW

可总结但必须保留来源：

- 机制；
- 研究结果；
- 技术特点；
- 适用场景；
- 一般性管理建议。

### RED

不可擅自删减或改变：

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

## 4. Numerical QA

### 4.1 强制核对

- 数字；
- 百分比；
- 单位；
- 剂量；
- 阈值；
- 时间；
- 样本量；
- HR；
- OR；
- RR；
- CI；
- P value；
- 推荐类别；
- 证据等级。

### 4.2 结果

`MATCH`
- 与来源一致。

`WARNING`
- 格式不同但语义等价，需要确认。

`MISMATCH`
- 值或含义不一致。

### 4.3 阻断规则

关键 NumericalFact `MISMATCH`：
- 自动阻止交付；
- 创建 ReviewItem；
- 必须人工处理。

---

## 5. Semantic QA

重点检查：

### 5.1 限定条件丢失
例如：

原文：
> 对符合特定条件的人群可考虑……

错误压缩：
> 推荐所有患者……

### 5.2 语气升级

禁止：

- “可考虑” → “推荐”
- “可能” → “明确”
- “与……相关” → “导致”
- “支持” → “证明”

### 5.3 边界丢失

检查：

- 年龄；
- 人群；
- 条件；
- 排除；
- 时间；
- 风险范围；
- 适应证。

### 5.4 Synthesis 冒充 Source

任何跨段落重组都不能标为 SOURCE。

---

## 6. Semantic Relationship & Evidence Binding QA

质量控制对象不再仅限 Edge，而是任何会让听众推断“两个信息之间存在关系”的表达。

### 6.1 必须验证的关系类型

- Claim ↔ Claim；
- Title / Primary Message ↔ Claim；
- Data ↔ Claim；
- Numeric ↔ Metric / Outcome / Population / Timeframe；
- Legend ↔ Series；
- Axis ↔ Metric / Unit；
- Annotation ↔ Comparison；
- Color ↔ Semantic Meaning；
- Visual Group ↔ Meaning；
- Page / Context ↔ Implied Relationship；
- Node ↔ Node / Clinical Relationship。

### 6.2 Provenance

关键关系必须标：

- SOURCE；
- SUMMARY；
- SYNTHESIS。

RED + SYNTHESIS：
- 必须人工确认。

### 6.3 Title Entailment

检查：

- 标题是否被底层 Claim 支持；
- 标题是否扩大适用人群；
- 标题是否升级推荐语气；
- 标题是否把相关写成因果；
- 标题是否把可能写成确定。

规则：

> 标题的语义强度不得超过来源允许的最大语义强度。

### 6.4 Data Semantic Binding

数字正确还不够，还必须确认：

- 指标正确；
- 结局正确；
- 人群正确；
- 时间正确；
- 干预 / 对照正确；
- 单位正确。

### 6.5 Visual Semantic Binding

检查：

- Legend 是否绑定正确 Series；
- Axis 是否绑定正确 Metric / Unit；
- Annotation 是否指向正确比较；
- Color 是否改变风险 / 推荐含义；
- Grouping 是否制造未经批准的临床归属；
- Label 是否属于正确数字；
- Connector 是否对应已批准 Relationship。

### 6.6 Contextual Implication

页面相邻、连续出现、空间邻近不等于临床关系。

但如果上下文整体会让合理读者形成来源外临床推断，必须标记：

- `CONTEXTUAL_IMPLICATION_WARNING`
- 或 `HUMAN_REVIEW_REQUIRED`。

### 6.7 风险

典型 RED Semantic Relationship：

- 诊断标准 → 诊断；
- 条件 → 治疗；
- 生物标志物 → 药物选择；
- 药物 → 剂量；
- 症状 → 处理；
- 因果关系；
- 升级 / 降阶；
- 禁忌 / 排除。



## 6A. Module 04 第一批冻结质量规则

以下情况必须由 Title / Claim Entailment 或 Semantic QA 明确判断：

- 标题是否有支持 Claim；
- 标题语义强度是否超过来源；
- 是否丢失 Population / Condition / Timeframe / Exclusion；
- 多个正确 Claim 是否被组合成来源未支持的新结论；
- 是否因标题润色造成不确定性、相关性或推荐强度升级；
- 是否出现“有 SourceRef 但引用并不支持结论”的假溯源；
- 标题与 Primary Message 的 provenance 是否保留；
- 是否存在未建模但能让合理听众形成明确医学推断的页面表达。

`SUPPORTED` 以外的高风险结论不得直接进入 Approved Semantic Page Graph；RED 的 `PARTIALLY_SUPPORTED / CONFLICT / NEEDS_HUMAN_REVIEW` 必须进入 Medical Review Sheet。



## 6B. Module 04 第二批冻结质量规则｜Data Binding

Data QA 必须分成至少两层：

### Numerical QA
回答：
> 数字有没有抄错？

### Data Binding QA
回答：
> 这个数字是不是属于这个 Metric、Outcome、Population、Time、Group 与比较关系？

以下任一情况不得因数值匹配而 PASS：

- 正确数值绑定错误 Metric；
- 正确数值绑定错误 Outcome；
- 正确数值绑定错误 Population / Subgroup；
- 正确数值绑定错误 Timepoint / Timeframe；
- Baseline / Final / Change 混淆；
- Absolute / Relative 指标混淆；
- HR / CI / P value 对应错误比较；
- Numerator / Denominator 对应错误；
- Missing / NR 被转为 0；
- 估算值被当作精确 SOURCE；
- 跨研究不可比数据被直接用于优劣比较。

### RED Data Gate

当 DataBinding 为 RED：

- `BOUND` → 可继续；
- `PARTIALLY_BOUND` → HUMAN_REVIEW_REQUIRED；
- `UNBOUND` → BLOCK；
- `CONFLICT` → BLOCK / HUMAN_REVIEW_REQUIRED；
- `NEEDS_HUMAN_REVIEW` → HUMAN_REVIEW_REQUIRED。

### Derived Calculation

系统衍生值必须：

- 标记 `DERIVED_CALCULATION`；
- 保存公式；
- 保存输入数据；
- 保存计算版本；
- provenance = SYNTHESIS；
- 仅使用白名单计算。



## 6C. Module 04 第三批冻结质量规则｜Clinical Relationship

Clinical Relationship QA 必须独立检查：

### Provenance
- 两个 SOURCE Claim 不代表关系为 SOURCE；
- SOURCE Relationship 必须有直接关系证据。

### Direction
- 不自动反向；
- association ≠ prediction；
- prediction ≠ causation；
- temporal ≠ causation。

### Transitivity
默认禁止：
- A→B + B→C ⇒ A→C。

### Meaning-preserving conditions
必须检查：
- Population；
- Condition；
- Timeframe；
- Exclusion；
- Dose；
- AND / OR / NOT / EXCEPT；
- polarity。

### Recommendation Relationship
推荐强度、Class、Evidence Level 必须绑定正确 Relationship。

### Incomplete Path
若来源不存在 B→C：
- 系统允许 A→B 与 C→D 分离；
- 不得为了完整流程图生成 B→C。

### RED Relationship Gate

以下任一情况不得自动批准：

- RED + SYNTHESIS；
- CONFLICT；
- AMBIGUOUS 高风险关系；
- 关键 Condition 缺失；
- direction 未验证；
- recommendation strength 未验证。

### Visual Connector
所有医学语义 Connector 必须能够追溯到一个或明确的一组 Clinical Relationship ID。
视觉上出现无 Relationship ID 的医学连接：
- `UNAUTHORIZED_SEMANTIC_CONNECTOR`
- Policy Gate = BLOCK。



## 6D. Module 04 第四批冻结质量规则｜Contextual Relationship

### 检测范围

Contextual QA 至少检查：

1. Intra-page；
2. Adjacent-page；
3. Section。

### Semantic Trigger

以下表达应触发关系检查：

- 因此 / 所以 / 由此 / 从而；
- 基于上述；
- 下一步；
- 相比之下；
- 更优 / 更适合 / 优先；
- 随后 / 之后；
- 当 / 若 / 对于；
- Clinical Implication / Practice Impact / Take-home / Conclusion；
- 具有预设语义的问句 / 反问句。

### Context inheritance

禁止：
- 仅因页面相邻继承 Population / Outcome / Timeframe / Intervention / Comparator。

允许：
- 通过已验证 ContextContract 继承。

以下变化默认触发 Context Reset：

- New Study；
- New Guideline；
- New Population；
- New Intervention；
- New Case；
- New Section；
- 其他实质语义边界。

### Comparative implication

如果连续页面产生 A vs B 的隐含优劣关系：
- 必须检查 Comparability；
- `non_comparable / unknown` 不得直接形成比较结论。

### Evidence → Clinical Implication

研究结果进入 Clinical Implication / Take-home 时，不自动获得诊断、治疗或决策权限，必须重新做 Entailment / Relationship Verification。

### Question Presupposition

问句并非默认中性。
如果问句预设：
- 因果；
- 治疗选择；
- 禁忌；
- 诊断；
- 优劣；

必须把该预设作为 Semantic Assertion 审核。

### RED Contextual Gate

当 Contextual Implication 暗示 RED Clinical Relationship 时：
- SUPPORTED → 按 RED Policy；
- PARTIALLY_SUPPORTED / CONFLICT / AMBIGUOUS / NEEDS_HUMAN_REVIEW → HUMAN_REVIEW_REQUIRED；
- UNSUPPORTED → BLOCK。

### Checker 权限

Contextual Relationship Checker：
- 可检测；
- 可定位；
- 可建议调整叙事 / 增加限定 / Reset / 分隔；
- 不得修改 Claim；
- 不得自行建立新的 Clinical Relationship。



## 6E. Module 04 第五批冻结质量规则｜Visual Semantic Binding & Medical Visual Provenance

### Pure Styling vs Semantic Encoding

Visual QA 首先判断一个视觉属性是否承担医学语义。

Pure Styling：
- 可由 Design Agent 自由调整。

Semantic Encoding：
- 必须存在 VisualBinding；
- 修改需经过 Policy Gate。

### 空间语义

以下均可能产生关系，不能默认视为纯排版：

- grouping
- proximity
- alignment
- enclosure
- position
- hierarchy

### 视觉编码检查

必须验证：

- Color ↔ Semantic Meaning；
- Gradient ↔ Scale；
- Size ↔ Magnitude/Priority；
- Thickness ↔ Strength；
- Legend ↔ Series；
- Axis ↔ Metric / Unit；
- Annotation ↔ Comparison；
- Symbol ↔ Medical Meaning；
- Connector ↔ Relationship。

### Visual Hierarchy

区分：

- Presentation Priority；
- Clinical Priority；
- Evidence Priority；
- Risk Priority。

不得因为版式强调把 Presentation Priority 误读为 Clinical Priority。

### Statistical / Visual Misrepresentation

Visual QA 必须检查：

- truncated axis；
- reversed axis；
- linear / log mismatch；
- percentage / percentage-point confusion；
- range exaggeration；
- bar/area/size 与实际 magnitude 不成比例。

### Medical Visual Provenance

医学专用图必须分别保存：

1. Medical Semantic Provenance；
2. Visual Asset Provenance。

缺失其中任一项：
- 不得视为完整可审计视觉。

### Medical Visual Origin QA

- SOURCE_FIGURE：检查 SourceRef + copyright/license；
- ADAPTED_FROM_SOURCE：Semantic Fidelity QA；
- REDRAWN_FROM_EVIDENCE：SYNTHESIS + Relationship-level provenance；
- MEDICAL_REFERENCE_ASSET：检查是否承担医学语义；
- AI_GENERATED_MEDICAL_VISUAL：默认未验证。

### AI Medical Visual

`AI_GENERATED_MEDICAL_VISUAL`：
- 默认 `medical_verified=false`；
- 视觉逼真/专业风格不是医学验证；
- 未通过 Medical Visual QA 不得交付为医学事实图。

### Provenance Coverage

RED Medical Visual：
- 关键 Node Provenance Coverage = 100%；
- 关键 Relationship Provenance Coverage = 100%。

### Embedded Content

图片中的：
- text
- number
- threshold
- recommendation
- label
- conclusion

继续受 Claim / Data Binding / Clinical Relationship / Semantic QA 约束。

### Copyright Gate

医学准确性与版权许可独立。

至少检查：
- copyright_status
- license
- commercial_use
- adaptation_allowed
- citation_required

`copyright_status=unknown` 时：
- 不得默认允许商业交付；
- 不得默认允许公开传播。


## 7. Evidence Map QA

必须区分：

- Recommendation Class；
- Level of Evidence；
- Study Type；
- Effect Size；
- Outcome；
- Limitation。

禁止：

- 因“多项 RCT”自动生成强推荐；
- 把 Evidence Level 当 Recommendation Class；
- 原文无 Effect Size 时补数值；
- 自造“五星证据”等来源外标签。

原文没有 Effect Size：
> 显示 `SOURCE REQUIRED`。

---

## 8. Synthetic Case Policy

### 默认规则

`synthetic_case=false`

即：

- 不主动生成病例；
- 不因“页面更好讲”而自动补病例；
- 不生成虚构检查数值。

### 允许生成的唯一条件

用户明确要求：

- 模拟病例；
- 教学病例；
- 演练案例。

### 必须标注

`AI生成模拟病例｜非原文病例｜仅用于教学演示`

### 必须隔离

- 不进入 Source Fact Layer；
- 不与真实病例混合；
- 不标记为 SOURCE；
- 关键医学信息需回溯权威来源。

---

## 9. Medical Review Sheet

目标：

> 医生只审核高风险内容，而不是重新审核全部页面。

示例：

| Slide | 内容 | 风险 | 来源 | 自动结果 | 医生确认 |
|---|---|---|---|---|---|
| S05 | 诊断阈值 | RED | p14 | MATCH | □ |
| S06 | Decision Map关键分支 | RED | p14-17 | SYNTHESIS | □ |
| S09 | 药物推荐等级 | RED | Table 7 | MATCH | □ |
| S11 | 机制总结 | YELLOW | p5 | MATCH | 可选 |
| S12 | 标题排版 | GREEN | — | PASS | 自动 |

### 9.1 必须进入 Review Sheet

- RED Claim；
- RED SYNTHESIS Semantic Relationship；
- Numerical Mismatch；
- Evidence Conflict；
- Recommendation Conflict；
- Source Missing；
- Privacy Warning；
- Compliance Block。

---

## 10. 患者隐私

自动检测：

- 姓名；
- 住院号；
- 生日；
- 电话；
- 地址；
- 真实日期；
- DICOM 标签；
- 医院 / 医生识别信息；
- 人脸；
- 其他可识别患者内容。

### 10.1 处理策略

- 脱敏；
- 替换相对日期；
- 遮盖标签；
- 删除未授权标识；
- 必要时阻止公开版本。

---

## 11. 版权与机构标识

检查：

- 未授权医院 Logo；
- 未授权学校 Logo；
- 医疗机构名称；
- 论文图表原图；
- 商业图库；
- 人物肖像；
- 未注明来源的文献截图。

输出：

- PASS；
- WARN；
- BLOCK。

---

## 12. 渠道合规

### 12.1 internal_deck

重点：

- 患者隐私；
- 来源；
- 版权；
- 医学内容准确；
- 机构使用边界。

### 12.2 client_delivery

额外：

- 交付范围；
- 来源层；
- 脱敏状态；
- 审核责任；
- 可编辑内容边界。

### 12.3 public_xiaohongshu

额外检查：

- 是否变成面向普通用户的诊疗建议；
- 是否存在医疗效果承诺；
- 是否有药品推广倾向；
- 是否存在未授权机构背书；
- 是否包含敏感联系方式 / 站外导流；
- 是否需要声明“仅作资料整理与视觉表达”。

---

## 13. 小红书公开传播底线

针对当前内容运营场景：

1. 案例必须脱敏；
2. 不展示未经授权的医院 / 学校 Logo；
3. 不做诊断或治疗承诺；
4. 不做虚假资质背书；
5. 不把“医学信息设计”包装成临床诊疗服务；
6. 不在图片、正文、评论中放站外联系方式；
7. 不承诺“保证准确”“保证通过”“保证治疗效果”；
8. 涉及药物、治疗建议时应保持资料解读语境；
9. 公开内容必要时增加：
   - `仅作资料整理与PPT视觉表达示例`
   - `不构成医疗建议`

---

## 14. 视觉质量规则

### 14.1 Functional Visual

Functional Visual 必须以 **Approved Semantic Page Graph** 为输入，不得自行重新推理医学关系。

优先：

- Clinical Decision Map；
- Evidence Map；
- Disease Timeline；
- Mechanism Map；
- Risk Stratification Map；
- Outcome Plot；
- Management Cycle；
- Trial Evidence Matrix。

Decision Map 中的箭头只是 Semantic Relationship 的一种渲染；Evidence Map 中的证据连接、Outcome Plot 中的图例/坐标轴、Timeline 中的时间先后，同样属于 Semantic Binding。

### 14.2 弱化 Decorative Visual

非必要不使用：

- 医生照片；
- 药瓶；
- 听诊器；
- 泛医疗图标；
- 无信息功能的人体剪影；
- 纯气氛图库图。

### 14.3 页面层级

- Level 1：唯一结论；
- Level 2：最多 3 个核心证据；
- Level 3：必要条件 / 数字 / 注释；
- Level 4：来源。

---

## 15. 合规 Agent 与 Medical Verifier 的边界

### Medical Verifier 负责
> “资料是否被正确表达？”

### Compliance Agent 负责
> “这些内容能否以这种形式用于这个渠道？”

禁止合并为一个 Agent。

---

## 16. Block Conditions

以下情况阻止交付：

1. RED 项未确认；
2. Numerical Mismatch；
3. RED SYNTHESIS Semantic Relationship 未确认；
4. 关键推荐等级冲突；
5. 关键证据等级冲突；
6. Source Missing；
7. 患者隐私泄漏；
8. public_xiaohongshu 存在 Compliance Block。

---

## 17. 审计要求

最终交付记录：

- Source 文件哈希；
- Claim Graph 版本；
- Medical Verifier 结果；
- Numerical QA；
- Semantic QA；
- Human Review；
- Compliance；
- 最终 Deck 版本。

任一最终页面应能回答：

> 这句话来自哪里？  
> 这条箭头为什么存在？  
> 这个数字是否核对过？  
> 哪些内容是 AI 综合出来的？  
> 哪些内容由医生确认过？


---

## 17A. 已冻结模块的质量守门规则

### Claim Table v0.1

QA 必须验证：

- Claim 是否原子化到可独立验证；
- `source_quote` 与 `normalized_claim` 是否同时存在；
- 数字 / 阈值 / 推荐类别 / 证据等级是否结构化；
- SOURCE / SUMMARY / SYNTHESIS 是否正确；
- Claim 内是否混入未验证 Clinical Relationship；
- 同事实是否正确 Canonicalize；
- 冲突来源是否被错误融合；
- 使用外部知识补全后是否仍被错误标成 SOURCE。

任一 RED Claim 的关键条件丢失：阻断。

### Information Triage v0.1

QA 必须验证：

- Presentation Question 是否存在；
- Bucket 是否属于固定四类；
- RED 是否被当作普通加分项而非约束；
- Meaning-Preserving Bundle 是否被错误拆散；
- EXCLUDED Claim 是否仍保留于底层数据；
- 每个 TriageDecision 是否有 reason；
- 用户 Override 是否进入 AuditLog；
- Presentation Dependency 是否被误写为 Clinical Semantic Relationship。

MUST 内容超出 Duration 但系统未触发用户确认：Fail。

### Medical Information Architect v0.1

QA 必须验证：

- Narrative 是否由 Presentation Question 驱动；
- Narrative Spine / Section / Primary Message 是否保留 provenance；
- 每页是否只有一个 Primary Message；
- 页面是否满足四层信息模型；
- Meaning-Preserving Bundle 是否保持意义完整；
- Architect 是否创建了未经验证的 Semantic Relationship / Clinical Relationship；
- Audience Adaptation 是否只改变呈现层而未修改底层 Claim；
- Architect 是否补充来源外医学内容；
- Narrative / Page Override 是否记录。

### 系统级禁止事项

以下任一出现即视为架构违规，而不仅是“内容质量较差”：

1. Design / Architect / Triage 直接修改 locked medical facts；
2. Presentation Order 被当作 Clinical Relationship；
3. 为了“故事完整”自动生成不存在的医学箭头；
4. SOURCE 与 SYNTHESIS 在最终页面无法区分；
5. EXCLUDED 被物理删除并失去审计能力。


---

## 18. Rule Enforcement Matrix

质量体系采用“制定者、执行者、验证者分离”原则。

### 18.1 三类约束

#### A｜Hard Constraint

适用于可以确定性判断的规则。

主要执行机制：

- Schema Validator；
- Capability Control；
- RBAC / API Allowlist；
- State Machine；
- Deterministic Validator。

典型规则：

- SOURCE Claim 必须有 SourceRef；
- Architect 不得写 Clinical Edge；
- Design Agent 不得修改 locked medical fields；
- Numeric mismatch 阻止交付；
- Synthetic Case 未开启时不得创建。

默认动作：`BLOCK`。

#### B｜Semantic Constraint

适用于需要判断语义是否改变的规则。

主要执行机制：

- Semantic QA；
- Medical Verifier。

典型规则：

- “可考虑”是否被升级成“推荐”；
- “相关”是否被写成“导致”；
- 人群、条件、时间窗口是否丢失；
- Presentation 文案是否暗示未验证 Clinical Relationship。

动作：

- `BLOCK`；
- 或 `HUMAN_REVIEW_REQUIRED`。

#### C｜Human-governed Constraint

适用于系统可识别风险、但不应自行做最终医学裁决的规则。

例如：

- 权威来源冲突；
- RED SYNTHESIS Semantic Relationship；
- 关键临床解释存在合理争议；
- 医生必须确认的适应证 / 特殊人群问题。

动作：`HUMAN_REVIEW_REQUIRED`。

---

### 18.2 Rule Ownership

每条规则必须定义：

- `rule_id`
- `module`
- `constraint_type`
- `enforced_by`
- `validated_by`
- `violation_action`
- `severity`

禁止只写“Agent不得……”而没有执行机制。

---

### 18.3 典型 Rule Enforcement Matrix

| Rule | Type | Enforced by | Validated by | Violation |
|---|---|---|---|---|
| SOURCE Claim必须存在SourceRef | HARD | Schema Validator | Policy Engine | BLOCK |
| Architect不得创建Clinical Edge | HARD | Capability / Output Schema | Policy Engine | BLOCK |
| Triage不得修改Claim | HARD | API Permission | Policy Engine | BLOCK |
| Design Agent不得修改NumericFact | HARD | Locked Field / API Permission | Numerical QA + Policy Engine | BLOCK |
| SUMMARY不得升级推荐语气 | SEMANTIC | Semantic QA | Medical Verifier | REVIEW/BLOCK |
| 关键限定条件不得静默丢失 | SEMANTIC | Semantic QA | Medical Verifier | REVIEW/BLOCK |
| RED SYNTHESIS Semantic Relationship必须人工确认 | HUMAN_GOVERNED | Policy Gate | Human Medical Reviewer | REVIEW |
| 权威来源冲突不得自动融合 | HARD + HUMAN | Conflict Rule | Human Medical Reviewer | BLOCK/REVIEW |

---

### 18.4 Self-check is insufficient

禁止以下实现：

> 在 Architect Prompt 中写“不要创建 Clinical Edge”，然后默认它会遵守。

正确实现：

1. Architect 没有 Clinical Edge write capability；
2. PageSpec Schema 不接受 Clinical Edge 新建字段；
3. 若输出文本仍暗示临床关系，Semantic QA 检测；
4. Policy Engine 决定是否 BLOCK。

---

### 18.5 Policy Engine 与 Medical Verifier

二者不可混淆。

**Policy Engine**
- 不判断医学内容本身；
- 执行规则；
- 汇总验证结果；
- 控制状态推进。

**Medical Verifier**
- 比较 Source Meaning 与 Generated Meaning；
- 判断 Claim / Semantic Relationship / Binding 是否被原文支持；
- 输出医学语义验证结果。

---

### 18.6 Policy Gate 阻断条件

以下任一发生，状态不得继续：

- Hard Constraint Violation；
- Critical Rule Violation；
- Numeric Mismatch；
- Unauthorized Agent Write；
- RED 未确认；
- Compliance Block；
- Source Integrity Fail。

所有 Gate Decision 均需记录至 AuditLog。


### 18.7 Visual Semantic Enforcement

Visual Design Agent 的限制不应只写成“不能新增箭头”。

Hard Constraint 应覆盖：

- 不得新增 Semantic Relationship；
- 不得改变 Relationship 方向；
- 不得交换 Legend / Series；
- 不得改变 Axis / Metric / Unit；
- 不得把 Annotation 移到另一比较对象；
- 不得改变颜色所编码的风险 / 推荐语义；
- 不得通过分组、同色、位置、层级创造新的临床含义。

Pure Styling 可自由，Semantic Layout 必须受 `VisualEncodingContract` 约束。


---

## 19. Module 05｜Medical Verifier & Source Fidelity Gate

### 19.1 默认验证目标

Medical Verifier 默认验证：
- Source Meaning 与 Generated Meaning 的忠实度。

不默认验证：
- 来源是否为最新医学实践；
- 患者个体诊疗是否正确；
- 模型医学常识是否优于来源。

### 19.2 Verification Mode

- SOURCE_FIDELITY
- CROSS_SOURCE_CONSISTENCY
- EXTERNAL_MEDICAL_CHECK

不同 Mode 使用不同 Source Pool，禁止混源。

### 19.3 Read-only Verifier

Medical Verifier 不得直接修改：
- Claim；
- NumericFact；
- SemanticRelationship；
- PageSpec；
- Source。

只允许写：
- VerificationResult；
- VerificationIssue。

### 19.4 Verification Scope

必须覆盖：

1. Claim；
2. Title / Primary Message；
3. Data Binding；
4. Clinical Relationship；
5. Contextual Implication；
6. Medical Visual Semantic Fidelity。

### 19.5 RED Gate

当 risk = RED：

- SUPPORTED → 进入后续 Policy Gate；
- PARTIALLY_SUPPORTED → HUMAN_REVIEW_REQUIRED；
- AMBIGUOUS → HUMAN_REVIEW_REQUIRED；
- CONFLICT → HUMAN_REVIEW_REQUIRED / BLOCK；
- NEEDS_HUMAN_REVIEW → HUMAN_REVIEW_REQUIRED；
- UNSUPPORTED → BLOCK。

### 19.6 Confidence

Model confidence：
- 仅用于 review priority；
- 不替代 source evidence；
- 不替代 provenance；
- 不替代 human review；
- 不允许单独批准 RED。

### 19.7 Correction Loop

```text
Verifier detects issue
      ↓
VerificationIssue
      ↓
Responsible Module
      ↓
Revision / Regeneration
      ↓
Re-verification
```

禁止 Verifier 静默修复后直接 PASS。


---

## 19A. Module 05 Batch 2｜Semantic Fidelity Verification

### Minimum Sufficient Source

Verifier 必须优先找到能够完整支持当前对象的最小充分 Source Span。

不允许：
- 仅以文档标题、章节相关性或主题相关性判定 SUPPORTED。

### Semantic Frame Comparison

Verifier 以 Source Semantic Frame 与 Generated Semantic Frame 为主要比较对象。

必须逐项检查 Meaning-Critical Slots：

- Scope；
- Quantifier；
- Modality；
- Polarity；
- Conditions；
- Logic；
- Relationship Type；
- Direction；
- Recommendation；
- Timeframe；
- Exclusion；
- Evidence Grade。

### Meaning Preservation

SUMMARY 可以压缩文字，但不能压缩掉医学边界。

### Scope

无来源支持的：
- SCOPE_EXPANSION；
- SCOPE_NARROWING；

均不得静默接受。

### Quantifier / Modality

必须检测：
- selected → all；
- may → recommended；
- associated_with → causes；
- should → may consider；
等升级或弱化。

### Negation / Polarity

关键 polarity flip：
- Critical Failure。

特别区分：
- absence of evidence；
- evidence of absence。

### Condition Logic

AND / OR / NOT / EXCEPT 变化若改变适用范围：
- Fidelity Failure。

### Recommendation Unit

推荐必须作为完整语义对象验证：
- Population
- Condition
- Action
- Strength
- Class
- Evidence Level
- Exclusion / Exception

### Multi-source

多来源可以共同形成 SYNTHESIS，但：
- 不得把“分别兼容”误判为“直接支持组合结论”。

### Anti Cherry-pick

绑定多个 SourceRef 时：
- 必须检查所有直接相关来源；
- 明确冲突不得被忽略；
- 无 SourcePriorityPolicy 时保持 CONFLICT。



---

## 19B. Module 05 Batch 3｜Issue Resolution & Re-verification

### Issue Routing

VerificationIssue 必须按类型映射到责任模块。

禁止：
- 通用 Rewrite Agent 统一修改所有错误。

### Immutable Revision

修订：
- 创建新版本；
- 保留旧版本；
- 记录 Issue ID 与修改理由。

### Dependency Invalidation

上游医学对象发生实质语义变化：
- 下游依赖对象必须 STALE / INVALIDATED；
- 在重建和重验前禁止继续使用。

### Re-verification

每次修订同时执行：

1. Targeted Re-verification；
2. Regression Verification。

### Anti-delete Evasion

删除触发 Issue 的内容并不自动等于修复。

必须重新检查：
- Page Goal；
- MUST_INCLUDE；
- Meaning-Preserving Bundle；
- Narrative Integrity。

### Capability

Revision Mode 不提高原 Agent 权限。

### Root Cause

多模块问题：
- 优先修最上游 Root Cause；
- 按 Dependency Graph 拓扑顺序重建。

### Issue State

只有独立 Re-verification 可以写：
- VERIFIED_RESOLVED。

### Retry / Convergence

自动修复：
- 有有限 Retry Budget；
- 重复 Critical Issue → Human Review；
- Recurrent Issue 进入 QA Analytics。

### Human Override

人工可批准继续使用，但：
- 原 VerificationResult 不变；
- Override 单独留痕；
- 来源未支持 ≠ 被人工批准后就变成 SOURCE SUPPORTED。

### Version-aware Verification

任何实质语义修改：
- 旧 VerificationResult 失效；
- 新版本重新建立 Source Span Support；
- 重新验证。

### Delivery Integrity

最终交付：
- 只引用 immutable version；
- 禁止 `latest`。

### Cross-gate Re-run

Revision 影响到：
- Data
- Context
- Visual
- Compliance
- Copyright
等对象时，相应 Gate 必须重跑。


---

## 19C. Module 05 Batch 4｜Cross-source Conflict & External Medical Verification

### Context before Conflict

跨来源判断流程：

1. Source Context Frame；
2. Comparability；
3. Conflict Typing；
4. Version / Authority / Regulatory Context；
5. Verification Result。

语境不等价：
- 不得直接判医学冲突。

### Conflict Typing

必须保留不一致原因：
- direct contradiction；
- version change；
- scope/population/condition difference；
- evidence evolution；
- recommendation difference；
- regulatory/jurisdiction difference；
- unresolved inconsistency。

### Version Management

新版本存在：
- 不等于旧版本全部失效；
- 优先做 Claim / Relationship-level Supersession。

### Source Type Semantics

严禁互相替代：

- RCT / Meta-analysis → Evidence；
- Guideline / Consensus → Recommendation；
- Regulatory / Label → Approval / Indication / Dose / Contraindication。

### Regulatory Verification

以下属性独立验证：

- Indication
- Dose
- Contraindication
- Approval Status
- Reimbursement / Regulatory Limitation

指南推荐不覆盖监管状态。

### External Verification Mode

只有显式启用：
- EXTERNAL_MEDICAL_CHECK

才允许外部来源进入验证流程。

SOURCE_FIDELITY：
- 不静默更新用户材料。

### Source Pool Isolation

必须分离：

- USER_SOURCE_POOL
- EXTERNAL_VERIFICATION_POOL

外部来源只能产生：
- EXTERNAL_VERIFICATION provenance；
- External Verification Finding；
- Evidence Synthesis。

### Source Qualification

外部来源进入高风险判断前必须验证：
- Source Type；
- Organization；
- Date / Version；
- Primary / Secondary；
- Official / Regulatory Status；
- Jurisdiction；
- Verifiable Identifier。

资格不足：
- Lead only；
- 不得直接支持 RED 内容。

### Recency / Applicability

最新不等于最适用。

同时评估：
- Recency
- Authority
- Jurisdiction
- Population
- Project Purpose

### Retraction / Correction

Retracted：
- 不得作为有效高风险证据。

Corrected / Amended：
- 使用有效版本；
- 保留版本链。

### Time-bounded External Verification

必须记录：
- verified_as_of
- search_scope
- source_versions

### Evidence Synthesis

跨来源综合：
- provenance = SYNTHESIS；
- component-level Source Binding；
- 不得伪装成单一来源的 SOURCE Claim。


---

## 20. Module 06 Batch 1｜Visual Generation Contract & Prompt Compiler

### Upstream Gate

页面视觉生成只接受：
- Approved Semantic Page Graph 的不可变版本。

禁止：
- Raw PDF → Image Prompt；
- Unverified Claim → Image Prompt；
- Free-form LLM summary → Image Prompt。

### Lock Levels

Contract 必须使用：

- HARD_LOCK
- SEMANTIC_LOCK
- BOUNDED_CREATIVE
- FREE_CREATIVE

任何未授权 lock downgrade：
- BLOCK。

### Medical Truth Lock

以下默认不能由视觉模型重新推理：

- Claims
- Numeric Facts
- Thresholds / Units
- Drug Names
- Population / Conditions / Exclusions
- Recommendation Class / Evidence Level
- Clinical Relationships
- Logic Operators
- Source Bindings

### Mandatory Object Coverage

所有 Mandatory Content Object：
- 必须出现；
- 不得静默合并；
- 不得新增未批准医学对象。

### Exact Text

RED / 数字密集页：
- 高风险精确文字优先 Controlled Composition；
- 不能只依赖图像模型文字渲染。

### Functional Visual Integrity

Visual Strategy Selector 决定功能图类型。
图像模型不得为了视觉偏好把：
- Decision Map
- Evidence Map
- Mechanism Map
- Treatment Pathway
等降级成 generic cards/list。

### Layout Freedom

允许视觉创意，但必须在 Layout Freedom Envelope 内。

### Priority Integrity

Presentation Priority 不得被转译为 Clinical / Evidence / Risk Priority。

### Medical Visual Asset

必须声明：
- allowed origin
- AI generation allowed
- medical visual QA required
- semantic role

### Generation Mode

每页必须：
- FULL_IMAGE 或
- CONTROLLED_COMPOSITION

之一。

### Prohibited Transformations

至少禁止：
- invent medical objects
- alter numeric values
- change relation direction
- change AND/OR/NOT/EXCEPT
- omit key exclusion
- add fake citation
- upgrade recommendation strength

### Contract-as-QA

生成后必须使用同一 Contract 反向验证：
- Mandatory Object Coverage
- Exact Text Fidelity
- Numeric Fidelity
- Relationship Fidelity
- Visual Semantic Fidelity
- Source Visibility


---

## 20A. Module 06 Batch 2 Draft QA｜Visual Strategy Selector（未冻结）

### Selector QA 顺序

1. Visual Intent 是否正确；
2. Information Structure Profile 是否完整；
3. Standard Override 是否应触发；
4. Hard Exclusion 是否完整执行；
5. Candidate Set 是否来自 Visual Taxonomy Registry；
6. Score 仅用于合法候选；
7. Top candidate 是否与 Page Goal / Semantic Graph 一致；
8. Generation Strategy 是否与精确度和风险匹配；
9. Selector 是否制造了新医学关系；
10. 是否存在“无合适视觉却强行画图”的行为。

### 禁止的 Selector 行为

- 只按对象数量选图；
- 只按审美偏好选图；
- 为了图形完整补医学关系；
- 对不可比研究做直接优劣可视化；
- 将 time-to-event 当普通 time-series；
- 将 continuous estimate + uncertainty 默认画为 bar；
- 将 AND/OR 决策逻辑降级为普通卡片；
- 将 Table/Matrix 视为失败兜底；
- 让 Image Model 自由重画精确统计图；
- 因 Top1/Top2 接近而强迫唯一答案。


---

## 20B. Module 06 Batch 2 v0.2 QA｜Hard Rules vs Scoring（未冻结）

### Hard Gate QA

以下问题不得进入 scoring：
- 不支持的医学关系；
- 不满足 Comparability 的直接比较；
- Clinical Logic 丢失；
- 推导了未经批准统计量；
- Time-to-event 被普通 time-series 替代；
- 视觉类型需要新增底层医学关系才能成立；
- Visual Type 无法表达必须保留的 AND/OR/NOT/EXCEPT；
- 使用自由 Image Model 重构必须保持精确的数据几何。

结果：
- `INVALID_CANDIDATE`

### Scoring QA

Scoring 仅比较：
- 已经医学合法；
- 已经统计合法；
- 已经逻辑合法；
- 已通过来源和 Comparability Gate；
的候选。

Scoring 允许优化：
- Semantic Fit；
- Medical Convention Fit；
- Data Fidelity；
- Auditability；
- Audience Fit；
- Visual Communication Fit。

### Calibration QA

权重、阈值、ambiguity margin：
- 不写入 Frozen Rules；
- 必须版本化；
- benchmark 调整必须记录版本；
- 不得通过调参绕过 Hard Gate。

### Registry QA

Visual Mapping Policy / Standard Policy / Generation Policy：
- 每条有版本；
- 可回滚；
- 有 applicability 条件；
- 不得与 Frozen Constitution 冲突。

### No Forced Winner

Top1 / Top2 差异不足时：
- 允许 `AMBIGUOUS`；
- 不允许通过微小 scoring 差异伪装高确定性。


---

## 20D. Module 06 Batch 3 Draft QA｜Generation Strategy Router（未冻结）

### Router QA 顺序

1. VisualStrategyDecision 是否已批准；
2. 是否正确拆分 Generation Components；
3. Data Egress / Privacy Gate；
4. Asset Policy Gate；
5. Exact Data Geometry Gate；
6. Semantic Topology / Clinical Logic Gate；
7. Exact Text Gate；
8. Capability Registry Qualification；
9. 合法 Engine Candidate Set；
10. 软评分；
11. Fallback；
12. Page-level Generation Mode；
13. Post-generation Validator Coverage；
14. Generation Provenance。

### 必须 Hard Fail 的路线

- free image model 重构精确数据几何；
- 不能锁定 RED Clinical Relationship topology；
- 高风险 Exact Text 无可验证字符串渲染；
- Medical Visual Asset 违反 asset contract；
- 外部 API 违反 data egress policy；
- Engine 未进入 qualified capability registry；
- 路线没有可执行的 Post-generation Verification；
- fallback 需要改变 Visual Type 或医学内容。

### Soft Optimization 仅允许比较

- visual quality；
- editability；
- generation reliability；
- latency；
- cost；
- workflow convenience。

这些指标不得覆盖 Hard Gate。


---

## 20E. Module 06 Batch 3 v0.1 QA｜Router Constitution（FROZEN）

### Hard Qualification

以下不参与加权评分，任一失败直接使路线无效：

- Visual Strategy 被 Router 修改；
- 组件要求不同但被强迫同一路由；
- Exact Data Geometry 交给不可验证自由生成；
- Clinical Topology 无法锁定；
- RED Exact Text 无 authoritative rendering path；
- MedicalVisualAssetContract 不允许该生成方式；
- Protected Semantic Layer 被后续生成模型重绘/扭曲/重排；
- 外部处理违反 Data Egress / Privacy；
- Engine capability 未经过版本化 qualification；
- Fallback 降低医学语义或改变 Visual Type；
- Material Engine Change 后仍继承旧 qualification；
- Generation Provenance 不完整；
- 缺少可执行 Post-generation Verification。

### Protected Semantic Layer QA

必须检查：

- repaint；
- crop；
- warp；
- occlusion；
- text mutation；
- node movement causing relationship change；
- edge redraw；
- chart geometry mutation；
- axis/legend mutation；
- source/citation遮挡。

### FULL_IMAGE QA

FULL_IMAGE 资格来自 Policy + Capability + Contract 联合判断。
不因“当前经验认为某模型不准”而写死 Constitution。

### Optimization QA

仅 Qualified Engine Set 进入软优化。

允许：
- visual quality；
- reliability；
- editability；
- latency；
- cost；
- workflow convenience。

不允许通过软评分抵消 Hard Qualification failure。


---

## 20F. Module 06 Batch 3｜Final Conflict Boundary QA（FROZEN）

### Responsibility Collision Checks

1. Batch 2 可输出 `preferred_generation_strategy`，但不得写 `effective_engine_route`。
2. Batch 3 可写 `PageGenerationPlan / effective_generation_route`，不得改 `selected_primary_visual`。
3. Batch 3 不得生成新的 Source Fidelity / Clinical Correctness 结论。
4. Batch 3 只消费 Comparability / Verification / Asset / Privacy 结果，不重新 adjudicate。
5. Batch 3 的 Exact Geometry / Topology / Text 规则检查的是 Engine Capability，不重复定义医学语义。

### Protected Semantic Layer Checks

允许：
- semantic-invariant format conversion；
- 足够分辨率的 rasterization；
- 经验证的 whole-layer uniform scaling。

需重新验证或禁止：
- crop 导致标签/图例缺失；
- resample 导致细小 CI / text 不可读；
- partial occlusion；
- geometry warp；
- internal relayout；
- generative repaint；
- edge / axis / legend / semantic color remapping。

### Provenance Separation

必须分别存在：
- Medical Semantic Provenance；
- Visual Asset Provenance；
- Generation Execution Provenance。

不得以“生成过程可追溯”替代“医学来源可追溯”。
