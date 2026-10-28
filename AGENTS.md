# FactPPTv2 — FactDeck mainline

## 目标、方案与验收标准（2026-10-25，先读）

本节为总纲；与下文冲突时以本节为准，并在 PR 说明中指出冲突。

### 目标
- 产品：源文档（指南、文献、研究资料）→ **可编辑原生 PPTX**，每个实质内容逐字溯源到原文，附溯源报告。
- 市场：汇报须与源数据一致的人；切入点呼吸与危重症医生；先做 SaaS，最终海外。当前阶段先做**中文功能验证**。
- 6 周目标（2026-10-12 起）：10 位医生各做出一份真实汇报 PPT，≥3 位愿付费。
- 三大问题：耗时长、token 高、视觉不到付费水准。

### 方案
1. **固定模板库主线**（`factdeck/template_lib/`）：Jinja HTML → Playwright 测量 → 原生 PPTX；不做逐页自由设计/整页生图。
2. **视觉**：药企投资者日/学术会议/咨询报告/GOLD 指南式——行动标题、一个主图表、3–4 条带数字要点、缩写/参考文献页脚；
   不做网页卡片风。主题 `gold_clinical`（深蓝页眉、单一金色强调、功能灰）。不嵌入商业模板素材、药企/GOLD 原图或 logo。
3. **版式**：封面/章节、要点卡、对照、流程、时间轴、决策算法树、评估矩阵、双路径树、试验设计、森林图、终点读出（柱/折线）、
   机制级联、数据表、研究格局泳道、证据要点。图表几何由填充数据计算，无装饰。
4. **选版式**（`template_lib/selector.py`）：规则按逻辑关系与数据形状打分 → 数据不足沿固定链降级 → 分数接近时才由大模型在
   合格候选中挑一个并给理由（不合格回退）→ 节奏：相邻内容页不同版式，图表页 ≥1/3。每页记录关系、信号、候选、降级、理由。
5. **溯源不变**：实质内容只引用逐字事实；不合格就降级，**绝不为凑版式编数据**。
6. **可观测性**：每次生成记录各阶段耗时与 token。

### 验收标准（功能项须有自动测试或可复现样例）
- [ ] 溯源：数字、药名、剂量、阈值、比较结论均可定位原文；溯源报告覆盖每页。
- [ ] 原生可编辑：文字、表格、图表、连接线可在 PowerPoint 直接编辑；无整页图片/嵌入 SVG。
- [ ] 选版式：COPD 样例与人工判断一致（当前 18/19，差异源于节奏规则）；数据不足正确降级且不改输入；相邻不重复；
      图表页 ≥1/3（有合格候选时）；每页有中文理由。
- [ ] 版式质量：Playwright 测量无溢出/重叠；示例数据页标“示例数据，教学示意，非诊疗建议”，真实试验名不与虚构数字同页。
- [ ] 回归：`tests/test_layout_selector.py`、`test_template_lib_v1`、`test_template_lib_pharma` 全过；全量失败数不高于基线
      （本机装 Playwright Chromium 后 22 个，均为缺失的旧夹具/资产）。测试不得写真实 `data/job_stats.sqlite`（见 `tests/conftest.py`）。
- [ ] 可观测性：输出总耗时、各阶段耗时、token。
- [ ] 性能：约 20 页中文汇报的耗时与 token 较基线明显下降（目标待基线后填写）。
- [ ] 产品：10 位医生完成真实汇报、≥3 位愿付费；视觉被评价为“可以直接拿去讲”。

### 现状与未完成（2026-10-25）
- 新项目默认 `generation_route: TEMPLATE_LIB`；DECK brief 下发 `template_library`；RENDER/`generate` 走 `template_lib/render_deck.py`
  （原生 PPTX + trace.md）。全流程测试 `tests/test_template_mainline.py`，记录 `docs/TEMPLATE_MAINLINE_RUN_2026-10-25.md`。
  **未用真实资料和真实执行端跑过。**
