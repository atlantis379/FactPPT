# deckkit · 主题可插拔的 PPT 美化管线

**目标**：任意内容 × 任意视觉风格，都能产出专业版面 —— 而不是为某一份 PPT 定制。

```
deck.json  +  theme  ──►  slides.html  ──►  逐页 PNG / PDF  (可选 PPTX)
（内容）      （风格）      自包含单文件       Chromium 渲染
```

---

## 为什么它能"应对不同风格不同主题"

| 设计原则 | 含义 |
|---|---|
| **版式不含任何写死的颜色** | 9 类版式全部只引用主题令牌（`var(--heading)` 等），换主题不改一行布局代码 |
| **主题是纯数据** | 一个主题 = 一组颜色/字体/圆角/阴影令牌。新增风格只加数据，不加代码 |
| **插画与主题解耦** | 14 个矢量 motif 用 `currentColor` 绘制，自动继承当前主题的强调色（无需为每个主题准备素材） |
| **固定画布 + 绝对定位** | 每页固定 1280×720，区块按坐标摆放 —— 从结构上杜绝跑版、溢出、被裁切 |
| **无框架、无网络依赖** | 纯 HTML/CSS，Chromium 无头渲染；不依赖 Slidev/SPA，不存在"导出链路"故障 |

---

## 一条命令跑完整条链路

    python -m deckkit all 报告.docx --theme corporate -o out/report
    python -m deckkit all 论文.pdf  --theme clinical  -o out/thesis
    python -m deckkit all deck.json --themes corporate,acme-dark,cmcc-red -o out/multi   # 多风格变体

依次执行 extract -> build -> render -> pptx -> 门禁（溢出/对比度/图表/图片）-> 报告，
产出 deck.json / slides.html / 逐页 PNG / PDF / 原生可编辑 PPTX / pipeline_report.json / REPORT.md。
**任一阶段或门禁失败即非零退出**，可直接接入 CI 或批量运行。

完整的可复现证据清单见 deckkit/REPORT.md。

## 快速开始

```powershell
cd E:\EasyPPT

python -m deckkit themes                     # 列出所有主题
python -m deckkit check  deckkit\examples\gold.json      # 校验内容（类型/容量/字段）
python -m deckkit render deckkit\examples\gold.json --theme clinical -o out\gold
python -m deckkit gallery deckkit\examples\showcase.json -o out\showcase --png   # 一份内容 × 全部主题
```

产物：`out\<theme>\slides_<theme>.html`、`deck_<theme>.pdf`、`png\01.png …`

---

## 从文档自动生成（任意内容）

```powershell
# 任意 docx / pdf / txt / md  ->  deck.json
python -m deckkit extract "报告.docx" -o out\deck.json --theme corporate
python -m deckkit extract "论文.pdf" -o out\deck.json --theme clinical `
    --title "自定义标题" --brand "品牌名" --tagline "一句话主张" --source "来源说明"
```

抽取是**确定性 + 抽取式**的：**上到幻灯片的每一句都从原文摘取**（不生成、不改写、不编造数字），
因此自动生成的稿子天然保持源文可追溯。数字会自动识别为 `value`/`unit` 并优先进入指标页。

判定规则（按顺序）：

| 条件 | 归入版式 |
|---|---|
| 含表格 | `table` |
| ≥4 个带单位的数字 | `kpi` |
| 2–4 条短句 **且** 出现顺序词（①②③/首先/步骤/流程/阶段…） | `steps` |
| 2–4 条短句（枚举型，如获奖清单） | `cards` |
| 长段落 | `cards`（按句子分组，抽取式压缩到字数额度） |

### 实测（三份**未见过的**文档）

| 文档 | 类型 | 结果 |
|---|---|---|
| 研究一种融合多场景的高价值区域智能识别新方法 V1.4 | QC/技术方案 docx | 16 页，标题自动识别正确，奖项→卡片、成员→表格 |
| 金媛论文（答辩版本）V4 | 表格式学位论文 docx | 16 页，标题自动识别为真实论文题目，缩略词表/设备清单→表格 |
| GOLD 2026 解读（期刊 PDF） | **双栏**学术 PDF | 16 页，正文可用；**自动标题不可靠，请用 `--title`** |

### 已知边界（诚实记录）

1. **双栏学术 PDF 的自动标题/分节不可靠**：朴素行式抽取无法恢复栏内阅读序。请显式传
   `--title/--brand`，或优先提供 docx（抽取质量最好）。单栏 PDF 正常。
2. 抽取是**抽取式压缩**：超长句会按字数上限截断并加 `…`（原文不受影响）。
3. 表格只搬运单元格文本，不做跨页表格合并。
4. 扫描件（无文本层）不支持，需先 OCR。

---


| 主题 | 定位 | 主色 / 强调色 |
|---|---|---|
| `clinical` | 临床蓝 · 医学学术 | `#033E75` / `#268B90` |
| `corporate` | 企业深蓝 · 经营汇报 | `#12385f` / `#c8892b` |
| `editorial` | 纸感暖调 · 学术编辑（衬线） | `#7a3b2e` / `#3f6b58` |
| `techdark` | 深色科技 · 产品发布 | `#0e2a45` / `#25c2c7` |
| `mono` | 极简黑白 · 咨询风格 | `#111111` / `#c0392b` |

