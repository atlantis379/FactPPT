# FactPPTv2 主线：FactDeck 生成线与执行端协作

2026-10-14新的[模型理解总结与同步证据索引要求](MODEL_UNDERSTANDING_SUMMARY.md)已接入新SUMMARY任务：先输出作者主旨、组织依据、结论和关系的理解结果，再写总结，代码负责索引与校验。不以压缩率、字数或PPT页数决定总结；展示取舍在DECK阶段处理。当前新任务合同为`model_understanding.v4`，理解结果为`source_understanding.v1`，同步索引为`summary_evidence.v1`，[原文覆盖登记](SOURCE_COVERAGE_LEDGER.md)为`source_coverage.v2`：逐句登记、每句绑定point正文中的实际表达，SUMMARY_REVIEW逐句判定覆盖，未完整项作为阻断问题退回作者修订。旧合同与历史总结保留兼容；结构登记完整不等于语义审核通过。

2026-10-15完成[独立语义清单与双向QA盲测](SUMMARY_BLIND_TRIAL_2026-10-15.md)：4条封存遗漏检出3条，源文清单自身仍会漏项；事实告警也存在误报。该方法目前为离线实验，没有自动替换独立审核或提供完整性保证。

本机五步工作台入口与使用说明见[LOCAL_WORKBENCH.md](LOCAL_WORKBENCH.md)：上传资料、要求与模板、内容复核、生成审核、下载交付。任务对接现有Codex＋Adobe执行端，未实现无人值守模型调用。

已制作的[十套学术原生模板库](ACADEMIC_TEMPLATE_LIBRARY.md)采用A路线，提供POTX、PPTX、PDF和实际逐页预览。工作台可浏览、下载并在项目设置中选择；选择绑定实际设计参考和配色，更换后重新核对视觉生成。

当前执行分工采用[Sol、Luna、本地代码三路径方案](THREE_PATH_EXECUTION_PLAN.md)（2026-10-04）。用户已放弃本地模型接入；自动模型路由尚未实现，生产合同和确认关口仍按本文流程。
已实施的审核覆盖、worker共享证据格式及独立对照入口见[CONTEXT_IMPLEMENTATION.md](CONTEXT_IMPLEMENTATION.md)。新总结审核采用`summary_review.v2`，逐条包含关键要点的版本绑定目标；旧审核不自动补造判定。

页面语义复核须同时检查事实、上下文、关系类型/方向与章节覆盖；箭头只是表达关系的一种形式。复核输入、问题闭环及整套回归要求见[SEMANTIC_REVIEW_PROTOCOL.md](SEMANTIC_REVIEW_PROTOCOL.md)。

逐项执行分工以[THREE_PATH_EXECUTION_PLAN.md](THREE_PATH_EXECUTION_PLAN.md)为准：Luna负责明确范围的局部候选，Sol负责综合、复杂关系、设计及独立审核，本地代码负责确定性执行。ImageGen/Adobe及人工关口按原视觉路线执行。旧分工与本地模型评估仅为历史记录。

主线是 **FactDeck**（`factdeck.v1`，接口 `/api/deck`）：任意类型的原始资料 → 全文总结 →
事实库 → 按需求编排页面 → 程序渲染为原生可编辑 PPT。页面上的实质内容只能来自事实库，
而事实库中的每一条都是来源原文的逐字引文，由程序而不是模型判定是否成立。

原“整页图片”流程（`57098-full-slide.v1`，接口 `/api/fact`）保留给已有项目，不再是主线；
它不能作为文字精确的渲染器使用。原语义接口 `/api/projects` 与 `/legacy` 不变。

## 已选定的 PPT 视觉生成方案（2026-10-01）

用户固定采用 **A 原生矢量路线**：锁定内容与设计说明 → 生成带文字完整设计稿 → 去字 →
图形矢量化 → 转成原生 PPT 形状 → 填入锁定的原生文字、表格、数据与连接线 → PowerPoint 核对。
当前默认视觉以米白、炭黑、墨蓝和低饱和蓝灰为起点，允许部分纹理细节损失。
详见 [PPT_GENERATION_ROUTE.md](PPT_GENERATION_ROUTE.md) 与 [VISUAL_STANDARD.md](VISUAL_STANDARD.md)。

这条路线已纳入 `/api/deck` 主线：新项目默认 A，应用自动串联设计稿、版面拆解、去字与矢量化任务，
素材齐备后自动进行原生导出。实际工具调用由 Codex＋Adobe 执行端完成；最终核对使用本机PowerPoint。
接入不记录医学、客户风格或逐页审核通过。生成图中的文字与医学关系不能替代事实库和来源核对。

