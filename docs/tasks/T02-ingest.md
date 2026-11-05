# T02 — 原始数据快照与读取

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M0 | T01 | 半天 | SPEC §5.1 |

## 目标
把两份原始数据复制进仓库成为只读快照，写 sha256 清单，并提供类型化的读取函数和 `ingest` 命令。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T01 验收命令通过。
- `/workspace/fil/page_rows.json` 与 `/workspace/filament-shots/inventory.json` 存在，`sha256sum` 与 SPEC §5.1 一致（不一致 → 停下报告，**不要**改 SPEC 里的期望值）。

## 要创建/修改的文件（只能动这些）
- `data/raw/page_rows.json`、`data/raw/inventory.json`（用 `cp` 复制，不准用代码改写）
- `data/raw/SHA256SUMS`（`cd data/raw && sha256sum page_rows.json inventory.json > SHA256SUMS`）
- `src/filament_picker/ingest.py`
- `src/filament_picker/cli.py`（只新增 `ingest` 子命令）
- `tests/test_ingest.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
@dataclass(frozen=True, slots=True)
class RawRow:
    row_index: int          # 在 page_rows.json 数组里的下标（0 起）
    brand: str              # b
    series: str             # s
    price_text: str         # p（可能是 ""）
    channel: str            # ch
    url: str                # u
    color_raw: str          # c
    family: str             # f
    hexes: tuple[str, ...]  # h，原样（不带 #，不改大小写）

@dataclass(frozen=True, slots=True)
class InventorySeries:
    brand: str
    series: str
    variant_image_paths: tuple[str, ...]

class SnapshotMismatchError(RuntimeError): ...
class RowFormatError(ValueError): ...

RAW_DIR: Path = REPO_ROOT / "data" / "raw"
EXPECTED_SHA256: dict[str, str] = {"page_rows.json": "510566fc…（SPEC §5.1 全长）", "inventory.json": "b6a775ea…（全长）"}

def sha256_file(path: Path) -> str: ...
def verify_snapshots(raw_dir: Path = RAW_DIR) -> None: ...   # 任一文件 sha256 不符 → SnapshotMismatchError(文件名)
def load_rows(path: Path) -> list[RawRow]: ...               # 每个对象的键集合必须 == {"b","s","p","ch","u","c","f","h"}，h 必须是 list[str]，否则 RowFormatError(f"row {i}: ...")
def load_inventory(path: Path) -> list[InventorySeries]: ... # 只读 data["series"]，每项取 brand / series / variant_image_paths（缺 variant_image_paths 视为空）
```
CLI：`filament-picker ingest` → `verify_snapshots()`，读两份文件，打印一行 `rows=<n> brands=<不同 b 数> series=<不同 (b,s) 数>`，返回 0；校验失败打印错误返回 1。

## 输入/输出示例
```text
$ .venv/bin/filament-picker ingest
rows=3845 brands=21 series=318
```
`load_rows(...)[2808]` == `RawRow(row_index=2808, brand="Bambu Lab", series="PETG Basic", price_text="¥2,800 JPY", channel="Bambu Lab 日本官方商城", url="https://jp.store.bambulab.com/products/petg-basic", color_raw="Black 黑色 (30105)", family="黑白灰", hexes=("000000",))`（真实行）

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_ingest.py`（读真实数据的测试加 `@pytest.mark.data`）
- `verify_snapshots()` 不抛异常；`sha256_file(RAW_DIR/"page_rows.json") == EXPECTED_SHA256["page_rows.json"]`。
- `len(rows) == 3845`；`rows[2808]` 等于上面的 RawRow（逐字段）。
- `Counter(len(r.hexes) for r in rows) == {0: 3245, 1: 582, 2: 17, 4: 1}`。
- 不同 brand 数 == 21；不同 (brand, series) 数 == 318。
- `len(load_inventory(RAW_DIR/"inventory.json")) == 313`。
- 把 page_rows.json 复制到 `tmp_path` 并在末尾追加一个空格 → `verify_snapshots(tmp_path)`（同时复制 inventory.json）抛 `SnapshotMismatchError`。
- 临时文件 `[{"b":"x"}]` → `load_rows` 抛 `RowFormatError`；`[{"b":"x","s":"","p":"","ch":"","u":"","c":"","f":"","h":"000000"}]`（h 是字符串）→ 抛 `RowFormatError`。
- `main(["ingest"]) == 0`，stdout == `rows=3845 brands=21 series=318\n`。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_ingest.py -q && (cd data/raw && sha256sum -c SHA256SUMS) && .venv/bin/filament-picker ingest
```

## 不要做
- 不要清洗、去重、排序、改写原始数据；快照必须与源文件逐字节相同。
- 不要在这里做品牌 slug、颜色名解析（那是 T03/T04）。
- 不要读 `/workspace/filament-shots/` 下的图片。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
