# Windows x64 EXE 构建与交接

## 结论

EXE 必须在原生 Windows x64 上构建。PyInstaller 不提供“在 WSL 编译 Windows EXE”的可靠交叉编译链；本项目不把 WSL 当作 Windows 构建机。Linux 交付物由 Linux 脚本生成，Windows 团队只需生成并验收 Windows onedir EXE。

构建入口是：

```powershell
# 在当前 arctic_route_control_center 仓库根目录执行；脚本会从其父目录
# 自动推导兄弟仓库工作区，也可按需传入实际的 -WorkspaceRoot。
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\packaging\windows\build-windows.ps1 -Clean
```

也可以在 `cmd.exe` 中使用等价的薄包装脚本（参数原样转交给 PowerShell）：

```bat
packaging\windows\build-windows.bat -Clean
```

产物目录：`dist\arctic-route-control-center\`，入口为 `arctic-route-control-center.exe`；可交接压缩包为 `release\Arctic_Route_Control_Center-Windows-x86_64.zip`。这是 `console=True` 的 onedir 应用：必须保留整个目录，不能只复制 EXE；双击会保留后端命令台，并自动打开本机浏览器，命令台关闭即停止后端。

Viewer 发行语义与 Linux AppImage 保持一致：冻结目录内包含初始动态 `viewer-root` 和一个经审计的 `winter-rebuilt-20260215-viewer-package-v4`。运行时的可写制品目录仍在外部 `data_root\artifacts\inbox` / `data_root\artifacts\ready`，不会被复制进 EXE/ZIP。若外部 `ready` 中也有同名 v4，Viewer 列表会保留 3 条记录（初始制品、内嵌 v4、外部 ready/v4）；同名记录允许重复，并通过来源专用路径分别打开。

远端 `main` 跟踪初始动态 `packaging\viewer-root`，但不跟踪经审计 v4。Windows 构建者需要另行取得完整 `winter-rebuilt-20260215-viewer-package-v4` 目录；若仓库快照不完整，也可另行取得完整 `viewer-root` 目录。脚本会分别校验两者，不会从其他 `ready` 包猜测或替换。收到压缩包时应解压到仓库外目录并保持内部文件字节不变，然后传入目录路径。

## 构建机要求

- Windows 10/11 x64；原生 PowerShell 5.1 或 PowerShell 7。
- Python 3.13 x64（脚本通过 `uv sync --locked` 创建并同步隔离环境）。
- `uv`、`git` 在 PATH 中；建议安装 Miniforge/Mambaforge 并让 `mamba` 在 PATH 中。
- 六个正式仓库必须是同一个工作区的兄弟目录：`arctic_route_contracts`、`arctic_route_orchestrator`、`work_package_a`、`work_package_b`、`work_package_c`、`work_package_d`，以及本项目 `arctic_route_control_center`；Control Center 必须在 `main`，D 必须在 `research-validation-system`，所有发布输入工作区必须干净。
- 构建期间可访问 Python 包源；正式构建应使用锁定版本和经过审核的网络出口。

不要把 `credentials/`、`.env*`、`.cdsapirc`、原始海冰/气象数据、缓存、实验分支或历史 Viewer 包复制进工作区来“帮助”构建。数据和凭据在运行机外置目录配置。

## 脚本行为

`build-windows.ps1` 按以下顺序执行：

1. 拒绝 WSL/非 Windows/非 x64 环境，并检查六个正式仓库存在 Git 元数据。
2. 若未显式设置 `ARCTIC_ROUTE_ECCODES_PREFIX`，按 `packaging\windows\environment.yml` 自动创建或补全 `build\windows-native` 原生 Mamba 前缀；该前缀与可清理的 PyInstaller 工作目录分离。
3. 建立 `build\windows-x64\venv`，使用 `uv sync --locked` 同步当前整合项目、六个本地包、PyInstaller、pytest、ruff；不会隐式改写 `uv.lock`。
4. 调用 `scripts\prepare_runtime_assets.py`：从 D 分支复制静态 Viewer allowlist，从 `-ViewerRootPackage` / `ARCTIC_ROUTE_VIEWER_ROOT`（默认随 Control Center 跟踪的 `packaging\viewer-root`）复制初始动态制品数据，并用 `-ReadyPackage` / `ARCTIC_ROUTE_READY_PACKAGE` 指定已审计的 v4 ready 目录，将其字节不变地嵌入 `viewer\packages\`；历史、实验和凭据不进入冻结目录。
5. 调用发布扫描器检查资源树；扫描禁止凭据/`.env*`/`.cdsapirc`、原始数据、RC1/RC2、demo-engineering、`direct_url.json`、`uv_cache.json`、Torch/safetensors、实验依赖和构建机绝对路径。资源树和最终冻结 onedir 都必须得到 `PASS`；不存在可绕过 Viewer provenance 或其他绝对路径检查的例外参数。
6. 默认运行控制中心测试，然后以 `packaging\arctic_route_control_center.spec` 执行 PyInstaller onedir；spec 会显式收集 CARRA 的动态 `cdsapi`/ECMWF Datastores 依赖，并移除 `direct_url.json`/`uv_cache.json`。
7. 调用 `verify-windows.ps1` 做 clean-PATH `--self-test`、CARRA `--packaging-self-test`、冻结子进程入口、loopback HTTP、catalog/settings/artifacts、root+内嵌/外部 ready 同名制品索引与来源路径、路径穿越拒绝和同等禁止内容扫描；通过后再生成整个 onedir 的交接 ZIP 及 SHA256，同时写出 `.sha256` 校验文件。

脚本会检查 `uv.lock` 与 `pyproject.toml` 一致；锁文件缺失或六个依赖仓库处于 detached/dirty 状态会直接失败。正式构建必须在干净工作区重复执行。

可用 `-SkipTests` 仅用于排查构建机问题；对外发布不能跳过测试。`-Clean` 只删除本项目的明确构建目录 `build\windows-x64` 和 `dist`，不会删除或移动外部 `artifacts\inbox`、`artifacts\ready` 或 `artifacts\invalid`。

## ecCodes / DLL 验收

Work Package A 的 GRIB 读取依赖 ecCodes。Windows 构建必须确认 PyInstaller 目录同时包含 ecCodes Python 模块、原生 DLL 和 definitions/data。构建脚本通过实际 A 依赖安装并运行 `--self-test`；如果运行 A 下载/预处理时出现 `eccodes`、DLL 或 definitions 缺失，应停止发布，检查 `dist\arctic-route-control-center` 中的 `eccodes`/`eccodeslib` 文件，并在同一台干净 Windows 机器复验，不能用开发机 PATH 中的 DLL 掩盖问题。

自动创建原生前缀失败时，也可先手工执行：

```powershell
mamba env create --yes --prefix .\build\windows-native --file .\packaging\windows\environment.yml
$env:ARCTIC_ROUTE_ECCODES_PREFIX = (Resolve-Path .\build\windows-native).Path
```

构建 spec 会收集该前缀 `Library\bin` 中的 DLL，并把 ecCodes definitions 放入产物。验收脚本会临时把开发环境的 Python/Mamba 路径从 `PATH` 移除，以防开发机依赖掩盖漏打包。

## 运行目录与双凭据 / CARRA

默认可写目录：`%LOCALAPPDATA%\ArcticRouteControlCenter`，包含 `config`、`data`、`artifacts\inbox`、`artifacts\ready`、`artifacts\invalid`、`run`、`logs`、`cache`。可用启动参数 `--data-root <外部数据目录>` 覆盖。构建脚本默认从仓库内 `packaging\viewer-root` 读取初始动态制品，从 `%LOCALAPPDATA%\ArcticRouteControlCenter\artifacts\ready\winter-rebuilt-20260215-viewer-package-v4` 读取内嵌 v4；可分别用 `-ViewerRootPackage <目录>` / `ARCTIC_ROUTE_VIEWER_ROOT` 和 `-ReadyPackage <目录>` / `ARCTIC_ROUTE_READY_PACKAGE` 覆盖构建输入。所有路径都由构建者按实际机器提供，脚本不写死盘符、用户名或团队工作区。运行时新制品仍按原路径接收、校验和提升。

控制中心有两类彼此独立的外部凭据路径，均只保存路径、不保存或回显内容：

- Copernicus Marine：外部 `.env.copernicus`，用于海冰、海流、水位、波浪等 Marine 数据。
- CDS/CARRA：外部 `.cdsapirc`，用于 C3S/ECMWF CARRA 再分析的风场、温度和能见度。CARRA 是再分析源，不是 Copernicus Marine 凭据的别名；启动 CARRA 下载任务前必须在“设置”填写此路径。

两个文件都必须放在程序目录、仓库和交接 ZIP 之外；Windows 不要求 POSIX 的 `0600`，但应限制为当前用户可读。构建/验收扫描必须确认 EXE 目录中没有这两个文件、`.env*`、`credentials*` 或凭据值。A 下载会复用已有完整快照，部分下载采用 `.part`，失败时保持可恢复状态。

控制中心的独立 `a_carra_acquire` 任务只允许已登记 East domain 走廊、带时区的 UTC ISO-8601 起止时间、3 小时边界和最长 216 小时窗口；类别仅为 `wind_field`、`temperature`、`visibility`。它只写 A 的数据和 manifest，不偷偷创建 Contracts 场景，也不能把 CARRA 再分析当作 `frozen_forecast` 或实时预测。正式运行前应在设置页分别填写两个路径，Marine 任务不能读取 `.cdsapirc`，CARRA 任务不能读取 `.env.copernicus`。

## 干净机器验收

把整个 `dist\arctic-route-control-center` 复制到一台没有开发环境、没有仓库和没有 Python 的 Windows x64 机器，执行：

```powershell
$testRoot = Join-Path ([IO.Path]::GetTempPath()) "arctic-route-cc-test"
Set-Location <复制后的 onedir 目录>
.\arctic-route-control-center.exe --self-test --data-root $testRoot
```

应看到 JSON 中 `ok: true`，且 Viewer 为 `ready`。随后运行 CARRA 动态依赖自检（不联网、不读取凭据内容）：

```powershell
.\arctic-route-control-center.exe --packaging-self-test
```

JSON 应同时显示 `cdsapi` 和 `ecmwf_datastores` 可用。然后双击 EXE 或执行：

```powershell
.\arctic-route-control-center.exe
```

浏览器应打开 `http://127.0.0.1:8130/`。在“制品库”确认当前 Viewer 可用；把待验证包放入外置数据目录的 `artifacts\inbox`，只有校验、`PUBLISHED`、12 条候选路线和 gate PASS 全部满足时才能提升为 `ready`。若把内嵌 v4 的同名副本放入临时数据根的 `artifacts\ready`，Viewer 选择器应显示 3 条记录，并可分别打开内嵌与外部 ready 路径；不要直接改包内 `viewer` 文件。

在设置中分别配置 Copernicus Marine `.env.copernicus` 与 CDS/CARRA `.cdsapirc`；两者均只存外部绝对路径。CARRA 仅支持风场、温度、能见度等已登记类别，不能用一个凭据文件替代另一个。需要联网验收时，用测试走廊和一个 3 小时周期执行最小真实下载；记录周期数、缓存复用、发布结果和源站失败原因，但不得记录凭据内容。无凭据或无网络时，只能报告“未执行真实 smoke”，不能用 mock 结果替代。

若验收失败，保留 `verify-windows.ps1 -KeepTemp` 的日志，把命令输出、`server.stderr.log` 和 `runtime-assets-manifest.json` 交回，不要通过关闭校验、忽略发布扫描、把凭据复制进产物或手工拷 DLL 解决。任何构建机绝对路径、凭据路径或秘密值都属于发布失败，必须修复资源来源后重新构建。