新增主题：在 `deckkit/themes.py` 的 `THEMES` 里加一组令牌即可（21 个键，缺键会被 `tokens_css` 直接报错，防止静默失效）。

---

## 输出格式（同一份 deck 与主题，三条产物线）

```powershell
python -m deckkit render <deck.json> --theme clinical -o out          # HTML + 逐页 PNG + PDF
python -m deckkit pptx   <deck.json> --theme clinical -o out\d.pptx   # 原生可编辑 PPTX
python -m deckkit audit  <deck.json> --theme clinical                 # 溢出/裁切审计
```

| 产物 | 定位 | 特点 |
|---|---|---|
| `slides_<theme>.html` | 视觉真源 | 自包含单文件；渐变/`color-mix`/精确间距，排版表达力最强 |
| `deck_<theme>.pdf` + `png/` | 投影与归档 | Chromium 渲染，所见即所得 |
| `*.pptx` | **交付与协作** | **原生可编辑**：标题/正文/数字/来源页脚都是真正的文本框；仅装饰性插画是位图 |

**PPTX 保真门**：导出后自动回读 PPTX 全文，逐条比对 deck 中每个字符串是否**逐字出现**，
缺字即 `fidelity: FAIL` 并列出缺失项 —— 不靠"文件能打开"就算通过。

> 换 `--theme` 即换整套视觉：HTML / PDF / PNG / **PPTX** 四条产物同步切换，配色与字体全部来自同一组主题令牌。

## 图表版式（数据类 PPT）

```json
{
  "type": "chart",
  "title": "试点比对：新增入网与无效退网",
  "subtitle": "数据全部取自申报书原文",
  "note": "口径：12 个街道试点，与集采图层空间叠置比对；单位：个。",
  "chart": {
    "kind": "bar",                    // bar | bar-grouped（多 series）| line
    "baseline": 0,                    // 柱状图必须显式声明（零基线策略）
    "categories": ["新增入网", "无效退网"],
    "series": [{ "name": "场景数量", "unit": "个", "values": [1124, 257] }]
  }
}
```

**同一份几何计算同时驱动 SVG 与 PPTX**，两版不可能漂移。规则是**强制**的，不是假设：

| 策略 | 行为 |
|---|---|
| 柱状图必须声明 `baseline` | 缺失 → 渲染为显式校验失败块，而不是画一张可疑的图 |
| 空值（`null`）不得按 0 绘制 | 跳过该点 + 在页脚显式列出"缺失值" |
| y 轴上限 | 整步长规则（1/2/2.5/5/10×10ᵏ），刻度读作 0/500/1000/1500 而非 3.75/11.25 |

### 几何校验（`chartcheck` / `chartselftest`）

```powershell
python -m deckkit chartcheck    <deck.json> --theme <t>   # 正例：逐标记比对
python -m deckkit chartselftest <deck.json> --theme <t>   # 注入破坏，证明校验器能抓错
```

校验器**不信任画面**：它按 deck 声明的数字用 `charts.compute()` 重算每个柱/点的位置与高度，
再与浏览器中 SVG 的实际 `getBBox()`（用户坐标系，不受页面缩放影响）逐项比对，容差 0.75 单位。

