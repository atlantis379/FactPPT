# 逐单元去向与限定条件登记（2026-10-15）

## 已接入范围

新SUMMARY任务使用`model_understanding.v3`，新增`source_coverage.v1`；接受端强制校验，独立SUMMARY_REVIEW收到登记表与代码缺口报告。旧v1/v2总结、旧租约继续按原合同校验，不自动迁移或生成通过记录。没有新增API、自动模型调用或人工确认。

理解仍先于总结，页数、密度和展示取舍仍在DECK阶段处理。此登记是理解和总结的同步索引，不要求按每个单元写一个要点，不以机械拆句替代理解。

## 原文单元去向

合同中的`source_coverage_input`由本地代码从`all_units`生成，包括原生文字和当前转录/转录提案，列出全部单元ID、页ID、字符数和`source_units_sha256`。单元文本、来源页或集合变化会使旧登记失效。已缓存的图片检查不因此重复执行；现有视觉检查、转录确认和独立审核关口保留。

每个单元的`parts`由模型按完整语义划分，填写零起始字符区间`[start,end)`，代码回取原文，不要求模型重抄全文。如提交可选`quote`则必须逐字匹配。代码核对区间、不允许重叠，检查所有非空白字符有去向。页眉、标点、标题、图注不能被代码默默忽略；空单元仍需登记一行。

| disposition | 含义与要求 |
|---|---|
| EXPRESSED | 实质内容指向一个或多个`section_id/conclusion_id`理解结论；结论已有point_ids映射 |
| PENDING | 原文歧义、未能理解或尚未完成表达，绑定实际`pending_issue_index`，保留人工关口 |
| SOURCE_METADATA / METHODS_GOVERNANCE / REFERENCE_LIST / AUTHOR_DISCLOSURE / NON_SUBSTANTIVE_LAYOUT | 明确非论断分类及理由；独立审核判断分类是否成立 |
| DUPLICATE_TRANSLATION | 分类理由及`duplicate_unit_id`，由独立审核确认等义，代码不判断译文正确性 |

不提供“因PPT篇幅略去实质内容”的处置状态。跨章节/参考页内容不得直接绑成EXPRESSED，先PENDING裁定。一个很长的原文块挂到一个结论并不证明其每个含义均已表达，这需要独立审核检查。

## 每条结论的六类限定条件

`conclusions[].facets`必须恰好包括`population/time/threshold/condition/exception/negation`。同类存在多项时全部列入`items`，不能只填一项代表全部。

- `PRESENT`：列出每项`unit_id/source_quote`和`point_id/summary_quote`。原文引用必须在本结论EXPRESSED片段内；总结引用必须确实出现在本结论point正文，不能用context、理解层或证据索引代替。
- `NOT_STATED`：模型明确判断原文未述这一类条件，并说明理由。不是代码默认值，也不是“生成失败所以没有”。独立审核必须核验。
- `PENDING`：不确定或待修订，绑定`pending_issue_index`。现有人工确认的未决问题关口继续生效。
- `UNASSESSED`：骨架默认状态，禁止提交为完成结果。

例如时间项：

```json
{"status":"PRESENT","reason":"来源明确限定风险发生时段",
 "items":[{"unit_id":"u1","source_quote":"出院后最初几周",
           "point_id":"s1.k1","summary_quote":"出院后最初几周"}]}
```

这是字段示例，不是对实际章节的审核或修订。

## 本地检查与边界

代码一次返回全部结构缺口：未登记单元、单元内未登记文字、失效来源、无效/跨章节结论绑定、未判断字段、不在原文的引文、没有进入point正文的表达、无效待确认编号。报告`ACCOUNTED`仅代表登记与绑定完整；`semantic_status`始终为`NOT_REVIEWED`，不生成医学/语义通过。

代码不能判定：NOT_STATED是否误判、非论断分类是否滥用、一个字段是否还有未识别的第二项条件、两段不同措辞是否真正等义、原始提取/转录是否漏掉了图中文字。因此原始资料覆盖、独立审核及人工确认仍不可省略。登记在提取出的单元全集上闭合，不代表原PDF语义全集必然完整。

只读工具（不修改工作流）：

```powershell
python tools/audit_summary_coverage.py --summary FULL_SUMMARY.json --units UNITS.json --out output/coverage/report.json --scaffold output/coverage/scaffold.json
```

`--summary`是完整总结对象；`--units`可用all_units单元列表或既有来源缓存`pages[].units`。退出码2表示仍有结构缺口，0也不表示语义审核通过。scaffold只列单元和未判断字段，不自动分配去向、不默认SUPPORTED、不会改写原总结。

## 当前章节验证

S03旧版总结只读副本与登记骨架存于`output/source_coverage_rollout`。旧总结没有新登记，因此预期报告缺口；不能将“未登记”计为“医学内容遗漏”，也不能把本次代码测试当作新一轮盲测。后续需要模型按原文填写，再独立核验，才能评价真实漏检是否下降。

## v2：逐句登记与逐句审核（model_understanding.v4，2026-10-15）

起因：S03 v3首稿登记为ACCOUNTED，但独立盲评只有208/406（51.23%）条来源命题在要点正文中完整表达（`output/coverage_comparison_v3/REPORT.md`）。原因有三：登记片段可以是整页，只要挂到某个结论即算EXPRESSED；未写进总结的内容可以标PENDING；约1/3原文不在论断跨度内，被PENDING后不再表达。v4对新SUMMARY任务改为`source_coverage.v2`，旧v3总结和已领取的v3任务仍按v1校验。

作者端（代码硬校验）：

