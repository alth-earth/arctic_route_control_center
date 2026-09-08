# 整合架构与发行边界

## 运行流程

```text
AppImage/EXE 启动器（保留命令台）
  -> 127.0.0.1 本地 HTTP 控制面
  -> 自动打开默认浏览器
  -> Contracts 只读配置 / A 下载与 Bundle / Orchestrator 正式运行
  -> 统一 Viewer 发布器 -> artifacts/inbox
  -> 完整校验 -> artifacts/ready -> D Viewer 只读展示
```

控制面只接收白名单操作和 `data_root` 内的相对输入路径，不执行用户提供的 shell 字符串。长任务在独立 worker 进程运行，stdout/stderr 写入任务日志；同一主机默认只运行一个任务。

## 所有权

- Contracts 是 Corridor、Scenario、Vessel、RunContext 和 DatasetBundle 身份的唯一事实源。
- A 负责采集、预处理、manifest/cache、DatasetBundle 与 RunContext。
- B 只消费 A 公共制品并发布正式 RiskFrame/RiskWindow。
- C 只消费正式风险制品并发布路线、候选集与重规划结果。
- Orchestrator 负责进程、身份绑定、超时和 Viewer 发布。
- D 是 consumer，只验证和显示生产者字段，不重算风险或路线。

## 发行内容

包含六个正式 Python 包、控制中心、正式配置、D 普通网页资源，以及构建时按次显式声明的 Viewer 数据制品（每个制品自带 `bundle.json` 与 `checksums.json`，自描述校验通过；未声明则不内嵌任何 Viewer 数据，产物只含 Viewer UI）。不包含 A 的 23GB 数据目录、历史备份、自包含重复 HTML、RC1/RC2/demo-engineering 分支内容、legacy CNN、Torch/safetensors、校准/网格实验、synthetic/legacy CLI 或凭据。

外部目录固定为：

```text
data_root/
  config/settings.json
  data/work-package-a/
  artifacts/inbox/
  artifacts/ready/
  artifacts/invalid/
  run/jobs/<job-id>/
  logs/
  cache/
```

`artifacts/inbox/<包名>` 可由用户放入未完成或新制品。控制中心识别但不提供给 Viewer；只有 Schema、checksums、PUBLISHED、12 路线、preflight 和 formal motion 全部通过才允许原子提升到 `ready`。

## 已知能力边界

当前统一发布器从“已完成的 A/B/C/Replay 制品”开始，并非从网络下载一键重建全部链路。C 的 formal motion 生产仍传递依赖研究 smoothing 源码和源码摘要；为避免把研究构件混入发行包，首个发行版只消费已经存在且身份绑定的 formal motion sets，不在裁剪包内承诺新生成 motion。

当前随包 Viewer 是 2026-02 Tromso 研究回放，包含 9 次路线修订和 12 条候选路线，状态为 retrospective dynamic replay。它用于工程展示，不代表严格因果回放、实船标定、导航认证或适航结论。

当前 D Viewer 的发布 JSON 已由统一发布器规范为包内相对资源引用，并重新计算 manifest、assembly identity 与 checksum。发布扫描器对任何构建机绝对路径均 fail-closed，不保留 Viewer provenance 例外。
