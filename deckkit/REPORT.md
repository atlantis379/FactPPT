# deckkit — 能力收口报告

> 目标：**应对不同风格、不同主题内容的 PPT 都能进行美化**，而不是针对某一份 PPT 做一次性美化。
> 本文是这套能力的可复现证据清单。

---

## 1. 一条命令：任意文档 → 成品 PPT（含全部门禁）

```powershell
python -m deckkit all "报告.docx" --theme corporate -o out\report
python -m deckkit all "论文.pdf"  --theme clinical  -o out\thesis --source "来源说明"
python -m deckkit all "deck.json" --themes corporate,acme-dark,cmcc-red -o out\multi   # 多风格变体
```

单次运行产出**四路产物**并跑完**五道门禁**：

| 阶段 | 产出 / 检查 |
|---|---|
| extract | `deck.json`（文档 → 结构化 deck，抽取式、源文可追溯） |
| build | `slides.html`（自包含，本地素材自动复制） |
| render | `png/*.png`（逐页）+ `deck_<theme>.pdf` |
| pptx | `deck.pptx`（**原生可编辑**，令牌写入主题部分 + 往返校验） |
| gate:overflow | 版式溢出 / 裁切审计 |
| gate:contrast | WCAG 对比度契约 |
| gate:charts | 图表几何独立重算（有图表时） |
| gate:images | 图片裁切几何 + 资源身份（有图片时） |
| report | `pipeline_report.json` + `REPORT.md` |

**任一阶段或门禁失败即非零退出**，可直接接入 CI 或批量运行。

---

## 2. 端到端实测（四类真实文档，全部 PASS）

| 输入 | 类型 | 页数 | 主题 | 门禁 | 耗时 |
|---|---|---|---|---|---|
| 研究一种融合多场景的高价值区域智能识别新方法 V1.4 | 技术方案 docx | 16 | corporate | 全部 PASS | 11.8s |
| 金媛论文（答辩版本）V4 | 表格式学位论文 docx | 16 | clinical | 全部 PASS | 12.6s |
| GOLD 2026 解读（`source.pdf`） | **双栏**期刊 PDF | 16 | techdark | 全部 PASS | 21.0s |
| `images.json` × 3 主题 | 图片版式 deck（多风格变体） | 5×3 | corporate / acme-dark / cmcc-red | 全部 PASS | 8.7 / 7.6 / 8.0s |

---

## 3. 架构：四条通用性原则

1. **版式里零个字面颜色** —— 只引用 `var(--token)`，因此换主题不需要改任何布局代码。
2. **主题是纯数据** —— 22 个设计令牌；5 套内置 + 品牌色无限生成 + 现成 PPTX 模板导入。
3. **插画是 `currentColor` 矢量** —— 14 个 motif 随主题自动变色，无需按主题准备素材。
4. **固定 1280×720 画布 + 绝对定位块** —— 从结构上杜绝跑版；并有审计门复核。

**几何只有一份真源**：图表与图片的槽位几何都由 Python 计算后同时驱动 HTML/SVG 与 PPTX，
两版产物不可能漂移，且都可被独立重算校验。

---

## 4. 能力矩阵

| 维度 | 覆盖面 |
|---|---|
| **输入** | docx · pdf（单栏/双栏） · txt · md · 已有 `deck.json` |
| **风格** | 内置 5 套（clinical / corporate / editorial / techdark / mono）+ 品牌色生成 + PPTX 模板导入 → 当前 11 套，`themecheck` 0 违规 |
| **版式** | 13 类：cover · closing · statement · steps · cards · kpi · compare · timeline · table · **chart** · **image-hero** · **image-split** · **image-grid** |
| **插画** | 14 个主题自适应矢量 motif |
| **产物** | 自包含 HTML · 逐页 PNG · PDF · **原生可编辑 PPTX（本身即正规模板）** |
| **门禁** | 溢出审计 · PPTX 逐字保真 · 主题往返 · WCAG 对比度 · 图表几何 · 图片裁切 |

---

## 5. 证据清单（均为可复跑命令 + 正反例）

### 5.1 版式与主题

| 证据 | 命令 | 结果 |
|---|---|---|
| 全主题溢出审计 | `python -m deckkit selftest <deck.json>` | **11 主题 / 0 失败** |
| 主题对比度 | `python -m deckkit themecheck` | **11 套 / 0 违规** |
| 主题独立性 | 同一 deck 换 `--theme` | HTML/PDF/PNG/PPTX 四路同步切换 |

