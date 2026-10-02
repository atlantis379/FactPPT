# 高准确度语义分析方案：观点、证据、局限与语义证据层

如果目标是对一篇文章、一段研究材料或报告做**高准确度语义分析**，并稳定提取出「观点、证据、依据、条件、局限、反例、不确定性」，建议不要做成一次性的“让大模型总结一下”，而是构建一个：

> **Evidence-grounded Semantic Analysis Pipeline（证据锚定的语义分析流水线）**

核心思想是：

> **先忠实解析原文，再识别命题，再绑定证据，最后才允许模型解释。**

这比直接让 LLM 输出“观点 / 证据 / 局限”可靠得多。

---

## 1. 推荐总体架构

```text
原始材料
   ↓
Document / Section / Paragraph / Sentence
   ↓
Atomic Claim Extraction
原子观点提取
   ↓
Evidence Linking
证据绑定
   ↓
Qualifier / Scope / Condition Extraction
适用条件、范围、限定词
   ↓
Limitation / Uncertainty Extraction
局限、不确定性
   ↓
Relation Graph
观点—证据—局限关系图
   ↓
Independent Verification
二次验证
   ↓
Structured JSON
```

其中最关键的是：不要直接抽取“总结”，而是先抽取 **Claim（命题）**。

例如原文：

> 在本研究中，接受治疗 A 的患者在 12 周时 FEV1 较基线提高 180 mL，而安慰剂组提高 60 mL。两组差异具有统计学意义。但是，本研究样本量较小，且随访时间仅为 12 周，因此长期疗效仍需进一步研究。

不要只输出：

> 治疗 A 可以改善肺功能，但研究存在局限。

这种方式会损失很多重要信息。

更好的结构是：

```json
{
  "claim": {
    "text": "治疗A可改善患者肺功能",
    "type": "causal_or_effect",
    "strength": "moderate"
  },

  "evidence": [
    {
      "type": "quantitative_result",
      "text": "12周时FEV1较基线提高180 mL",
      "value": 180,
      "unit": "mL",
      "group": "治疗A组"
    },
    {
      "type": "comparison",
      "text": "安慰剂组提高60 mL",
      "value": 60,
      "unit": "mL"
    },
    {
      "type": "statistical_evidence",
      "text": "两组差异具有统计学意义"
    }
  ],

  "scope": {
    "population": "本研究纳入患者",
    "time_horizon": "12周"
  },

  "limitations": [
    {
      "type": "sample_size",
      "text": "样本量较小"
    },
    {
      "type": "follow_up",
      "text": "随访时间仅为12周"
    }
  ],

  "uncertainty": [
    {
      "text": "长期疗效仍需进一步研究"
    }
  ]
}
```

这才是真正适合后续研究、PPT、报告生成、知识库或 RAG 的语义层。

---

## 2. 建议至少拆分为 8 类语义对象

不要只设计：

```text
观点
证据
局限
```

至少应设计为：

| 对象 | 含义 |
|---|---|
| **Claim** | 作者明确提出或材料能够支持的命题 |
| **Evidence** | 支撑 Claim 的事实、数据、实验结果、引用 |
| **Reasoning** | Evidence 如何支持 Claim |
| **Qualifier** | “可能”“显著”“主要”“在某些患者中”等限定 |
| **Scope** | 人群、时间、地点、研究条件、适用范围 |
| **Counterevidence** | 与观点冲突或削弱观点的证据 |
| **Limitation** | 研究设计、数据、方法、外推等限制 |
| **Uncertainty** | 作者尚不能确定的问题 |

其中尤其容易被模型漏掉的是：

**Qualifier + Scope**

例如：

> Treatment A may reduce exacerbations in patients with eosinophilic asthma.

绝不能简单抽成：

> Treatment A reduces exacerbations.

因为：

```text
may
↓
不确定性 / 语气强度

patients with eosinophilic asthma
↓
适用人群限定
```

如果把这两个部分丢掉，语义已经发生实质改变。

---

## 3. 最推荐：两阶段抽取 + 一阶段验证

准确率最高的方案通常不是一次 LLM 调用，而是：

1. 忠实抽取
2. 语义解释
3. 独立验证

### 3.1 第一阶段：忠实抽取

