# T05 — 效果标签与材料

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M0 | T03 | 半天 | SPEC §5.8 |

## 目标
按固定正则表给每行打效果标签（silk / matte / dual ……），并判定材料 PLA / PETG。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T03 验收通过（用到 `nfkc`）。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/effects.py`
- `tests/test_effects.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
EFFECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...]   # SPEC §5.8 表的前 14 行，顺序不变
MULTI_FAMILY: str = "多色/渐变"

def detect_effects(series: str, color_raw: str, family: str) -> tuple[str, ...]: ...
    # t = nfkc(series + " " + color_raw).lower()；按 EFFECT_PATTERNS 顺序 re.search 命中即追加；
    # family == MULTI_FAMILY 时最后追加 "multi"
def detect_material(series: str) -> str: ...   # "PETG" in series.upper() → "PETG" 否则 "PLA"
```

## 输入/输出示例
- `detect_effects("PLA Silk Dual-Color", "Red&Blue", "多色/渐变") == ("silk", "dual", "multi")`（真实行 1827）
- `detect_effects("PETG Basic", "Black 黑色 (30105)", "黑白灰") == ()`
- `detect_material("PETG-Basic") == "PETG"`，`detect_material("PLA哑光（拼多多）") == "PLA"`

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_effects.py`
- 上面 4 个例子。
- 参数化 `golden_ids` 35 行：`list(detect_effects(row["series"], row["raw_name"], <该行 f>)) == row["effects"]`，`detect_material(row["series"]) == row["material"]`。（golden 里没有 f：用 `raw_rows[row["row_index"]]["f"]` 取。）
- `@pytest.mark.data` 全量计数（按行）：multi 610、matte 597、silk 592、gradient 250、translucent 246、dual 156、sparkle 137、metallic 107、cf 96、glow 75、tri 59、wood 56、marble 29、gf 28、color_change 5；无任何 effect 的行 == 1772。
- `@pytest.mark.data`：按行材料 PLA 3083、PETG 762。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_effects.py -q
```

## 不要做
- 不要增删正则、不要改顺序、不要给效果去重以外的任何"智能"处理（例如 silk 与 matte 互斥判断）。
- 不要按颜色名判断材料。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