检查项：`GEOMETRY`（位置/高度）、`SERIES_ORDER`（系列归属）、`CATEGORY_ORDER`、
`VALUE_LABEL`（数值标签必须等于声明值）、`BASELINE`（必须存在且等于声明基线）、
`TRANSFORM`（y 轴变换）、`YTICKS`、`MISSING`（空值不得被画成 0）。

**已取证的正反例**（`chartselftest`，10 项全部符合预期）：

| fixture | 期望 | 实际捕获 |
|---|---|---|
| baseline-correct | PASS | PASS |
| geometry-wrong（柱高 ×1.45） | FAIL | `GEOMETRY` |
| series-swapped（交换系列归属） | FAIL | `GEOMETRY` |
| category-order-swapped | FAIL | `GEOMETRY` |
| label-altered（标签改 999） | FAIL | `VALUE_LABEL` |
| baseline-moved | FAIL | `BASELINE` |
| axis-rescaled（y 轴上限 ×1.3） | FAIL | `TRANSFORM` |
| extra-mark-injected（多画一个标记） | FAIL | `GEOMETRY` |
| missing-value-zeroed（给空值补 0） | FAIL | `GEOMETRY` |
| bar-without-baseline（未声明基线） | SPEC_FAIL | `SPEC_FAIL` |

## 从品牌色生成主题（任意风格）

```powershell
python -m deckkit theme-from "#E4002B" --name cmcc-red              # 浅色
python -m deckkit theme-from "#5B2C87" --name brand-purple --mode dark
python -m deckkit theme-from "#0E7C5A" --name brand-green --accent "#D9A441"

python -m deckkit themecheck                    # WCAG 对比度审计（全部主题）
python -m deckkit themecheck --themes mono,techdark
```

生成结果会存到 `deckkit/themes_user/<name>.json` 并被**自动加载**，之后任何命令都能直接
`--theme cmcc-red` 使用。也可以直接把品牌色当主题：`--theme "#E4002B"`。

### 推导规则（确定性）

| 令牌 | 来源 |
|---|---|
| `primary` | 品牌色压深到能承白色文字（品牌条底色） |
| `heading` / `ink` / `ink2` / `muted` | 品牌色相下的深浅中性色阶梯 |
| `bg` / `bg2` / `line` / `primary_soft` / `accent_soft` | 品牌色相的极浅色调 |
| `accent` | 默认取近互补色相（+158°），可用 `--accent` 覆盖 |
| `accent_text` | `accent` 的**高对比版本**，用于强调色文字 |
| `badge` / `badge_on` / `on_primary` | 实算 WCAG 对比度后选定，不靠亮度猜 |
| `ok` / `warn` / `danger` | 固定语义色相，按浅/深色模式调档 |

### WCAG 对比度强制（这是"任意品牌色都可用"的保证）

每一条承载语义的「前景/背景」配对都会被推到达标为止，**不是假设而是实算**：

| 配对 | 阈值 | 说明 |
|---|---|---|
| `ink` / `surface` | 7.0 | 正文 |
| `heading` / `bg`, `heading` / `surface` | 4.5 | 标题 |
| `ink2` / `surface`, `accent_text` / `bg`, `accent_text` / `surface` | 4.5 | 次级正文、强调色文字 |
| `on_primary` / `primary`, `badge_on` / `badge` | 4.5 | 品牌条、徽章文字 |
| `muted` / `bg`, `accent` / `bg` | 3.0 | 脚注、装饰标记（非正文） |

> 本轮用这把尺子回审了原有 5 套内置主题，**查出 2 处真实不达标**：
> `corporate` 的 accent 仅 2.74（已修正为 `#B77D27`）；`techdark` 的 `primary/bg`
> 属无意义配对（primary 是品牌条**底色**而非文字），已从契约中移除并改为
> `on_primary/primary`。同时引入 `accent_text`：文字用高对比版、装饰标记用原色。

**当前主题清单**：内置 5 套（clinical / corporate / editorial / techdark / mono）
+ 生成主题（cmcc-red / telecom-blue / brand-green / brand-purple …），
`themecheck` 全部 **0 违规**。