## 流程

| 步骤 | 谁做 | 程序检查 |
|---|---|---|
| 1. 建项目：标题、教学提纲、需求（受众、目的、时长、目标页数、重点、语气、备注）、配色 | 操作人 | 需求字段与配色合法 |
| 2. 导入资料：PDF、PPTX、DOCX、XLSX、TXT/MD、PNG/JPG/WEBP | 操作人 | 拆成“阅读页”与“可引用单元”（文本框、表格单元格、备注、段落、工作表行），记录位置与校验值 |
| 3. `READ_SOURCE` 逐页阅读 | 执行端 | 每页都有记录；含图片/图表的页必须看原件；图表中的文字逐格转录为新单元（待确认）；有上下级的表格行或分类子项写 `parent`（所属分组格），第二次转录独立读出并比对；PDF 文字层打断的正文句子可按原件整句转录为一格 |
| 3a. `CLAIMS` 论断清单（每份资料一个任务） | 执行端 | 每页的论断都是原文片段（每段不超过200字，不能整页引用）加类型和适用范围，资料有性质说明（指南、研究、推广材料等）；程序自动标出限定词、关键数字和引文角标，并提示未列入的原件页标题和强调 |
| 4. `SUMMARY` 全文总结 `full_source_summary.v3` | 执行端 | 覆盖全部阅读页和提纲条目；每章 `key_points` 列出归纳及支撑它的本章文字单元，内容确认稿逐条附原文；提纲带要点时每个条目写信息结构 `message`（见下文）；未决问题列入 `pending_issues` |
| 4a. `SUMMARY_REVIEW` 独立总结审查 | 总结作者和论断清单作者之外的执行端 | 逐条要点判为 ENTAILED / PARTIAL / NOT_ENTAILED / CONTRADICTED，核心句和每条关系判为 SUPPORTED / UNSUPPORTED；原文不支持、矛盾、核心句或关系不成立为阻断问题，须修订总结或由审核人书面驳回 |
| 5. 内容确认 | 客户（操作人记录） | 绑定总结校验值；有未决问题、未经独立审查或有未处理的阻断问题时不能确认 |
| 6. `FACTS` 事实库 | 执行端 | 引文逐字存在于单元；显示文字只能是引文的逐字节选，不得删去否定/限定词；关键项（数字+比较符号+单位、技术缩写、专有名称）不得多出；同一对象同一属性不同取值自动成为冲突 |
| 7. `DECK` 页面规格 | 执行端 | 内容只引用事实编号；为贴合版面可从来源单元切出新的逐字事实（与事实库同一道核对，不得带推导，每条都须上页）；作者文字不得含数字、比较、专有名称或评价/方向性措辞；事实所在原句中没有上页、却限定它的分句（研究、人群、时间、地点、比较对象、条件或数字；在所示文字之后的只算“特别是／相较于”一类限定）须在本页另有事实写明，与删去的范围标签同样处理；转录记录为子项的表格行须用 `levels` 缩进在其上一级行之下；每条箭头有支持事实；提纲全覆盖；未上页的总结章节须写原因；页数与需求偏差、连续多页列表/表格给出提醒 |
| 8. `SECOND_READ` 第二次独立转录/截取 | 另一个执行端 | 与第一次逐格比对，一致则解除待确认；PDF 截取图独立再框一次，交并比 ≥ 0.9 视为一致，否则须人工说明 |
| 9. `SEMANTIC_REVIEW` 语义审查（两张检查表） | 两个互不相同、且与作者不同的执行端 | `COVERAGE` 覆盖/逐字：每个来源页、提纲条目、关键要点都有状态；`RELATIONS` 语义/关系：每条关系和多条目页面结构逐条判定。两张表都须逐条处置问题台账中的未闭环问题；BLOCKER 须修订页面并经独立复核标为已修复，或由审核人书面裁定。此前独立审核已通过、且内容指纹未变的条目（页面、来源页、教学条目、关系、章节）沿用原判定，不进入简报与结果合同（`carried_review` 只给计数），判定仍记在原审核人名下；有未闭环问题的条目每轮都重新判定 |
| 10. 人工确认 | 审核人 | 确认/否定推导，裁定来源冲突，对照原件确认转录 |
| 11. A 原生矢量生成 | Codex＋Adobe 执行端、程序 | 锁定内容 → 完整设计稿 → 版面拆解 → 去字 → SVG → 原生图形与锁定内容；自动排队及存档；检查溢出、重叠、文字／表格／备注；PowerPoint输出PDF/PNG并验证编辑能力 |
| 12. 前5页审核 → 风格确认 → 其余逐页审核 | 审核人、客户 | 审核绑定页面图片校验值；重新渲染即失效 |
| 13. 交付 | 操作人 | `deck.pptx`、`deck.pdf`、`facts_report.md`、`verification_report.json`、逐页 PNG 打包 |