模型只回答：

> 原文明确说了什么？

禁止推理、扩写、常识补充。

建议输出：

```text
Claim
Evidence
NumericFact
Limitation
Qualifier
Scope
SourceSpan
```

每一个对象都必须绑定来源位置：

```text
source_text
sentence_id
paragraph_id
start_char
end_char
```

也就是说，每条结论都必须可以回到原文。

---

### 3.2 第二阶段：语义解释

这一步才允许模型分析：

> 这些证据之间是什么关系？

关系类型例如：

```text
supports
contradicts
qualifies
limits
explains
causes
correlates_with
derived_from
```

可以形成：

```text
Claim A
   ↑ supports
Evidence 1
Evidence 2

Claim A
   ↓ limited_by
Limitation 1
Limitation 2
```

最终得到一个小型：

> **Knowledge Graph / Argument Graph**

---

### 3.3 第三阶段：Verifier

建议使用第二次独立模型调用，且不要把第一次模型的输出默认当成事实。

Verifier 只负责检查：

```text
这个 Claim 是否真的能由原文支持？

证据是否对应这个 Claim？

有没有扩大原文含义？

有没有把 correlation 变成 causation？

有没有遗漏限定词？

数字是否完全一致？

局限是否来自原文？

是否出现模型自己创造的信息？
```

输出例如：

```json
{
  "verdict": "SUPPORTED",
  "confidence": 0.94,
  "issues": []
}
```

或者：

```json
{
  "verdict": "OVERSTATED",
  "issues": [
    "原文使用 may，但 Claim 使用了肯定表达"
  ]
}
```

这一层能显著减少 hallucination。

---

## 4. 最重要原则：Extractive First, Abstractive Second

这是整个系统中最重要的原则之一。

第一阶段：

> **Extract**

从原文拿东西。

第二阶段：

> **Interpret**

解释这些东西。

第三阶段：

> **Synthesize**

才进行总结。

不要采用：

```text
原文
 ↓
LLM总结
```

推荐采用：

```text
原文
 ↓
SourceSpan
 ↓
Atomic Claim
 ↓
Evidence
 ↓
Relation
 ↓
Validated Claim
 ↓
Summary
```

否则模型很容易把以下内容混成同一层级：

```text
作者认为
研究发现
研究推测
研究证明
其他研究认为
```

---

## 5. Claim 应进一步分类

例如在医学论文中，可设计：

```text
Claim
├── Fact Claim
├── Quantitative Claim
├── Causal Claim
├── Association Claim
├── Mechanism Claim
├── Recommendation
├── Interpretation
├── Hypothesis
└── Prediction
```

例如：

> IL-5 plays an important role in eosinophil survival.

属于：

```text
Mechanism Claim
```

而：

> Mepolizumab reduced annualized exacerbation rates by 53%.

属于：

```text
Quantitative Effect Claim
```

而：

> These findings suggest that...

属于：

```text
Interpretation
```

这三者不能混为一谈。

---

## 6. Evidence 也建议分类

```text
Evidence
├── NumericFact
├── ExperimentalResult
├── Observation
├── Citation
├── ExpertStatement
├── MechanisticEvidence
├── StatisticalEvidence
├── ComparativeEvidence
└── Example
```

尤其推荐把：

```text
NumericFact
```

单独建对象，而不是隐藏在 Evidence 文本里。

例如：

```json
{
  "metric": "FEV1",
  "value": 180,
  "unit": "mL",
  "direction": "increase",
  "timepoint": "12 weeks",
  "population": "treatment group"
}
```

这样后续才能进一步实现：

- 数字一致性检查
- PPT 数据卡片
- 图表自动生成
- 不同文章结果对比
- 自动生成 Evidence Table

---

## 7. 推荐的最终数据结构

不建议只设计为：

```json
{
  "viewpoint": "...",
  "evidence": "...",
  "limitation": "..."
}
```

更建议设计成：

```json
{
  "document_id": "...",

  "claims": [
    {
      "claim_id": "C001",

      "claim_text": "...",

      "claim_type": "effect",

      "assertion_strength": "moderate",

      "scope": {
        "population": "...",
        "condition": "...",
        "time": "..."
      },

      "qualifiers": [
        "may"
      ],

      "evidence_ids": [
        "E001",
        "E002"
      ],

      "limitation_ids": [
        "L001"
      ],

      "source_refs": [
        "S001"
      ]
    }
  ],

  "evidence": [],

  "numeric_facts": [],

  "limitations": [],

  "uncertainties": [],

  "source_spans": [],

  "relations": []
}
```