## 从现成 PPTX 模板继承风格

```powershell
python -m deckkit theme-from-pptx "公司模板.pptx" --name acme
python -m deckkit theme-from-pptx "深色模板.potx" --name acme-dark --mode dark
```

读取模板**真实的主体部分**（`ppt/theme/themeN.xml`）：

| 读取项 | 来源 | 映射到 |
|---|---|---|
| `accent1` | 颜色方案 | `primary`（OOXML 约定：accent1 是主品牌色） |
| `accent2…6` | 颜色方案 | `accent`（取第一个足够饱和的作为强调色） |
| `lt1` / `lt2` | 颜色方案 | `bg` / `bg2` / `surface` |
| `dk1` / `dk2` | 颜色方案 | `ink`（深色模板下 `dk2` 通常是浅色文字槽） |
| `majorFont` / `minorFont` | 字体方案（latin + ea + Hans） | `font` |
| 母版背景填充 | `slideMaster*.xml` 的 `p:bg` | `bg`，并据此**自动判定浅色/深色模式** |

> 只吸收**配色与字体**；版式始终使用 deckkit 的 16:9 固定栅格（模板若为 4:3，
> 命令会输出 `aspect_note` 明确告知）。导入后同样跑 `themecheck` 对比度契约，
> **不合适的企业模板不会产出不可读的幻灯片**。

**实测**（`examples/templates/` 两个合成企业模板）：

| 模板 | 提取结果 | 对比度 | 渲染审计 | PPTX 保真 |
|---|---|---|---|---|
| `acme-corp.pptx`（海军蓝+橙，微软雅黑） | primary `#1E4C76`、accent `#E47417`、font 微软雅黑 | PASS | PASS | PASS |
| `acme-dark.pptx`（母版深底+青/琥珀） | 自动判为 dark、bg = 母版色 `#0E141B`、heading 青 `#2FB8C6` | PASS | PASS | PASS |

### 导出的 PPTX 是一份**正规模板**，不只是"看起来对"

`pptx` 导出时会把 deckkit 令牌**写进导出包的 `ppt/theme/theme1.xml`**（颜色方案 + 字体方案），
并把页面底色注入母版 `<p:bg>`。因此在 PowerPoint 里：

- 主题颜色选择器显示的是**本设计的配色**（accent1=品牌主色、accent2=强调色 …），不是 Office 默认；
- 从功能区换主题色 / 拖动形状配色，能正确跟着主题走；
- 字体方案就是设计所用字体。

```powershell
python -m deckkit pptx deck.json --theme clinical -o out.pptx --roundtrip
python -m deckkit pptx deck.json --theme clinical -o out.pptx --no-inject-theme   # 旧行为
```

**往返校验（`--roundtrip`）**：导出后立刻用 `theme-from-pptx` 把主题读回来比对，分两级：

| 级别 | 检查 | 说明 |
|---|---|---|
| **种子保真** | `accent1` / `accent2` / `dk2` / `lt2` | **逐字节相等**（写什么就必须读到什么） |
| **派生稳定** | `bg` / `accent` / `ink` / `font` | 经重新推导后仍相等 |

> `primary` 有意**不**按字面往返：写入的 `accent1` 是品牌**种子**，读回时会由
> `from_brand()` 重新推导出品牌条主色（必须深到能承白字）。校验器把
> `primary` 与 `accent1` 对比，而不是与派生值对比 —— 这是语义正确的比法。

**实测**（5 种主题，含内置浅/深色、模板导入、品牌色生成）：

| 主题 | PPTX 保真 | 往返校验 | 不一致项 |
|---|---|---|---|
| clinical（内置浅色） | PASS | PASS | 0 |
| techdark（内置深色） | PASS | PASS | 0 |
| acme-corp（模板导入） | PASS | PASS | 0 |
| acme-dark（模板导入·深色） | PASS | PASS | 0 |
| cmcc-red（品牌色生成） | PASS | PASS | 0 |

## 图片版式（照片/实景配图）

