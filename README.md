# filament-picker

离线优先的 3D 打印耗材选色站。按色号、照片或模型颜色在目录里找接近的耗材，并给出购买入口和粗略打印成本。

在线站点：

- 选色站：[https://filament.ibaozi.com](https://filament.ibaozi.com)
- 叠色工作区：[https://stack.filament.ibaozi.com](https://stack.filament.ibaozi.com)（也可在主站打开 `#/stack`）

这是一个非商业、小规模的公益项目。源码仓库：<https://github.com/a523959108-rgb/filament-picker>。

## 功能

- 浏览和搜索耗材目录，按色差（CIEDE2000）推荐接近的颜色
- 上传照片或使用模型封面，提取主色后再匹配目录
- 打印参数、补色和成本估算（部分数据来自 Open Filament Database）
- 叠色工作区：四色托盘映射、预览和推荐可买色
- 可选的本机模型预览（`/models`，需单独配置账号，不包含在公开默认部署里）
- 可选的 Spoolman 库存对接（只在私有网络启用，不在公开站打开）

## 许可证

本仓库以 **AGPL-3.0-only** 发布，全文见 [LICENSE](LICENSE)。`pyproject.toml` 与 `web/package.json` 的 `license` 字段同为 `AGPL-3.0-only`。

叠色工作区复用了 [Lumina-Layers](https://github.com/lumina-layer-studio/Lumina-Layers)（Lumina Studio）的前端代码、样式和热床绘制，上游许可证为 **AGPL-3.0-only**。本项目因此也采用 AGPL-3.0-only，以便继续分发这部分代码。来源、上游 commit、文件清单和本地修改见 [NOTICE](NOTICE) 与 [third_party/lumina-layers/README.md](third_party/lumina-layers/README.md)。

部分打印参数和色值来自 [Open Filament Database](https://github.com/OpenFilamentCollective/open-filament-database)，按 MIT 使用，说明见 [data/ofd/LICENSE](data/ofd/LICENSE)。

自托管的 Lumina 后端 fork 在单独仓库：[filament-lumina](https://github.com/a523959108-rgb/filament-lumina)。

## 环境

- Python 3.11（项目锁定为 `>=3.11,<3.12`）
- Node.js 24.x，用于 `web/` 前端

## 本地运行

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/filament-picker --version
.venv/bin/filament-picker validate request docs/schemas/examples/request.example.json
.venv/bin/pytest -q

cd web
npm ci
npm test
npm run build
cd ..
.venv/bin/filament-picker serve
```

浏览器打开 `http://127.0.0.1:8787/`。前端单独开发可用 `cd web && npm run dev`（开发服务器把 `/api` 代理到 `127.0.0.1:8787`）。

不要把真实密钥、账号或 `.env` 提交进仓库。服务器环境变量的占位模板在 `deploy/filament-picker.env.example`；模型预览账号只通过环境变量 `FILAMENT_PICKER_PREVIEW_USER` 在服务器上配置，占位值会被拒绝。部署说明见 `deploy/`。叠色后端的地址不写进仓库，放在服务器本地的 `upstream.env`（模板 `deploy/lumina/upstream.env.example`）和 `deploy/lumina/docker/.env`（模板 `deploy/lumina/docker/.env.example`）。

公开站与个人打印控制的边界见 [docs/all-in-one-boundary.md](docs/all-in-one-boundary.md)。

选色 worker 的常驻运行手册（只准备，未启动）见 [docs/dingtalk-worker-runbook.md](docs/dingtalk-worker-runbook.md)。

## 目录结构

- `src/filament_picker/`：选色、目录、API 和 CLI
- `web/`：前端（Vite）
- `data/`：目录快照与派生数据；`data/auth/`、`data/models-private/` 被 git 忽略
- `docs/`：规格、任务和功能说明
- `deploy/`：Nginx / systemd / 叠色后端的部署示例。`deploy/release/dist.tgz` 是本地构建的前端包，不提交，构建步骤见 [deploy/DEPLOY.md](deploy/DEPLOY.md)
- `third_party/lumina-layers/`：Lumina 许可证与复用说明
- `tools/dtimg-outbox/`：可选的运维小工具，不参与选色站运行

## 贡献

欢迎 issue 和 pull request。改行为或阈值前请先看 `docs/SPEC.md`。提交前请运行：

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest -q
cd web && npm run lint && npm test
```