- 原生 PPTX：0 图片、0 嵌入 SVG；PowerPoint COM 自动比对，测试 deck 9 页差异 ≤0.016。WPS 未核对；渐变、局部圆角、小阴影、上标为近似。
- 溯源：`template_lib/bind.py` 绑定事实库，`pipeline.run(facts=…)` 输出每页 `trace.md`/`trace.json` 与备注【溯源】行。
  未做：真实项目事实库；模板页强调片段；COPD 样例 plan 仍为未绑定示例数据。
- 可观测性：模板生成、语义模型、tie-break 记录耗时与 token（取接口返回值）；Codex worker 只有次数和墙钟时间。无 20 页真实基线。
- tie-break 未在真实接口验证；规则权重只在 COPD 样例上手调。

### 决策记录（2026-10-25，用户已确认）
- **停用路线 A**（整页设计图→去字→矢量化→原生化；VISUAL_DESIGN/LAYOUT/CLEAN/VECTOR/BLIND_READ）：成本随页数线性增长且常返工
  （约 820 秒/页）。代码保留可读，不再投入，不为新项目排这些任务。
- **不留逐页设计后门**：模板页不回退 `composed`/`free`；不合格降到要点卡或数据表；装不下就新增版式（全体复用）。
- **视觉问题改模板**，不回到逐页设计。
- **溯源是主线前提**：显示文字只来自事实引用或受检作者标签，图上数值都在本页事实中，代码出溯源报告。
- 优先级：① fills 绑定事实库+溯源报告 → ② `/api/deck` 默认模板库（已完成）→ ③ 真实中文材料 20 页建耗时/token 基线 →
  ④ PowerPoint/WPS 人工核对 → ⑤ 最晚第 4 周医生试用。医生反馈前不新增版式。

## 项目约定

处理项目前先读 `docs/FACTPPTV2.md`。仓库独立于迁移来源，运行路径均从仓库根解析。主线 FactDeck（`factdeck.v1`，`/api/deck`）：
sources → summary → fact store → deck spec → 代码渲染原生 PPTX。整页生图流程（`57098-full-slide.v1`，`/api/fact`）只服务已有项目。

## Worker collaboration (mainline)

- The app owns sources, units, summaries, fact stores, deck specs, confirmations, renders and jobs. Workers author JSON; code decides acceptance.
- Claim with `tools/codex_worker.py`; complete every requested page/unit. `requires_visual` pages need actual visual inspection;
  never claim inspection you did not do.
- READ_SOURCE: record every page; transcribe text/numbers in pictures and charts cell by cell as seen; diagram boxes are cells,
  arrows are cells "start→end"; table sub-rows/subtypes name their group cell as `parent`; a body sentence the PDF text layer
  splits may be transcribed whole. Never guess unreadable content.
- Semantic-first (`semantic_map_first`, default since 2026-10-27): no CLAIMS/STRUCTURE/SUMMARY tasks; code cuts units into verbatim
  sentences (`factdeck/auto_claims.py`) and assembles the draft.
  - SEMANTIC_MAP: read every page; name topics in speaking order (role, one-sentence thesis, units, main line, `pages` budget) and
    their links; every substantive page belongs to a topic; titles/theses carry no numbers.
  - TOPIC_PASS (per topic): read all its sentences (table cells come with row/column headers); decide the question, messages
    (core / support / limit — limits stand alone — and reserve for notes), each citing sentence ids; relations with sentence ids;
    page plan; checks for unverifiable data (never drop it); left_out with reasons; gaps. Decide what matters before what fits:
    relevant overflow goes to reserve, not left_out. Labels carry no numbers; content is sentence ids only. Every sentence and
    table row is cited, checked or left out; judge each omission (typed `why` + note) — never script left_out. Customer
    `exclusions` are code rules: excluded sentences are neither shown nor citable.
- CLAIMS (older projects): per source page, claims of 1–8 verbatim spans (sentence or cell, never a page) with a type and scope
  fragments; source gets a profile. Excerpt and label only.
