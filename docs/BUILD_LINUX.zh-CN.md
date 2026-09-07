# Linux x86_64 / AppImage 构建

发行物采用“PyInstaller onedir + AppImage 外壳”。运行时保留命令台，后端只监听 loopback，并自动打开系统浏览器。AppImage 内只读；下载、日志、缓存、凭据路径和新增制品全部写入外部用户数据目录。Viewer 默认内嵌初始动态制品和经审计的 v4；外部 `artifacts/ready` 仍可接收新制品，同名内嵌/ready 记录允许同时显示。

## 构建基线

推荐在 Ubuntu 22.04 x86_64 或等价容器中构建，以获得比本机 WSL Ubuntu 24.04/glibc 2.39 更宽的兼容性。本机可以产出并验收 AppImage，但该结果不自动证明兼容旧 glibc 发行版。

需要：`uv`、Python 3.13（可由 uv 安装）、Git、curl，以及 appimagetool。也可先用 `packaging/linux/environment.yml` 创建 Mamba 构建环境。

```bash
cd "$(git rev-parse --show-toplevel)"
chmod +x packaging/linux/build-appimage.sh scripts/verify_runtime.py
packaging/linux/build-appimage.sh --download-appimagetool
```

若团队自行审计并保存 appimagetool：

```bash
APPIMAGETOOL=/opt/tools/appimagetool-x86_64.AppImage \
APPIMAGETOOL_SHA256=<经审核的 SHA256> \
APPIMAGE_RUNTIME=/opt/tools/runtime-x86_64 \
APPIMAGE_RUNTIME_SHA256=<经审核的 SHA256> \
  packaging/linux/build-appimage.sh
```

输出：

```text
release/Arctic_Route_Control_Center-x86_64.AppImage
release/Arctic_Route_Control_Center-x86_64.AppImage.sha256
```

无 FUSE 环境使用：

```bash
./release/Arctic_Route_Control_Center-x86_64.AppImage \
  --appimage-extract-and-run
```

默认数据目录是 `~/.local/share/arctic-route-control-center`；可用 `--data-root /绝对路径` 或 `ARCTIC_ROUTE_DATA_ROOT` 覆盖。Copernicus Marine `.env.copernicus` 与 CDS/CARRA `.cdsapirc` 必须位于程序、仓库、数据和制品目录之外，POSIX 权限应为 `0600`；界面分别保存两个绝对路径，不复制、读取或回显凭据内容。

构建脚本会验证仓库内 `packaging/viewer-root` 的 checksums、D 分支静态 Viewer、v4 ready 输入、控制中心测试、冻结程序自检、实际冻结任务子进程、编排器内部入口、HTTP 端点和路径穿越拒绝，再生成 SHA256。脚本内置本次已审查 appimagetool 与 type-2 runtime 的 SHA256；在线文件若变化会安全失败。正式长期发布仍应把这两个工具固定到内部制品库。

2026-09-03 本机构建的验收结果、成品摘要、真实 CARRA 最小下载和浏览器回归证据见 `RELEASE_VERIFICATION.zh-CN.md`。