任何上游变化都会让下游自动失效：资料、阅读或转录变化 → 论断清单；论断清单、阅读或提纲变化 → 总结；总结 → 总结审查；总结 → 内容确认与事实库；
事实库或需求 → 页面规格；页面规格 → 语义审查与渲染；渲染 → 页面审核与风格确认。
可在第 7 步之后随时生成草稿渲染（`render?draft=true`），草稿显示待确认标记，不能用于审核。

## 执行端协作

应用不调用模型，也不代替客户或医生通过任何环节。执行端（Codex、Claude 或人工）通过
本地传输工具领取任务合同、按 `result_contract` 撰写结果并提交：

```powershell
.\.venv\Scripts\python.exe tools\codex_worker.py list
.\.venv\Scripts\python.exe tools\codex_worker.py show FLOW_ID
.\.venv\Scripts\python.exe tools\codex_worker.py queue FLOW_ID READ_SOURCE
.\.venv\Scripts\python.exe tools\codex_worker.py claim FLOW_ID --worker Codex-A --out data\worker\task.json
.\.venv\Scripts\python.exe tools\codex_worker.py complete FLOW_ID --task data\worker\task.json --result data\worker\result.json
.\.venv\Scripts\python.exe tools\codex_worker.py render FLOW_ID [--draft]
.\.venv\Scripts\python.exe tools\codex_worker.py generate FLOW_ID
.\.venv\Scripts\python.exe tools\codex_worker.py generate FLOW_ID --first-pages 15
.\.venv\Scripts\python.exe tools\codex_worker.py generation FLOW_ID
```

- 任务合同的 `brief` 含资料、规则和结果模板；编号、校验值必须原样保留。
- 不做外部检索；不得新增资料中没有的事实。
- `SEMANTIC_REVIEW` 的执行端标识必须不同于事实库和页面规格的作者；`SECOND_READ` 必须不同于第一次转录者和截取者，且合同中不提供第一次的文字和截取框。
- 失败用 `fail FLOW_ID --task ... --error ...` 回报；租约15分钟，长任务用 `renew` 续约；最多3次任务尝试。失败排回队列，真实调用由执行端重领后完成。
- 新SUMMARY任务按brief的`chunks`（连续整页，每块≤5页、约100句）分块做。每完成一块用 `draft FLOW_ID --task ... --result 当前总结.json` 保存进度：代码校验已完成块的逐句登记并续约，有新完成块时清零尝试次数。会话中断后下一个领取者拿到`draft`（`done_chunks`及草稿），从下一块继续。所有保存过草稿的执行端都记为作者（`summary_meta.contributors`），不得再做SUMMARY_REVIEW。
- **分章撰写（2026-10-16）。** 多章资料可用 `set-chapters FLOW_ID --plan by_source|分章.json --operator … --reason …` 分章：每章 `{id, title, source_ids, outline_ids}`，每份资料、每个提纲条目恰好属于一章（`by_source` 为每份资料一章、提纲按序对应）。分章后 SUMMARY 与 SUMMARY_REVIEW 按章排队（`queue … SUMMARY` 默认排下一章，`--chapters` 指定），任务说明只带本章资料、论断和提纲条目，章节编号以“章id-”开头；本章资料完成论断清单即可开写，不必等全书。审查独立性按章判断，问题以 `SUMMARY:章id` 登记，只由本章审查回看、只退回本章修订。全部章节为当前版本时，程序按章序把各章原样拼接为全文总结并整体复验（`pending_issue_index` 按前面各章顺延）；全部章节审查为当前版本后才进入客户确认，确认对象仍是全文。改分章会搁置已有总结（快照记录在 `chapters_history`），原总结未闭环的审查问题按此决定记为人工裁定。分章不能与“先定整体结构”同时使用。
- **任务归档。** 已完成或已取消任务的说明与草稿在每次写入时移到快照文件（`task.archive` 记路径与哈希，`Store.archived_task` 可还原），项目数据只留在办任务。`tools/compact_projects.py` 可一次归档全部项目并压缩数据库。
- 旧整页图片流程的命令加 `--api fact`（含 `image` 命令）。
- A 主线新增 `VISUAL_DESIGN`、`VISUAL_LAYOUT`、`VISUAL_CLEAN`、`VISUAL_VECTOR`；启动生成后自动排队，素材齐备自动导出。PNG/SVG用 `asset` 连同真实回执提交，版面用 `complete` 提交JSON。详情见 [PPT_GENERATION_ROUTE.md](PPT_GENERATION_ROUTE.md)。
- 多执行端可用 `claim --binding PAGE_ID` 在原SQLite事务内领取指定页，`asset/complete --compact`取得简短回执；独立续约与工具限额由 `tools/visual_worker_runtime.py`管理。每端使用独立worker身份和任务文件、一页一个当前租约。当前协调agent派页；不代表服务器已能无人值守调用模型。详见 [PARALLEL_WORKER_PLAN.md](PARALLEL_WORKER_PLAN.md)。

