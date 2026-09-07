# Linux x86_64 发行验收记录

> 本页记录的是历史构建，数值不代表当前源码或即将生成的 Windows EXE。重新发布时请以
> 构建目录中的 `runtime-assets-manifest.json` 和同目录 `.sha256` 为唯一来源，并重新执行
> Linux/Windows 验收脚本。

验证时间：2026-09-04 22:23 +08:00

## 成品

- 路径：`release/Arctic_Route_Control_Center-x86_64.AppImage`
- 架构：x86-64 AppImage / ELF 64-bit
- 大小：`184134136` bytes
- SHA-256：`9fca146f0e8f57219724562d07488999d78862ddf34b10b7002160584ef7934d`
- 校验文件：`release/Arctic_Route_Control_Center-x86_64.AppImage.sha256`

## 自动验收

- 控制中心：28 tests PASS，Ruff PASS。
- Work Package A：完整 `make check` 216 tests PASS、Ruff PASS、锁文件检查 PASS；公开 `acquire-carra` CLI 可用。真实 causal replay 检查遵循 fail-closed 语义：当前本机 manifest 的旧历史窗口不能宣称 full feasibility，因此不会把 `ready_ticks=0` 误报为代码失败。
- Work Package D：125 tests PASS，Ruff PASS。
- Orchestrator 全量：191 tests PASS（退出码 0；host `cfgrib` 的 ecCodes warning 已记录），Viewer/exporter 定向回归也通过。
- 冻结程序：包 metadata、ecCodes 2.48.0、A 冻结 worker、CARRA 动态依赖、Orchestrator、Viewer exporter、HTTP API 和路径穿越拒绝均 PASS。
- 最终 AppImage 解包后扫描 27047 个文件，凭据、原始数据、缓存、RC1/RC2、demo-engineering、实验依赖、`direct_url.json`、`uv_cache.json` 和构建机绝对路径违规数为 0。
- `.sha256` 文件复核 PASS。

## 真实 CARRA smoke

使用外置权限为 `0600` 的 `.cdsapirc`，对已登记 `tromso_to_isfjorden_outer` 走廊执行一个周期、一个 `temperature` 类型的真实下载：

- 有效时次：`2026-02-15T00:00:00Z`
- 请求周期：1；首次下载：1；处理：1；发布：1
- 第二次相同请求：缓存命中 1；重新下载 0
- GRIB、East domain 网格、三时间语义、manifest、来源快照与 SHA-256 均验证通过
- 原始缓存和不可变来源快照 SHA-256：`2de5e3b9db3732d0caf8c58969c29e36140d44f95b850f90189395fc777e7fca`

真实凭据路径和内容未写入发行物、任务摘要或本记录。CARRA 仍是 retrospective reanalysis，不具有未来预测或 `frozen_forecast` 资格。

## 浏览器验收

直接启动最终 AppImage 后验证（当前外部默认 Winter 制品为 v4）：

- 设置页可同时保存两类外部凭据路径，互不覆盖。
- Viewer 点击运行后，路线层和三个目标显隐控件仍可操作。
- 运行中把展示层从 `full_voyage` 切为 `rolling_0_24h`、隐藏最快路线并高亮低风险卡片后，运行 candidate ID、运行路线来源、同一仿真时刻和船位保持不变。
- 所有“设为运行路线/仅展示比较”按钮仍禁用；运行路线仍为原 `full_voyage/recommended`。
- v4 动态回放重新扫描、R2–R6 adoption、运行锁定和控制项回归通过；截图及绑定证据：
  `work_package_d/output/playwright/winter-rebuilt-20260215-current-standard-v4/`。

## 边界

该成品是在 WSL Ubuntu 24.04 / glibc 2.39 上构建，已完成本机黑盒验收，但不自动证明兼容旧 glibc 发行版；面向更广 Linux 发行时应在 Ubuntu 22.04 基线上复建。随包 Winter Viewer 是研究/工程展示，不是导航或实船资格。Windows EXE 未在 WSL 生成，须由 Windows x64 团队按 `BUILD_WINDOWS.zh-CN.md` 与 `WINDOWS_AI_PROMPT.zh-CN.md` 构建和验收。