```json
{ "type": "image-hero",  "title": "…", "subtitle": "…", "src": "assets/a.jpg", "focal": [0.24, 0.5] }
{ "type": "image-split", "title": "…", "side": "left", "src": "assets/b.jpg", "focal": [0.5, 0.2],
  "points": ["…", "…"] }
{ "type": "image-grid",  "images": [ { "src": "…", "caption": "…", "focal": [0.5, 0.45] } ] }
```

**槽位几何是唯一真源**（`images.GEOM`）：HTML 与 PPTX 都从这里取尺寸，不存在"CSS 里另写一个高度"的漂移。

### 裁切语义与策略（强制执行）

| 规则 | 行为 |
|---|---|
| 语义 | 与 CSS `object-fit:cover` + `object-position:fx% fy%` **完全一致**：源图上 (fx,fy) 的点落在画面 (fx,fy) 处 |
| 绝不拉伸 | `object-fit` 必须是 `cover`；PPTX 用原生 `crop_left/right/top/bottom` |
| 焦点安全区 | 焦点由公式保证留在画面内；校验器独立重算裁切矩形并比对 |
| 缺失素材 | 渲染为**带文件名的占位块**，而不是拉伸或静默留白 |
| 过度放大 | 裁切后放大超过 `MAX_UPSCALE=3.0` 时给出 `UPSCALE` 告警（不静默） |
| 自包含 | 引用的本地素材自动按相对路径复制到输出目录，HTML/PDF 可直接分发 |

### 裁切几何校验（`imagecheck` / `imageselftest`）

```powershell
python -m deckkit imagecheck    <deck.json> --theme <t>
python -m deckkit imageselftest <deck.json> --theme <t>   # 注入破坏，证明能抓错
```

校验器**不信任构建产物**：它从实时 DOM 读取 `naturalWidth/Height`、`clientWidth/Height`、
`object-fit`、`object-position`，**自己重实现一遍 CSS cover 算法**，再与 `images.crop_plan()`
按 deck 声明重算的结果逐字段（x/y/w/h，容差 1.5 源像素）比对。

检查项：`SRC_MISMATCH`（放错图）、`ASSET`（图未加载）、`FIT`（被拉伸）、
`BOX_ASPECT`（槽位比例被改）、`FOCAL`（焦点被改）、`CROP_RECT`（可见源矩形不符）、`UPSCALE`。

**已取证的正反例**（`imageselftest`，6 项全部符合预期）：

| fixture | 期望 | 实际捕获 |
|---|---|---|
| crop-correct | PASS | PASS |
| stretched（object-fit:fill） | FAIL | `FIT` |
| focal-reset（object-position:0% 0%） | FAIL | `FOCAL` |
| aspect-broken（改图片高度） | FAIL | `BOX_ASPECT` |
| src-swapped（两图互换） | FAIL | `SRC_MISMATCH` |
| asset-missing（src 指向不存在文件） | FAIL | `SRC_MISMATCH` |

> 本轮这把尺子回审时**查出一个真实缺陷**：CSS 里有一行 `.imggrid-cell .ph-img{height:300px}`
> 把网格图统一压成 300px，与几何模块声明的槽位（604×236）不一致 —— 静默改变了裁切比例。
> 已改为完全由 `images.GEOM` 驱动（绝对定位），并移除硬编码尺寸。
> 另外 `src-swapped` 一开始**没被抓住**：校验器从渲染后的图片重算裁切，属自证；
> 已补上**资源身份检查**（`SRC_MISMATCH`）。

### 双栏 PDF：栏感知抽取（pdf_mode）

期刊/报告的双栏 PDF 用朴素行序抽取会把左右栏**缝进同一行**，读出半句接半句的乱码。
现在默认走**栏感知**路径：

1. 用 **layout 模式**取得保留视觉版式的行；
2. 按行内的大段空白（>=5 空格）切出左右栏片段；
3. 单片段行用**行首缩进**判定归属哪一栏；
4. **按栏累积**（关键：只切分不累积会把句子切碎），再按 通栏 -> 左栏 -> 右栏 输出。

    python -m deckkit extract 期刊.pdf -o out/deck.json         # 默认栏感知
    python -m deckkit extract 期刊.pdf --pdf-mode flow -o ...   # 旧的朴素路径

**结构性判据**（可直接复核）：

