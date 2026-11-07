# Install xuexitong-mcp from a release tag (Windows PowerShell 5.1+).
#   powershell -ExecutionPolicy Bypass -File install.ps1 [-Profile student|reviewer|teacher] [-Ref v0.3.0]
# The install is a git checkout so that `update` / `rollback` work later.
# No account, password, cookie or token is asked for or stored by this script.
param(
    [string]$Repo = "https://github.com/Leoliny87/chaoxing-teaching-mcp.git",
    [string]$Dir = "$HOME\xuexitong-mcp",
    [string]$Ref = "",
    [string]$Venv = "$HOME\.cache\xuexitong-mcp\venv",
    [ValidateSet("student", "reviewer", "teacher")][string]$Profile = "student",
    [string]$Python = "",
    [string]$ConfigDir = "$HOME\.config\xuexitong-mcp"
)
$ErrorActionPreference = "Stop"

function Need($cmd) { if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "缺少 $cmd，请先安装。" } }
Need git
if (-not $Python) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $Python = "py -3" } elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" } else { throw "缺少 Python 3.10+。" }
}
if (Test-Path "$Dir\.git") { throw "$Dir 已经安装过；更新请运行：`"$Venv\Scripts\python.exe`" -I `"$Dir\scripts\launch_stdio.py`" update" }

if (-not $Ref) {
    $tags = git ls-remote --tags --refs $Repo | ForEach-Object { ($_ -split "refs/tags/")[1] } | Where-Object { $_ -match '^v\d+\.\d+\.\d+$' }
    if (-not $tags) { throw "仓库里没有发布版本（vX.Y.Z 标签）。" }
    $Ref = $tags | Sort-Object { $p = $_.TrimStart('v').Split('.'); [int]$p[0] * 1000000 + [int]$p[1] * 1000 + [int]$p[2] } | Select-Object -Last 1
}
Write-Host "安装 $Ref 到 $Dir（角色：$Profile）"
git clone --quiet $Repo $Dir
git -C $Dir -c advice.detachedHead=false checkout --quiet --detach $Ref

Write-Host "创建虚拟环境 $Venv（Windows 上请保持短路径）"
& cmd /c "$Python -m venv `"$Venv`""
$py = "$Venv\Scripts\python.exe"
& $py -X utf8 -I -c "import sys; sys.path.insert(0, r'$Dir\server'); from xuexitong_mcp.updater import check_manifest; from pathlib import Path; p = check_manifest(Path(r'$Dir')); print('文件校验通过' if not p else '文件校验失败：' + '; '.join(p[:5])); sys.exit(1 if p else 0)"
if ($LASTEXITCODE -ne 0) { throw "文件校验失败，已停止。" }
& $py -m pip install --disable-pip-version-check -q -r "$Dir\requirements-lock-py314-linux.txt"
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败。" }

$cfgDir = $ConfigDir
$cfg = "$cfgDir\config.toml"
if (-not (Test-Path $cfg)) {
    New-Item -ItemType Directory -Force $cfgDir | Out-Null
    # write UTF-8 without BOM: Python's TOML reader rejects a BOM
    $text = ((Get-Content "$Dir\config\config.example.toml" -Encoding UTF8) -replace '^profile = "teacher"', "profile = `"$Profile`"") -join "`n"
    [System.IO.File]::WriteAllText($cfg, $text + "`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "已生成配置 $cfg（请按需填写 write_allow_courses、[tutor] 等）"
} else { Write-Host "保留已有配置 $cfg" }

& $py -X utf8 -I "$Dir\scripts\launch_stdio.py" --config $cfg --list-tools | Out-Null
if ($LASTEXITCODE -ne 0) { throw "自检失败。" }
$launch = "$Dir\scripts\launch_stdio.py"
Write-Host "`n安装完成。MCP 客户端配置示例："
@{ mcpServers = @{ xuexitong = @{ command = $py; args = @("-I", $launch); env = @{ XUEXITONG_MCP_BROWSER = "填你的 BrowserSkill 实例 ID"; BSK_AUTO_START = "0"; BSK_AUTO_UPDATE = "off" } } } } | ConvertTo-Json -Depth 5
Write-Host "`n以后更新：`"$py`" -I `"$launch`" update     回退：... rollback"
Write-Host "每日自动更新：`"$py`" -I `"$launch`" schedule  会打印要登记的计划任务命令"
