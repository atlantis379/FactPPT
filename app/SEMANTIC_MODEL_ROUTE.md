# 语义行为的模型路线（阅读 · 结构 · 叙事 · 分配）

政策依据：`skills/auditable-medical-presentation-reference/references/project/docs/workflows/SOURCE_READING_TO_NARRATIVE_DERIVATION_POLICY_v0.2.md`。治理原则是：**阅读、结构、叙事、分配是语言模型完成的语义行为；确定性代码只验证它们确实发生过、可追溯、判断已声明。代码不生产它们，模型不给自己打分。**

改造前 `app/` 与这条原则方向相反：`extract` / `triage` / `architect` 全部由规则引擎产出，`NarrativePlan.narrative_spine` 直接等于 `presentation_question`，而且 `record_run` 拒绝任何外部适配器。本模块把这三个动作交还给模型，同时加三道必须是**可观测拒绝**的闸。

```
extract / triage / architect
   ├─ 网关 app/semantic_model.py    配置解析 → 资格闸 → egress 闸 → 载荷最小化 → 调用
   ├─ 复核 app/main.py              确定性校验模型输出，不通过则不写入
   └─ 审计 app/model_adapter.py     记录 adapter/model/prompt 版本、输入输出哈希、egress 决策
```

## 1. 三道闸（顺序即优先级）

### 1.1 资格闸（`SM-01`）

引擎必须在 [`config/semantic_model_capabilities.json`](../config/semantic_model_capabilities.json) 里声明该能力，且 `qualification_status == QUALIFIED`。注册表受版本控制、必须带基准证据（`required_benchmark_suite` / `tested_at` / `evidence_refs`），**请求方不能注册或提升资格**。没有证据的路由被拒绝，而不是被尝试。

闸的次序是刻意的：未知能力先失败，资格不足先于项目策略失败——因为没有哪个项目策略能授权一条未资格化的路线。

### 1.2 egress 闸（`SM-01`）

回环端点不算外发（数据没有离开本机），只走资格闸。外部端点需要项目**两次显式同意**，而不是一次：

| 能力类型 | 需要的声明 |
| --- | --- |
| 摘要类（`triage` / `architect`，只发 Claim 摘要） | `allow_external_generation=true` 且 `generation_data_egress_policy=CONTRACT_MINIMIZED` |
| 需要原文（`source_candidate_extraction`，M1 要求读全文） | `allow_source_text_egress=true` 且 `source_text_egress_policy=FULL_TEXT` |

**设计简报的许可不能当成患者文档的许可。** 把一部患者向源文档发到外部模型，与把一份排版简报发出去，是两个不同量级的决定，所以用两套字段、两套阶梯。

原文阶梯刻意只有 `DENY` / `FULL_TEXT` 两档：阅读规则要求读全文，`PAGE_MINIMIZED` 这类"半外发"档位只会被误用。

载荷按注册表里的 `allowed_fields` 过滤，`forbidden_fields` 是**真的被丢掉**（`build_payload` 做白名单裁剪），不是写在文档里给人看。

### 1.3 复核闸（`SM-02`）

模型输出必须过确定性复核才写入。分工如下——**模型说什么不算**：

| 动作 | 模型负责 | 代码负责 |
| --- | --- | --- |
| 阅读（M1） | 指出原文说了什么，并给出一条逐字引文 | 引文必须在**所引那一页**的文本中逐字命中（空白无关比较）；`risk` / `numeric_facts` / `conditions` / `id` / `provenance` / `review_status` 全部由代码派生 |
| 分诊（M2） | 桶位与一句理由 | 覆盖率（每条 Claim 恰好一次）、桶合法性、`score`、时长成本、`NEEDS_USER_INPUT` 判定 |
| 架构（M3+M4） | `narrative_spine`、页面分组、顺序、`why_this_page`、`figure_intent` | 每页 ≤4 Claim、覆盖恰好一次、`figure_intent → visual_type` 映射、`provenance`、章节结构 |

两条推论值得单独说：

- **引文是唯一被信任的模型输出，而它本身不可信**——因为它要在原文里命中才被接受。模型编造一句话就被丢弃，且丢弃原因进审计（`quote is not in the cited page text`）。全部候选都不合格时直接失败，不写任何 Claim。
- **`figure_intent` 由模型声明，`visual_type` 由代码映射。** `figure_intent`（`CAUSAL / PROGRESSION / COMPARISON / TAXONOMY / PROCESS / SCALE / DATA / QUOTATION / NONE`）按政策是 material-agnostic、在分配阶段就定下的；映射到本应用自己的版式词汇（`EVIDENCE_MAP` / `EVIDENCE_MATRIX` / `CLINICAL_DECISION_MAP` / `CONCEPTUAL_FRAMEWORK`）是代码的事。页面把 `why_this_page` 与 `figure_intent` 落进 `PageSpec.goal`，使 REG-READ-015 要求的声明可追溯——这也是布局模型此前缺少的那块信息。