## 论断清单与总结审查（原文 → 总结）

总结不直接从原文归纳，而是先列出每份资料说了什么，再由另一个执行端检查归纳是否忠实。

**论断清单（`CLAIMS`）。** 每页的论断是一个命题，只由原文片段组成：

```json
{"id": "k1", "type": "recommendation",
 "spans": [{"unit_id": "S01:s19:b4", "quote": "若生物制剂可及且可负担，对于符合以下条件的患者，考虑加用Type 2靶向生物制剂"}],
 "scope": {"population": "", "time": "", "condition": "若生物制剂可及且可负担"}}
```

- `spans` 是 1–8 个逐字片段，程序记下每段在单元中的字符位置。每段不超过200字：一句话或一个格子，不能整页引用。
  表格中的一个取值写成“行名 + 列名 + 格子”三个片段。
- `type` 取自：推荐、定义、标准/阈值、研究结果、比较、相关（非因果）、机制、作者解读/推测、产品信息、背景、讨论题。
- `scope` 的人群、时间、条件都是本页原文片段；原文没写就留空。
- 程序自动补上三项：限定词（“可能”“约”“仅”“不”等，词表在 `config/factdeck_lexicon.json` 的 `claim_qualifiers`）、
  关键数字、引文角标。
- 每份资料还有 `profile`：资料性质取自指南、共识、临床试验、真实世界研究、荟萃分析、综述、企业推广材料、说明书、病例、讲课材料、其他；
  出品方和日期须是资料中的原文。
- 正文页没有论断时须说明原因。原件的页标题和强调没有列入任何论断时，程序给出提示。
- 论断的编号为 `页面编号#k1`。

**总结引用论断。** 要点（`point_coverage`）、关键依据（`key_points`）和关系都列 `claim_ids`，程序据此推出所依据的单元。
核心句写 `{"claim_id": …}`，程序取该论断的原文和类型。要点文字中不见于所引论断的数字，程序列入 `unmatched_tokens`。

**独立总结审查（`SUMMARY_REVIEW`，`summary_review.v2`）。** 审查人只看所附论断和单元原文，逐条判断；每条`key_points`须返回对应`target_id`的结论，不能只写章节结论：
- 要点和章节总结：
  - ENTAILED：原文完整支持；
  - PARTIAL：大体支持，但有扩大、缺少限定词或范围不符，记为提示；
  - NOT_ENTAILED：原文不支持；
  - CONTRADICTED：与原文矛盾。
  后两种为阻断问题。
- 核心句和每条关系：SUPPORTED / UNSUPPORTED，UNSUPPORTED 为阻断问题。
- 重点检查：相关写成因果、解读写成结果、限定词或人群和时间丢失、数字不符、推广材料的说法被当作中立结论。
- 审查人须不同于总结作者和论断清单作者。
- 问题进入问题台账（编号 SR-），不随新一轮审查清空：下一轮须在 `prior_issues` 中逐条处置（FIXED 须引用当前版本编号，OPEN / NEEDS_HUMAN / RETAINED），同一位置仍有问题时并入原编号。
- 未闭环的提示须在内容确认时逐项确认已知悉（`acknowledged_issues`）。
- 阻断问题须修订总结，或由审核人在工作台书面驳回。确认稿逐条标出审查结论。

## 信息结构（总结与页面之间）