这样得到的就不只是“摘要”，而是一个：

> **Semantic Evidence Layer**

它可以被后续任何系统重复使用。

---

## 8. 高准确度场景建议增加 Entailment

如果对准确性要求很高，建议增加：

> **Entailment（语义蕴含判断）**

即判断：

> 原文是否真的蕴含这个 Claim？

例如原文：

> Treatment A was associated with lower mortality.

模型生成：

> Treatment A reduces mortality.

这两句话看起来接近，但第二句引入了更强的**因果关系**。

Verifier 应输出：

```text
Source:
A was associated with B

Claim:
A causes B

Result:
NOT ENTAILED
```

可以设计为：

```json
{
  "entailment": "partial",
  "entailment_score": 0.71
}
```

或者采用离散状态：

```text
ENTAILED
PARTIALLY_ENTAILED
NOT_ENTAILED
CONTRADICTED
```

这对于医学、科研、商业研究尤其重要。

---

## 9. 推荐的完整处理流程

如果追求：

- 准确
- 可工程化
- 成本可控

建议采用：

```text
                 ┌─ Sentence segmentation
                 │
Document ────────┼─ Paragraph segmentation
                 │
                 └─ Section detection
                         ↓
                 Candidate Claim Extraction
                         ↓
                   Atomic Claim
                         ↓
             ┌───────────┼────────────┐
             ↓           ↓            ↓
          Evidence     Scope      Limitation
             ↓           ↓            ↓
             └──────── Relation ──────┘
                         ↓
                  Source Grounding
                         ↓
                 Entailment Check
                         ↓
                 LLM Verification
                         ↓
                Confidence / Status
                         ↓
                  Semantic JSON
```

模型角色最好逻辑分离：

```text
Extractor
↓
Reasoner
↓
Verifier
```

即使三个角色底层都使用同一个强模型，也建议使用三个独立的 Prompt / Context。

不建议：

```text
一个超级 Prompt 完成全部工作
```

后者虽然简单，但在长文档中非常容易出现语义漂移。

---

## 10. 与可靠 PPT 生成系统的衔接

这套架构非常适合继续接入“可靠 PPT 生成”。

整体链路可以变成：

```text
SourceSpan
↓
Evidence
↓
Claim
↓
ValidatedClaim
↓
Narrative
↓
Slide
```

对应关系可以设计为：

```text
PPT标题
= Claim

数字卡片
= NumericFact

正文
= Evidence

脚注
= SourceRef

注意事项
= Limitation
```

这样生成出来的 PPT 才能真正做到：

> **每句话有依据，每个数字有来源，每个结论知道自己的适用范围。**

这会比普通的：

```text
RAG + LLM → PPT
```

可靠得多。

---

## 11. 推荐下一步

如果要继续工程化，建议下一步直接定义：

```text
Claim
Evidence
Limitation
Scope
Qualifier
SourceSpan
Relation
NumericFact
Uncertainty
```

对应的：

> **JSON Schema v1**

一旦这一层定义稳定，后续的：

- 论文分析
- PDF 解析
- 研究报告抽取
- 知识库
- RAG
- 自动摘要
- 自动生成 PPT
- 数据一致性验证
- Citation / SourceRef
- Human Review

都可以复用同一个 **Evidence Layer**。

---

## 核心结论

如果只记住几条原则，可以归纳为：

1. **不要直接让模型总结全文。**
2. **先拆 Atomic Claim，再找 Evidence。**
3. **Claim 必须绑定 SourceSpan。**
4. **Qualifier 和 Scope 不能丢。**
5. **NumericFact 单独结构化。**
6. **区分相关性、因果性、解释和推测。**
7. **使用独立 Verifier 做二次验证。**
8. **高准确度场景加入 Entailment。**
9. **最终输出结构化 Semantic Evidence Layer。**
10. **生成 PPT、报告或知识库之前，再做 Narrative Synthesis。**
