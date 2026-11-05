# T03 — 颜色名解析

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M0 | T01 | 半天 | SPEC §5.2–§5.3 |

## 目标
实现 `nfkc()` 和 `parse_color_name()`：把颜色原名拆成英文名、中文名、色号。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T01 验收通过；T02 已完成（真实数据测试需要 `data/raw/`）。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/names.py`
- `tests/test_names.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
WEIGHT: re.Pattern[str]   # SPEC §5.3 逐字
PCODE: re.Pattern[str]
TCODE: re.Pattern[str]
ZH: re.Pattern[str]

@dataclass(frozen=True, slots=True)
class ParsedName:
    name_en: str | None
    name_zh: str | None
    code: str | None

def nfkc(s: str) -> str: ...
def parse_color_name(raw: str) -> ParsedName: ...   # 严格按 SPEC §5.3 伪代码，步骤顺序不能变
```

## 输入/输出示例
SPEC §5.3 的 10 行表格（全部真实）。再如：`nfkc("樱花粉（Sakura Bloom）") == "樱花粉(Sakura Bloom)"`；`nfkc("  a\u3000 b ") == "a b"`。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_names.py`
- 参数化：SPEC §5.3 表格 10 行，`parse_color_name(raw) == ParsedName(name_en, name_zh, code)`。
- 参数化：`golden_ids` 的 35 行，`parse_color_name(row["raw_name"])` 的三个字段分别等于 `row["name_en"]`、`row["name_zh"]`、`row["code"]`。
- `nfkc` 两个例子如上。
- `@pytest.mark.data`：对 `raw_rows` 全量解析：有 code 的行数 == 467；brand == "Bambu Lab" 且有 code 的 246 行 code 全部 `re.fullmatch(r"\d{5}")`；brand == "彩多屋 CaiLab" 有 code 的行 == 221；CaiLab code 前缀统计 `Counter(re.match(r"[A-Z]+", c)[0])` 中 RB == 40、AC == 33、G == 30、MT == 25。
- 所有返回的非 None 字段都不以空格开头/结尾。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_names.py -q
```

## 不要做
- 不要"改进"正则（例如顺手支持 `kg` 以外的单位、支持更多色号格式）。表里没有的情况就照伪代码的结果。
- 不要做 slug / 拼音（T04）。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
