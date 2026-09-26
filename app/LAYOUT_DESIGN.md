# 模型参与的 PPT 布局 · 渲染 · 视觉复核

本模块从已批准的 Semantic Deck 开始。模型只决定页面构图；标题、Claim、数值、来源和关系始终由语义层锁定，并由 PPTX 回读校验。模板与主题只提供视觉约束，不决定每页的信息结构。

链路与责任分工：

```text
Layout IR 设计 → 编译 BeautificationPlan → 写出 PPTX → 回读验证 → PowerPoint 实物复核
  模型/现有工作流      native_beautifier      packager      render_readback       人 / 模型
```

模型与代码分权：**模型产出构图（语义摘要、版式选择、分组、权重、理由），代码计算坐标并验证边界**。模型不写文字、不改 Claim、不给自己打分。

## 1. 流程

1. `GET /api/projects/{id}/layout-design-brief` 获取页面目标、主信息、批准的证据与合法构图候选。可加 `?page_id=...` 只取一页。
2. `POST /api/projects/{id}/layout-design/run` 调用配置的模型逐页产出 Layout IR；或由现有模型工作流将 JSON 提交给 `POST /api/projects/{id}/layout-ir`。提交与自动调用都先验证语义摘要、Claim 覆盖、构图边界和文字容量。
3. `GET /api/projects/{id}/beautification-plan` 查看解析后的原生对象、坐标、候选理由与 `text_fit` 报告。
4. `POST /api/projects/{id}/layout-visual-review/run` 先构建可编辑 PPTX，再用本机 PowerPoint 逐页导出 PNG，让支持图片输入的模型对每张图给出 `PASS/REVISE` 与问题。记录绑定语义、Layout IR、编译计划、PPTX 字节和每页图片哈希。`GET /api/projects/{id}/layout-visual-review` 会指出缺页、待修页或过期的复审。
5. `GET /api/projects/{id}/presentation.pptx` 只交付全部页面已通过 W15 视觉复审的**同一份 PPTX 字节**。结构回读、语义和合规门仍各自独立；模型视觉 `PASS` 不等于临床事实批准，W16 人工门仍另行执行。

当前 Codex 模型无需充当 HTTP 服务：`POST /api/projects/{id}/layout-visual-review/render` 生成并返回已校验的 PPTX 与逐页 PowerPoint PNG 路径/哈希；模型逐页看图后，用 `POST /api/projects/{id}/layout-visual-review` 提交每页 `PASS/REVISE`、问题、对应 PNG 哈希和 PPTX 哈希。漏页或字节变化均拒绝登记。这个入口与自动视觉模型共享同一渲染与交付校验，不把人工/模型审稿 JSON 当作图片本身。若只提交 `REVISE`，交付继续阻断。

复审缓存按语义、Layout IR、编译计划和素材哈希建立；缓存 PPTX 若损坏或缺任一页图片，会重建。最终化校验回执放在输出目录之外，符合打包器的私有回执约束。真实 PowerPoint 单页冒烟验证已确认 PPTX→PNG→`REVISE` 记录→交付阻断的链路；它验证流程，不代表该页通过了视觉审美复核。

若希望自动闭环，调用 `POST /api/projects/{id}/layout-cycle/run`，请求体可指定 `page_ids` 与 `max_rounds`（1–3，默认 2）。它逐轮完成设计、PowerPoint 渲染和视觉点评：只重做返回 `REVISE` 的页面，但每轮都重新审阅**全套幻灯片**，因为任一布局变化都会使旧的整套视觉证明失效。达到上限时返回剩余问题供人工处理。没有合格图片模型、本机 PowerPoint 或全页 `PASS` 时，交付保持阻断。

模型调用使用 OpenAI 兼容的 chat-completions 接口。构图模型设置 `EASYPPT_LAYOUT_MODEL_URL`、`EASYPPT_LAYOUT_MODEL_ID`，视觉复审模型另设 `EASYPPT_LAYOUT_REVIEW_MODEL_URL`、`EASYPPT_LAYOUT_REVIEW_MODEL_ID`；两者不得是同一 URL 下的同一模型。密钥分别由 `EASYPPT_LAYOUT_MODEL_API_KEY` 与 `EASYPPT_LAYOUT_REVIEW_MODEL_API_KEY` 提供。默认可用回环地址上的本地模型；外部 HTTPS 端点只有在项目同时启用 `allow_external_generation` 和 `generation_data_egress_policy=CONTRACT_MINIMIZED` 时才会接收逐页简化设计简报或 PowerPoint 预览图。未配置模型时仍能生成供内部诊断的 PPTX 草稿，但正式交付缺少 W15 复审会被阻断。

