# T12 — 批量取色、校准与抽检

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M1 | T08 T11 | 半天 | SPEC §5.9、§8.4、§11 |

## 目标
对目录中所有有商品图的条目取色写出 `extracted.json`；用官方色做校准报告；生成 50 条抽检 HTML；让 `build-catalog --extracted` 把取色结果并入目录。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T08、T11 验收通过；`data/build/filament-catalog.json` 已由 T08 生成；`/workspace/filament-shots/` 存在。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/calibrate.py`（新增：批量取色、校准、抽检三个函数）
- `src/filament_picker/catalog.py`（**只**修改 `build_entry` / `build_catalog` 中处理 `extracted` 的分支，删除 T08 的"需要 T12"提示）
- `src/filament_picker/cli.py`（新增 `extract`、`calibrate`、`qa-sample` 三个子命令；修改 `build-catalog` 的 `--extracted` 分支）
- `tests/test_calibrate.py`、`tests/test_catalog_extracted.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
EXTRACTED_PATH: Path = REPO_ROOT / "data" / "extracted" / "extracted.json"
CALIBRATION_PATH: Path = REPO_ROOT / "data" / "qa" / "calibration.csv"
QA_SAMPLE_PATH: Path = REPO_ROOT / "data" / "qa" / "sample.html"

def run_extract(catalog: Catalog, now: str, limit: int | None = None) -> dict[str, Any]: ...
    # 对 variant_image 非 null 的条目（按 id 升序；limit 取前 N 个）调用 extract_colors(path, entry["effects"])
    # 返回 {"generated_at": now, "results": {id: {...}}}，每项字段固定：
    #   image, status("ok"|"no_foreground"|"skipped"), hexes, confidence, share, spread, n_pixels, error(None 或错误码)
    #   ImageMissingError / ImageUnreadableError → status "skipped"，error = e.code，数值字段 0、hexes []
def calibrate(catalog: Catalog, extracted: dict[str, Any]) -> list[dict[str, Any]]: ...
    # 取 hex_source ∈ {official, store_swatch} 且 len(hex)==1 且 extracted 结果 status=="ok" 的条目
    # 每行 {id, hex_source, catalog_hex, extracted_hex(=hexes[0]), delta_e(round 2), confidence}；按 id 升序
def summarize(rows: list[dict[str, Any]]) -> list[str]: ...
    # 先输出每个有 store_swatch 行的品牌一行：f"store_swatch {brand_slug} n={n} median={m:.1f} p80={p:.1f}"（按 brand_slug 升序）
    # 最后一行：f"bambu n={n} median={m:.1f} p80={p:.1f}"（official 行）；百分位用 np.percentile 默认线性插值
def qa_sample(catalog: Catalog, extracted: dict[str, Any], n: int = 50, seed: int = 20261105) -> str: ...
    # 候选 = status ok 的 id 升序列表；np.random.default_rng(seed).choice(len, size=min(n,len), replace=False)，再按 id 排序
    # 返回 HTML：每行 <img src="file://{image}" width=160>、提取色块、目录色块（若有）、id、confidence；不引外部 CSS/JS
