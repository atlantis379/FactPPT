# 医学 PPT 插画素材生成与复用规则（四页样例）

本规则补充 `STYLE_LOCK + CONTENT_LOCK + LAYOUT + VISUAL_METAPHOR + NEGATIVE_CONSTRAINTS`。页面内容来自已核对来源；插画只解释受批语义，不写医学正文或阈值。四页样例见 `validation/visual_sample_4_pages/visual_contract.json`。

## 1. 生成单位

- 以**一个独立的医学视觉主题**为一个生成任务，不以整页或整张大图为单位。第 4 页的“脓腔形成”“水平气液面”“治疗后吸收”是三个语义不同的主题，各生成一张；不能把三张有白底的画拼成跨卡片的大图。
- 每张生成素材必须是真透明 Alpha PNG，只保留主体及其必要的局部放大连线；不含白底、卡片、文字、数字、页码、边框或水印。PPT 的文字、卡片、顺序和来源标记由可编辑对象绘制。
- 房屋、医院等简单且需要跨页复用的符号优先使用同一套原生/矢量图标组件；只有独特而复杂的医学插画才走图片生成。

## 2. 先查复用，再决定是否生成

每个 `medical_illustration` 在 `VISUAL_METAPHOR.assets` 声明稳定的 `asset_key`、`TRANSPARENT_ALPHA` 和 `REUSE_BY_CONTRACT_DIGEST`。编译器用风格 ID、配色、描述、医学语义、来源引用和透明要求计算 `contract_digest`，**不把页码计入身份**。同一主题在另一页出现且这些条件相同，引用同一文件。

生成前读取 `asset_registry.json`。只有 `asset_key` 与契约摘要一致、文件 SHA-256 一致、图片为足够尺寸的 RGBA、四角 Alpha 为 0、且视觉样例复核状态有效时才返回 `REUSE`。缺失、语义变化、背景不透明或文件变动时返回 `GENERATE_REQUIRED`，仅为该主题输出一份素材提示词。不得因为同一素材在两页出现就再次请求图片模型。

`VISUAL_PASS_CONCEPTUAL_ONLY` 仅证明该素材用于概念样例的视觉复核，不代表临床事实批准。涉及 RED 医学判断的正式交付仍走 W16 人工门。

## 3. 四页样例的当前状态

第 4 页三张去底插画分别保存在 `lung_stage_01.png`、`lung_stage_02.png`、`lung_stage_03.png`。PPT 构建前会校验契约和注册表；当前三项均返回 `REUSE`，因此不再生成。`build_ppt_v2.py` 将它们独立放入三个卡片，PowerPoint 实物图中已无横跨页面的白底矩形。

可复核命令：

```powershell
python visual_prompt_contract.py validation\visual_sample_4_pages\visual_contract.json validation\visual_sample_4_pages\compiled_prompts --asset-registry validation\visual_sample_4_pages\asset_registry.json
python validation\visual_sample_4_pages\build_ppt_v2.py
python validation\render_with_powerpoint.py validation\visual_sample_4_pages\four_page_visual_sample_v2.pptx validation\visual_sample_4_pages\powerpoint_png_v2
```

第一条命令应报告 `reused 3 of 3 generated assets`；若素材未通过复用检查，只输出对应缺失主题的提示词，停止 PPT 构建，待生成、去底和复核后再登记。整页图片参考稿是另一条输出路径，仍需逐页校对锁定文字，不能反向成为医学事实来源。