**复用边界。** 第六章 25 页来源、50 页 PPTX 是回归样本，用来证明空结构页阻断、渲染回读和视觉复审能发现真实问题；它的版式或文案不是通用模板。下一份材料应重新执行全文阅读、分诊、叙事与分页，再由模型根据该材料的页面目标选择 Layout IR。

手动提交的单页 Layout IR 示例：

```json
{
  "schema_version": "layout-ir.v1",
  "semantic_digest": "从 layout-design-brief 复制的摘要",
  "pages": [{
    "page_id": "p1",
    "archetype": "FLEX_COMPOSITION",
    "focus_claim_id": "c1",
    "layout_tree": {
      "kind": "row", "gap": 28,
      "children": [
        {"kind": "claim", "claim_id": "c1", "weight": 2},
        {"kind": "claim", "claim_id": "c2", "weight": 1}
      ]
    },
    "rationale": "先呈现核心证据，再补充解释边界"
  }]
}
```

`FLEX_COMPOSITION` 是一棵受约束的横排/纵排树：模型决定分组、留白与权重，布局编译器计算坐标。每个批准的 Claim 必须恰好出现一次且保持原顺序；目前只用于没有显式关系连接线、Claim 数为 2–4 的页面。关系页继续走可审计的流程图版式。文字容量不足会拒绝构图，要求模型重试或回到分页阶段，不会截断事实。

版心容量是硬约束，不是风格偏好：`FLEX_COMPOSITION` 的版心固定为 `top=230, height=334`，单行高度下限 100px，因此 4 条 Claim 既不能做 4 行竖排，也不能在两行分组里塞下高密度文本。真实课件（13 页 / 193 字的 4-Claim 页）实测 864 组两行构图全部触发容量阻断，最终回退 `EVIDENCE_CARDS`。**要在这种页面上做焦点强调，须在分页阶段拆页**，不是在版式层硬挤。

模型候选还受页面语义硬约束：没有已批准的时间顺序信号，就不能选时间线；没有比较信号，就不能选比较栏。短文本的字号与证据区位置会随内容量计算，来源标签贴近对应 Claim。结构回读通过之后仍要查看实际 PowerPoint 渲染图，不能把 `PASS` 当作视觉质量评分。

## 2. 本层强制规则

登记在 [`config/rules/mvp_rules.json`](../../config/rules/mvp_rules.json)，与其余 HARD 规则同表：

| ID | 规则 | 强制点 | 动作 |
| --- | --- | --- | --- |
| `LD-01` | 渲染后的视觉阅读顺序必须等于该页已批准 Claim 顺序。构图不得改写已批准叙事。 | `layout_ir` + `render_readback` 阅读顺序检查 | BLOCK |
| `LD-02` | `FOCUS_EVIDENCE` 的焦点必须是本页第一条受批 Claim；把靠后的 Claim 提到页面首位属于叙事决策，归上游。 | `layout_ir.validate_layout_ir` | BLOCK |
| `LD-03` | 文字容量按交付文本框**真实得到的**内缩度量，不按声明的矩形度量。 | `layout_ir.assess_plan_text_fit` + `native_beautifier` | BLOCK |
| `LD-04` | Artifact Tool 运行时链接不上时打包**失败封闭**；`node_modules` 路径解析不出包不等于可用构建。 | `packager._ensure_node_modules_link` | BLOCK |

### 2.1 阅读顺序契约（LD-01）

回读用确定性模型判定顺序，不靠人眼：**同带内按左边界、带间按上边界**；带宽 = 参与对象高度中位数 × `ROW_BAND_RATIO(0.5)`，下限 4px。被比较的对象只有该页 `claim_ids` 声明的 Claim，共位图层（叠放遮罩/卡片对）不参与比较。

这两条推论必须记住：

- 焦点块和支撑卡若不在同一带，几何顺序就会落在两者之间。`FOCUS_EVIDENCE` 曾把焦点块按整条支撑栈垂直居中（文本 top=317），而支撑卡从 top=255 起排，`|317−255|=62 > 29`，焦点被判成页面第二条信息——纯版式假象触发了 BLOCK。修正做法是让焦点块与首个支撑卡同处第一阅读带，带内左边界更小，顺序即等于受批顺序。
- 页面相邻与讲述顺序不自动产生临床关系。含"因此、优先、推荐、相比之下"等跨页含义的转换必须有 Context Contract。

### 2.2 文本框内缩（LD-03）

写出器输出 `<a:bodyPr anchor="t">` 时不显式写内缩，读取方因此套用 DrawingML 默认值：`lIns=rIns=91440 EMU (0.1 in)`、`tIns=bIns=45720 EMU (0.05 in)`。IR 画布是 96 px/in，即**左右各 9.6px、上下各 4.8px**。

