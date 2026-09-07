[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactPath,
    [string]$WorkspaceRoot = "",
    [switch]$KeepTemp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT" -or -not [Environment]::Is64BitOperatingSystem) {
    throw "验收必须在 Windows x64 原生环境执行。"
}
$ArtifactPath = (Resolve-Path $ArtifactPath).Path
$Exe = Join-Path $ArtifactPath "arctic-route-control-center.exe"
if (-not (Test-Path $Exe)) { throw "找不到 onedir EXE：$Exe" }
$EmbeddedPackagesRoot = Join-Path $ArtifactPath "viewer\packages"
$EmbeddedPackages = @(Get-ChildItem -LiteralPath $EmbeddedPackagesRoot -Directory -Force -ErrorAction SilentlyContinue)
if ($EmbeddedPackages.Count -ne 1) {
    throw "Windows Viewer 必须内嵌且仅内嵌一个 ready 制品（当前 $($EmbeddedPackages.Count) 个）。"
}
$EmbeddedPackage = $EmbeddedPackages[0]
$ExpectedEmbeddedName = "winter-rebuilt-20260215-viewer-package-v4"
$ExpectedBundleSha256 = "f993ac113ac7280e9378710fdc84a825338ebd6ea4b5193ce8679aeb5c3b114a"
$ExpectedChecksumsSha256 = "92ca583e52d41d277d22750631f083b0de798cb5ce8f9b105ef7a1d0123f7d33"
$ExpectedAssemblyId = "winter-viewer-sha256-f3113a19243bce88f712717ad91bddd9d3c76d93c6d84ac3c57e930496dff1ad"
if ($EmbeddedPackage.Name -ne $ExpectedEmbeddedName) {
    throw "内嵌 Viewer 制品名称不符合已审计 v4：$($EmbeddedPackage.Name)"
}
$embeddedBundlePath = Join-Path $EmbeddedPackage.FullName "bundle.json"
$embeddedChecksumsPath = Join-Path $EmbeddedPackage.FullName "checksums.json"
if ((Get-FileHash -LiteralPath $embeddedBundlePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedBundleSha256) {
    throw "内嵌 v4 bundle.json SHA256 不匹配。"
}
if ((Get-FileHash -LiteralPath $embeddedChecksumsPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedChecksumsSha256) {
    throw "内嵌 v4 checksums.json SHA256 不匹配。"
}
$embeddedBundle = Get-Content -LiteralPath $embeddedBundlePath -Raw | ConvertFrom-Json
if ($embeddedBundle.combined_presentation.status -ne "PUBLISHED" -or
    $embeddedBundle.combined_presentation.assembly_id -ne $ExpectedAssemblyId) {
    throw "内嵌 v4 assembly/status 不匹配。"
}
$embeddedChecksums = Get-Content -LiteralPath $embeddedChecksumsPath -Raw | ConvertFrom-Json
$checksumProperties = @($embeddedChecksums.files.PSObject.Properties)
if ($checksumProperties.Count -eq 0 -or
    -not ($checksumProperties.Name -contains "bundle.json")) {
    throw "内嵌 v4 checksums.json 文件表无效。"
}
$expectedPackageFiles = @($checksumProperties | ForEach-Object { $_.Name }) + "checksums.json"
$actualPackageFiles = @(Get-ChildItem -LiteralPath $EmbeddedPackage.FullName -Recurse -File -Force | ForEach-Object {
    $_.FullName.Substring($EmbeddedPackage.FullName.Length).TrimStart('\', '/') -replace '\\', '/'
})
$expectedPackageListing = @($expectedPackageFiles | Sort-Object) -join "`n"
$actualPackageListing = @($actualPackageFiles | Sort-Object) -join "`n"
if ($expectedPackageListing -ne $actualPackageListing) {
    throw "内嵌 v4 文件集合发生变化。"
}
foreach ($property in $checksumProperties) {
    $expected = ([string]$property.Value).ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath (Join-Path $EmbeddedPackage.FullName $property.Name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "内嵌 v4 校验失败：$($property.Name)" }
}

$workspaceVariants = @()
if (-not [string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
    $resolvedWorkspace = (Resolve-Path -LiteralPath $WorkspaceRoot).Path
    $workspaceVariants = @($resolvedWorkspace, ($resolvedWorkspace -replace '\\', '/'))
}

# Keep this scan self-contained: final verification is intentionally runnable
# on a clean Windows machine without Python.  It mirrors scripts/scan_release.py
# for path names, credential-shaped values, raw data, and absolute build paths.
$forbidden = '(?i)(?:^|/)(?:credentials?(?:\.[^/]*)?|\.env(?:\.[^/]*)?|\.cdsapirc|direct_url\.json|uv_cache\.json|torch(?:-[^/]*)?|safetensors(?:-[^/]*)?|rc[12](?:[_.-][^/]*)?|demo[-_]engineering|raw(?:[_-].*)?|original(?:[_-].*)?|downloads?|archives?)(?:/|$)|\.(?:bz2|csv|gz|grib1?|grib2?|grb1?|grb2?|h5|hdf5|jp2|nc4?|netcdf|parquet|tar|tif|tiff|zarr)$'
$absolutePath = '(?i)(?<![A-Za-z0-9_/:])/(?:root|home|mnt|tmp|workspace|workspaces|Users|opt|srv|var|run|build|builds|agent|runner|project|repo|repos|checkout|checkouts|code|src|work)/[^\s"<>]+|(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s"<>\\/]+[\\/][^\s"<>]+|(?<![A-Za-z0-9_])\\\\(?:Users|home|root|workspaces?|builds?|agents?|runners?|projects?|repos?|checkouts?|code|src|work)\\[^\s"<>]+|file:///[^\s"<>]+'
$secretAssignment = '(?im)(?<![A-Za-z0-9_])["'']?(?:COPERNICUSMARINE_(?:SERVICE_)?(?:USERNAME|PASSWORD)|CDSAPI_(?:KEY|URL)|(?:API|ACCESS|SECRET)[_-]?KEY|PASSWORD)["'']?\s*[:=]\s*["'']?\S+'
$textExtensions = @('.bat', '.cfg', '.css', '.desktop', '.html', '.ini', '.js', '.json', '.md', '.ps1', '.py', '.pyi', '.sh', '.svg', '.toml', '.txt', '.xml', '.yaml', '.yml')
$experimentalMarkers = @('experimental', 'calibration_shadow', 'formal_grid_experiments', 'grid_experiments', 'model-cpu', 'model_cpu', 'legacy_cnn', 'legacy-cnn', 'coupling_benchmark', 'profiling', 'development')
$bad = @()
foreach ($item in (Get-ChildItem -LiteralPath $ArtifactPath -Recurse -Force)) {
    $relative = $item.FullName.Substring($ArtifactPath.Length).TrimStart('\', '/') -replace '\\', '/'
    if ($relative -match $forbidden) {
        $bad += "$relative (forbidden release path)"
    }
    $parts = $relative.ToLowerInvariant().Split('/')
    $hasProjectNamespace = $false
    foreach ($part in $parts) {
        if ($part.StartsWith('arctic_route_')) { $hasProjectNamespace = $true }
    }
    if ($hasProjectNamespace) {
        foreach ($part in $parts) {
            foreach ($marker in $experimentalMarkers) {
                if ($part.Contains($marker)) {
                    $bad += "$relative (experimental project dependency: $part)"
                    break
                }
            }
        }
        if (-not ($parts -contains 'viewer')) {
            foreach ($part in $parts) {
                if ($part -eq 'research' -or $part.StartsWith('research_')) {
                    $bad += "$relative (research project dependency: $part)"
                }
            }
        }
        if ($parts -contains 'historical' -or $parts -contains 'history') {
            $bad += "$relative (historical project dependency)"
        }
    }
    if (-not $item.PSIsContainer -and ($textExtensions -contains $item.Extension.ToLowerInvariant() -or $item.Name -eq 'METADATA')) {
        try {
            $content = [IO.File]::ReadAllText($item.FullName)
            if ($content -match $secretAssignment) {
                $bad += "$relative (credential-shaped value)"
            }
            if ($content -match $absolutePath) {
                $bad += "$relative (build-machine absolute path)"
            }
            foreach ($workspaceVariant in $workspaceVariants) {
                if ($content.IndexOf($workspaceVariant, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $bad += "$relative (workspace absolute path)"
                    break
                }
            }
        } catch {
            $bad += "$relative (could not read text payload for release scan)"
        }
    }
}
if ($bad.Count -gt 0) {
    throw "产物发布扫描失败（禁止内容/实验依赖/凭据/绝对路径）：$($bad[0])"
}
$nativeEcCodes = Get-ChildItem -LiteralPath $ArtifactPath -Recurse -File -Force | Where-Object {
    $_.Extension -in @(".dll", ".pyd") -and $_.Name -match "(?i)eccodes"
}
if (-not $nativeEcCodes) {
    throw "产物中未找到 ecCodes 原生 DLL/PYD；不能依赖开发机 PATH。"
}
$ecCodesDefinitions = Get-ChildItem -LiteralPath $ArtifactPath -Recurse -Directory -Force | Where-Object {
    $_.Name -eq "definitions" -and $_.FullName -match "(?i)eccodes"
}
if (-not $ecCodesDefinitions) {
    throw "产物中未找到 ecCodes definitions 目录。"
}

$temp = Join-Path ([IO.Path]::GetTempPath()) ("arctic-route-cc-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temp -Force | Out-Null
$proc = $null
$originalPath = $env:PATH
$environmentNames = @(
    "ARCTIC_ROUTE_ROOT", "ARCTIC_ROUTE_PRODUCTION_PACKAGE", "ARCTIC_ROUTE_ECCODES_PREFIX",
    "ECCODES_DEFINITION_PATH", "ARCTIC_ROUTE_DATA_ROOT", "ARCTIC_ROUTE_READY_PACKAGE",
    "ARCTIC_ROUTE_VIEWER_ROOT", "ARCTIC_ROUTE_BUILD_ASSETS", "PYTHONPATH", "LD_LIBRARY_PATH"
)
$originalEnvironment = @{}
foreach ($name in $environmentNames) {
    $originalEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    [Environment]::SetEnvironmentVariable($name, $null, "Process")
}
try {
    # Do not allow Python, Mamba or ecCodes from the build machine to satisfy
    # missing frozen DLLs.  Windows system directories remain available.
    $env:PATH = @(
        (Join-Path $env:SystemRoot "System32"),
        $env:SystemRoot,
        (Join-Path $env:SystemRoot "System32\Wbem")
    ) -join ";"
    $selfTest = & $Exe --self-test --data-root $temp 2>&1
    if ($LASTEXITCODE -ne 0) { throw "--self-test 失败：$selfTest" }
    $selfJson = $selfTest | Select-Object -Last 1 | ConvertFrom-Json
    if (-not $selfJson.ok) { throw "--self-test 返回 ok=false。" }
    if (-not $selfJson.worker_entrypoints) { throw "冻结版工作进程入口未通过导入自检。" }

    $cdsapiTest = & $Exe --packaging-self-test 2>&1
    if ($LASTEXITCODE -ne 0) { throw "CARRA cdsapi 动态依赖自检失败：$cdsapiTest" }
    $cdsapiJson = $cdsapiTest | Select-Object -Last 1 | ConvertFrom-Json
    if (-not $cdsapiJson.ok -or -not $cdsapiJson.ecmwf_datastores) {
        throw "CARRA cdsapi 动态依赖自检返回失败：$cdsapiTest"
    }

    $stageOutput = & $Exe --orchestrator-stage-worker 2>&1
    if ($LASTEXITCODE -ne 2 -or ($stageOutput -join "`n") -notmatch "usage: stage_worker") {
        throw "编排器 stage worker 内部入口验收失败：$stageOutput"
    }
    $exportOutput = & $Exe --orchestrator-script replay_viewer_export.py -- --help 2>&1
    if ($LASTEXITCODE -ne 0 -or ($exportOutput -join "`n") -notmatch "replay-viewer-export") {
        throw "Viewer exporter 内部入口验收失败：$exportOutput"
    }

    # Exercise the same writable ready directory used in production.  Copying
    # the embedded v4 package into the clean data root intentionally creates a
    # same-name duplicate; the Viewer must retain both source entries and use
    # a source-specific URL rather than silently deduplicating or shadowing it.
    $readyRoot = Join-Path $temp "artifacts\ready"
    $readyPackage = Join-Path $readyRoot $EmbeddedPackage.Name
    New-Item -ItemType Directory -Path $readyRoot -Force | Out-Null
    Copy-Item -LiteralPath $EmbeddedPackage.FullName -Destination $readyPackage -Recurse -Force

    $port = 18730 + (Get-Random -Minimum 0 -Maximum 1000)
    $stdout = Join-Path $temp "server.stdout.log"
    $stderr = Join-Path $temp "server.stderr.log"
    $proc = Start-Process -FilePath $Exe -ArgumentList @(
        "--no-browser", "--host", "127.0.0.1", "--port", $port,
        "--data-root", $temp
    ) -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $base = "http://127.0.0.1:$port"
    $healthy = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 250
        try {
            $health = Invoke-RestMethod "$base/api/health" -TimeoutSec 2
            if ($health.ok -eq $true) { $healthy = $true; break }
        } catch { }
    }
    if (-not $healthy) { throw "服务未在 15 秒内启动；日志：$stderr" }
    foreach ($endpoint in @("/api/catalog", "/api/settings", "/api/artifacts")) {
        $response = Invoke-RestMethod ($base + $endpoint) -TimeoutSec 5
        if ($response.ok -ne $true) { throw "接口验收失败：$endpoint" }
    }
    $viewerIndex = Invoke-RestMethod "$base/viewer/packages.json" -TimeoutSec 10
    $viewerPackages = @($viewerIndex.packages)
    if ($viewerIndex.default_package -ne "viewer-root" -or $viewerPackages.Count -ne 3) {
        throw "Viewer 制品索引未保留 root + 内嵌 ready + 外部 ready 三条记录：$($viewerIndex | ConvertTo-Json -Depth 4)"
    }
    $embeddedEntry = @($viewerPackages | Where-Object {
        $_.location -eq "embedded" -and $_.package_dir -ne "viewer-root"
    })
    $readyEntry = @($viewerPackages | Where-Object {
        $_.location -eq "ready" -and $_.package_dir -eq $EmbeddedPackage.Name
    })
    if ($embeddedEntry.Count -ne 1 -or $readyEntry.Count -ne 1) {
        throw "Viewer 未同时暴露同名内嵌/ready 制品：$($viewerPackages | ConvertTo-Json -Depth 4)"
    }
    $encodedPackageName = [Uri]::EscapeDataString($EmbeddedPackage.Name)
    $embeddedChecksums = Invoke-RestMethod "$base/viewer/packages/$encodedPackageName/checksums.json" -TimeoutSec 10
    $readyChecksums = Invoke-RestMethod "$base/viewer/ready-packages/$encodedPackageName/checksums.json" -TimeoutSec 10
    if (-not $embeddedChecksums.files -or -not $readyChecksums.files) {
        throw "同名内嵌/ready 制品的来源专用路径未返回 checksums。"
    }
    $jobRequest = @{
        operation = "a_bundle"
        parameters = @{
            scenario_id = "murmansk_dikson_july_2026_retrospective_v1"
            at = "2026-07-15T00:00:00Z"
            types = @("temperature")
            mode = "retrospective_best_estimate"
            knowledge_as_of = "2026-07-23T00:00:00Z"
        }
    } | ConvertTo-Json -Depth 4
    $jobStart = Invoke-RestMethod "$base/api/jobs" -Method Post `
        -ContentType "application/json" -Headers @{ Origin = $base } `
        -Body $jobRequest -TimeoutSec 5
    $jobId = $jobStart.job.job_id
    $jobResult = $null
    for ($i = 0; $i -lt 100; $i++) {
        Start-Sleep -Milliseconds 200
        $jobResult = (Invoke-RestMethod "$base/api/jobs/$jobId" -TimeoutSec 5).job
        if ($jobResult.status -notin @("queued", "running")) { break }
    }
    if ($jobResult.status -ne "failed" -or $jobResult.log_tail -notmatch '"event": "worker_start"') {
        throw "冻结版任务子进程未被实际执行：$($jobResult | ConvertTo-Json -Depth 3)"
    }
    if ($jobResult.log_tail -match "ModuleNotFoundError|vessel_traffic_model\.toml") {
        throw "冻结版任务子进程存在漏打包：$($jobResult.log_tail)"
    }
    $pathTraversalSucceeded = $false
    try {
        Invoke-WebRequest "$base/viewer/../config/default.json" -UseBasicParsing -TimeoutSec 5 | Out-Null
        $pathTraversalSucceeded = $true
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode.value__ -notin @(400, 404)) {
            throw "路径穿越返回了非拒绝状态。"
        }
    }
    if ($pathTraversalSucceeded) { throw "路径穿越请求意外成功。" }
    Write-Host "PASS: EXE self-test、冻结任务/编排器子进程、loopback 服务、API、root+内嵌/ready 同名制品、路径拒绝、ecCodes DLL/definitions 均通过。"
} finally {
    $env:PATH = $originalPath
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $originalEnvironment[$name], "Process")
    }
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
        $proc.WaitForExit()
    }
    if (-not $KeepTemp -and (Test-Path $temp)) {
        Remove-Item -LiteralPath $temp -Recurse -Force
    } elseif ($KeepTemp) {
        Write-Host "临时验收目录保留：$temp"
    }
}
