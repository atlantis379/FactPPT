# FactPPTv2 — FactDeck mainline

## 目标、方案与验收标准（2026-10-25，先读这一节）

本节是当前阶段的总纲。下文旧段落与本节冲突时，以本节为准，并在 PR 说明里指出冲突。

### 目标
- 产品：把源文档（指南、文献、研究资料）变成**可编辑的原生 PPTX**，页面上每个实质内容都能逐字溯源到原文，并附溯源报告。
- 市场：凡是需要“汇报内容必须和源数据一致”的人；切入点是呼吸与危重症医生。先做 SaaS（网页服务），最终目标是海外市场。
- 当前阶段：**先完成中文功能验证**，英文/海外之后再做。
- 6 周目标（Ship in Six，2026-10-12 起）：10 位医生各用 FactPPTv2 做出一份真实汇报 PPT，其中至少 3 位愿意付费。
- 当前三大问题：生成耗时长、token 消耗高、视觉不够好（达不到“愿意付费”的水准）。

### 方案
1. **固定模板库为主线**：放弃逐页自由设计/整页生图，改为一套固定版式库（`factdeck/template_lib/`），流程为 Jinja HTML → Playwright 测量 → 原生 PPTX。
2. **视觉标准**：参照药企投资者日、学术会议、咨询报告和 GOLD 指南的版式——行动标题、一个主图表、3–4 条带数字的要点、缩写/参考文献页脚；不做网页卡片风。主题 `gold_clinical`（深蓝页眉、单一金色强调、功能灰）。商业模板素材、药企/GOLD 原图和 logo 一律不嵌入。
3. **版式库**：封面/章节、要点卡、对照、流程、时间轴、决策算法树、评估矩阵、双路径树、试验设计、森林图、终点读出（柱/折线）、机制级联、数据表、研究格局泳道、证据要点。图表用填充数据计算出的几何，不画装饰。
4. **选版式**（`factdeck/template_lib/selector.py`）：先按内容逻辑关系和数据形状用规则打分 → 每个版式有最低数据要求，不够就沿固定链降级 → 只有分数接近时才让大模型在合格候选中挑一个并给一句理由（不合格输出一律回退）→ 整份节奏约束：相邻内容页不同版式，图表页 ≥ 1/3。每页记录关系、命中信号、候选、降级和理由。
5. **溯源不变**：实质内容只引用逐字事实；版式不合格时降级，**绝不为了凑版式编数据**。
6. **可观测性**：每次生成记录各阶段耗时和 token 用量，作为优化耗时和成本的依据。

### 验收标准
功能（每项都要有自动测试或可复现的样例输出）：
- [ ] 溯源：成品 PPT 中所有数字、药名、剂量、阈值、比较结论都能定位到原文位置；溯源报告覆盖每一页。
- [ ] 原生可编辑：文字、表格、图表、连接线在 PowerPoint 中可直接编辑，不是整页图片或嵌入 SVG。
- [ ] 选版式：COPD 样例中每页选择与人工判断一致（当前 18/19，唯一不同为节奏规则所致）；数据不足时正确降级且不改动输入数据；相邻内容页不重复；图表页 ≥ 1/3（可用合格候选时）；每页有中文理由。
- [ ] 版式质量：每个版式在 Playwright 测量中无溢出、无重叠；示例数据页标注“示例数据，教学示意，非诊疗建议”，真实试验名不与虚构数字同页出现。
- [ ] 回归：`tests/test_layout_selector.py`、`test_template_lib_v1`、`test_template_lib_pharma` 全部通过；全量测试失败数不高于基线（`miso/pharma-layouts` 为 62 个已知失败）。
- [ ] 可观测性：每次生成输出总耗时、各阶段耗时和 token 用量。

性能与成本（目标值待用户确认，先以可观测性数据建立基线）：
- [ ] 一份 20 页左右的中文汇报，生成耗时和 token 用量相比当前基线明显下降，具体目标在拿到基线后填写。

