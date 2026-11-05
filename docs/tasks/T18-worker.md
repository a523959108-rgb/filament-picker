# T18 — inbox→outbox worker 与清理

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M2 | T17 | 半天 | SPEC §9.1、§9.5 |

## 目标
实现文件队列 worker：原子认领 inbox 请求 → `run_plan` → 原子写 outbox → 归档到 done/failed；定期清理 7 天前文件；JSON lines 日志。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T17 验收通过。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/worker.py`
- `src/filament_picker/cli.py`（只新增 `worker` 子命令）
- `scripts/run_worker.sh`（SPEC §9.5 逐字，`chmod +x`）
- `tests/test_worker.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
SUBDIRS: tuple[str, ...] = ("inbox", "processing", "done", "failed", "outbox", "public/cards", "logs")
CLEAN_DIRS: tuple[str, ...] = ("inbox", "done", "failed", "outbox", "public/cards")
REQ_SUFFIX: str = ".request.json"

def ensure_dirs(root: Path) -> None: ...
def request_id_from_name(name: str) -> str: ...               # "abc.request.json" → "abc"
def claim(req: Path, root: Path) -> Path | None: ...         # os.rename 到 processing/；FileNotFoundError → None
def write_json_atomic(path: Path, obj: dict[str, Any]) -> None: ...   # 同目录 tmp 文件 + os.replace；ensure_ascii=False indent=2 + "\n"
def process_request(path: Path, catalog: Catalog, root: Path, card_base_url: str | None,
                    now: Callable[[], datetime]) -> dict[str, Any]: ...
    # 永不抛异常：JSON 解析失败 / schema 不符 → INVALID_REQUEST；最外层 except Exception → INTERNAL（traceback 只写日志）
def cleanup(root: Path, now: float) -> int: ...               # 只删 CLEAN_DIRS 下的普通文件，mtime 早于 now - RETENTION_DAYS*86400
def run_worker(root: Path, catalog_path: Path, once: bool, card_base_url: str | None) -> int: ...
    # SPEC §9.5 循环；目录加载失败 → 日志 CATALOG_ERROR，返回 2；SIGTERM/SIGINT → 处理完当前请求返回 0
```
日志 `logs/worker.log`，每行一个 JSON：`{"ts": ISO8601, "event": "start"|"claimed"|"done"|"cleanup"|"catalog_reload"|"error", "request_id": str|null, "status": "ok"|"error"|null, "code": str|null, "elapsed_ms": int|null, "detail": str|null}`。
CLI：`filament-picker worker --root DIR [--once] [--catalog PATH]`（`--catalog` 默认 `get_settings().catalog`；card_base_url 来自 `get_settings()`）。

## 输入/输出示例
```text
tmp_root/inbox/msgEXAMPLE0001.request.json   （request.example.json，image_paths 改成合成黑方块，constraints {"materials":["PETG"]}）
$ filament-picker worker --root tmp_root --once --catalog docs/schemas/examples/filament-catalog.example.json
→ tmp_root/outbox/msgEXAMPLE0001.json   status ok，首选 bambu-lab/petg-basic/black-30105 ΔE 0.0
→ tmp_root/done/msgEXAMPLE0001.request.json
```
（示例目录只有 4 条，足够覆盖 worker 测试；不依赖 data/build/。）

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_worker.py`（全部在 `tmp_root` 下，用示例目录 `docs/schemas/examples/filament-catalog.example.json`）
- 上面的正常流程：outbox JSON `validate_json("result") == []`、`matches[0]["picks"][0]["id"] == "bambu-lab/petg-basic/black-30105"`、`done/` 有该请求、`processing/` 和 `inbox/` 为空。
- inbox 里写 `bad.request.json` 内容 `"{not json"` → `outbox/bad.json` status error `INVALID_REQUEST`，请求移到 `failed/`。
- 含 `sessionWebhook` 的 context → `INVALID_REQUEST`。
- `*.request.json.tmp` 与图片文件不被处理（仍留在 inbox）。
- `monkeypatch` 让 `planner.run_plan` 抛 `RuntimeError("boom")` → status error `INTERNAL`，result 中不含 "boom"，`logs/worker.log` 有 event error 且 detail 含 "boom"。
- 认领：`claim` 同一文件两次 → 第二次 None。
- 并发：inbox 放 10 个请求，`subprocess` 同时起 2 个 `worker --once`（同 root）→ outbox 恰 10 个文件、done 恰 10 个、日志中 `event == "done"` 恰 10 行，没有任何 request_id 出现两次。
- cleanup：5 个 CLEAN_DIRS 各放一个文件 `os.utime` 到 8 天前，再各放一个新文件，另在 inbox 建子目录 `keep/`（旧 mtime）、在 `logs/` 放旧文件 → `cleanup(root, time.time()) == 5`；新文件、子目录、logs 文件都还在。
- 目录路径不存在 → `run_worker(...) == 2`，日志有 `CATALOG_ERROR`。
- `write_json_atomic` 写后目录中无 `.tmp` 残留。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_worker.py -q && test -x scripts/run_worker.sh && bash -n scripts/run_worker.sh
```

## 不要做
- 不要用 watchdog/inotify、线程池、asyncio；就是 sleep 轮询。
- 不要写 systemd / cron / supervisor 配置；不要启动常驻进程（部署由人决定）。
- 不要读写真实的 `/home/box/agent-data/shared/filament-picker/`（测试只用 tmp）。
- 不要回复钉钉、不要读监听器的任何文件；结果只写 outbox。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
