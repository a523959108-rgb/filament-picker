# T14 — 配色规划

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M2 | T09 T10 | 半天 | SPEC §9.3 |

## 目标
从用户图片规划出 n 个目标色（每个带占比），供匹配使用。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T09、T10 验收通过（`tests/helpers_images.py` 已有 `quadrants` 等）。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/palette.py`
- `tests/test_palette.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
@dataclass(frozen=True, slots=True)
class PaletteColor:
    index: int
    hex: str
    lab: tuple[float, float, float]   # round 2
    share: float                      # round 3
    def to_dict(self) -> dict[str, Any]: ...   # {"index","hex","lab"(list),"share"}

def plan_palette(path: Path, n_colors: int, keep_small: bool) -> list[PaletteColor]: ...
    # SPEC §9.3；ImageTooSmallError / NoForegroundError / 读图异常直接抛
```

## 输入/输出示例
| 输入（合成图） | n_colors, keep_small | 结果 |
|---|---|---|
| `quadrants(400)` | 4, False | `#000000`、`#C8102E`、`#00AE42`、`#FFFFFF`，share 各 0.25（同 share 按 L 升序） |
| `quadrants(400)` | 2, False | `[#000000 0.5, #C8102E 0.5]`（绿并入黑、白并入红：按 ΔE 最近） |
| `square_on_white("#00AE42")` | 4, False | `[#00AE42 1.0]` |
| 绿方块 + 中间 12×12 `#0000FF`（占前景 1%） | 4, False | 1 色，与 `#00AE42` 的 ΔE < 2（蓝色被并入，中心略偏） |
| 同上 | 4, True | 2 色：`#00AE42` 0.99、`#0000FF` 0.01 |
| `tiny(32)` | 任意 | `ImageTooSmallError` |
| `blank_white(200)` | 任意 | `NoForegroundError` |

参考：四象限颜色两两 ΔE00：黑–红 40.92、黑–绿 56.22、黑–白 100、红–绿 78.25、红–白 51.98、绿–白 38.08（均 > MERGE_DE，不会合并）。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_palette.py`（蓝块图在测试里用 Pillow 在 `square_on_white` 结果上画 `(94,94)-(105,105)` 的 12×12 区域）
- 上表 7 行，hex 与 share 逐个断言；index 从 0 连续。
- `sum(p.share for p in result) == pytest.approx(1.0, abs=0.002)`。
- 每个 `PaletteColor.lab == tuple(round(x, 2) for x in hex_to_lab(...))` 的近似（各分量差 < 0.01）——仅对纯色结果（前三行）。
- 确定性：同一图跑两次结果 `==`。
- `to_dict()` 拼进 result.example 的 palette 后 schema 校验通过。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_palette.py -q
```

## 不要做
- 不要在配色时删高光/阴影（`drop_highlights=False`，SPEC 已定）。
- 不要做"感知显著性"、边缘检测、分割模型等任何额外处理。
- 不要按色系/色名对目标色命名。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