**内容规则版本 `content-rules.2026-10-16`**：新SUMMARY任务改为`model_understanding.v4`（逐句登记、逐句覆盖审核、分块续做，见[原文覆盖登记](SOURCE_COVERAGE_LEDGER.md)）。
v4总结是客户确认的完整笔记，DECK在确认之后按它出页（用户决定，2026-10-16；2026-10-17改为方案A）：每个内容页用`key_point_ids`标注所讲的总结要点；每节的core要点和全部limit要点（例外、禁忌、条件）每条至少一页、内容多就拆页，不允许删减；support要点可合并上页或不上页，不上页的由程序原样放进其所在节第一页的演讲者备注（“讲稿补充”），确认过的内容不丢失；页数由内容决定，不再提示“页数与目标相差较大”，DECK说明也不再要求参照目标页数或提纲建议区间。页面放核心句、关键数字/阈值、流程与分支，上页内容的限定与强度词必须随之上页；该页所标要点的总结全文由代码原样写入演讲者备注（“【讲稿】”，位于“【来源追溯】”之前），研究细节、机制列举、例子等由讲稿承载。只生成前N页的范围只校验所标要点有效。按10-13规则运行的项目须先`adopt-rules`才能再排任务；采纳记录在`rules_history`。

**2026-10-14 审计后的规则（内容规则版本 `content-rules.2026-10-13`）。**
- 信息结构不再只在提纲带要点时启用：每一章都写 `message`。提纲没有要点时，要点就是本章 `key_points`，编号按顺序为 `<章节id>.k1`、`.k2`……；内容页缺少焦点 `focus` 是错误，不再只是提醒。
- 本章页面上的每条候选关系都要处理（`candidate_decisions`）：采纳（须在 relations 中出现），或拒绝并给出规定原因（不是要点之间的关系 / 不属于本章要点 / 与已采纳的重复 / 所涉要点无资料支撑）。
- 审查合同不再预填通过结论，每一项都须明确判定。
- 语义审查 RELATIONS 另判“说少了”：每条总结关系的 `expression`（EXPRESSED / FLATTENED 被压平为并列 / MISSING 未上页），并逐章写下只看页面能复述的核心论点，判断核心句与局限是否在页面上（`chapters`）。
- 修订无法解决的问题（来源证据缺失、人工决策）一经提出就进入人工队列（NEEDS_HUMAN），不在修订循环中反复出现。
- 每个项目按建立时的内容规则版本运行；规则在项目中途变化时，新内容任务须先用 `codex_worker.py adopt-rules --operator … --reason …` 明确采纳并记录。

视觉设计只能放大内容里已有的结构，所以每个提纲条目要先说清三件事：最重要的是哪一句、要点之间是什么关系、哪些是限定。

**导入时，程序记录原件自身的信号。**
- 单元的 `signals` 记录作者的标记：
  - `title`：PPTX 的页标题（标题占位符，或页面顶部字号最大的文本框）、DOCX 的标题样式、PDF 页面顶部的最大字号行；
  - `emphasis`：框内部分加粗、标色或放大的片段。整框同一样式不算标记；页脚区的缩写和文献也不算。
- 资料的 `relations` 是候选关系，每条写明依据（`basis`）：
  - 原件箭头：先后或条件分支；
  - 表格：对象×属性；
  - “1、2、”编号：先后；
  - 连接词：满足任一、均需满足、条件、先后、对照、定义、证据。连接词表放在 `config/factdeck_lexicon.json` 的 `relation_connectives`。
- 候选只是提议，不因匹配而成立。

**总结时，执行端为每个提纲条目的章节写 `message`。**

```json
"message": {"core": {"claim_id": "S01:s7#k1"},
            "roles": {"outline_1.4": "core", "outline_1.1": "support", "outline_1.3": "limit"},
            "relations": [{"type": "sequence", "items": ["outline_1.4", "outline_1.1"], "unit_ids": ["S01:s7:a1"], "from_candidate": "R1a2b3c4d5e"},
                          {"type": "compare", "items": ["outline_1.1", "outline_1.2"], "claim_ids": ["S01:s6#k1", "S01:s6#k2"]}]}
```

程序核对以下各项：
- 核心句是核心要点所列的论断之一；
- 每个有资料支撑的要点都有角色，且恰好一条 `core`；
- 关系类型取自 `sequence / branch / any_of / all_of / compare / matrix / evidence / definition`；
- 关系引用的要点、论断和单元都存在，且在本章页面内；
- 引用候选时，单元须属于该候选；没有候选的关系须列出支撑它的论断。

没有候选的关系标为 `manual`，在确认稿中写“人工判断，请确认”。核心句恰好是原件页标题或强调片段时，程序记下 `marked`。

**确认稿是一份故事板。** 每个条目依次列出：
- 核心句及其出处；
- 关系：以文字图示表示，如“先后：A → B”“满足任一：A / B”“对照：A | B”；
- 支撑要点和限定要点。

