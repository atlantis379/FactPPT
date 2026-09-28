# factdeck：事实库 + HTML 渲染引擎（主线）

目标：最终 PPT 的内容、描述、逻辑与原始资料一致，同时页面美观、可编辑。
思路是**从结构上保证正确**，而不是生成之后再检查。本目录是与主题无关的引擎；
应用中的完整流程（阅读、总结、确认、审核、交付）见 `app/deckflow.py` 与
[docs/FACTPPTV2.md](../docs/FACTPPTV2.md)。

```
原始资料 ──► 阅读页 / 可引用单元 ──► 事实库（逐字引文 + 位置） ──► 页面规格（只引用事实编号）
               │                          │                            │
        PDF/PPTX/DOCX/XLSX/TXT/图片   程序核对：引文存在、逐字节选、      程序核对：作者文字不含实质内容
                                     关键项一致；冲突/推导/转录待确认     箭头有支持事实、提纲与总结覆盖
                                                                        ▼
                                   HTML/CSS 版式 ──► PNG / PDF / 原生可编辑 PPTX
                                                     程序核对：无来历不明文字、无溢出越界重叠、PPTX 回读
```

## 各模块

| 文件 | 作用 |
|---|---|
| `ingest.py` | 任意支持格式 → 阅读页 + 可引用单元（PDF页、幻灯片文本框/表格单元格/备注、Word段落/表格单元格、工作表行、文本段落）；图表转录单元 |
| `lexicon.py` + `config/factdeck_lexicon.json` | 关键项识别（数字+比较符号+单位、技术缩写、中文数量词、项目术语）、逐字节选判定、作者文字检查；不含任何特定疾病词表 |
| `facts.py` | 事实核对：引文逐字存在；显示文字须为引文的逐字节选且未删去否定/限定词；多出关键项或改写需命名推导并人工确认；冲突检测与裁定 |
| `deck.py` | 页面规格核对：版式结构与容量、作者文字、箭头支持、提纲覆盖、总结章节覆盖或省略原因、页数与需求 |
| `render.py` + `extract.js` + `templates/deck.html.j2` | 9 种通用版式、5 套配色；逐页自动收紧字号；Chromium 渲染 PNG/PDF；从 DOM 导出原生 PPTX；备注写来源追溯；PPTX 回读核对 |
| `sources.py`, `cli_facts.py`, `__main__.py` | 文件夹项目的命令行入口 |

## 命令行

```powershell
.\.venv\Scripts\python.exe -m factdeck factdeck\examples\biologics <资料目录> output\factdeck_demo
```

`examples/biologics` 是早期原型的样例（重度哮喘生物制剂），需要对应的 9 份原始资料才能通过事实核对。

## 已知局限

- 程序核对拦不住“节选脱离语境”“并列暗示比较”等语义问题；由独立执行端的语义审查（`SEMANTIC_REVIEW`）和人工逐页审核把关。
- 渲染字体优先使用微软雅黑，与 PPTX 一致；在非 Windows 机器上会回退到思源黑体，行宽已预留 3%，仍建议在 PowerPoint 中抽查。
- 扫描版 PDF 需要逐页转录。
- 不生成插画；原件中的图将以“原件图片引用”进入页面（设计见 `docs/FIGURE_REFERENCE.md`，尚未实现）。