按声明矩形（内缩 0）度量会高估可用宽度，恰在换行临界点上少算一行：估算 2 行、渲染 3 行，第三行压住下方的 provenance 标签。真实课件里 S02-c04 与 S09-c27 都栽在这里（框高 67px，实际需要 89px）。因此 `layout_ir.text_frame_insets(kind)` 是唯一入口：`kind="text"` 用 DrawingML 默认值，形状（卡片）保留自带内边距预算，`assess_plan_text_fit` 与 `_layout_flex` 共用它。

> 判断哪边是"对的"：计划声明文本框就是那个矩形，渲染器不得静默缩小文字区。两个方向都可修，本项目选"让估算器对齐渲染器"，因为内缩是输出格式的真实属性，任何打开该 PPTX 的读取方都会得到它；把 writer 的内缩清零是跟格式对抗。

### 2.3 FLEX 树必须"行在外、列在内"（`LD-01` 的构件级约束）

`row[column[c1,c2], column[c3,c4]]` 是最自然也最危险的写法：c1 与 c3 落在同一条阅读带，页面读作 c1、c3、c2、c4，等于静默改写受批顺序。规划器现在**在算坐标时就拒绝**这种树并给出改法（`column[row[…], row[…]]`），不再等到渲染回读才报 BLOCK——设计者应当在设计时听到这件事，且要听到怎么改。

### 2.4 标题与其他文字按框选字号（`LD-03` 的延伸）

页面标题来自已验收的读取件，通常是行动标题（"标准下调为过去一年≥1次中重度急性加重"），天然长于一行 38px。此前字号写死，编译器于是**拒绝已批准的标题**——要求缩短承载证据的文案来迁就一个硬编码的框。编译器拥有这个框，因此改为按框选字号（确定性阶梯 38→34→30→27→24→21），不低于声明下限。

同理，带 `conditions` 的 Claim 天然更长：FLEX 版心从 334px 提到 370px（564–600 这段此前是空的，来源页脚在 666），字号阶梯下探到正文级。**先让版式容纳受批文本，再谈缩小文字**；缩字缩到看不见条件，正是条件存在的意义被抹掉。

## 3. 渲染运行时（LD-04）

生成 PPTX 依赖本机 Artifact Tool runtime。Codex Desktop 环境会自动提供；其他本地环境通过 `EASYPPT_ARTIFACT_NODE`、`EASYPPT_ARTIFACT_NODE_MODULES`、`EASYPPT_ARTIFACT_BIN_DIR`、`EASYPPT_ARTIFACT_PYTHON`、`EASYPPT_PRESENTATIONS_SKILL_DIR` 指向等价运行时路径。

Node 从构建目录的 `node_modules` 解析 `@oai/artifact-tool`，所以每次构建都要把运行时链接进去。**判定成功只看包能否解析**，不看链接是否存在：

- 符号链接可能被环境降级成普通空目录且**不抛异常**（受限沙箱下实测如此），`Path.exists()` 会误判成功，故障随后在 Node 深处以 `ERR_MODULE_NOT_FOUND` 暴露；
- 无权限时退回目录联接 `mklink /J`；该命令输出为本地代码页（中文 Windows 上是 GBK），按 UTF-8 解码会抛 `UnicodeDecodeError`，因此控制台输出统一走 `errors="replace"`；
- 清理路径用 `cmd rmdir`（只删空目录或联接，不递归），拒绝替换非空目录。

失败时必须给出带原始输出的明确错误，而不是让下游报模块找不到。

## 4. 验证步骤

### 4.1 三件套一次产出

```bash
python -m app.beautify_cli APPROVED_SEMANTIC_DECK.json OUT.pptx \
  --layout-ir IR.json --plan OUT.plan.json --preview-dir OUT_PREVIEW
```

stdout 即回读验证结果 JSON，`status` 必须 `PASS`。生产交付再加 `--finalize --validation-receipt PATH_OUTSIDE_OUTPUT_DIRECTORY`，执行包完整性、布局、字体和 Artifact Tool 回读验证。

回读检查的对象是**实际写出的字节**，覆盖：Canvas/页数、必需对象与精确文本、几何漂移、越界、截断、空文本、阅读顺序、Z 序倒置、语义层遮挡。

### 4.2 PowerPoint 实物复核（不可省）

`--preview-dir` 里的 PNG 是写出器自带光栅化，**不等于放映效果**。涉及排版细节的复核必须用 PowerPoint 导出实物图：`python app/validation/render_with_powerpoint.py IN.pptx OUT_DIR`（win32com `Slides(i).Export(..., "PNG", 1280, 720)`），再逐页看。

