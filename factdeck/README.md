# factdeck：事实库 + HTML 渲染的课件生成原型

目标：最终 PPT 的内容、描述、逻辑与原始资料一致，同时页面美观、可编辑。
思路是**从结构上保证正确**，而不是生成之后再检查。

```
原始资料 ──► 来源单元 ──► 事实库（逐字引文 + 位置） ──► 页面规格（只引用事实编号）
              │               │                           │
          可定位的最小单位   程序核对：引文存在、关键项一致    程序核对：作者文字不含医学内容
                          冲突/推导/图片转录 → 待人工确认     箭头必须有支持事实
                                                           ▼
                                   HTML/CSS 设计 ──► PNG / PDF / 原生可编辑 PPTX
                                                     程序核对：无来历不明文字、无溢出、PPTX 回读
```

## 各模块

| 文件 | 作用 |
|---|---|
| `sources.py` | 把原始资料拆成来源单元：PPTX 文本框/表格单元格/备注、PDF 页（两种读法，防双栏错乱）、图片表格转录。来源编号由 `sources_manifest.json` 固定 |
| `facts.py` | 事实核对：引文必须逐字存在；显示文字中的数字（含比较符号和单位）、药名、靶点、量表名必须在引文中；否则需要命名的推导并由人确认。同一药物同一属性不同取值 → 冲突 |
| `deck.py` | 页面规格核对：作者文字（标题、引导语）不得含数字、中文数量词、比较符号、药名或靶点，术语表中的词除外；机制图每条箭头要有支持事实 |
| `render.py` + `extract.js` | Jinja 模板 → Chromium 渲染 → 每页 PNG、PDF；从 DOM 导出原生 PPTX（文本框、表格、形状、连接线）；备注写入来源追溯；PPTX 回读核对 |
| `templates/deck.html.j2` | 设计规范与版式（封面、表格、指标卡、机制图、研究对比） |

## 运行

```powershell
.\.venv\Scripts\python.exe -m pip install -r factdeck\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m factdeck factdeck\examples\biologics output\raws output\factdeck_demo
```

输出：`deck.pptx`、`deck.pdf`、`slideNN.png`、`render_report.json`，以及项目目录下的
`facts_report.md`（拒绝项、冲突、推导、待确认清单）。

## 人工确认只需要做少数决定

在 `facts.json` 中：

- `derivations[].confirmed = true`：确认推导（例如“原表第 3 列 = 本瑞利珠单抗”、“202415 = 2024 + 角标 15”）
- `resolutions["奥马珠单抗|单价(元/支)"] = "<选定的事实编号>"`：解决来源冲突
- 图片转录文件中 `independent_reads = 2, reads_agree = true`：第二次独立读取（另一个模型或人工）一致

存在未确认项时，输出标记为“审核稿”，页面上以淡黄色圆点标出对应内容。

## 已知局限

- 程序核对拦不住没有数字的判断性措辞（如“疗效明显优于”）；这需要独立的语义审查模型逐句判断“原文是否支持这句话”，尚未接入。
- “漏讲重要内容”需要按大纲条目检查覆盖，尚未接入。
- HTML 在本机用思源黑体/Noto 渲染，PPTX 使用微软雅黑，行宽已预留 3%，仍需在 Windows PowerPoint 中抽查。
- 图片生成（ImageGen）只用于不含文字的插画：模板中的 `data-raster` 元素可直接替换为生成的 PNG。