末尾的“故事线”把各条目的核心句按讲述顺序排成一列。

**页面对齐信息结构。**
- 每个内容页用 `focus: {"fact": id}` 标出本页焦点。焦点须是本页显示的事实，并来自核心要点或某条关系的单元，否则给出提示。
- 关系所在页面的版式宜匹配关系类型，不匹配时给出提示：
  - 先后、条件分支：flow / timeline；
  - 满足任一、均需满足：cards / grid；
  - 对照：compare / table；
  - 对象×属性：table；
  - 结论←证据：hero / cards。
- 标为 `limit` 的要点，其原文事实必须显示在标注该要点的页面上，否则报错。
- 语义审查对照 `message`，核对焦点、关系与原文是否一致。

## 页面规格（DECK 结果）

```json
{"facts_sha256": "…", "title": "…", "theme": "navy-teal",
 "glossary": [{"text": "2型炎症", "fact": "t2.lead"}],
 "omissions": [{"section_id": "s4", "reason": "需求限定为临床医生，药物经济学不展开"}],
 "facts": [{"id": "d.eos.label", "unit": "S02:p3:b4", "quote": "外周血嗜酸性粒细胞计数", "section_ids": ["s1"]}],
 "pages": [{"id": "p1", "layout": "bullets", "section": {"text": "概述"}, "title": {"text": "…"},
            "lead": {"fact": "f3"}, "items": [{"fact": "f1"}, {"fact": "f2"}],
            "outline_ids": ["outline_1"], "section_ids": ["s1"]}]}
```

先设计版面，再定格子里放什么。事实库按要点抽取，颗粒度常常和版面不符：一句话可能要拆成标签和数值、流程节点、表格单元，或对照面板里的各项。
这时页面作者在 `facts` 中从来源单元切出新事实 `{id, unit, quote, display?, entity?, attribute?, value?, note?, section_ids}`。
这些事实与事实库走同一道程序核对：逐字引文、逐字节选、不得删去否定或限定词、同属性冲突。编号不得与事实库重复，每条都须在页面上用到，
不能带推导，也不能是图。语义审查合同中标为 `carved_by_deck`，审查人要对照原单元检查切分语境和标签与数值的配对。
改写、换算这类非逐字内容仍须回到事实库阶段写推导。任务合同的 `layouts` 为每种版式给出适用内容（`use_for`）和最小示例（`example`）。

修订版页面规格须在 `issue_responses` 中逐条回应语义问题台账中的全部未闭环问题（`review_issues`）：CHANGED（写明页面）、NOT_CHANGED（写明理由）或 NEEDS_HUMAN。是否修复由下一轮独立复核判定。
提交时，程序还会按句形提示容易丢失上下文的节选（`factdeck/context.py`，词表在 `config/factdeck_lexicon.json` 的 `context_signals`）：引导句没有带上它引出的条目、以转折或承接词开头而前文不在本页或上一页。语义审查合同对每条事实给出同样的提示。

流程图箭头的支持事实可以是本页引用的事实，也可以是原件箭头单元建成的事实。后者不必印在页面上，但同样进入待确认和语义审查（`edge_facts`）。
原件箭头单元有两种来源：

- PPTX 中的原生流程图由程序在导入时从图形取出（`factdeck/diagram.py`），单元方法为 `pptx_arrow`，文字为“起点→终点（标签）”。
  单元同时记录两端和标签对应的文本框单元。来源包括粘连在图形上的连接线、未粘连但端点相接的连接线（含分叉的总线和折线连接线）
  以及方向箭头图形。只有无填充、无边框、至多4字的文本框才算箭头标签。按位置推断的箭头在位置说明中注明。
  用作支持事实时，两个节点须分别引用这两个端点单元的事实，方向一致。
- 图片中的流程图由 READ_SOURCE 逐格转录框和箭头，箭头格写成“起点→终点”；两端须与两个节点显示的文字一致。

箭头可带标签：`[起点, 终点, 支持事实, {"fact": id}]`，至多5字，由程序画在箭头上（PPTX 中为原生文字）。
原件箭头带标签时，页面必须引用原件中这条箭头的标签单元；页面没画出这个标签时给出提醒。
较早导入的资料可用 `tools\codex_worker.py backfill-structure FLOW_ID`（旧名 `backfill-arrows`）补上箭头单元、作者标记和候选关系。
补录前先确认已有单元逐一不变，再追加，不影响已确认的总结和事实库。

