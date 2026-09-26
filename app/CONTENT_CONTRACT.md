# v2 内容保真合同（第 1 项进行中）

`POST /api/v2/content/verify` 接收 `ContentPackage`，依次检查来源摘录、结论、页面文案和受控计算。响应的 `source_findings`、`assertion_findings`、`slide_findings`、`calculation_findings` 保留每个对象的状态与原因。`BLOCK` 不得交付；`NEEDS_REVIEW` 须经独立复核；`SUPPORTED` 仅表示本层合同通过，不代表原始材料自身真实。

公开接口只做预检：请求者提供的文件哈希和摘录不能证明真实文件内容。公开接口没有可信来源抽取记录，因此即使逐字一致也返回 `SOURCE_FILE_NOT_VERIFIED` 和总状态 `NEEDS_REVIEW`。内部 `extract_source` 已可从实际 PDF／Word／Excel 文件计算 SHA-256、抽取带原生位置的摘录，`verify_content_files` 再用这些记录核对内容合同。不能把客户端原样传入的摘录同时当作可信记录。抽取遇到空白 PDF 页、Excel 公式值缺失或非文本对象时会标为 `SOURCE_EXTRACTION_INCOMPLETE`，不能自动交付。

结论与页面文字只有逐字一致才可能自动通过。改写、缩写与多来源归纳进入复核；可检测的否定、方向、范围和强度反转以及未注明来源或受控计算的数字被阻断。受控计算必须关联两个带来源位置、数字和单位的数据事实，公式、输入和结果重新计算；结论还须关联计算及其输入来源。

`ReviewReceipt` 绑定结论／页面及依赖对象的内容指纹；作者不能为自己签发复核。模型复核需预先登记资格 ID。内部 `verify_content_package` 才接受服务器传入的复核凭据与资格清单，公开接口拒绝这些字段。当前尚无可信身份签发、持久化和模型资格注册流程；因此这一接口不能作为云端交付门。后续第 4、5 项须接入认证、审核权限、持久化与界面，并在每次内容或来源变更后重新计算指纹。

2026-09-25 复核发现，早期新增的公开 `/api/v2/reviewers`、`/api/v2/reviews`、`/api/v2/delivery-gate` 曾允许请求者自报审核身份，并把请求中的摘录直接作为可信来源。这些公开接口现返回 `503`，不得据此宣称审核或交付已可用。内部 `review_issuance` 与 `delivery_gate` 仍可用于构建后续认证流程；恢复 HTTP 路径前必须绑定服务器保存的原文件、内容版本和认证主体。