产品（6 周）：
- [ ] 10 位医生各完成一份真实汇报 PPT；至少 3 位愿意付费。
- [ ] 医生试用后的反馈中，视觉被评价为“可以直接拿去讲”。

### 尚未完成
- 选版式模块未接入主流程（`factdeck/deck.py` 仍由页面规划自由选版式）。
- 原生 PPTX 输出仍是占位（`native_hook.py` 只做准备）。
- 大模型 tie-break 未在真实接口上验证；规则权重只在 COPD 样例上手工调过。

Read `docs/FACTPPTV2.md` before processing a project. This repository is independent
of the migration source. All runtime paths resolve from this repository root.

The mainline is **FactDeck** (`factdeck.v1`, `/api/deck`): sources → summary → fact
store → deck spec → code-rendered native PPTX. The earlier full-slide image workflow
(`57098-full-slide.v1`, `/api/fact`) is kept for existing projects only.

The user selected visual route **A with native vectors** on 2026-10-01:
locked content/design → full design image with text → remove text → vectorize
artwork → native PPT shapes → locked native text/tables/data/connectors.
Read `docs/PPT_GENERATION_ROUTE.md` and its decision record. This is the selected
visual direction; the production API has not yet integrated these tool stages.

## Worker collaboration (mainline)

- The app owns immutable sources, units, summaries, fact stores, deck specs,
  confirmations, renders and jobs. Workers author JSON; code decides what is accepted.
- Claim tasks with `tools/codex_worker.py`; inspect the claimed brief and complete
  every requested page or unit. Pages marked `requires_visual` need visual inspection
  of the original. Do not claim inspection you did not do.
- READ_SOURCE: record every page; transcribe text and numbers in pictures/charts
  cell by cell exactly as seen; in diagrams, each box is a cell and each arrow a cell
  "start→end"; a table sub-row or subtype names its group cell as `parent`; a body sentence the
  PDF text layer breaks apart may be transcribed whole. Never guess or complete unreadable content.
- CLAIMS lists what each page of a source says: each claim is 1–8 verbatim spans
  (a sentence or a cell, never a whole page) with a type (recommendation, result,
  association, interpretation, …) and scope fragments; the source gets a profile
  (guideline, trial, promotional, …). Excerpt and label only; never reword or infer.
- SUMMARY covers all source pages and outline items, citing claims (`claim_ids`). Preserve doses, thresholds,
  operators, populations, limitations and uncertainty; list open questions.
  With a structured outline, each item gets a `message`: a verbatim core sentence
  (prefer the author's marked titles/emphasis), one role per point (exactly one core;
  limits must reach the pages) and relations, preferring the sources' candidates.
- FACTS: every fact is a verbatim quote of one source unit. `display` may only be
  an in-order excerpt of the quote — never reword, never drop a negation or
  qualifier. Anything non-verbatim goes into a named derivation for human review.
- DECK: substantive content is fact references only. Design the page first; when the
  store's facts are too coarse for a slot (label/value, flow node, table cell), carve
  new verbatim facts from source units in the deck's `facts` — same code gate, no
  derivations, each one used on a page. Authored text (titles, leads, labels)
  organises and names; it carries no numbers, comparisons, drug/entity names or
  evaluative wording. Mark each content page's `focus` from the item's core or relations.
  Choose layouts by content shape (flow/cards/compare/timeline/
  grid before bullets). Follow the project requirements; split dense pages.
  One page, one design solution: write each content page's `design` note first (what is seen
  first / read next / kept for reference / the one strong element and why), then choose a layout
  or compose the page (`composed`, `factdeck/compose.py`), or write its body as HTML/CSS
  (`free`, `factdeck/free.py`: every word in a fact or authored span, styles PowerPoint can reproduce; check the
  PowerPoint render, not only the browser's). Peers get identical treatment; a
  dropped scope label ("中国：") must be stated once on the page, and so must a clause of the
  fact's source sentence that sets its context (study, population, time, place, comparator,
  condition, number) when the page leaves it out. Sub-rows recorded under a parent cell nest
  under that row (`levels`). Whitespace and repetition are
  signals: fix them for that page or give the reason in `design.exceptions`.
  Drawing principle: a drawing carries only the layer the text cannot — where a number sits on
  a scale, how a course runs over time, how parts connect or branch. Ask it of every page: if the
  layer exists, draw it and state it in `design.figure`; if not, don't draw (no decorative icons
  or pictures, and no drawing that implies more than the source, e.g. aligning scales the source
  says are not equivalent). Drawings carry no words of their own: labels are page facts; geometry
  follows facts (bars proportional, arrows backed, a `line` names the facts it draws in `encodes`
  or is an `axis`). Draw natively first (composed blocks, `factdeck/figures.py`, code-drawn SVG
  icons that become native shapes); generated pictures only where real form must be shown.
