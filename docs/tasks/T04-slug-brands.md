# T04 — slug、品牌表与系列 slug

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M0 | T03 | 半天 | SPEC §5.4–§5.5、§5.10 |

## 目标
实现 `slug()`、品牌 slug 查表、系列 slug、颜色段和单行 `row_id`；以及条目的拼音字段函数。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T03 验收通过。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/slug.py`
- `src/filament_picker/brands.py`
- `tests/test_slug.py`、`tests/test_brands.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
# brands.py
BRAND_SLUGS: dict[str, str]                 # SPEC §5.4 表，21 项，键 = b 原文，按表顺序
BRAND_ALIASES: dict[str, tuple[str, ...]]   # 键 = slug，值 = 别名（全部小写），按表顺序
BRAND_ORDER: tuple[str, ...]                # 21 个 slug，按表顺序
class UnknownBrandError(ValueError): ...
def brand_slug(name: str) -> str: ...       # 查不到 → UnknownBrandError(name)

# slug.py
def slug(s: str, maxlen: int = MAX_SLUG_LEN) -> str: ...
def series_clean(s: str) -> str: ...
def series_slug(s: str) -> str: ...
def color_segment(parsed: ParsedName, raw: str) -> str: ...
def row_id(brand_slug: str, series: str, parsed: ParsedName, raw: str) -> str: ...  # f"{brand_slug}/{series_slug(series)}/{color_segment(parsed, raw)}"
def pinyin_fields(name_zh: str | None) -> tuple[str | None, str | None]: ...      # SPEC §5.10 → (pinyin, pinyin_initials)
```

## 输入/输出示例
| 调用 | 结果 |
|---|---|
| `slug("PLA+ 2.0")` | `"pla-plus-2-0"` |
| `slug("菠菜绿")` | `"bo-cai-lv"` |
| `slug("Blue&Green")` | `"blue-green"` |
| `slug("a"*30 + " " + "b"*40)` | `"a"*30`（截到 60 再退到最后一个 `-`） |
| `slug("x"*70)` | `"x"*60`（60 字符内没有 `-`，直接截断） |
| `series_slug("PLA哑光（拼多多）")` | `"pla-ya-guang"` |
| `series_slug("彩虹丝绸 PLA（RB 系列）")` | `"cai-hong-si-chou-pla-rb-xi-lie"` |
| `pinyin_fields("樱花粉")` | `("ying hua fen", "yhf")` |
| `pinyin_fields(None)` | `(None, None)` |
| `brand_slug("没毛病/ByeHassle")` | `"byehassle"` |

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_slug.py`
- 上表每一行一个断言。
- 参数化 `golden_ids` 35 行：`series_slug(row["series"]) == row["series_slug"]`；`row_id(row["brand_slug"], row["series"], parse_color_name(row["raw_name"]), row["raw_name"]) == row["row_id"]`。
- `color_segment(ParsedName(None, None, None), "???")` 以 `"x"` 开头、长度 9，且对同一 raw 两次结果相同。
- `@pytest.mark.data` 全量 3845 行：最长 row_id 长度 == 108；没有任何 color_segment 以 `x` + 8 位十六进制的兜底形式出现（`re.fullmatch(r"x[0-9a-f]{8}", seg)` 计数 == 0）。

`tests/test_brands.py`
- `len(BRAND_SLUGS) == 21 == len(BRAND_ALIASES) == len(BRAND_ORDER)`；`BRAND_ORDER[0] == "bambu-lab"`，`BRAND_ORDER[-1] == "byehassle"`。
- 所有别名 `== alias.lower()`。
- `brand_slug("Foo")` → `UnknownBrandError`。
- `@pytest.mark.data`：`raw_rows` 里每个不同的 `b` 都能 `brand_slug()`。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_slug.py tests/test_brands.py -q
```

## 不要做
- 不要计算品牌 slug（只能查表）；不要给表外品牌自动生成 slug。
- 不要改 `lazy_pinyin` 的参数（默认风格，无声调）。
- 不要在这里做去重 key（T06）。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
