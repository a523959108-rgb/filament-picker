# 部署说明（OFD 打印参数 / 色值 / 成本计算器）

本次色值和打印参数只更新静态站和随包目录，**不需要改 nginx，也不要在服务器上重新导入数据**。模型预览登录另有一项必配环境变量，见下文。

## 模型预览账号（上线必配）

只要这台机器会跑 `filament-picker serve` 并且要让模型预览能登录，服务器上的 env 文件（不要提交进仓库）必须增加：

```bash
FILAMENT_PICKER_PREVIEW_USER=<当前预览账号名>
```

值由运维填写，并且要和库里已经建好的那个单账号一致。仓库只在 `deploy/filament-picker.env.example` 放占位 `change-me-preview-user`，不写真账号。未设置、空白，或仍是这个占位值时，进程在启动日志里提示 `FILAMENT_PICKER_PREVIEW_USER 未配置，模型预览拒绝所有登录`，登录接口返回 503。程序没有内置默认用户名，不会静默放行。

## 包里有什么

- `dist.tgz`：前端生产构建（`web/dist`）。里面已经包含更新后的 `web-catalog.json`、打印参数和色值。
- `bundle.tgz`：后端运行所需的源码、`data/build/filament-catalog.json`、`data/ofd/enrichment.json`（Open Filament Database 的离线结果）和 `data/manual_overrides.json`。
- 网站运行时只读这些静态文件，**不会访问** Open Filament Database 或任何外网。OrcaSlicer 预设是详情页上的下载链接，由用户自己点击，页面加载时不请求。

## 怎么换上

1. 备份现有 `web/dist`（或 nginx 的静态目录）和 `data/build/filament-catalog.json`。
2. 用 `dist.tgz` 覆盖静态目录。`web-catalog.json` 仍走现有的短缓存；带指纹的 `/assets/` 仍可长缓存。不必为这次改 nginx。
3. 用 `bundle.tgz` 里的目录覆盖后端的目录数据。不要改 `FP_CATALOG`、`FP_ROOT`、`FP_CARD_BASE_URL` 或 `deploy/filament-picker.env` 里的已有项。
4. 重启 `filament-picker serve`（或现有的进程管理方式），让进程读到新的目录文件。静态文件由 nginx 直接提供时，重启后端只影响 `/api/plan` 用的目录。

## 什么时候才要重新导入

这次的色值、eSUN 置信度和打印参数已经写进目录和 `data/ofd/enrichment.json`，部署时不要再跑导入。

只有在你用 `filament-picker build-catalog` **从 raw 快照重建目录**之后，OFD 补上的色值会被清掉。那时才需要在有本地快照的机器上重跑：

```bash
filament-picker import-ofd \
  --snapshot /path/to/open-filament-database-all.json.gz \
  --orca-index /path/to/orcaslicer-index.json
filament-picker export-web
```

然后重新构建前端并再打一次 `dist.tgz`。快照来自 Open Filament Database（MIT，见 `data/ofd/LICENSE`），不要把导入改成网站在线拉取。

## 校验

```bash
sha256sum -c SHA256SUMS
```
