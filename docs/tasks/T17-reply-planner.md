# T17 — 回复 Markdown、run_plan 与 plan 命令

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M2 | T16 | 半天 | SPEC §9.7–§9.9 |

## 目标
把前面所有步骤串成 `run_plan()`（worker 和 API 共用），生成逐字固定的 Markdown 回复，并提供本地 `plan` 命令。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T13–T16 验收通过。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/reply.py`、`src/filament_picker/planner.py`
- `src/filament_picker/cli.py`（只新增 `plan` 子命令）
- `tests/test_reply.py`、`tests/test_planner.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
# reply.py
APPROX_NOTE: str = "> 近似色 = 颜色来自店铺示意色或商品图取色，不是官方色值，请以实物为准。"
def build_reply_markdown(result: dict[str, Any]) -> str: ...   # status error → result["error"]["message_zh"]

# planner.py
def error_result(request: dict[str, Any], code: str, finished_at: str, elapsed_ms: int,
                 params: dict[str, Any], catalog_generated_at: str | None,
                 warnings: list[str]) -> dict[str, Any]: ...
    # 结构同 result.error.example.json；request 缺字段时 request_id/created_at/context 用 "invalid"/finished_at/{}
def run_plan(request: dict[str, Any], catalog: Catalog, root: Path,
             now: Callable[[], datetime], card_base_url: str | None) -> dict[str, Any]: ...
    # SPEC §9.9。捕获 FPError（→ e.code）与 CatalogValidationError（→ CATALOG_ERROR）转成 error_result；
    # 其他异常不捕获（由 worker 最外层处理）。返回前 validate_json("result")，有错 → error_result(..., "INTERNAL", ...)
```
CLI：`filament-picker plan <image> [--note TEXT] [--out DIR]`：request_id = `f"cli-{now:%Y%m%d%H%M%S}"`，`--out` 默认 `REPO_ROOT/"data"/"build"/"cli-root"`（作为 root），目录从 `get_settings().catalog` 读；stdout 打印 result JSON（`ensure_ascii=False, indent=2`）；status ok 返回 0，error 返回 1。

## 输入/输出示例
- 金标：`build_reply_markdown(json.load(open("docs/schemas/examples/result.example.json")))` == 该文件 `reply_markdown`（逐字）。
- 端到端（合成图 + 真实 M0 目录）：`square_on_white("#00AE42")` + note `"1色 只要拓竹 PLA"` → palette `[#00AE42 1.0]`，首选 `bambu-lab/pla-basic/bambu-green-10501` ΔE 0.0「几乎一样」，备选 `bambu-lab/pla-lite/green-16501` ΔE 4.69。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_reply.py`
- 金标逐字相等。
- 去掉 `card_url`（设 None）→ 输出不含 `![配色卡]`，其余行不变。
- 把第一个 pick 改成 `is_approx: true, hex_source: "store_swatch"` → 该行变成 `（ΔE 4.4，接近，近似色）`，且倒数第二行 == `APPROX_NOTE`。
- 把 single_series_option 设 None → 不含 `**同系列方案**`。
- picks 为空 → 该目标下一行是 `   - 暂无 ΔE ≤ 10 的耗材`。
- 输出每行都没有行尾空格；不以 `\n` 结尾。
- `status == "error"` → 输出 == `error.message_zh`。

`tests/test_planner.py`（固定时钟 `t0 = datetime(2026,11,5,14,3,12,tzinfo=ZoneInfo("Asia/Tokyo"))`，`now = iter([t0, t0 + timedelta(milliseconds=1840)]).__next__`）
- `@pytest.mark.data` 端到端如上：`status == "ok"`、`created_at == request["created_at"]`、`finished_at == "2026-11-05T14:03:13+09:00"`、`elapsed_ms == 1840`、`card_path` 在 `tmp_root/public/cards/` 下且文件存在、`card_url is None`（base_url None）、`validate_json("result", r) == []`、`context` 原样。
- 同上但 `card_base_url="https://cards.example.invalid"` → `card_url` 以它开头，reply 第二行是 `![配色卡](...)`。
- `image_paths` 指向不存在文件 → status error、`error.code == "IMAGE_MISSING"`、`card_path is None`、`reply_markdown == "没找到这张图片，可能已过期，请重新发送。"`，schema 通过。
- `tiny` 图 → `IMAGE_TOO_SMALL`；`blank_white` → `NO_FOREGROUND`；`#FF00FF` 方块 + 只要拓竹 PLA → `NO_MATCH`（最近 ΔE 17.31，见 T15）。
- 多图：`image_paths` 2 张 → warnings 含 `"EXTRA_IMAGES_IGNORED:1"`。
- CLI：`main(["plan", str(img), "--note", "1色 只要拓竹 PLA", "--out", str(tmp_path)])` 返回 0，stdout 可 `json.loads`，`request_id` 匹配 `^cli-\d{14}$`（需 `FP_CATALOG` 指向 T08 生成的目录；不存在则 skip）。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_reply.py tests/test_planner.py -q && .venv/bin/python -c "import sys; sys.path.insert(0, 'tests'); from helpers_images import square_on_white; from pathlib import Path; square_on_white(Path('/tmp/fp_green.png'))" && .venv/bin/filament-picker plan /tmp/fp_green.png --note '1色 只要拓竹 PLA' --out /tmp/fp_cli_root > /tmp/fp_plan.json && .venv/bin/filament-picker validate result /tmp/fp_plan.json && grep -q 'bambu-lab/pla-basic/bambu-green-10501' /tmp/fp_plan.json
```

## 不要做
- 不要在 reply 里加 emoji、链接以外的格式、署名；模板逐字。
- 不要发送任何消息；`run_plan` 只返回 dict，不写 outbox（T18 写）。
- 不要在 `run_plan` 里 `except Exception`。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
