# T23 — FastAPI /api/plan

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M3 | T17 | 半天 | SPEC §10.3 |

## 目标
提供 HTTP API：健康检查、上传图片跑 `run_plan`、按安全文件名取色卡图。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T17 验收通过。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/api.py`
- `tests/test_api.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
ALLOWED_EXT: dict[str, str] = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/heic": "heic"}
def create_app(catalog_path: Path, root: Path, card_base_url: str | None = None,
               now: Callable[[], datetime] | None = None) -> FastAPI: ...
    # 启动时 load_catalog 一次（失败直接抛）；now 默认 datetime.now(ZoneInfo(TZ))
    # GET  /api/health → {"ok": True, "catalog_generated_at": cat.generated_at}
    # POST /api/plan   multipart: file (必填), note: str = "", constraints: str | None（JSON 字符串）
    #   读 file 时累计字节，> MAX_UPLOAD_BYTES → 413 {"detail": "图片超过 10MB"}
    #   constraints 不是合法 JSON 对象 → 仍返回 200，result status error INVALID_REQUEST
    #   存 root/"inbox"/f"web-{uuid4().hex}.{ext}"（ext 由 content_type 查 ALLOWED_EXT，未知 → "bin"），
    #   构造 request（request_id = 文件名去扩展名，context {}），调 run_plan，返回 result（HTTP 200）
    # GET  /api/cards/{name} → CARD_NAME_RE 不匹配或文件不存在 → 404；否则 FileResponse(image/png)
```

## 输入/输出示例
```text
POST /api/plan  file=<绿方块 png>  note="1色 只要拓竹 PLA"
→ 200 {"status":"ok", "matches":[{"picks":[{"id":"bambu-lab/pla-basic/bambu-green-10501","delta_e":0.0,...}, ...]}], ...}
GET /api/cards/../x            → 404
GET /api/cards/EXAMPLE_TOKEN.png → 404（名字长度不对）
```

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_api.py`（`fastapi.testclient.TestClient`；目录用示例目录，唯独绿方块用例 `@pytest.mark.data` 用 T08 真实目录）
- `/api/health` → 200，`ok is True`，`catalog_generated_at == "2026-11-05T12:00:00+09:00"`（示例目录）。
- 示例目录 + 黑方块 + `constraints='{"materials":["PETG"]}'` → 200，result schema 通过，首选 `bambu-lab/petg-basic/black-30105`；`card_path` 文件存在；inbox 下多了一个 `web-*.png`。
- 拿上一步 `card_path` 的文件名 GET `/api/cards/<name>` → 200，`content-type` 为 `image/png`，内容与文件字节相同。
- 10MB + 1 字节的上传 → 413；恰好 10MB 的非图片字节 → 200 且 `error.code == "IMAGE_UNREADABLE"`。
- `constraints="not json"` → 200，`error.code == "INVALID_REQUEST"`。
- `/api/cards/../x`、`/api/cards/EXAMPLE_TOKEN.png`、32 位合法名但文件不存在 → 均 404。
- `@pytest.mark.data`：绿方块 + "1色 只要拓竹 PLA" → 首选 `bambu-lab/pla-basic/bambu-green-10501`。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_api.py -q
```

## 不要做
- 不要加鉴权、CORS 放开、限流、数据库（API 只给本机/前端用，公开部署是 SPEC §14 的未决问题）。
- 不要在 API 里写 outbox 或 `*.request.json`（那是 worker 的协议，API 直接调 run_plan）。
- 不要用 pydantic 模型定义 result（直接返回 dict，schema 校验已在 run_plan 里）。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
