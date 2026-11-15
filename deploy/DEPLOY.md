# 部署说明（OFD 打印参数 / 色值 / 成本计算器）

本次色值和打印参数只更新静态站和随包目录，**不需要改 nginx，也不要在服务器上重新导入数据**。模型预览登录另有一项必配环境变量，见下文。

## 模型预览账号（上线必配）

只要这台机器会跑 `filament-picker serve` 并且要让模型预览能登录，服务器上的 env 文件（不要提交进仓库）必须增加：

```bash
FILAMENT_PICKER_PREVIEW_USER=<当前预览账号名>
```

值由运维填写，并且要和库里已经建好的那个单账号一致。仓库只在 `deploy/filament-picker.env.example` 放占位 `change-me-preview-user`，不写真账号。未设置、空白，或仍是这个占位值时，进程在启动日志里提示 `FILAMENT_PICKER_PREVIEW_USER 未配置，模型预览拒绝所有登录`，登录接口返回 503。程序没有内置默认用户名，不会静默放行。

## 包里有什么

- `dist.tgz`：前端生产构建（`web/dist`）。里面已经包含更新后的 `web-catalog.json`、打印参数和色值。这个包不进 git，按下一节在本地构建。
- `bundle.tgz`：后端运行所需的源码、`data/build/filament-catalog.json`、`data/ofd/enrichment.json`（Open Filament Database 的离线结果）和 `data/manual_overrides.json`。
- 网站运行时只读这些静态文件，**不会访问** Open Filament Database 或任何外网。OrcaSlicer 预设是详情页上的下载链接，由用户自己点击，页面加载时不请求。

## 怎么构建 dist.tgz

`deploy/release/dist.tgz` 是构建产物，仓库不保存它（根目录 `.gitignore` 已忽略）。没有构建或部署脚本依赖已经提交的那份包。在要发布的检出上重新构建：

```bash
cd web
npm ci
npm run build
mkdir -p ../deploy/release
tar -czf ../deploy/release/dist.tgz -C dist .
sha256sum ../deploy/release/dist.tgz
```

校验和留在本地，不要把 `dist.tgz` 提交回去。`deploy/release/SHA256SUMS` 只记录仍在树里的 `bundle.tgz` 和 `DEPLOY.md`。

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

然后按上文「怎么构建 dist.tgz」重新构建前端并再打一次包。快照来自 Open Filament Database（MIT，见 `data/ofd/LICENSE`），不要把导入改成网站在线拉取。

## 校验

```bash
sha256sum -c SHA256SUMS
```

## 拍照找耗材

纯静态前端，没有新接口。照片在浏览器里取色和匹配，不上传、不落盘。不新增环境变量，不改数据库，不跑迁移，不改 nginx。

主站和叠色子域用的是同一份 `web/dist`。两边都要换上这一份，否则子域上的「拍照找耗材」会缺页面，主站上「用这个颜色打开叠色」带去的 `#/stack?colors=...` 也看不到预填色。

1. 在构建机的 `web/` 目录执行 `npm ci && npm run build`。
2. 用新的 `web/dist` 覆盖 nginx 静态目录（或按现有流程打 `dist.tgz` 再替换）。`web-catalog.json` 仍走现有短缓存。
3. 不必重启 `filament-picker serve`。静态文件由 nginx 提供时，后端进程不用动。
4. 打开 `https://filament.ibaozi.com/#/photo`，以及从主站点进 `https://stack.filament.ibaozi.com/#/stack?colors=...`，确认目标色已填入。

没有新的 `deploy/filament-picker.env` 项。`FILAMENT_PICKER_PREVIEW_USER` 仍只用于模型预览登录，和这个功能无关。