真实课件实测：自带预览与 PowerPoint 的换行完全一致，但这一步仍是必需的——它是唯一能证明"渲染器真的这么排"的证据，也是发现文字压住标签、末行孤字这类问题的入口。

### 4.3 视觉复核判据

结构门通过不等于版面可用。逐页看实物图，按这四类判：

1. **文字**：是否溢出框、是否压住相邻对象（provenance 标签）、字号是否与信息层级匹配；
2. **层级**：第一眼看到的是不是该页主信息；焦点卡是否真的领先，而不是被支撑卡平分；
3. **留白**：空白是否集中在页脚一带（底部堆空），还是分散为光学居中；
4. **版式语法**：并列内容用栅格、顺序内容用流程、比较内容用栏目——版式必须服务页面目标，模型选的版式不得与已批准关系冲突。

模型给出的 `PASS`/`REVISE` 只是视觉建议，不替代事实与来源验证，也不构成质量评分。

## 5. 渲染器比较与迁移

当前整改先保留生产用的 Artifact Tool 写出器，建立模型布局和验收闭环。PptxGenJS 与 automizer 尚未切入生产；后续应使用同一份 Layout IR 和代表性医学页面做盲评与往返测试，再决定渲染器迁移和客户模板路径。

`python -m app.compare_renderers SEMANTIC.json COMPARE_DIR --layout-ir IR.json --powerpoint-render` 会用同一份布局计划生成当前写出器与 PptxGenJS 两份 PPTX，分别做 Claim/关系/来源回读，并经 PowerPoint 导出 PNG 供逐页盲评。PptxGenJS 适配器对 IR 的 px 字号转换为 pt；不转换时，同一 IR 会在 PowerPoint 中显示为更大的文字。该比较器使用 `bench/node_modules/pptxgenjs` 的本地安装，也可用 `--pptxgenjs-module` 指定版本。比较报告始终保留 `VISUAL_REVIEW_REQUIRED`，因为结构校验通过不能证明版面优秀。

## 6. 未决发现

**CJK 行首禁则未生效（未修，证据已更新）。** 端到端实跑的 7 页里，第 04 页第二行以「，」开头、第 01 页出现末行孤字「。」。根因是文本 run 不带东亚语言标记，渲染器按拉丁规则断行。

原计划"只补 `lang="zh-CN"`"在本轮被否掉：`@oai/artifact-tool` 的类型声明里没有可设的语言字段，这条修法落不了地。**要与估算器的 CJK 禁则/标点挤压模型同批改**，否则容量门与实际断行会脱节（加了标记后每行能容纳更多字符，而 `measure_text` 仍按无禁则预测）。证据：`app/validation/run_gold2026_v2/png/slide-01.png`、`slide-04.png`。

另有 `FOCUS_EVIDENCE` 在半页留白上的表现：阅读顺序修复把焦点块从垂直居中改为顶部对齐后，左栏下方空出约 150px。顺序优先于留白，方向正确；若要优化，应让整块证据区在 242–640 内做光学居中，而不是回退阅读顺序。

## 7. 验证记录

- `app/validation/end_to_end_validation_20260913.md`：**原始材料 → 模型读全文 → 模型分段定呈现 → 出 PPT** 全链路实跑（GOLD 2026，11 页材料 → 27 条 Claim → 7 页交付件），含各阶段实测、17 个真实缺陷的定位与修正、逐页 PowerPoint 视觉复核与诚实边界。模型产物在 `app/validation/model_workflow/authored/`，交付件在 `app/validation/run_gold2026_v2/`。
- `app/validation/qualification/SEMANTIC-ACT-QUALIFICATION-v0.1.json`：模型端点的五项资格证据（全文完整性 100%、引文命中率 1.00、分诊与叙事覆盖 27/27、数字越界 0）。
- `app/validation/layout_validation_20260913.md`：GOLD 2026 COPD 13 页真实课件布局层验证（模型接入两条路径、分页数据来源、4 个真实缺陷的定位与修正、PowerPoint 实物复核结论、未决发现与产物清单）。
- `app/validation/out/`：修复前基线（回读 FAIL）与修复后交付件（回读 PASS），用作回归证据。
- `app/validation/*.py`：可复用脚手架——`model_endpoint_server.py`（运维方模型端点，含 `--mode dump`）、`semantic_act_qualification.py`（资格基准）、`prepare_model_response.py`（按内容校验并安装模型答案）、`apply_numeric_bindings.py`（reviewer 通道补全 RED 数字绑定）、`author_layout_ir.py`（按断言撰写的构图模板 → 可提交 IR）、`run_full_pipeline.py`（端到端阶段驱动）、`submit_layout_ir.py`、`recon.py`、`find_claims.py`、`render_with_powerpoint.py`、`check_reading_artifacts.py`。
