[CmdletBinding()]
param(
    [string]$WorkspaceRoot = "",
    [string]$PythonVersion = "3.13",
    [switch]$Clean,
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令失败（$LASTEXITCODE）：$Command $($Arguments -join ' ')"
    }
}

if ($env:OS -ne "Windows_NT" -or $env:WSL_DISTRO_NAME) {
    throw "此脚本必须在原生 Windows x64 PowerShell 中执行，不能在 WSL 中交叉构建。"
}
if (-not [Environment]::Is64BitOperatingSystem) {
    throw "只支持 Windows x64；当前系统不是 64 位。"
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
    $WorkspaceRoot = (Get-Item $ProjectRoot).Parent.FullName
}
$WorkspaceRoot = (Resolve-Path $WorkspaceRoot).Path
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "找不到 git。"
}
$requiredRepos = @(
    "arctic_route_contracts", "arctic_route_orchestrator", "work_package_a",
    "work_package_b", "work_package_c", "work_package_d"
)
foreach ($repo in $requiredRepos) {
    $repoPath = Join-Path $WorkspaceRoot $repo
    if (-not (Test-Path $repoPath)) { throw "缺少正式仓库：$repoPath" }
    & git -C $repoPath rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) { throw "缺少正式仓库或 Git 元数据：$repoPath" }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "找不到 uv。请先按 docs/BUILD_WINDOWS.zh-CN.md 安装并确认 uv 在 PATH 中。"
}
$BuildRoot = Join-Path $ProjectRoot "build\windows-x64"
$Venv = Join-Path $BuildRoot "venv"
$Assets = Join-Path $BuildRoot "runtime-assets"
$DistRoot = Join-Path $ProjectRoot "dist"
$ReleaseRoot = Join-Path $ProjectRoot "release"
$ReleaseZip = Join-Path $ReleaseRoot "Arctic_Route_Control_Center-Windows-x86_64.zip"
$WorkRoot = Join-Path $BuildRoot "pyinstaller-work"
$ExeDir = Join-Path $DistRoot "arctic-route-control-center"
$NativeRoot = Join-Path $ProjectRoot "build\windows-native"
$NativeEnvironment = Join-Path $ProjectRoot "packaging\windows\environment.yml"

if ($Clean) {
    # Keep the separately audited native Mamba prefix: recreating it is not
    # needed for a clean PyInstaller build and can be expensive.
    foreach ($target in @($BuildRoot, $DistRoot)) {
        if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    }
}
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null