## 2. 拒绝不得静默降级（`SM-03`）

配置了端点但资格不足或未获授权时，该阶段**直接失败**（HTTP 422，带可执行提示：缺哪个声明、需要哪个基准套件），不会退回规则引擎。否则"配置了模型却被拒"这件事会从审计里消失。

未配置端点时规则引擎是**默认路径**，不是降级——`configured_semantic_model()` 返回 `None`，走原有确定性实现。

## 3. 部署步骤

1. 设置 `EASYPPT_SEMANTIC_MODEL_URL` / `EASYPPT_SEMANTIC_MODEL_ID`，需要时 `EASYPPT_SEMANTIC_MODEL_API_KEY`。回环可 `http`；外部必须 `https`，且禁止重定向。
2. 在 `config/semantic_model_capabilities.json` 里为该引擎补资格证据（`required_benchmark_suite` + `tested_at` + `evidence_refs`）。**在此之前路由是 BLOCKED**——这是刻意的，见下节。
3. 需要外发时，在项目上声明 `allow_external_generation` / `generation_data_egress_policy`，需要原文时再声明 `allow_source_text_egress` / `source_text_egress_policy`。
4. 查看 `GET /api/model-adapters` 与 `GET /api/semantic-model-capabilities`；后者可带 `?project_id=...`，直接返回该项目每个能力的可用性与缺失的声明。

## 4. 审计

每次运行记录 `adapter_id` / `model_version` / `prompt_version` / `input_hash` / `output_hash` / `executed_at`；外部运行额外带 `data_egress`（`capability`、`decision`、`policy`、`payload_sha256`、`payload_bytes`）。

外部运行没有合规的 egress 决策时，审计层直接拒绝写入（`model_adapter.validate_egress_decision`）——缺字段、或 `decision` 不是 `EGRESS_APPROVED` / `LOOPBACK_NO_EGRESS`，都不落库。

## 5. 与已接受读取件的对接（`reading_structure_artifact.v0.2`）

**为什么需要这一跳。** 上面第 4 节的能力路线是让本应用自己产出叙事；但按政策，阅读/结构/叙事/分配是**别的执行体**（skill 侧 W01-R）已经完成并验收过的语义行为。如果不接它，`LD-01` 守住的"已批准顺序"来源就永远是应用自己——一个没有凭证的声明。

**登记，不重算。** `POST /api/projects/{id}/reading-structure` 接受一份已验收的 artifact，`app/reading_structure.py` 先过它自己的门（`RS-01`），再挂到项目上。应用**不会**因为拿到 artifact 就重新推导叙事或页面集：那会产出第二份、且无人验收过的叙事。

**门判什么**（只判代码可判的，人的判断仍留给人）：

| 代码 | 规则 | 触发条件 |
| --- | --- | --- |
| `NOT_A_FULL_TEXT_READ` / `INCOMPLETE_READ` / `CHARACTERS_NOT_FULLY_READ` | REG-READ-001 | `reading_mode != FULL_TEXT_READ`；块未读全；字符覆盖 < 98% |
| `MECHANICAL_STRUCTURE_DERIVATION` | REG-READ-001 | `structure_derivation != LLM_SEMANTIC_SYNTHESIS`（按标题切出来的结构是目录） |
| `THREAD_MISSING` | REG-READ-004 | thread 无法用自己的话说出 |
| `BLOCK_COVERAGE_MISSING` / `DUPLICATE_BLOCK_IDS` / `EVIDENCE_ONLY_WITHOUT_REASON` | REG-READ-002 | 块没有覆盖状态、id 重复、evidence_only 没有理由 |
| `NODE_WITHOUT_WHY_HERE` / `NODE_WITHOUT_BLOCKS` | REG-READ-003 | 节点没写 why_here 或没有证据块 |
| `NARRATIVE_ORDER_INCOMPLETE` / `NARRATIVE_ORDER_UNDECLARED` | REG-READ-014 | narrative_order 未覆盖全部节点；未声明与源序的差异及理由 |
| `PAGE_WITHOUT_WHY_THIS_PAGE` / `PAGE_WITHOUT_FIGURE_INTENT` / `EMPTY_PAGE` | REG-READ-015 | 页面没有存在理由、没有图意、既无图又无内容 |
| `EVIDENCE_PAGE_WITHOUT_BLOCKS` | REG-READ-012 | 证据页没记录来源块，日后无法审计（`figure_intent=NONE` 的封面/收束页不受此限） |
| `NODE_NOT_EXPOSED` | REG-READ-017 | 有节点没有被任何页面渲染（节点是否被渲染，按"它的证据是否出现在某页"判定，对有无 `narrative_node_ids` 的两种 artifact 形状都成立） |
| `PAGE_ORDER_CONTRADICTS_NARRATIVE` | REG-READ-017 | 节点**首次出现**的顺序与声明的叙事序不符（结构页与附录页回溯合法，不算违反） |
| `UNDECLARED_GAPS` / `FAILURES_WITHOUT_DECLARATION` | REG-READ-010 | `checks` 报 FAIL 但 disposition 未声明差距、或没有 `coverage_declaration`——**未声明的缺口等于拒绝** |

