# T08 — 商品图匹配与目录组装 build-catalog

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M0 | T05 T06 T07 | 半天 | SPEC §5.9–§5.12；docs/schemas/filament-catalog.schema.json |

## 目标
把锁定 ID 的条目组装成 `data/build/filament-catalog.json`（M0 版：只有官方色和店铺示意色），并通过 schema 校验。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T05、T06、T07 验收通过；`data/ids.lock.json` 存在且 `keys=3821`。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/variants.py`、`src/filament_picker/catalog.py`
- `data/manual_overrides.json`（内容固定为 `{"schema_version": 1, "hex": {}, "store_swatch_confidence": {}}` + 换行）
- `src/filament_picker/cli.py`（只新增 `build-catalog` 子命令）
- `tests/test_variants.py`、`tests/test_catalog.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
# variants.py
VARIANT_RE: re.Pattern[str]          # SPEC §5.11 逐字
VariantIndex = dict[tuple[str, str], dict[str, str]]   # (brand 原文, series 原文) → {norm_key: 绝对路径}
def norm_key(s: str) -> str: ...
def build_variant_index(inventory: list[InventorySeries]) -> VariantIndex: ...
def find_variant_image(index: VariantIndex, info: RowInfo) -> str | None: ...

# catalog.py
CATALOG_PATH: Path = REPO_ROOT / "data" / "build" / "filament-catalog.json"
OVERRIDES_PATH: Path = REPO_ROOT / "data" / "manual_overrides.json"
class CatalogValidationError(RuntimeError): ...

@dataclass(frozen=True, slots=True)
class Catalog:
    generated_at: str
    entries: tuple[dict[str, Any], ...]
    by_id: dict[str, dict[str, Any]]

def build_entry(group: list[RowInfo], entry_id: str, variant_index: VariantIndex,
                overrides: dict[str, Any], extracted: dict[str, Any] | None) -> dict[str, Any]: ...
def build_catalog(rows: list[RawRow], lock: dict[str, Any], inventory: list[InventorySeries],
                  overrides: dict[str, Any], extracted: dict[str, Any] | None, now: str,
                  source: dict[str, str]) -> dict[str, Any]: ...
    # 只输出当前存在的组（status="active"）；entry_id 取 lock.entries[dedup_key].id（lock 里没有 → CatalogValidationError，提示先跑 assign-ids）
    # extracted 参数在 T08 恒为 None（T12 才接上）；source = {"page_rows_sha256","inventory_sha256","ids_lock_sha256"}
    # 末尾 validate_json("catalog")，有错 → CatalogValidationError(错误前 20 条)
def write_catalog(path: Path, catalog: dict[str, Any]) -> None: ...   # mkdir parents；ensure_ascii=False indent=2 + "\n"；tmp + os.replace
def load_catalog(path: Path) -> Catalog: ...                         # 文件缺失/JSON 错/校验失败 → CatalogValidationError
```
CLI：`filament-picker build-catalog [--extracted PATH] [--now ISO8601]`（`--now` 默认当前 Asia/Tokyo 时间，秒精度）→ 写 `CATALOG_PATH`，打印 `entries=3821 with_hex=600 official=246 store_swatch=354 image_extracted=0`。T08 里传 `--extracted` → 打印 `--extracted 需要 T12` 并返回 2。

## 输入/输出示例
- `docs/schemas/examples/filament-catalog.example.json` 的 4 个条目是真实条目的期望输出（Bambu PETG Basic 黑、eSUN PETG-Basic 黑、CaiLab bamboo-rb009 合并条目、ByeHassle 樱花粉）。
- `find_variant_image(index, <行 2808 的 RowInfo>) == "/workspace/filament-shots/Bambu Lab/PETG_Basic/variant_00_Black.jpg"`（靠 name_en 第二次尝试命中）。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_variants.py`
- `norm_key("Black 黑色 (30105)") == "black黑色30105"`；`norm_key("Red&Blue") == "redblue"`。
- `VARIANT_RE.match("variant_00_Black.jpg")[2] == "Black"`；`VARIANT_RE.match("cover.jpg") is None`。
- `@pytest.mark.data`：行 2808 → 上面的路径；全量 3845 行中 `find_variant_image` 非 None 的 == 2457，其中 brand_slug == "bambu-lab" 的 == 43，hexes 为空的 == 2101。

`tests/test_catalog.py`（`@pytest.mark.data`，用真实 rows + `data/ids.lock.json`；`now="2026-11-05T12:00:00+09:00"`）
- `validate_json("catalog", cat) == []`；`cat["counts"] == {"entries":3821,"with_hex":600,"official":246,"store_swatch":354,"image_extracted":0,"manual":0}`。
- `cat["entries"]` 按 id 严格升序；`[b["slug"] for b in cat["brands"]] == list(BRAND_ORDER)`。
- 对例子文件里的 4 个条目：`cat` 中同 id 的条目 `==` 例子条目（整个 dict 逐字段相等）。
- 材料计数：PLA 3059、PETG 762。
- 合并条目 `cailab/rainbow-shift-pla/bamboo-rb009`：`source_rows` 有 2 个，`aliases == ["竹 RB009"]`，`len(offers) == 2`。
- 覆盖：overrides `{"schema_version":1,"hex":{"esun/petg-basic/black":{"hex":["#111111"],"note":"test"}},"store_swatch_confidence":{"esun":0.3}}` → 该条目 `hex_source == "manual"`、`hex_confidence == 0.9`；其他 eSUN store_swatch 条目 `hex_confidence == 0.3`。
- lock 去掉一个 key → `pytest.raises(CatalogValidationError)`。
- `load_catalog` 读一个不存在的路径 → `CatalogValidationError`；读写出的文件 → `len(cat.entries) == 3821`，`cat.by_id["bambu-lab/petg-basic/black-30105"]["hex"] == ["#000000"]`。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_variants.py tests/test_catalog.py -q && .venv/bin/filament-picker build-catalog --now 2026-11-05T12:00:00+09:00 | grep -x 'entries=3821 with_hex=600 official=246 store_swatch=354 image_extracted=0' && .venv/bin/filament-picker validate catalog data/build/filament-catalog.json && .venv/bin/pytest -q
```

## 不要做
- 不要在这里做任何图片读取或取色（T10–T12）。
- 不要给条目新增 schema 以外的字段；不要改 schema。
- 不要把 `data/build/` 提交进 git。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