$EcCodesPrefix = $env:ARCTIC_ROUTE_ECCODES_PREFIX
if ([string]::IsNullOrWhiteSpace($EcCodesPrefix)) {
    $EcCodesPrefix = $NativeRoot
    $nativeDefinitions = Join-Path $EcCodesPrefix "Library\share\eccodes\definitions"
    $nativeDll = Get-ChildItem -LiteralPath (Join-Path $EcCodesPrefix "Library\bin") `
        -Filter "*eccodes*.dll" -File -ErrorAction SilentlyContinue
    if (-not $nativeDll -or -not (Test-Path $nativeDefinitions)) {
        if (-not (Get-Command mamba -ErrorAction SilentlyContinue)) {
            throw "找不到完整的 ecCodes 前缀，也找不到 mamba。请安装 Mambaforge/Miniforge，或设置 ARCTIC_ROUTE_ECCODES_PREFIX。"
        }
        if (Test-Path $EcCodesPrefix) {
            Invoke-Checked "mamba" @(
                "env", "update", "--yes", "--prefix", $EcCodesPrefix,
                "--file", $NativeEnvironment, "--prune"
            )
        } else {
            Invoke-Checked "mamba" @(
                "env", "create", "--yes", "--prefix", $EcCodesPrefix,
                "--file", $NativeEnvironment
            )
        }
    }
}
$EcCodesPrefix = (Resolve-Path $EcCodesPrefix).Path
$EcCodesDll = Get-ChildItem -LiteralPath (Join-Path $EcCodesPrefix "Library\bin") -Filter "*eccodes*.dll" -File -ErrorAction SilentlyContinue
$EcCodesDefinitions = Join-Path $EcCodesPrefix "Library\share\eccodes\definitions"
if (-not $EcCodesDll -or -not (Test-Path $EcCodesDefinitions)) {
    throw "ecCodes Windows x64 Mamba 前缀不完整：$EcCodesPrefix。请设置 ARCTIC_ROUTE_ECCODES_PREFIX。"
}

$LockFile = Join-Path $ProjectRoot "uv.lock"
if (-not (Test-Path $LockFile)) {
    Write-Host "uv.lock 不存在，先生成锁文件；请将审查后的 uv.lock 纳入发布提交。"
    Invoke-Checked "uv" @("lock", "--directory", $ProjectRoot)
}
Invoke-Checked "uv" @("lock", "--check", "--directory", $ProjectRoot)

Invoke-Checked "uv" @("venv", "--python", $PythonVersion, $Venv)
$BuildPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $BuildPython)) { throw "Python 虚拟环境未生成：$BuildPython" }
$arch = (& $BuildPython -c "import platform; print(platform.machine())").Trim()
if ($arch -notin @("AMD64", "x86_64")) { throw "Python 不是 x64：$arch" }

$env:ARCTIC_ROUTE_ROOT = $WorkspaceRoot
$env:ARCTIC_ROUTE_PRODUCTION_PACKAGE = "1"
$env:ARCTIC_ROUTE_ECCODES_PREFIX = $EcCodesPrefix
$env:ECCODES_DEFINITION_PATH = $EcCodesDefinitions
# The spec and verify-windows.ps1 jointly freeze and exercise the optional
# CARRA cdsapi/ECMWF Datastores path; no runtime credential is needed here.
Invoke-Checked "uv" @("pip", "install", "--python", $BuildPython, $ProjectRoot,
    "pyinstaller>=6.16,<7", "pytest>=8.3,<10", "ruff>=0.11,<1")

if (Test-Path $Assets) { Remove-Item -LiteralPath $Assets -Recurse -Force }
Invoke-Checked $BuildPython @(
    (Join-Path $ProjectRoot "scripts\prepare_runtime_assets.py"),
    "--workspace-root", $WorkspaceRoot, "--output", $Assets
)
Invoke-Checked $BuildPython @(
    (Join-Path $ProjectRoot "scripts\scan_release.py"),
    "--root", $Assets, "--workspace-root", $WorkspaceRoot
)

if (-not $SkipTests) {
    Invoke-Checked $BuildPython @("-m", "pytest", "-q")
}

New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null
$env:ARCTIC_ROUTE_BUILD_ASSETS = $Assets
Invoke-Checked $BuildPython @(
    "-m", "PyInstaller", "--noconfirm", "--clean",
    "--distpath", $DistRoot, "--workpath", $WorkRoot,
    (Join-Path $ProjectRoot "packaging\arctic_route_control_center.spec")
)
if (-not (Test-Path (Join-Path $ExeDir "arctic-route-control-center.exe"))) {
    throw "PyInstaller 未生成 EXE：$ExeDir"
}
Get-ChildItem -LiteralPath $ExeDir -Recurse -File | Where-Object {
    $_.Name -in @("direct_url.json", "uv_cache.json")
} | Remove-Item -Force
Invoke-Checked $BuildPython @(
    (Join-Path $ProjectRoot "scripts\sanitize_frozen_tree.py"),
    "--root", $ExeDir
)

# Run the same release scanner on the frozen tree as an additional build-time
# guard.  The clean-machine PowerShell verifier below remains necessary, but
# this catches resource leakage before creating the handoff archive.
Invoke-Checked $BuildPython @(
    (Join-Path $ProjectRoot "scripts\scan_release.py"),
    "--root", $ExeDir, "--workspace-root", $WorkspaceRoot
)

& (Join-Path $ProjectRoot "packaging\windows\verify-windows.ps1") -ArtifactPath $ExeDir
if ($LASTEXITCODE -ne 0) { throw "Windows 产物验收失败。" }
$hash = (Get-FileHash -LiteralPath (Join-Path $ExeDir "arctic-route-control-center.exe") -Algorithm SHA256).Hash
New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null
if (Test-Path $ReleaseZip) { Remove-Item -LiteralPath $ReleaseZip -Force }
Compress-Archive -Path (Join-Path $ExeDir "*") -DestinationPath $ReleaseZip -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $ReleaseZip -Algorithm SHA256).Hash
$ExeHashFile = Join-Path $ReleaseRoot "arctic-route-control-center.exe.sha256"
$ZipHashFile = "$ReleaseZip.sha256"
"$hash  arctic-route-control-center.exe" | Set-Content -LiteralPath $ExeHashFile -Encoding ascii
"$zipHash  $(Split-Path $ReleaseZip -Leaf)" | Set-Content -LiteralPath $ZipHashFile -Encoding ascii
Write-Host "PASS: Windows x64 onedir 构建完成：$ExeDir"
Write-Host "SHA256(arctic-route-control-center.exe): $hash"
Write-Host "EXE SHA256 文件：$ExeHashFile"
Write-Host "交接 ZIP：$ReleaseZip"
Write-Host "SHA256(Windows x64 ZIP): $zipHash"
Write-Host "ZIP SHA256 文件：$ZipHashFile"