- `source_coverage_input.units[].segments`由代码按句末标点（。！？；!?;）切好单句。每个片段必须落在一个segment之内（`segment_index`即整句；句内再分处置才写`start/end`），整段/整页一次登记报`OVERSIZED_PART`。
- `EXPRESSED`必须带`expressions[{point_id, summary_quote}]`：`point_id`属于所绑定结论，`summary_quote`逐字存在于该point正文，否则`UNEXPRESSED_SOURCE`。context、证据索引、理解层不算。
- `PENDING`必须写`pending_kind`：`SOURCE_AMBIGUOUS`/`SOURCE_ILLEGIBLE`/`SCOPE_DECISION`。“还没写进总结”不是待定理由（`INVALID_PENDING_KIND`）。
- 论断清单标为论断的原文不能归为非论断分类（重复翻译除外），否则`CLAIM_SPAN_DISMISSED`。
- v2不再登记六类限定条件（`conclusions[].facets`），提交该字段报`OBSOLETE_FACET_LEDGER`；每条理解结论仍须至少绑定一个已登记片段（`UNBOUND_CONCLUSION`）。限定条件随原句写进point正文，由逐句审核判定。`conditions_and_limits`同一文本用于3个以上结论时总结被拒绝。
- 同一`summary_quote`代表4句以上原文时不阻断，但写入`warnings`交给审核逐句核实。

审核端（SUMMARY_REVIEW，独立身份）：brief附`coverage_targets`（每个片段的原文、处置及作者给出的表达），`result_contract.coverage_review`须逐条判定，不多不少。EXPRESSED片段判`FULL/PARTIAL/MISSING/CONTRADICTED`；其它片段判`ACCEPTED/REJECTED`。判为FULL/PARTIAL/CONTRADICTED时须在`point_evidence`给出所读point正文的逐字片段，代码核对存在，防止按位置排列的判定串错位；PARTIAL/CONTRADICTED须在`missing_facets`标明缺失类别：population/time/threshold/condition/exception/negation/modality/descriptor/relation/enumeration/number/other；说明文字以“?”为主（编码损坏）时拒收。非`FULL/ACCEPTED`必须写明缺什么，并作为BLOCKER进入总结问题台账（ref为片段编号），下次SUMMARY任务的`review_issues`带回给作者修订，下一轮审核按`prior_issues`逐条处置。代码只检查逐条完整；语义判断仍由独立审核负责。

写作规则（`factdeck/summary_evidence.py` RULES）：总结是完整教学笔记层；按连续1–3页一块完成“读→写→逐句登记”，不预设主题数或点数；列举、图表逐格（框/箭头/量表锚点与计分）、研究设计与效应值、机制链、定义标准、模态与比较词须照原文写全。

只读工具增加`--claims`，用于v2的论断归类检查：

```powershell
python tools/audit_summary_coverage.py --summary FULL_SUMMARY.json --units UNITS.json --claims CLAIMS.json --out output/coverage/report.json
```

### 实测与六类登记的删减（2026-10-16）

S03 p1–p10同一冻结清单（141条清晰命题）：v4修订稿要点正文完整表达139/141与140/141（两名独立盲评），v3首稿62/141（原评分者）与56/141（重评），旧版v2修订稿20/141。详见`output/coverage_comparison_v4/REPORT.md`。

第1轮逐句审核的7个问题中只有3个属于六类限定条件，另4个是强度（“至关重要”写成“有助于”、“尚未证明”写成“不能”）、描述词和关系。因此删去作者端六类登记，改由审核端在`missing_facets`标注缺失类别；六类及模态强度检查移入DECK的COVERAGE语义审查（`app/semantic_review.py`）。v3总结及其六类登记仍按v1校验。

随后完成的两项：

- 切句`sentence.v2`：句末的括号引文编号（“。(306)”“。(363,365,366)”）后面只有换行、句末标点或文末时并回前一句；后接正文的列表编号（“(1) 第一项”）仍另起一句。`source_coverage_input`和登记表记录`segmenter`；已提交的`sentence.v1`登记按原切法校验。S03全章由826句变为819句。单独成单元的图号（“Figure 2.1”）不变，按版式内容归类。
- 分块：brief的`chunks`把原文按连续整页分块（每块≤5页、约100句）。执行端每完成一块调用`summary-draft`保存草稿（API `POST /tasks/{id}/summary-draft`，CLI `draft`），代码用`chunk_progress`统计每块的登记问题、记录`done_chunks`并续约；有新完成块时清零尝试次数，会话中断后由下一个领取者从草稿继续。保存过草稿的所有执行端都是作者，SUMMARY_REVIEW须由其外的身份完成。SUMMARY_REVIEW同样带`chunks`：审核每判完一块的`coverage_review`就用同一接口保存（`review_progress`逐块核对判定齐全、依据存在），会话中断后由同一独立身份或另一个合格身份从草稿继续。

实验目录中的冻结稿按当时合同提交（含六类登记、`sentence.v1`切句），用现行代码校验会报`OBSOLETE_FACET_LEDGER`，第2轮审核的损坏说明文字会被拒收；实验结论以实验当时的记录为准。

### 整章试点（2026-10-16）

S03全章29页在验证副本`output/v4_pilot`的正式任务队列中运行（报告`output/v4_pilot/REPORT.md`）：作者4个会话完成10块首稿（62个要点、16,787字），第1轮逐句审核退回87个问题，一轮修订后第2轮审核确认85个已修复，剩7个。试点后补上：SUMMARY_REVIEW分块草稿、修订任务附`revision_base`、总结和审核结果中以“?”为主的损坏文字在提交时拒收。