版式：`cover`、`divider`、`bullets`（1–8条）、`table`（2–7列，1–9行，单元格为引用列表）、
`cards`（2–4张卡片+最多4条注释）、`compare`（2–3栏+底部说明带；面板可改放一张原件图，一页至多两张图）、`flow`（最多16个节点，
网格 col 0–4 / row 0–3，节点可带 `tag` 标注作用点，箭头 `[起点, 终点, 支持事实]`，右侧最多4条说明）、
`statement`（一句核心结论+最多3条支持）、`closing`、`figure`（一张原件图+最多3条侧栏事实，
见 `docs/FIGURE_REFERENCE.md`）、`hero`（一个不超过16字的主数值+标签+最多3条支持）、`timeline`（2–6步，每步 when+what）、
`grid`（2–6格，每格 heading+1–3条）、`chart`（2–8根柱，见下）、`agenda`（目录，2–8条作者文字，编号由程序生成）。
视觉以 `output/factdeck_demo` 为准：
- 字号层级固定（标题 34、导语 17、正文 16–17，只有数值用大字），内容少时保留留白、不放大字号，内容多时逐级收紧；
- 较长的正文字号大于标题会记为渲染错误；
- 内容区为白底细边框，浅色只用于说明区，深色只用于强调条、主数字块、核心节点和表头；
- 主体紧接页眉，原文中的分行保留为分行（流程图小框内除外）；
- 流程图节点按文字高度排版，卡片按单张判断数值或词语字号；
- 表格未给 `widths` 时按内容长度分配列宽；首列是同一组对象的相邻窄表会提示合并为一张多列表。

图表 `chart`：每根柱 `{label, value: {"fact": id}}`，柱长由程序从 value 事实的文字中读出数字计算——
每条 value 事实须恰好含一个数字，不能有比较符号、区间或负号，各柱单位一致；从 0 起画，不画刻度数字（刻度会是没有来源的数字）。
渲染后按事实重算每根柱的长度并与实际绘制比对；PPTX 中的柱是原生矩形。数值来自多份资料时提示“并排暗示可比”，由语义审查判断。

绘图原则（2026-10-19）：图只承担文字讲不了的那一层。
- 每页都先问这一层是否存在：数值落在同一刻度上的位置（分级界值、阈值区间、比例），过程随时间的走向（轨迹、年份间隔），
  各部分如何相连（汇聚、分支、因果链、判断路径）。存在就画，并在 `design.figure` 写明它是哪一层；不存在就不画。
- 不画装饰：只重复旁边标签的图标、与文字无关的配图都不画。不画比原文多说的图：原文说不可等同的量不并排对齐，
  “以上”“不足”只画到原文给出的界（以上的部分用浅色延伸，不画成确数）。
- 图不带自己的文字：标签都是本页事实；刻度不写数字（数字会没有来源），位置由事实里的数字计算。
- 几何由事实决定：条形按比例；箭头有原文支持；`line` 块以 `encodes` 列出它画出的本页事实，坐标轴、网格写 `axis: true`；
  图标以 `for` 指向它代表的本页事实。程序检查：画了图（line/icon/arrow/bar）的 composed 页没有 `design.figure` 是错误；
  flow/timeline/chart 页没写是提醒；`encodes` 中的事实不在本页是错误。
- 先用原生方式画：composed 块、`factdeck/figures.py`（bands 刻度分段、curve 曲线）、代码绘制的 SVG 图标（PPTX 中为原生形状）。
  只有必须表现真实形态时才用生成图（位图，须医学核对）。
示例见 `output/lean_ch13_revised`：第5页按真实年份排开的时间轴、第11页同一百分比刻度上的两组占比、第14页年龄带、
第16页肺功能轨迹、第25页容积-时间曲线、第29页 0.7 界值与复查区、第34页 FEV1 分级刻度。

强调：任一事实引用可写 `{"fact": id, "emph": ["片段"]}`，片段须按顺序逐字出现在显示文字中，最多3段、不超过显示文字的六成；
只改变字重和颜色，PPTX 中为加粗、着色的文字段。

客户模板：在项目页导入客户的 .pptx/.potx，程序读取主题中的配色和字体，按对比度要求（主色/白≥7、强调/白≥4.5、
深底强调≥4.5、正文/白≥7）调整后作为 `brand` 配色使用，模板原色一并记录；可另传标志（内容页右上角）。
模板字体未安装在渲染机上时改用微软雅黑并提示，保证预览与 PPTX 的排版一致。只改变外观，文字、版式和核对规则不变。配色：`navy-teal`、`clinical-blue`、
`graphite-amber`、`forest`、`plum`。内容放不下时拆页，不要缩减原文。

## 人工确认

