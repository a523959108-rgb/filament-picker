# T25 — 生产构建与 serve

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M3 | T24 | 半天 | SPEC §10.3 最后一条、§11 |

## 目标
一条命令构建前端（含导出目录），一条命令用 uvicorn 同时提供 API 和 `web/dist` 静态页面。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T24 验收通过。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/server.py`；`src/filament_picker/cli.py`（只新增 `serve`）
- `scripts/build_web.sh`（`chmod +x`）
- `tests/test_serve.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
# server.py
def build_server_app(dist: Path, catalog_path: Path, root: Path, card_base_url: str | None) -> FastAPI: ...
    # app = create_app(catalog_path, root, card_base_url)；
    # dist 不存在或无 index.html → RuntimeError("web/dist 不存在，先运行 scripts/build_web.sh")
    # 在所有 /api 路由之后 mount("/", StaticFiles(directory=dist, html=True))
```
CLI：`filament-picker serve [--host 127.0.0.1] [--port 8787] [--dist PATH]`（`--dist` 默认 `REPO_ROOT/"web"/"dist"`；catalog/root/card_base_url 来自 `get_settings()`）→ `uvicorn.run(app, host, port)`。
```bash
# scripts/build_web.sh（逐字行为）
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/filament-picker export-web
cd web && npm ci && npm run build
echo "built web/dist"
```

## 输入/输出示例
```text
$ scripts/build_web.sh
entries=3821
...
built web/dist
$ .venv/bin/filament-picker serve --port 8787
GET /            → 200 text/html（web/dist/index.html）
GET /web-catalog.json → 200
GET /api/health  → 200 {"ok": true, ...}
```

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_serve.py`（在 tmp 里造假 dist：`index.html` 含 `<div id="root">`、`web-catalog.json` 复制示例导出；不依赖真的 npm 构建）
- `GET /` → 200，正文含 `<div id="root">`；`GET /web-catalog.json` → 200 且 JSON 有 4 条；`GET /api/health` → 200（API 没被静态挂载遮住）。
- `GET /api/cards/../x` → 404。
- dist 不存在 → `pytest.raises(RuntimeError, match="build_web.sh")`。
- `main(["serve", "--help"])` 退出码 0 且帮助文字含 `--port`（`SystemExit` 捕获）。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_serve.py -q && scripts/build_web.sh && test -f web/dist/index.html && (.venv/bin/filament-picker serve --port 8787 & echo $! > /tmp/fp_serve.pid; sleep 3; curl -fsS http://127.0.0.1:8787/api/health | grep -q '"ok": *true' && curl -fsS http://127.0.0.1:8787/ | grep -q 'id="root"'; rc=$?; kill $(cat /tmp/fp_serve.pid); exit $rc)
```

## 不要做
- 不要绑定 `0.0.0.0`、不要写反向代理/HTTPS/域名配置、不要开公网端口（SPEC §14 Q1 未决）。
- 不要写 systemd/docker；不要让 serve 常驻（验收后已 kill）。
- 不要把 `web/dist` 提交进仓库。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
