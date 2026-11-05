# T11 — 单张商品图取色

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M1 | T09 T10 | 半天 | SPEC §8.3 |

## 目标
对一张商品图按 SPEC §8.3 取出主色（单色耗材 1 个，多色耗材最多 3 个），并给出置信度。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T09、T10 验收通过。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/extract.py`
- `tests/test_extract.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
@dataclass(frozen=True, slots=True)
class ExtractResult:
    status: Literal["ok", "no_foreground"]
    hexes: tuple[str, ...]      # no_foreground → ()
    confidence: float           # round 3；no_foreground → 0.0
    share: float                # round 3
    spread: float               # round 2
    n_pixels: int               # 采样后的像素数

MULTI_EFFECTS: tuple[str, ...] = ("multi", "dual", "tri", "gradient")
def extract_colors(path: Path, effects: Sequence[str]) -> ExtractResult: ...
    # 读图错误（ImageMissingError / ImageUnreadableError）直接向上抛，不在这里吞
```

## 输入/输出示例
| 输入（合成图） | effects | 结果 |
|---|---|---|
| `square_on_white(fg="#00AE42")` | `()` | `ExtractResult("ok", ("#00AE42",), 1.0, 1.0, 0.0, 14400)` |
| 同上 | `("silk",)` | confidence `0.6`，其余同上 |
| `blank_white()` | `()` | `ExtractResult("no_foreground", (), 0.0, 0.0, 0.0, 0)` |
| `two_tone(split=0.6)` | `("multi",)` | hexes `("#C8102E", "#00AE42")`，share `1.0`，confidence `1.0` |
| `two_tone(split=0.6)` | `()` | hexes `("#C8102E",)`，share `0.6`，confidence `0.6` |

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_extract.py`
- 上表 5 行，每行断言所有字段（`two_tone` 两行也断言 `n_pixels == 14400`）。
- `square_on_white(fg="#000000")`（黑色耗材，L=0 全部低于 SHADOW_L）→ status ok，hexes == `("#000000",)`（阴影规则不删）。
- 同一图片调用两次结果 `==`。
- 不存在的路径 → `pytest.raises(ImageMissingError)`。
- `@pytest.mark.data`：`/workspace/filament-shots/Bambu Lab/PETG_Basic/variant_00_Black.jpg`（真实商品图）→ status ok，`len(hexes) == 1`，`0.0 <= confidence <= 1.0`；不断言具体颜色。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_extract.py -q
```

## 不要做
- 不要调整 k、阈值、置信度公式或惩罚系数来让真实图片"更准"。
- 不要遍历全部商品图（T12）；不要写文件。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
