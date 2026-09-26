# 57098产品流程与Codex协作

## 工作流与状态

资料导入后，每一单元都需要阅读记录。正文、参考文献与空白单元均需登记；
图表、图片和PPTX必须核对原始视觉内容。解析文字只是阅读的输入，不能自动
充当全文理解。资料不完整时不能提交全文总结。

`full_source_summary.v2`绑定来源、阅读记录、授课目标和教学提纲校验值；
章节引用所有资料单元，所有教学条目映射到章节，未解决问题列为待办。
客户在全文核对后，由操作人在本地记录姓名、时间、方式和反馈。
这些记录不代表在线认证身份，也不能代替医学内容审核。

确认后建立逐页锁定正文、来源、提纲映射和视觉方案。默认每批5页。
前5页全部完成图片与医学审核后，客户确认风格；不足5页时核对全部。
之后再生成其余页面。未审核/缺失/过期页面阻止交付。

## Codex执行端

应用不直接调用图片API，不需要图片API密钥，也不会在后台模拟Codex工具。
由操作者将项目协作指令交给Codex，Codex使用以下本地传输入口：

```powershell
.\.venv\Scripts\python.exe tools\codex_worker.py list
.\.venv\Scripts\python.exe tools\codex_worker.py show FLOW_ID
.\.venv\Scripts\python.exe tools\codex_worker.py queue FLOW_ID READ_SOURCE
.\.venv\Scripts\python.exe tools\codex_worker.py claim FLOW_ID --out data\worker\task.json
```

阅读/总结/分页任务：读取合同的 `brief` 与原件，按 `result_contract` 撰写结果。
单元ID、来源校验值和版本校验值需保持原样；不得新增未经来源支持的医学事实。

```powershell
.\.venv\Scripts\python.exe tools\codex_worker.py complete FLOW_ID --task data\worker\task.json --result data\worker\result.json
```

图片任务：调用内置 `image_gen`，遵循合同五部分提示词；生成全部锁定文字与图形。
风格确认后的参考图可从应用页面图片接口获取。参考图仅用于统一风格。
写入实际工具调用ID、生成时间、provider=OpenAI、engine=image_gen及初步QA：

```json
{
  "provider": "OpenAI",
  "engine": "image_gen",
  "tool_call_id": "实际工具调用标识",
  "generated_at": "实际生成时间（ISO8601）",
  "preliminary_qa": {"status": "NEEDS_HUMAN_REVIEW", "issues": []}
}
```

```powershell
.\.venv\Scripts\python.exe tools\codex_worker.py image FLOW_ID --task data\worker\task.json --png ACTUAL_OUTPUT.png --receipt data\worker\receipt.json
```

传输工具自动计算图片校验值并绑定所领取合同；它不伪造调用标识、时间或QA。
执行失败用 `fail FLOW_ID --task ... --error ...` 回报。租约15分钟，长任务用
`renew FLOW_ID --task ...`续约。最多3次自动尝试后需操作者重新排队。
完成后返回产品审核，Codex不得替客户或医生写入通过。

## 版本与交付

资料/提纲/授课目标变化使总结与后续成果失效；总结修订要求重新内容确认。
风格变化要求重新生成图片和样图确认。分页或页数变化重新绑定全部页面合同。
换图使该页审核失效；样图换图或重审使风格确认失效并取消后续在途任务。
历史合同、结果、确认、图片和交付版本保留，数据库任务状态通过事务修改。

导出前校验来源、内容与风格确认、全部页面合同、PNG校验值、生成凭据和审核。
交付包包含 `editable.pptx`、`image_pages.pptx`、逐页PNG、审核报告；备注保留正文和来源。
可编辑内容版是内容核对稿，其版式与生成的图片版并不完全相同。

结构校验不能验证图片中文字。文字和医学通过来自记录的人工审核；工具凭据
是执行端实际调用回传的审计记录，不是供应商签名证明。

## API

所有新接口位于 `/api/fact`，OpenAPI见 `/docs`：

- 工作流创建/查询/设置、资料上传/移除/原件下载。
- 任务排队、原子领取、续约、JSON结果/图片回传和失败回报。
- 总结与分页修订、内容/风格确认、逐页视觉/医学审核。
- 确认稿下载、审计记录、交付版本生成与下载。

服务默认绑定127.0.0.1。本版本为本地单操作人产品，不提供远程客户登录或在线审批。