- SUMMARY_REVIEW, SEMANTIC_REVIEW and SECOND_READ must be done by a different worker
  identity than the author / first reader (SUMMARY_REVIEW also not by the claims author).
  SEMANTIC_REVIEW is two checklists (COVERAGE, RELATIONS) done by two different independent
  workers. Every review round answers each unresolved issue in the ledger (`prior_issues`:
  FIXED with evidence refs / OPEN / NEEDS_HUMAN / RETAINED); a deck revision answers each one in
  `issue_responses`. Send what a revision cannot fix to NEEDS_HUMAN instead of re-reporting it.
  Open the source page images you are asked to view; list only those you viewed.
  SUMMARY_REVIEW and SEMANTIC_REVIEW carry forward items an earlier independent round passed whose
  content fingerprint is unchanged (`carried_coverage` / `carried_review`): they are not in the brief
  or the result contract; judge only what is listed. A result that judges a carried item is refused.
  Carried verdicts stay their original reviewer's, so whoever holds one checklist's verdicts is not
  given the other; items with unresolved issues are never carried.
  SUMMARY_REVIEW judges every point ENTAILED / PARTIAL / NOT_ENTAILED / CONTRADICTED. Report problems honestly; never approve medical text.
- Route A may generate full-slide design references with text to establish the
  visual design. Generated text, numbers and medical relationships are not content
  authority. Remove design text, trace the actual artwork into native editable paths,
  group components, and fill native text/tables/data/connectors from locked facts.
  Do not substitute an embedded SVG or a whole-slide bitmap for native geometry.
  Partial texture loss is accepted. Use the current muted blue-gray palette as a
  starting point. Original source figures still follow `docs/FIGURE_REFERENCE.md`.
- Route A is the default production mainline. Start/resume with `generate`;
  the application queues VISUAL_DESIGN → VISUAL_LAYOUT → VISUAL_CLEAN → VISUAL_VECTOR.
  Use the existing Codex + Adobe execution endpoint, submit actual PNG/SVG with
  `asset` and the exact receipt contract, and layout JSON with `complete`.
  View actual design/clean outputs before claiming inspection. Do not edit locked
  content in layout results. Complete assets automatically trigger native compile
  and PowerPoint rendering; human gates remain mandatory. See docs/PPT_GENERATION_ROUTE.md.
- No external research by default. For a failed task report failure; don't
  fabricate results. Stop at customer confirmations, human confirmations and page review.

## Earlier full-slide image workflow (`/api/fact`, `--api fact`)

Only for existing projects on that workflow: image jobs call the native `image_gen`
tool, generate the complete slide with all locked text, use the claimed five-part
prompt and approved sample reference, and store the actual PNG through the image
completion endpoint with a receipt of the actual tool call. It does not qualify
ImageGen as an exact text renderer for any other pipeline.

## Development

Preserve legacy semantic endpoints and their safeguards. SQLite transactions
serialize job claims; do not replace them with concurrent writes to
`data/projects.json`. Keep factdeck domain-neutral: subject-specific vocabulary
belongs in project terms or `config/factdeck_lexicon.json`, not in code.

The UI must use the licensed template selected by the user (MIT or a purchased
commercial template). Do not invent a replacement visual shell. Preserve the
selected template's license; do not treat premium addons as free MIT components.