```
`catalog.py` 扩展规则（SPEC §5.9）：条目 `hex` 为空、`extracted.results[id].status == "ok"`、`confidence >= EXTRACT_MIN_CONF` → `hex = hexes`，`hex_source = "image_extracted"`，`hex_confidence = confidence`，`lab` = hex[0] 的 Lab；否则保持无 hex。manual 覆盖仍然优先。

CLI：
- `extract [--limit N]` → 写 `EXTRACTED_PATH`，打印 `ok=<n> no_foreground=<n> skipped=<n>`
- `calibrate` → 写 `CALIBRATION_PATH`（列顺序 `id,hex_source,catalog_hex,extracted_hex,delta_e,confidence`），逐行打印 `summarize()`
- `qa-sample [--n 50]` → 写 `QA_SAMPLE_PATH`，打印 `wrote data/qa/sample.html`
- `build-catalog --extracted data/extracted/extracted.json` → 并入取色结果

## 输入/输出示例
```text
$ .venv/bin/filament-picker extract
ok=<a> no_foreground=<b> skipped=<c>            # a+b+c 必须 = 2457
$ .venv/bin/filament-picker calibrate
store_swatch anycubic n=<n> median=<m> p80=<p>
...
bambu n=40 median=<m> p80=<p>                   # 参考实现：median 8.0 / p80 14.6（2026-11-05；有图 official 43 条里 3 条多色不进校准）
```
`extracted.json` 单项形状（示例，数值非真实）：`{"image": "/workspace/filament-shots/…/variant_00_Black.jpg", "status": "ok", "hexes": ["#1C1C1E"], "confidence": 0.512, "share": 0.71, "spread": 2.84, "n_pixels": 20000, "error": null}`

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_catalog_extracted.py`（不读图片，用手写的 extracted dict + 真实 rows/lock）
- 选一个无 hex 且有图的真实条目 id（`cailab/rainbow-shift-pla/bamboo-rb009`）：extracted 置信度 `0.40` → `hex_source == "image_extracted"`、`hex == ["#123456"]`、`hex_confidence == 0.4`；置信度 `0.39` → `hex == []`、`hex_source is None`、`hex_confidence is None`、`lab is None`（与 T08 无 hex 条目写法一致）。
- 给已有 official 色的 `bambu-lab/petg-basic/black-30105` 一个 conf 0.99 的结果 → 仍是 `official`、`["#000000"]`。
- 带 extracted 时 `counts.image_extracted == 1`，schema 校验通过，所有 id 与不带 extracted 时完全相同。

`tests/test_calibrate.py`
- `run_extract` 用 `tmp_path` 下的 2 张合成图（`square_on_white`、`blank_white`）+ 1 个不存在路径，构造 3 条目的最小 Catalog → results 状态分别 ok / no_foreground / skipped(error=="IMAGE_MISSING")；`limit=1` 只有 1 项。
- `summarize` 对手写 rows：official ΔE `[1, 2, 3, 4, 5]` → 最后一行 `"bambu n=5 median=3.0 p80=4.2"`；store_swatch esun `[10, 20]` → `"store_swatch esun n=2 median=15.0 p80=18.0"`。
- `qa_sample` 对 60 个 ok 结果 → HTML 里 `<img` 出现 50 次；同输入两次输出相同；对 10 个 → 10 次。
- `@pytest.mark.data`（慢，验收时跑）：真实目录 `run_extract` 后 `len(results) == 2457`；`calibrate` 中 official 行数 == 40（3 条多色丝绸 `len(hex)>1` 被 `len(hex)==1` 过滤）。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && cp data/ids.lock.json /tmp/fp_lock_before.json && .venv/bin/pytest tests/test_calibrate.py tests/test_catalog_extracted.py -q && .venv/bin/filament-picker extract | tee /tmp/fp_extract.txt && python3 -c "import re;t=open('/tmp/fp_extract.txt').read().split()[-3:];n=sum(int(x.split('=')[1]) for x in t);assert n==2457,n" && .venv/bin/filament-picker calibrate | tail -1 | grep -E '^bambu n=40 median=' && .venv/bin/filament-picker qa-sample && .venv/bin/filament-picker build-catalog --extracted data/extracted/extracted.json --now 2026-11-05T12:00:00+09:00 && .venv/bin/filament-picker validate catalog data/build/filament-catalog.json && cmp data/ids.lock.json /tmp/fp_lock_before.json
```

## 不要做
- **不要**根据校准结果改任何阈值、置信度公式或 `manual_overrides.json`；把数字写进报告即可。
- 不要并行/多进程（保持确定性和简单）；不要缓存到别处。
- 不要把 `data/extracted/`、`data/qa/` 提交。
- 不要修改 `catalog.py` 中与 extracted 无关的代码。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
