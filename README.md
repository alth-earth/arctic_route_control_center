# Arctic Route Control Center

这是 Arctic Route 六个正式代码包之上的本地 Web 管理与打包项目。它不复制 A/B/C/D 的
业务计算，也不改变正式合同；它负责启动、配置、任务编排、制品发现和 Viewer 挂载。

Linux x86_64 成品位于：

```text
release/Arctic_Route_Control_Center-x86_64.AppImage
```

当前验收版本大小为 `184113656` bytes，SHA-256 为
`cc9fd06f100e777cc43d7e0aac69b6de2662530eeba3946a6d23a7ad49e4acbf`；也可使用同目录
的 `.sha256` 文件校验。完整验收记录见 `docs/RELEASE_VERIFICATION.zh-CN.md`。

启动后命令台持续作为后端运行，并自动打开浏览器。无 FUSE 的 WSL 可执行：

```bash
./release/Arctic_Route_Control_Center-x86_64.AppImage --appimage-extract-and-run
```

开发模式：

```bash
uv sync
uv run arctic-route-control-center --no-browser --port 8130
```

浏览器打开 `http://127.0.0.1:8130/`。默认只监听本机回环地址。

运行数据默认写到：

- Linux: `${XDG_DATA_HOME:-~/.local/share}/arctic-route-control-center`
- Windows: `%LOCALAPPDATA%\ArcticRouteControlCenter`

可用 `--data-root /path/to/data` 或 `ARCTIC_ROUTE_DATA_ROOT` 覆盖。程序代码、凭据和数据
分离；真实凭据不得写入本仓库。设置页分别保存外部 `.env.copernicus`（Copernicus
Marine）和 `.cdsapirc`（CDS/CARRA）的绝对路径，两者可同时配置、互不覆盖，也不会读取或
回显凭据内容。

构建与交接见：

- `docs/BUILD_LINUX.zh-CN.md`
- `docs/BUILD_WINDOWS.zh-CN.md`
- `docs/WINDOWS_AI_PROMPT.zh-CN.md`
- `docs/ARCHITECTURE.zh-CN.md`
- `docs/USER_GUIDE.zh-CN.md`