- SUMMARY (older projects): cover all pages and outline items citing `claim_ids`; keep doses, thresholds, operators, populations,
  limitations, uncertainty; list open questions. Structured outline items get a `message`: verbatim core sentence (prefer the
  author's titles/emphasis), one role per point (exactly one core; limits reach the pages), relations (prefer source candidates).
- FACTS: each fact quotes one source unit verbatim; `display` is only an in-order excerpt (never reword or drop a negation/qualifier).
  Anything non-verbatim goes to a named derivation for human review.
- DECK: substantive content is fact references only. If store facts are too coarse for a slot, carve new verbatim facts in the
  deck's `facts` (same gate, no derivations, each used on a page). Authored text (titles, leads, labels) organises only: no numbers,
  comparisons, drug/entity names or evaluative wording. Mark each content page's `focus` from the item's core or relations.
  Template pages: `"template": {"layout": <proposal or null>, "fill": {…}}`; the selector decides the layout and refuses fills for
  layouts it rejects. Every shown string is `{"fact": id}` or `{"text": label}`; every drawn number must appear in a fact shown in
  the same fill; page/figure numbers, data note and source footer are written by code (`template_lib/bind.py`).
  No `composed`/`free` pages for new work; rules for those pages in existing projects are in `docs/FACTPPTV2.md`.
- Reviews: SUMMARY_REVIEW, SEMANTIC_REVIEW, SECOND_READ need a worker identity other than the author/first reader (SUMMARY_REVIEW
  also not the claims author). SEMANTIC_REVIEW = two checklists (COVERAGE, RELATIONS) by two different independent workers.
  Each round answers every unresolved ledger issue (`prior_issues`: FIXED with evidence refs / OPEN / NEEDS_HUMAN / RETAINED);
  deck revisions answer in `issue_responses`; what a revision cannot fix goes to NEEDS_HUMAN, not re-reported. Open the source
  images you are asked to view; list only those viewed. Items an earlier independent round passed with unchanged fingerprint are
  carried (`carried_coverage`/`carried_review`), absent from brief and contract; judging one is refused. Carried verdicts stay their
  original reviewer's, so a holder of one checklist's verdicts is not given the other; items with open issues are never carried.
  SUMMARY_REVIEW judges each point ENTAILED / PARTIAL / NOT_ENTAILED / CONTRADICTED. Report problems honestly; never approve medical text.
- Route A and `/api/fact` image jobs: existing projects only; follow `docs/PPT_GENERATION_ROUTE.md` / `docs/FACTPPTV2.md` (real tool
  calls with actual receipts, view outputs before claiming inspection, never edit locked content, human gates mandatory). ImageGen is
  not an exact text renderer for any other pipeline.
- No external research by default. Report failed tasks as failed; never fabricate. Stop at customer/human confirmations and page review.

## Development

Before committing a change to sentence cutting (`factdeck/auto_claims.py`, `source_coverage.segments`), the topic-pass
contract or its checks, run `python tools/replay.py <data root> <workflow id>` on a project copy with accepted topic
passes: it re-accepts the archived results under the new code (no model calls, no writes) and names what would be
refused or read against changed text. For the cut itself, save `tools/cut_audit.py <data root> --save before.json` on
the old code and run `--against before.json` on the new: changed/added/removed sentences and anomalies fixed or
introduced (a mis-cut is named by code, never repaired by guessing). Stored sentence references carry text anchors;
never compare ids alone.
A task's input (its fingerprint) holds only upstream artifacts, never the output of a sibling task of the same kind
(per source, topic, chapter, checklist); feedback between siblings goes through an inbox decided in a follow-up
(e.g. `pending_referrals`). `Store.check_siblings` enforces it on every completion; the suite runs it strict.

Preserve legacy semantic endpoints and their safeguards. SQLite transactions serialize job claims; do not replace them with
concurrent writes to `data/projects.json`. Keep factdeck domain-neutral: subject vocabulary goes in project terms or
`config/factdeck_lexicon.json`, not code. The UI uses the user-selected licensed template (MIT or purchased); do not invent a
replacement shell, preserve its license, and do not treat premium addons as free MIT components.