**连接键是 sha256，不是猜。** artifact 的 `source.sha256` 必须匹配某个已导入文档；块的 `unit` 就是该文档的页码，于是 `block.unit → SourceRef.page` 把 artifact 页面精确映射到已批准 Claim。`RS-02` 要求两个方向都不许静默丢：读到了但 Claim Table 没覆盖的页（`PAGE_WITHOUT_APPROVED_CLAIM`）与裁定通过但读取从未抵达的 Claim（`APPROVED_CLAIM_NOT_IN_READING`）都作为 `allocation_gaps` 上报。

**顺序被钉在 PageSpec 上**（`RS-03`）：页面集、页面顺序、每页 Claim 顺序与顺序都取自 artifact，并记录 `reading_page_id` / `narrative_node_ids` / `source_block_ids`。此后 `LD-01` 保护的"已批准顺序"第一次有了来处。重新挂一份不同的读取件会把既有页面标记为 `STALE`。

**交付身份包含读取件**：`immutable_snapshot_digest` 在有读取件时把 `reading_structure_sha256` 计入。一份演示稿不能换掉自己依据的叙事却仍叫同一个名字。（未挂读取件时该字段不参与，既有快照身份不变。）

**在仓库真实 artifact 上的实测结论**（`app/validation/` 与测试 `test_the_real_ch06_plan_artifact_is_gated_not_rubber_stamped`）：

| artifact | 门结论 |
| --- | --- |
| `out/reading_v02/artifact_medical.json` | 0 issue，可挂 |
| `out/ch06_plan_v1/artifact_medical_planned.json` | 2 issue：`PAGE_ORDER_CONTRADICTS_NARRATIVE`（p14 引入节点 5 晚于节点 6；p58 附录页引入节点 10 晚于节点 17） |
| `out/reading_v02/artifact_business.json` | 1 issue：`FAILURES_WITHOUT_DECLARATION`——`checks` 有 FAIL 却没有 `coverage_declaration`，按政策"未声明的缺口等于拒绝" |

即：**这两份曾被 skill 侧验收的工件，在本应用的门下会被拒绝**。这不是实现缺陷，而是门在做事；要么修正工件，要么按 REG-READ-010 记录修正过程与两次结果。

## 6. 模型端点的两种落地方式，以及本轮真正用哪一种

注册表里的 `execution_kind` 决定引擎是"厂商 HTTP 服务"还是"运维方自己的工作流"，两者走**同一道资格闸**：

| 引擎 | 是什么 | 现状 |
| --- | --- | --- |
| `openai_compatible_semantic` | 厂商/第三方 OpenAI 兼容服务，允许外发 | `PENDING_QUALIFICATION`，`evidence_refs` 为空 → **不可路由** |
| `operator_model_workflow` | **运维方自有的回环模型工作流**（不是厂商模型） | `QUALIFIED`，证据 `app/validation/qualification/SEMANTIC-ACT-QUALIFICATION-v0.1.json`；`external_data_egress=false` |
| `local_deterministic` | 规则引擎，不外发 | `QUALIFIED`，未配置端点时的默认路径 |

**端点即"模型的入口"，不是"生成内容的东西"。** 运维方工作流用一个只做运输的回环服务实现：

```
python -m app.validation.model_endpoint_server --store app/validation/model_workflow --mode serve --port 8765
# EASYPPT_SEMANTIC_MODEL_URL=http://127.0.0.1:8765/v1/chat/completions
# EASYPPT_SEMANTIC_MODEL_ID=operator-model-workflow
# EASYPPT_SEMANTIC_MODEL_ENGINE=operator_model_workflow     ← 端点必须声明它是注册表里的哪个引擎
```

它**从不生成内容**：按应用发来的载荷交付运维方写好的答案，没有答案就 HTTP 503 并写出载荷，
"大声失败"是刻意的——一个悄悄给出貌似合理回答的服务会让资格证据失去意义。
`--mode dump` 只记录载荷、不回答，用于先看清应用到底会问什么。

**端点必须声明引擎（`EASYPPT_SEMANTIC_MODEL_ENGINE`）**：一个部署可以登记多个模型引擎，
"字典里第一个 QUALIFIED 的"不是审计员能依赖的答案。未声明时按注册顺序取第一个合格引擎。

