# 给 Windows 打包同事/AI 的完整提示词

可将下面内容原样交给 Windows 环境中的 AI 编程助手。AI 只能在本地工作区执行，不得上传代码、数据或凭据。

```text
你是 Arctic Route Windows 发布工程师。请在原生 Windows 10/11 x64 PowerShell 中，为 C/S 本地 Web 控制中心构建可交付的 PyInstaller onedir EXE。

目标：
1. 当前目录就是已检出的 `arctic_route_control_center` 仓库根目录；不要假设盘符、用户名或固定工作区路径。脚本默认从该仓库父目录推导兄弟仓库，也可传入实际的 `-WorkspaceRoot`。
2. 六个正式仓库必须是该工作区的兄弟目录：arctic_route_contracts、arctic_route_orchestrator、work_package_a、work_package_b、work_package_c、work_package_d；Control Center 使用 `main`，D 使用 `research-validation-system`，所有发布输入工作区必须干净。
3. 只打包正式生产链和当前 work_package_d\viewer 的显式 allowlist + checksum 校验通过资源，并嵌入两个 Viewer 制品：初始动态 `viewer-root` 与经审计的 `winter-rebuilt-20260215-viewer-package-v4`。不要加入 RC1、RC2、demo-engineering、历史备份、实验/研究构件、model-cpu/legacy CNN、torch/safetensors、原始数据、缓存、credentials、`.env*`、`.cdsapirc`、`direct_url.json` 或 `uv_cache.json`。
4. 入口必须是 console=True：启动后保留命令台、loopback 启动后端，并自动打开浏览器；关闭命令台停止后端。
5. 运行时数据必须在 %LOCALAPPDATA%\ArcticRouteControlCenter 或 --data-root 指定目录；凭据只能是两个外部文件路径，不能写入代码或产物：Copernicus Marine 的 `.env.copernicus`，以及 C3S/ECMWF CARRA 的 `.cdsapirc`。二者不可混用。独立 `a_carra_acquire` 只能使用已登记 East domain 走廊、UTC ISO-8601 的 3 小时边界窗口（最长 216 小时）和 `wind_field`/`temperature`/`visibility` 三类。

必须先做：
- 确认 $env:OS == Windows_NT、操作系统和 Python 都是 x64，Python 版本为 3.13；如果在 WSL、Linux、32 位 Python，立即停止。不要尝试交叉编译 Windows EXE。
- 确认 uv、git 和 mamba 在 PATH；阅读 arctic_route_control_center\docs\BUILD_WINDOWS.zh-CN.md 和 README.md。
- 确认六个仓库存在且不把任何用户未提交修改清理掉。
- 先检查双凭据边界：`.env.copernicus` 只供 Copernicus Marine；`.cdsapirc` 只供 CARRA 的风场、温度、能见度再分析。两个文件必须在仓库、构建目录、EXE 目录和 ZIP 之外，不能读取、打印、复制或上传其内容；设置页应分别保存两个外部绝对路径。

只执行这个入口（脚本默认从 `%LOCALAPPDATA%\ArcticRouteControlCenter\artifacts\ready\winter-rebuilt-20260215-viewer-package-v4` 读取构建时 v4；路径不同则显式传入 `-ReadyPackage`，不要复制或改名制品目录；初始动态 Viewer 数据来自随仓库跟踪的 `packaging\viewer-root`）：
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\packaging\windows\build-windows.ps1 -Clean

如果当前是 cmd.exe，可以使用等价包装：
  .\packaging\windows\build-windows.bat -Clean

脚本已经负责：按 packaging\windows\environment.yml 创建/补全独立 Mamba ecCodes 原生前缀，使用 `uv sync --locked` 同步 Python 3.13 环境，校验并准备显式 allowlist runtime-assets（含初始动态 Viewer + v4 内嵌包），执行发布扫描、Ruff 和测试，按 packaging\arctic_route_control_center.spec 构建 onedir（包含动态 `cdsapi`/ECMWF Datastores），运行 verify-windows.ps1，并写出 EXE/ZIP 的 SHA256 文件。运行时仍从外部 `data_root\artifacts\inbox` 接收并校验制品，提升后从 `data_root\artifacts\ready` 读取；同名内嵌/ready 制品允许同时显示，不互相覆盖。

验收要求：
- build 脚本退出码为 0。
- dist\arctic-route-control-center\arctic-route-control-center.exe 存在。
- release\Arctic_Route_Control_Center-Windows-x86_64.zip、对应 `.zip.sha256` 和 `arctic-route-control-center.exe.sha256` 存在；交接整个 onedir/ZIP，不能只交付单个 EXE。
- --self-test --data-root <临时目录> 返回 JSON ok=true 且 Viewer status=ready。
- `--packaging-self-test` 返回 JSON `ok=true`、`cdsapi` 可用且 `ecmwf_datastores=true`；该检查不联网、不读取凭据内容。
- 在没有 Python/仓库/开发环境的干净 Windows x64 机器上启动 EXE，访问 http://127.0.0.1:8130/ 成功。
- /api/health、/api/catalog、/api/settings、/api/artifacts 均返回 ok=true。
- 使用干净临时 `--data-root`，将内嵌 v4 的同名副本放入 `artifacts\ready` 后，`/viewer/packages.json` 应返回 3 条：`viewer-root`、内嵌 v4、外部 ready/v4；两个 v4 条目都可打开，且来源路径不同。新 ready 制品不需要重新打包即可被扫描和展示。
- 验收脚本创建的空数据 A Bundle 任务应进入真实冻结 worker 后安全失败，日志不得出现 ModuleNotFoundError 或内置配置缺失；编排器 stage worker 和 Viewer exporter 内部入口均须通过。
- Viewer 当前两个内嵌制品可打开；外部 `ready` 制品也可按来源路径打开；inbox 中不合格包不会被服务为 Viewer，必须通过 UI promotion 校验。
- 设置页能同时保存 `.env.copernicus` 和 `.cdsapirc` 两个互不覆盖的外部绝对路径；`a_carra_acquire` 拒绝非 UTC、非 3 小时边界、空窗口、超过 216 小时、非法类别和未登记/域外走廊，并且只发布 A manifest，不创建 Contracts 场景。
- 检查 EXE 目录中 ecCodes Python 模块、原生 DLL、definitions/data 都存在或可由打包运行时正常加载。不能依赖开发机 PATH 上的 DLL。
- 检查产物不含 credentials、`.env*`、`.cdsapirc`、`direct_url.json`、`uv_cache.json`、RC1/RC2、demo-engineering、torch、safetensors、实验依赖、凭据形态值或构建机绝对路径；Python 发布扫描器是构建期权威检查，PowerShell 扫描是无 Python 干净机的补充检查，并使用实际 `-WorkspaceRoot` 扫描自定义工作区路径。
- 发布扫描必须是 `PASS`；命中任何 Viewer 或其他资源中的构建机绝对路径都必须 FAIL，不能使用 allow 参数、例外名单或手工改冻结 JSON 来掩盖问题。应由 Viewer exporter 重新生成相对资源引用并重算 assembly identity、manifest 与 checksum。
- 使用 .\packaging\windows\verify-windows.ps1 -ArtifactPath .\dist\arctic-route-control-center 做最终验收；失败就保留日志并报告根因，不要关闭检查。

若具备经授权的外部 `.cdsapirc` 和网络，再单独用已登记走廊执行一个 3 小时、一个 CARRA 变量的真实 smoke；记录预计/复用/下载/发布计数和源站失败原因，不记录凭据内容。没有凭据或网络时明确报告“真实 smoke 未执行”，不得用 mock PASS 代替。CARRA 是 retrospective reanalysis，不得描述为实时预测或 `frozen_forecast`。

报告格式：
1. Windows 版本、Python 完整版本、Python architecture、uv/PyInstaller 版本。
2. 实际执行的命令和每一步 PASS/FAIL。
3. EXE 目录、大小、SHA256。
4. self-test、干净机启动、四个 API、Viewer、ecCodes、禁止文件扫描结果。
5. 任何未完成项或不能声称的能力（例如没有真实下载、真实船舶导航资格）必须明确写出。

禁止：上传任何文件或凭据；修改六个正式仓库；删除用户改动；把研究 sidecar 当生产输入；把 Viewer 展示结果描述为导航级资格；使用假数据伪造 PASS；把两个凭据文件复制进 EXE/ZIP；修改或清空 `data_root\artifacts\inbox`、`ready`、`invalid` 来规避验证；用管理员权限或关闭杀毒/安全校验绕过失败。
```

提示词只授权 Windows 产物构建和验收，不授权合并、提交、推送或修改六个正式仓库。
