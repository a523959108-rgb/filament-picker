# T13 — 备注解析与参数合并

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M2 | T04 | 半天 | SPEC §9.2；docs/schemas/request.schema.json、result.schema.json 的 params |

## 目标
把用户随图文字解析成参数，并与显式 constraints、默认值合并成最终 `Params`。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T04 验收通过（用到 `BRAND_ALIASES` / `BRAND_ORDER`）。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/note_parser.py`
- `tests/test_note_parser.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
CN_NUM: dict[str, int]   # SPEC §9.2 的中文数字表

@dataclass(frozen=True, slots=True)
class NoteParse:
    values: dict[str, Any]          # 只含解析到的键；键顺序：max_colors, ams_slots, materials, brands, allow_approx, keep_small
    warnings: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class Params:
    max_colors: int
    ams_slots: int
    n_colors: int                   # = min(max_colors, ams_slots)
    materials: tuple[str, ...]
    brands: tuple[str, ...]
    allow_approx: bool
    keep_small: bool
    per_color: int
    note_parsed: dict[str, Any]
    def to_dict(self) -> dict[str, Any]: ...   # 键顺序与 result.schema params.required 相同；元组转 list

def parse_note(text: str) -> NoteParse: ...
def resolve_params(constraints: dict[str, Any] | None, note: NoteParse) -> Params: ...
    # 每个键：constraints > note.values > 默认值（DEFAULT_MAX_COLORS, DEFAULT_AMS_SLOTS, DEFAULT_MATERIALS, (), True, False, DEFAULT_PER_COLOR）
```

## 输入/输出示例
SPEC §9.2 表格 7 行（全部是测试用例）。
`resolve_params({}, parse_note("帮我配 4 色，AMS 一台，只要拓竹 PLA")).to_dict()` == `docs/schemas/examples/result.example.json` 的 `params`（逐字段）。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_note_parser.py`
- 参数化 SPEC §9.2 表 7 行：`parse_note(note).values == 期望`，`warnings` 期望（只有 `20色` 那行非空）。
- 额外：`"3 colors"` → `{"max_colors": 3}`；`"色差小一点"` → `{}`（`色差` 不算颜色数）；`"AMS lite 两台"` → `{"ams_slots": 8}`；`"有 AMS"` → `{"ams_slots": 4}`；`"pla 和 petg 都行"` → `{"materials": ["PLA", "PETG"]}`；`"易生或三绿"` → `{"brands": ["sunlu", "esun"]}`（按品牌表顺序，不按出现顺序）；`"0色"` → `{}` 且 warnings `("NOTE_VALUE_OUT_OF_RANGE:max_colors=0",)`。
- `resolve_params({}, parse_note("帮我配 4 色，AMS 一台，只要拓竹 PLA")).to_dict() == result.example.json["params"]`。
- 优先级：`resolve_params({"max_colors": 2}, parse_note("4色"))` → `max_colors == 2`、`n_colors == 2`、`note_parsed == {"max_colors": 4}`。
- `resolve_params({"ams_slots": 3}, parse_note("4色")).n_colors == 3`。
- 默认：`resolve_params(None, parse_note(""))` → `Params(4, 4, 4, ("PLA",), (), True, False, 2, {})`。
- `to_dict()` 结果对 result schema 的 params 子结构校验通过（拼进 result.example 替换 params 后整体 `validate_json("result", ...) == []`）。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_note_parser.py -q
```

## 不要做
- 不要用 LLM、jieba、任何 NLP 库；只用 SPEC 里的正则。
- 不要新增可解析的键（例如"预算""颜色偏暖"）。
- 解析不了的内容静默忽略，不要报错。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