| 指标 | flow（朴素） | columns（栏感知） |
|---|---|---|
| 检出双栏页 | 0 / 11 | **11 / 11** |
| 输入中把两栏缝在一行的行数 | — | **514（被切开的缺陷）** |
| **输出中含跨栏间隙的块数** | — | **0** |

**实测收益**（GOLD 2026 期刊解读 PDF，11 页双栏）：

| 项目 | 修复前 | 修复后 |
|---|---|---|
| 自动标题 | 期刊版权样板 / 随机正文句 | **《GOLD 2026 报告》关于慢性阻塞性肺疾病诊断、治疗、管理及预防全球策略更新要点解读** |
| 内容分节 | 35 | **199** |
| 输出块 | 1055（含串栏） | 945（**0 串栏**） |

本轮同时修掉两个抽取缺陷：

1. **pypdf visitor 的 tm 不是页面坐标** —— 必须用 CTM 做仿射变换
   （x = cm[0]*tm[4] + cm[2]*tm[5] + cm[4]），否则坐标毫无意义（x 范围只有 -1.3..146.7，而页宽 612）。
2. **前端裁剪会把标题裁掉** —— 遇到标题样行（>=12 汉字、无句末标点、非表单字段）也要停下；
   标题兜底从取最长改为**取出现最早的实质候选**（期刊标题就在页首），
   并把跨行拆断的标题**接回**（…全球策 + 略更新要点解读 -> 完整标题）。

## 版式原型（13 类）

| type | 用途 | 关键字段 |
|---|---|---|
| `cover` / `closing` | 封面 / 结尾 | `title` `subtitle` `motif` `meta_lines` |
| `steps` | 2–4 步流程图 + 导轨 + 结论条 | `steps[]` `rail[]` `callout` |
| `cards` | 卡片网格（2/3/4 列）+ 可选图形带 | `cards[]` `cols` `figure` |
| `kpi` | 关键指标大数字 + 图形 | `kpis[]`（`value/unit/tag/label`） |
| `compare` | 双栏对照 + 结论条 | `left` `right` `callout` |
| `timeline` | 横向里程碑时间轴 | `items[]` |
| `table` | 表格 | `columns[]` `rows[][]` |
| `chart` | **数据图表**（柱 / 分组柱 / 折线，含几何校验） | `chart{kind,baseline,categories,series[]}` 见上节 |
| \image-hero\ / \image-split\ / \image-grid\ | **图片版式**（全幅 / 图文分栏 / 网格，含裁切校验） | \src\ \ocal\ \images[]\ 见上节 |
| `statement` | 单点强调 | `body` |

内容 schema 见 `examples/gold.json`（医学，13 页）与 `examples/gis.json`（电信工程，11 页）。

---

## 插画（motif）

`wave` `bars` `nodes` `target` `shield` `globe` `layers` `flow` `gauge` `grid` `pulse` `scale` `check` `doc`

- 在 `motif` 字段填名字；不填则按页自动轮换，页面不会显得空。
- 全部 vector + `currentColor`，**换主题自动换色**。
- 需要真实照片/AI 插画时，把图片放进资源目录并在 motif 位置替换为 `<img>`（版式接口不变）。

---

## 已验证的通用性证据

| 证据 | 说明 |
|---|---|
| `out/showcase/<theme>/` × 5 | **同一份内容**（4 页：封面/流程/卡片/指标）在 5 种主题下的完整渲染 |
| `out/gis_corporate/` | **另一份内容**（GIS 申报书 11 页）× `corporate` 主题 |
| `out/gold_clinical/` | GOLD 2026 医学 13 页 × `clinical` 主题 |

---

## 已知边界（诚实记录）

1. **PDF/PNG 为最终视觉真源**；PPTX 若导出，复杂效果（渐变、`color-mix`）会有损耗，以 HTML/PDF 为准。
2. motif 是**抽象概念图**，不含人物/实景；需要实景插画时须自行提供素材。
3. 中文排版依赖系统字体（微软雅黑等），跨机器渲染需确认字体可用。
4. `steps` 最多 4 步、`kpi` 最多 4 项、`cards` 建议 ≤6 张 —— 超出会被 `check` 拦下（避免挤成一团）。
