# T15 — 耗材匹配

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M2 | T08 T13 T14 | 半天 | SPEC §9.4 |

## 目标
为每个目标色在目录里找 ΔE00 最近的耗材，算出同系列方案和所需料槽数。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T08、T13、T14 验收通过；`data/ids.lock.json` 存在（测试在内存里用 `build_catalog(..., extracted=None)` 构造 M0 目录，不依赖 `data/build/`）。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/matcher.py`
- `tests/test_matcher.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
@dataclass(frozen=True, slots=True)
class MatchResult:
    matches: list[dict[str, Any]]                 # result.schema 的 matches 结构（target_index, picks[...]）
    single_series_option: dict[str, Any] | None   # result.schema 的 single_series_option
    slots_used: int
    warnings: tuple[str, ...]                     # NO_MATCH_FOR_COLOR:<index>

def eligible(entry: dict[str, Any], params: Params) -> bool: ...
def label_for(delta_e: float) -> str | None: ...  # <2 几乎一样；<5 接近；<=10 勉强；>10 None
def name_display(entry: dict[str, Any]) -> str: ...
def match_palette(palette: list[PaletteColor], catalog: Catalog, params: Params) -> MatchResult: ...
    # 所有目标都无 pick → raise NoMatchError()
```

## 输入/输出示例
SPEC §9.4 的 4 行金标表（真实目录、参考实现算出）。
`#1B1B1D`（PLA, brands=[bambu-lab], allow_approx=True, per_color=2）→ 与 `result.example.json` 的 `matches`、`single_series_option`、`slots_used` 完全一致：
`bambu-lab/pla-tough/black-12101` ΔE 4.38「接近」（url 是 BambuStudio GitHub 色码表；offer.price_text 为空串，输出必须是 null）、`bambu-lab/pla-aero/black-14103` ΔE 6.08「勉强」；同系列 PLA Tough 最大 4.38；slots_used 1。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_matcher.py`（`@pytest.mark.data`；session 级 fixture 构造 M0 Catalog）
- 金标表 4 行：`params.per_color = 3`，前 3 个 pick 的 `(id, delta_e)` 与表一致（delta_e 精确到 2 位）。
- `#1B1B1D`：`match_palette([PaletteColor(0, "#1B1B1D", (9.84, 0.52, -1.38), 1.0)], cat, resolve_params({}, parse_note("帮我配 4 色，AMS 一台，只要拓竹 PLA")))` → `.matches == ex["matches"]`、`.single_series_option == ex["single_series_option"]`、`.slots_used == 1`、`.warnings == ()`（ex = result.example.json）。
- `sum(eligible(e, resolve_params({"materials": ["PLA", "PETG"]}, parse_note(""))) for e in cat.entries) == 484`。
- `label_for(1.99) == "几乎一样"`、`label_for(2.0) == "接近"`、`label_for(4.99) == "接近"`、`label_for(5.0) == "勉强"`、`label_for(10.0) == "勉强"`、`label_for(10.01) is None`。
- `name_display`：bambu PETG 黑 → `"黑色 Black (30105)"`；byehassle 樱花粉 → `"樱花粉 Sakura Bloom"`；cailab bamboo → `"Bamboo (RB009)"`；`{"name_zh": None, "name_en": None, "code": None, "name_raw": "X"}` → `"X"`。
- `eligible`：含 `multi` 效果的条目为 False；`allow_approx=False` 时 store_swatch 条目为 False；`hex_confidence 0.49` 的 store_swatch 为 False、`0.5` 为 True（手写条目 dict）。
- 两个目标，其中一个是 PLA+bambu 里找不到 ≤10 的颜色（`#FF00FF`）→ warnings 含 `"NO_MATCH_FOR_COLOR:1"`；只给 `#FF00FF` → `pytest.raises(NoMatchError)`。（参考实现：PLA+拓竹里离 `#FF00FF` 最近的是 `bambu-lab/pla-basic/magenta-10202` #EC008C，ΔE 17.31 > 10。若你的结果不同 → 停下报告，不要换颜色凑数。）
- 结果拼进 result.example 后 `validate_json("result", ...) == []`。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_matcher.py -q
```

## 不要做
- 不要加"系列优先级""品牌偏好""价格权重"（见 SPEC §14 Q8，未决）。
- 不要放宽 `MATCH_MAX_DE`，不要在无匹配时退回 ΔE>10 的结果。
- 不要渲染图片或生成文字（T16/T17）。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
