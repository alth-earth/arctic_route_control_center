# 使用说明

双击 AppImage/EXE 后不要关闭命令台；它就是持续运行的本地后端。浏览器会自动打开控制中心。按 `Ctrl+C` 或关闭命令台可停止服务。

推荐顺序：

1. 在“船舶与场景”检查 Contracts 配置。正式任务下拉框只显示发行白名单中的 6 个场景；研究、RC2、开发和 holdout 场景不进入操作入口。
2. 在“设置”分别填写两个外部绝对路径：`.env.copernicus` 用于 Copernicus Marine 的海冰、海流、水位和波浪；`.cdsapirc` 用于 CDS/CARRA 的风场、温度和能见度。两者可同时保存、互不覆盖，软件只保存路径，不读取或显示用户名、密码、令牌。Linux/WSL 下凭据文件必须只允许当前用户读写（例如 `chmod 600`），且应放在程序、仓库和数据/制品目录之外。
3. 在“A 数据下载”选择 Contracts 场景、来源和类型。12 类正式必需数据默认勾选，2 类可选，`vessel_traffic` 诊断模拟类型不可提交。具体场景的时间与模式来自 Contracts；冻结模板必须填写 UTC 锚点。
4. 如需独立采集 CARRA，在“CARRA 再分析采集”选择已登记 East domain 走廊、UTC 起止时间和 `wind_field`、`temperature`、`visibility`。时间必须落在 3 小时边界，窗口最长 216 小时。该任务只发布 A 数据、manifest 和来源证据，不创建或修改 Contracts 场景，也不能作为实时预测或 `frozen_forecast` 使用。
5. 在“制品构建”依次创建 A Bundle/RunContext、运行 Orchestrator、发布 Viewer 包。输入路径必须相对 `data_root`；独立 CARRA 数据进入 B/C/D 前仍须选择版本化 Contracts 场景。
6. 新包先进入 `artifacts/inbox`。在“制品库”确认状态为 ready 后点击“提升”；不完整包保持不可展示。
7. 点击“打开 Replay Viewer”查看随包默认制品，或在制品库中打开已提升的新包。

缺失数据、身份错配、非 12 路线、摘要错误或 formal motion 缺失都会失败关闭。不要把失败任务通过手工改 JSON 伪装为成功；查看“任务与日志”定位真实原因。

CARRA 是回溯再分析数据，不是未来预报。目录末端是否可用由 CDS 请求结果决定；界面不会用固定结束日期伪装可用性。数据集的时间覆盖、更新频率与 3 小时分析场说明以 [C3S CARRA 官方目录](https://cds.climate.copernicus.eu/datasets/reanalysis-carra-single-levels?tab=overview) 为准。