**答案按内容寻址，不只按载荷摘要**：Claim id 每次抽取都会变，只按摘要归档会把交付变成跑步机。
`<store>/by_capability/<capability>.json` 按**断言语义**归档，仅当每一条都能在当前载荷里对上才启用；
一条对不上就 503 并把对不上的那几条报出来。它只会省掉重复授权，不会回答另一个问题。

**资格怎么取得**（`python -m app.validation.semantic_act_qualification --pdf <原始PDF>`）：
驱动真实端点与真实接口，测量注册表点名的五项，逐项写 method / 样本量 / 实测值：

| 检查 | 本轮实测 |
| --- | --- |
| `full_text_read_completeness` | 11/11 单元送入，字符覆盖 **100%** |
| `quote_grounding_precision` | 27/27 候选逐字命中；命中率 **1.00**；已写入 Claim 的引文独立复核 0 处不符 |
| `triage_bucket_agreement` | 27 条各决策一次、桶位合法、MUST 1 304 s ≤ 1 800 s |
| `narrative_order_justification` | 7 页 27 条各用一次、无遗漏无重复、每页有存在理由 |
| `no_new_content` | 24 个数字全部出现在各自引文中，0 处越界 |

公平性由构造保证：引文命中率与"无新内容"是在**应用校验器跑之前**从端点原始回答上量的；
跑完校验器再量只能证明校验器是确定性的。

## 7. 全文总结产物（`full_source_summary.v1`）

阅读件的 `summarize()` 是运行统计，不是给读者看的医学总结。现在由模型另写一份 `full_source_summary.v1`：`overall_summary` 概括整份材料，`sections[]` 给出主题段落的标题、正文与 `source_block_ids`。代码只验证两层 sha256 身份（原始来源和已登记读取件）、每节有内容且块号存在、**来源的每一页至少有一条块引用**，不会用标题切分或拼接 Claim 来制造总结。`POST /api/projects/{id}/full-summary` 登记后，`GET /api/projects/{id}/full-summary` 把每个块展开为文件名、PDF 页码和块号；换掉读取件会使旧总结失效。

这份总结与演示稿的 Triage 相互独立：即使某页资料只进入 `evidence_only`，全文总结仍须覆盖它。第六章回归样本中，演示叙事节点没有触达原 PDF 的第 10–15、18–19 页，但 8 节全文总结的来源定位覆盖了 25/25 页。代码验证的是**覆盖与定位**，对叙述是否忠实、OCR 断句和临床含义的判断仍须按 W03/W16 审核；特别是旧教材的药物剂量不会因为被总结就成为当前建议。

可复用入口是 `GET /api/projects/{id}/full-summary/brief`：它从**当前已导入来源**逐页取全文文本，附上该页可引用的块号、来源和读取件哈希以及输出契约。缺页、空白抽取页、重复页或来源不匹配会阻断；不会裁掉「不进 PPT」的页。模型工作流据此撰写 JSON，交给 `POST /api/projects/{id}/full-summary` 验收。登记后的总结是读取件路径下正式交付的前置条件；换读取件或总结覆盖不足，`presentation.pptx` 阻断。

`POST /api/projects/{id}/full-summary/run` 已实现自动调用与同一校验、审计记录，但 `full_source_summary` 是独立的语义能力。目前注册表只声明了该能力的最小输入和外发契约，**没有授予任何现有引擎该能力**；因此该端点会清楚拒绝执行。投入使用前，须按 [`FULL_SUMMARY_QUALIFICATION.md`](validation/FULL_SUMMARY_QUALIFICATION.md) 对目标引擎建立章节总结专项基准，验证全文覆盖、来源定位、关键限定词/数字保留和无新增事实，记录证据后再更新资格注册表。外部模型还须满足项目的全文外发许可。不能借用 `architect` 或布局模型的资格。

## 8. 未完成（必须知道）

- **具体厂商模型的资格证据仍未取得。** `openai_compatible_semantic` 保持 `PENDING_QUALIFICATION`。
  本轮的证据只qualify**运维方自己的回环工作流**，它为这个端点背书，不为任何厂商模型背书。
- `operator_model_workflow` 的 `external_data_egress=false`，所以即使把项目的外发声明全打开，
  它也拿不到公网端点的路由资格（有测试锁定）。
- `verify` / `compliance` 仍是确定性代码——"模型不给自己打分"在验证侧本来就成立。
- 读取件的门只覆盖代码可判定的条款。thread 是否真的说清了论证、重点判断是否合理，仍是人工复核项。
- 端到端实跑记录与逐页视觉复核见 [`validation/end_to_end_validation_20260913.md`](validation/end_to_end_validation_20260913.md)。
