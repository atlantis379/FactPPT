$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$FactNodeExpected = (Get-Content -LiteralPath '.nvmrc' -Raw).Trim()
$FactNodeActual = (& node --version).TrimStart('v')
if ($FactNodeActual -ne $FactNodeExpected) { throw "需要Node.js $FactNodeExpected；当前是 $FactNodeActual" }
& python -c "import sys; assert sys.version_info[:2] == (3,12), '需要Python 3.12'"
if ($LASTEXITCODE -ne 0) { throw 'Python版本不符合锁文件' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { & python -m venv .venv }
if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
& .\.venv\Scripts\python.exe -m pip install -r app\requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Python依赖安装失败' }
& npm.cmd ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Node依赖安装失败' }
Write-Host '安装完成。运行 .\start.ps1 启动。'
