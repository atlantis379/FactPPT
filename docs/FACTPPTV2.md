# FactPPTv2 主线：FactDeck 生成线与执行端协作

主线是 **FactDeck**（`factdeck.v1`，接口 `/api/deck`）：任意类型的原始资料 → 全文总结 →
事实库 → 按需求编排页面 → 程序渲染为原生可编辑 PPT。页面上的实质内容只能来自事实库，
而事实库中的每一条都是来源原文的逐字引文，由程序而不是模型判定是否成立。

原“整页图片”流程（`57098-full-slide.v1`，接口 `/api/fact`）保留给已有项目，不再是主线；
它不能作为文字精确的渲染器使用。原语义接口 `/api/projects` 与 `/legacy` 不变。

## 流程

| 步骤 | 谁做 | 程序检查 |
|---|---|---|
| 1. 建项目：标题、教学提纲、需求（受众、目的、时长、目标页数、重点、语气、备注）、配色 | 操作人 | 需求字段与配色合法 |
| 2. 导入资料：PDF、PPTX、DOCX、XLSX、TXT/MD、PNG/JPG/WEBP | 操作人 | 拆成“阅读页”与“可引用单元”（文本框、表格单元格、备注、段落、工作表行），记录位置与校验值 |
| 3. `READ_SOURCE` 逐页阅读 | 执行端 | 每页都有记录；含图片/图表的页必须看原件；图表中的文字逐格转录为新单元（待确认） |
| 4. `SUMMARY` 全文总结 `full_source_summary.v2` | 执行端 | 覆盖全部阅读页和提纲条目；未决问题列入 `pending_issues` |
| 5. 内容确认 | 客户（操作人记录） | 绑定总结校验值；有未决问题不能确认 |
| 6. `FACTS` 事实库 | 执行端 | 引文逐字存在于单元；显示文字只能是引文的逐字节选，不得删去否定/限定词；关键项（数字+比较符号+单位、技术缩写、专有名称）不得多出；同一对象同一属性不同取值自动成为冲突 |
| 7. `DECK` 页面规格 | 执行端 | 内容只引用事实编号；作者文字不得含数字、比较、专有名称或评价/方向性措辞；每条箭头有支持事实；提纲全覆盖；未上页的总结章节须写原因；页数与需求偏差给出提醒 |
| 8. `SECOND_READ` 第二次独立转录 | 另一个执行端 | 与第一次逐格比对，一致则解除待确认 |
| 9. `SEMANTIC_REVIEW` 语义审查 | 与作者不同的执行端 | 逐页判断节选语境、并列/对比、箭头方向、作者文字、遗漏；BLOCKER 须修订页面或由审核人书面驳回 |
| 10. 人工确认 | 审核人 | 确认/否定推导，裁定来源冲突，对照原件确认转录 |
| 11. 渲染 | 程序 | HTML → 逐页 PNG、PDF、原生 PPTX；自动收紧字号直至不溢出；无来历不明文字、无溢出越界重叠、PPTX 回读每条事实都在 |
| 12. 前5页审核 → 风格确认 → 其余逐页审核 | 审核人、客户 | 审核绑定页面图片校验值；重新渲染即失效 |
| 13. 交付 | 操作人 | `deck.pptx`、`deck.pdf`、`facts_report.md`、`verification_report.json`、逐页 PNG 打包 |

任何上游变化都会让下游自动失效：资料、阅读或提纲变化 → 总结；总结 → 内容确认与事实库；
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
```

- 任务合同的 `brief` 含资料、规则和结果模板；编号、校验值必须原样保留。
- 不做外部检索；不得新增资料中没有的事实。
- `SEMANTIC_REVIEW` 的执行端标识必须不同于事实库和页面规格的作者；`SECOND_READ` 必须不同于第一次转录者，且合同中不提供第一次的文字。
- 失败用 `fail FLOW_ID --task ... --error ...` 回报；租约 15 分钟，长任务用 `renew` 续约；最多 3 次自动尝试。
- 旧整页图片流程的命令加 `--api fact`（含 `image` 命令）。

## 页面规格（DECK 结果）

```json
{"facts_sha256": "…", "title": "…", "theme": "navy-teal",
 "glossary": [{"text": "2型炎症", "fact": "t2.lead"}],
 "omissions": [{"section_id": "s4", "reason": "需求限定为临床医生，药物经济学不展开"}],
 "pages": [{"id": "p1", "layout": "bullets", "section": {"text": "概述"}, "title": {"text": "…"},
            "lead": {"fact": "f3"}, "items": [{"fact": "f1"}, {"fact": "f2"}],
            "outline_ids": ["outline_1"], "section_ids": ["s1"]}]}
```

版式：`cover`、`divider`、`bullets`（1–8条）、`table`（2–7列，1–9行，单元格为引用列表）、
`cards`（2–4张卡片+最多4条注释）、`compare`（2–3栏+底部说明带）、`flow`（最多16个节点，
网格 col 0–4 / row 0–3，节点可带 `tag` 标注作用点，箭头 `[起点, 终点, 支持事实]`，右侧最多4条说明）、
`statement`（一句核心结论+最多3条支持）、`closing`。配色：`navy-teal`、`clinical-blue`、
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
- 主线不生成插画：版式、装饰和图示都由代码绘制。图片生成模型只可用于不含文字的插画，但写实的机制/解剖类图本身在表达内容，
  无法由事实库核对，因此不计划接入。需要图时使用原件图片引用（设计见 `docs/FIGURE_REFERENCE.md`，尚未实现）。

## 命令行

同一引擎可对文件夹项目运行（示例与调试用）：

```powershell
.\.venv\Scripts\python.exe -m factdeck <项目目录> <资料目录> <输出目录>
```

项目目录包含 `facts.json`、`deck.json`、`sources_manifest.json` 与可选的 `transcriptions/`。
