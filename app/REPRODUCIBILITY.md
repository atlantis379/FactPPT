# 阶段合同与交付证据（开发中）

本地写出路线的输入依次为获批 Semantic Deck、来源文件哈希、可选 Layout IR／编辑性资产、编译后的 BeautificationPlan。输出依次为 PPTX、`verify_pptx` 回读结果和质量报告。`app/stage_contract.py` 固定 `approved_content → page_plan → pptx_build → pptx_quality` 的顺序，每个阶段记录上游输入摘要、输出 SHA-256 与工具代码摘要。报告只证明所检查的对象和字节彼此匹配，不证明原始材料真实，也不能代替独立语义复核。

CLI 成功验证后默认写 `OUTPUT.pptx.quality.json`，也可使用 `--quality-report` 指定路径。正式交付需要 `--finalize --validation-receipt`；质量报告会核对 finalizer 凭据中的 PPTX SHA-256、包检查和布局检查。未 finalise 的 CLI 报告标记 `release_eligible=false`。Web 交付把最终报告写为交付文件同目录下的 `.quality.json`，并在交付清单中登记其摘要。缓存的 PowerPoint PNG 必须同时匹配 PPTX、逐页 PNG 和 finalizer 凭据。

从仓库根目录使用 Node.js `24.21.0`（见 `.nvmrc`）和 Python 3.12：

```powershell
 nvm install 24.21.0
 nvm use 24.21.0
npm ci
python -m pip install -r app/requirements.lock
python -m app.reproducibility
python -m pytest
python -m app.validation.smoke_public_writer
```

`app/requirements.lock` 锁定当前 Windows/Python 3.12 测试环境的直接与递归 Python 依赖；`package-lock.json` 固定公开 PptxGenJS 写出器的依赖图，`npm ci` 会按锁文件安装。默认本地写出和统一复现检查使用 PptxGenJS，不依赖私人运行时，也不隐式回退。`python -m app.validation.smoke_public_writer` 从最小来源绑定 Semantic Deck 生成临时 PPTX，并同时执行包回读和语义读回检查。Linux 云端环境及中文字体的度量一致性须单独解析和验证；Windows 锁文件不代表 Linux 云端路线已资格化。

只有调用正式 finalizer 的旧交付路线才需要本机私有 Artifact Tool 和 presentation finalizer。若需验证该可选路线，可按 `app/runtime.env.example` 配置后运行 `python -m app.reproducibility --finalizer`；`app/external_runtime.lock.json` 记录已观测到的包版本与 finalizer 哈希，但包仍为 private，独立取得、授权及跨环境运行均未解决。默认 PPTX 写出不需要该私有路线。PowerPoint 桌面预览属于可选集成测试，不是无桌面环境下运行统一测试的前提。

统一测试还需要 `httpx`（FastAPI TestClient）和 `jsonschema`（版本化 Schema 回归），两者及其传递依赖已进入 Python 锁文件。`deckkit` 的纯内容合同可在没有浏览器运行时的情况下导入；其旧 HTML→PNG/PDF 渲染是可选功能，单独安装 `deckkit/requirements-render.txt` 后还须执行 `python -m playwright install chromium`。该可选浏览器栈不属于 EasyPPT PPTX 写出路径，也不是运行统一测试的前提。

质量报告的 `report_sha256` 检查报告正文是否变化，`validate_quality_report` 还会重新比对当前获批内容、来源哈希、页面计划、finalizer 凭据和 PPTX 字节。它不是数字签名；若交付记录需要对抗具有文件写权限的攻击者，应结合现有审计链和第 4 项的事务存储权限。第 6 项仍需云端逐页渲染、真实材料基准及 PowerPoint 抽样对照，不能仅凭这份报告验收。
