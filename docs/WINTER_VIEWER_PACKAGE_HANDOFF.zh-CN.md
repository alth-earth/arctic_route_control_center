# Winter Viewer 制品交接说明

本说明适用于 2026-02-15 Winter Viewer 制品 `winter-rebuilt-20260215-viewer-package-v2`。
本制品是外部运行时数据，不会嵌入 AppImage，也不包含 HTML/CSS/JS、原始 GRIB/NC、凭据或缓存。

## 制品位置与校验

Linux 默认运行时目录为：

```text
${XDG_DATA_HOME:-$HOME/.local/share}/arctic-route-control-center/
```

使用 `--data-root /绝对路径` 时，以指定目录为根。制品目录应为：

```text
<data-root>/arctic-route-control-center/artifacts/ready/
└── winter-rebuilt-20260215-viewer-package-v2/
```

建议交付以下压缩包，并先校验压缩包摘要：

```text
work_package_d/output/winter-rebuilt-20260215-viewer-package-v2.tar.gz
SHA-256: 7d540c5ab31bce1b69b673f8852d503ad2151a99b2c49a69010a97e85b8223fa
```

解包后的关键摘要：

```text
assembly_id:     winter-viewer-sha256-c4434cad9b1dac344c718206a4d34a83f2a1aeee5269ed89e48141625704cbb9
bundle.json:     5f463c6184f8d827c132b5e1bf3bd00f0776900a0148dae610bc4c963dd7f80b
checksums.json:  eae5f6e9acb4b024bf4238253f6619928bc8d7d6a8860998d519f83fd469fc6a
```

## 导入流程

不要直接覆盖现有制品，也不要把 v1 改名为 v2。将目录先放入：

```text
<data-root>/arctic-route-control-center/artifacts/inbox/
```

启动控制中心后，在“制品库”确认 v2 状态为 `ready`，点击“提升”。控制中心会校验 bundle、checksums、PUBLISHED、12 条路线和 formal motion，然后原子移动到 `artifacts/ready/`。

也可以使用本地 API：

```bash
curl -X POST http://127.0.0.1:8130/api/artifacts/promote \
  -H 'Content-Type: application/json' \
  --data '{"package_name":"winter-rebuilt-20260215-viewer-package-v2"}'
```

## 运行与语义边界

打开：

```text
http://127.0.0.1:8130/viewer/?package=winter-rebuilt-20260215-viewer-package-v2
```

Viewer 应显示 12 条路线、145 个风险帧和 Risk Explanation。点击运行后只锁定实际 candidate、motion、ETA 和运行路线；路线层、目标显隐和卡片高亮仍可操作。

该版本的 C motion 使用 `RAW_PASSTHROUGH`，表示绑定的生产前回退运动样本，不是曲线资格、实船标定或导航适航结论。仿真时间轴仍以路线 ETA 结束；没有真实因果 replay 时，界面必须保留动态重规划不可用提示。

验证截图和运行摘要位于：

```text
work_package_d/output/playwright/winter-rebuilt-20260215-current-standard/
```

AppImage 本身未重建；当前验证复用了已有 Linux x64 AppImage。实际部署时不要把凭据、原始数据或临时缓存复制到制品目录。