本轮用对比度这把尺子**回审旧主题**，查出并修复：`corporate` accent 仅 2.74（→ `#B77D27`）；
`techdark` 的 `primary/bg` 是无意义配对（primary 是品牌条**底色**）；`badge_on` 靠亮度猜（→ 实算）；
并引入 `accent_text`（文字用高对比版、装饰标记用原色）。

### 5.2 图表（`chartcheck` / `chartselftest`）

校验器按 deck 声明的数字**独立重算**每个柱/点的位置与高度，与浏览器中 SVG 的
`getBBox()`（用户坐标系）逐项比对，容差 0.75 单位。

| fixture | 期望 | 实际捕获 |
|---|---|---|
| baseline-correct | PASS | PASS |
| geometry-wrong（柱高 ×1.45） | FAIL | `GEOMETRY` |
| series-swapped | FAIL | `GEOMETRY` |
| category-order-swapped | FAIL | `GEOMETRY` |
| label-altered（标签改 999） | FAIL | `VALUE_LABEL` |
| baseline-moved | FAIL | `BASELINE` |
| axis-rescaled | FAIL | `TRANSFORM` |
| extra-mark-injected | FAIL | `GEOMETRY` |
| missing-value-zeroed | FAIL | `GEOMETRY` |
| bar-without-baseline | SPEC_FAIL | `SPEC_FAIL` |

策略强制：柱状图必须声明基线；**空值不得按 0 绘制**并在页脚显式标注；y 轴整步长（0/500/1000/1500）。

### 5.3 图片（`imagecheck` / `imageselftest`）

裁切语义与 CSS `object-fit:cover` + `object-position:fx% fy%` 完全一致；校验器从实时 DOM 读取
真实尺寸并**自己重实现一遍 CSS cover 算法**再比对。

| fixture | 期望 | 实际捕获 |
|---|---|---|
| crop-correct | PASS | PASS |
| stretched（object-fit:fill） | FAIL | `FIT` |
| focal-reset | FAIL | `FOCAL` |
| aspect-broken | FAIL | `BOX_ASPECT` |
| src-swapped | FAIL | `SRC_MISMATCH` |
| asset-missing | FAIL | `SRC_MISMATCH` |

### 5.4 PPTX 是正规模板（`pptx --roundtrip`）

导出时把令牌写进 `ppt/theme/theme1.xml`（颜色 + 字体方案）并注入母版背景，因此 PowerPoint 的
主题色选择器显示的是**本设计的配色**。往返校验分两级：**种子保真**（`accent1/accent2/dk2/lt2`
逐字节相等）+ **派生稳定**（`bg/accent/ink/font` 重推导后仍相等）。

实测 5 种主题（内置浅/深色、模板导入×2、品牌色生成）：**全部 PASS，0 不一致**。

### 5.5 双栏 PDF 栏感知抽取

| 指标 | flow（朴素） | columns（栏感知） |
|---|---|---|
| 检出双栏页 | 0 / 11 | **11 / 11** |
| 输入中把两栏缝在一行的行数 | — | **514（被切开的缺陷）** |
| **输出中含跨栏间隙的块数** | — | **0** |
| 自动标题 | 期刊版权样板 / 随机正文句 | **完整论文标题** |
| 内容分节 | 35 | **199** |

---

## 6. 已知边界（诚实记录）

1. **扫描件 PDF（无文本层）不支持**，需先 OCR。
2. 模板导入**只吸收配色与字体**，版式始终使用 deckkit 的 16:9 固定栅格（命令会输出 `aspect_note`）。
3. 抽取是**抽取式压缩**：超长句按字数额度截断加 `…`（原文不受影响）。
4. 表格只搬运单元格文本，不做跨页表格合并、不支持合并单元格。
5. 图表类型目前为柱 / 分组柱 / 折线；无堆叠、环形、散点。
6. 抽取稿的**信息取舍**由确定性规则决定，不做语义改写；重要结论仍建议人工校一遍。

---

## 7. 复现入口

```powershell
python -m deckkit themes                 # 主题清单
python -m deckkit all <doc> --theme <t> -o out     # 端到端
python -m deckkit audit|chartcheck|imagecheck|themecheck   # 单独跑门禁
python -m deckkit selftest|chartselftest|imageselftest     # 门禁自证（正反例）
```
