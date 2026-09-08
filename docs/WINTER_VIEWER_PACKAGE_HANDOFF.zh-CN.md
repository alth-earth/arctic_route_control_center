# Winter Viewer 制品交接说明

## 当前默认：Winter v4（2026-09-04 22:17 +08:00）

当前应导入并运行不可变制品 `winter-rebuilt-20260215-viewer-package-v4`。它作为运行时 `ready`
制品从数据根目录（`artifacts/ready`）加载；如需随发行物内嵌，应在构建时按 `--viewer-package`
显式声明（发行默认不再自动内嵌任何 Viewer 制品）。v4 目录本身不包含 HTML/CSS/JS、原始 GRIB/NC、
凭据或缓存。

Linux 默认数据根为：

```text
${XDG_DATA_HOME:-$HOME/.local/share}/arctic-route-control-center/
```

因此 v4 的外部 ready 目录仍是：

```text
<data-root>/arctic-route-control-center/artifacts/ready/
└── winter-rebuilt-20260215-viewer-package-v4/
```

交付压缩包与摘要：

```text
deliveries/winter-rebuilt-20260215-viewer-package-v4.tar.gz
SHA-256: 12c5ff2525ae9c0787f2cd6df679d5883ea730634d01bfa1555e8893ced4a89a
```

```text
assembly_id:     winter-viewer-sha256-f3113a19243bce88f712717ad91bddd9d3c76d93c6d84ac3c57e930496dff1ad
bundle.json:     f993ac113ac7280e9378710fdc84a825338ebd6ea4b5193ce8679aeb5c3b114a
checksums.json:  92ca583e52d41d277d22750631f083b0de798cb5ce8f9b105ef7a1d0123f7d33
```

将 v4 目录先放入 `artifacts/inbox/`，启动控制中心后进入“制品库”，点击“重新扫描”，确认
v4 通过校验后再点击“提升”。提升操作会校验 Schema、PUBLISHED、12 条路线、formal motion、
manifest 和全量 checksum，并原子移动到 ready；不要直接覆盖其他制品目录。

```bash
curl -X POST http://127.0.0.1:8130/api/artifacts/promote \
  -H 'Content-Type: application/json' \
  --data '{"package_name":"winter-rebuilt-20260215-viewer-package-v4"}'
```

v4 的 active route、船位、航向、trail 和 ETA 来自 C 发布的 formal `motion_samples`。D 的
`route_visual_smoothing.js` 只把制品中每个候选的 `geometry.coordinates` 转为 screen-space
Canvas 绘制命令；圆角和 trim 是展示策略，不是写死的 Winter 航线，且绝不改变运行路线或船位。
运行锁定后路线层、三目标显隐和候选高亮仍可操作；“设为运行路线”保持禁用，“重新选择路线”
会暂停并解除锁定。动态回放标签为 `retrospective_post_hoc_dynamic_projection`，不代表 causal、
实时预测、导航级或实船资格。

Viewer 地址（外部 ready 副本与内嵌同名时使用 `package_location=ready` 区分）：

```text
http://127.0.0.1:8130/viewer/?package=winter-rebuilt-20260215-viewer-package-v4&package_location=ready
```

截图与最终二进制证据位于：
`work_package_d/output/playwright/winter-rebuilt-20260215-current-standard-v4/`。

## 历史 v2（仅审计，不作为当前默认）

以下内容适用于历史制品 `winter-rebuilt-20260215-viewer-package-v2`，仅用于审计追溯。
本制品不会嵌入当前 Linux/Windows 发行物，也不包含 HTML/CSS/JS、原始 GRIB/NC、凭据或缓存。

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

发行物会在构建时嵌入初始动态 Viewer 与 v4；外部 `artifacts/ready` 仍是运行时接收和读取新制品的目录。实际部署时不要把凭据、原始数据或临时缓存复制到程序或制品目录。
