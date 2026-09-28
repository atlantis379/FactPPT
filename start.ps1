param([int]$Port = 8001)
$ErrorActionPreference = 'Stop'
$FactRoot = $PSScriptRoot
Set-Location -LiteralPath $FactRoot
$FactPython = Join-Path $FactRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $FactPython)) { throw '请先运行 install.ps1 安装独立依赖。' }
$FactEnv = Join-Path $FactRoot 'runtime.env'
if (Test-Path -LiteralPath $FactEnv) {
    Get-Content -LiteralPath $FactEnv | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim().Trim('"').Trim("'"), 'Process')
        }
    }
}
Write-Host "FactPPTv2: http://127.0.0.1:$Port"
& $FactPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
