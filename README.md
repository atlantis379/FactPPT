# FactPPTv2

独立的本地医学课件产品，固化 `57098-full-slide.v1` 流程。

**资料导入 → 全文阅读与总结 → 客户内容确认 → 分页与视觉设计 → 前5页样图 → 客户风格确认 → 全页生成与复核 → PPT交付**

## 启动

需要 Windows、Python 3.12、Node.js 24.21.0。PowerPoint用于原有渲染复核功能。

```powershell
cd E:\FactPPTv2
.\install.ps1
.\start.ps1
```

默认服务 `http://127.0.0.1:8001`；也可双击 `start.cmd`。依赖已经按锁文件安装的机器可以直接启动。

新产品从空项目开始。旧项目数据未导入，原源码目录保留。新服务无需访问迁移来源目录。

## 能力

- 批量资料导入：PDF、PPTX、DOCX、XLSX、图片、TXT/MD。
- 全文阅读记录、来源位置、综合总结、章节与教学提纲覆盖。
- 两次本地客户确认，逐页视觉与医学内容审核，版本变化自动失效。
- SQLite任务队列、租约、最多3次自动尝试、断点续作与单页重生成。
- Codex内置ImageGen协作生成完整页面图片；无执行端时保持等待。
- 锁定PptxGenJS交付：可编辑内容PPT、整页图PPT、PNG和审核报告。
- 原语义流程在 `/legacy` 和既有 `/api/projects` 接口保留。

使用与协作细节见 [docs/FACTPPTV2.md](docs/FACTPPTV2.md)。迁移来源和逐文件校验记录见 `migration_manifest.json`。

界面模板等待用户选型，当前首页临时进入API文档。可选择MIT或购买的商用模板，
选定后接入上述流程。不会用自制界面替代选择结果。