- `POST /confirmations/derivations/{id}`：确认或否定一条推导（改写、单位换算、表格列对应等）。否定后依赖它的事实被拒绝。
- `POST /confirmations/conflicts`：为来源冲突选定采用的事实；未采用的事实被拒绝。
- `POST /confirmations/transcriptions/{unit_id}`：对照原件确认转录文字（可修正）。
- `POST /semantic-review/issues/{issue_id}/dismiss`：书面驳回语义审查问题。
- `GET /confirmations`：当前页面所用事实中仍待确认的项目。

所有确认、审核记录为本地记录（`LOCAL_RECORDED_NOT_AUTHENTICATED`），不是在线身份认证。

## 边界

- 程序能保证：页面文字逐字来自原文、数字/单位/比较符号/专有名称未被改动、每条内容可追溯到原文位置、PPT 由预览页面逐元素导出并回读核对。
- 程序不能单独保证：节选是否脱离语境、并列是否暗示比较、是否漏讲——这些由独立语义审查和人工逐页审核把关。
- 扫描版 PDF 没有文字层时，页面会被标为需看原件，内容通过转录进入事实库并需要第二次读取或人工确认。
- 已选定的 A 路线允许生图建立完整设计参考，再去字、矢量化并填入原生内容。图像模型不能确认医学事实，
  生成的机制、解剖、数据和关系仍须来源支持；原件证据图片继续使用原件图片引用
  （`docs/FIGURE_REFERENCE.md`：原件内嵌图片与 PDF 区域截取均已实现）。生产自动接入状态见上述路线说明。

## 命令行

同一引擎可对文件夹项目运行（示例与调试用）：

```powershell
.\.venv\Scripts\python.exe -m factdeck <项目目录> <资料目录> <输出目录>
```

项目目录包含 `facts.json`、`deck.json`、`sources_manifest.json` 与可选的 `transcriptions/`。

## 可观测性（每次生成的耗时与 token）

`factdeck/jobstats.py` 为每个 job 记录：总墙钟时间、各阶段耗时（`stage`）、每次模型调用的
`model / stage / source / 耗时 / prompt_tokens / completion_tokens / total_tokens`。token 只取接口返回的
`usage`；接口没返回就记为 `null`（`tokens_known: false`，汇总里计入 `calls_tokens_unknown`），**从不估算**。

- 记录点：`app/semantic_model.call_semantic_model`（摘要、抽取、分诊、编排等能力，stage = 能力名）、
  `app/layout_ir._call_json_model`、选版式的大模型 tie-break（stage = `select`）、模板库整份生成
  `template_lib.pipeline.run`（select / fill / render_html / measure / native / verify）。没有活动 job 时不记录。
  `app/main.py` 的四个语义模型调用点各自开一个 job（若已在 job 中则并入）。
- 持久化：job 的输出目录写 `job_stats.json`；同时写入索引 `data/job_stats.sqlite`
  （或环境变量 `FACTDECK_JOB_STATS_DB`）。
- 执行端（Codex worker）任务：应用拿不到执行端的 token，`workflow_task_stats` 只统计每类任务的数量、尝试次数、
  领取→完成的墙钟时间（含执行端等待，非计费依据）和视觉回执里的 `elapsed_seconds`；token 一律标“unknown”。
- 查看：`python tools/job_stats.py`（最近 job）、`python tools/job_stats.py <job_id 或 job_stats.json>`、
  `python tools/job_stats.py --workflow <workflow_id>`；接口 `GET /api/deck/job-stats`、
  `GET /api/deck/job-stats/{job_id}`、`GET /api/deck/workflows/{workflow_id}/task-stats`。

### 已知限制（2026-10-14 代码审查，待下一轮处理）
- 更正转录或重新执行 `backfill-structure` 会改变候选关系，但不会让当前总结失效：总结中的 `from_candidate` 可能指向已不存在的候选，新候选没有决定。重算候选后须人工检查或重写总结。
- `rules_version` 只拦住新排的内容任务；采纳新规则前已排队的旧任务、人工编辑和 SUMMARY_AMEND 会按新规则校验。旧总结缺少 `candidate_decisions` 时只能重写，不能局部修订。
- 盲读判为 FAIL 后没有人工裁定入口；修订盲读只会换人重读同一张去字图，应改为重做设计稿或去字稿。
- 结构化提纲的 deck 只用 `point_ids` 时，语义审查的逐章复述会被跳过。
- `structure_first` 不能与带要点的提纲同时使用；开关变更记录在 `settings_history`，会让总结及其下游全部失效。
