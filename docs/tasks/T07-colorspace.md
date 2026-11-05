# T07 — 颜色空间与 CIEDE2000

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M0 | T01 | 半天 | SPEC §6 |

## 目标
实现 sRGB↔Lab（D65）和向量化 CIEDE2000。之后取色、配色、匹配、目录 lab 字段全部依赖这两个模块。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T01 验收通过。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/colorspace.py`、`src/filament_picker/ciede2000.py`
- `tests/test_colorspace.py`、`tests/test_ciede2000.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
# colorspace.py
HEX_RE: re.Pattern[str] = re.compile(r"^#[0-9A-Fa-f]{6}$")
def hex_to_rgb(h: str) -> tuple[int, int, int]: ...      # 不匹配 HEX_RE → ValueError
def rgb_to_hex(rgb: Sequence[int]) -> str: ...           # 大写 "#RRGGBB"；分量不在 0–255 → ValueError
def rgb_to_lab(rgb: np.ndarray) -> np.ndarray: ...       # (...,3) 任意整数/uint8 → (...,3) float64
def lab_to_rgb(lab: np.ndarray) -> np.ndarray: ...       # (...,3) → (...,3) uint8（clip 后 round）
def hex_to_lab(h: str) -> tuple[float, float, float]: ...
def lab_to_hex(lab: Sequence[float] | np.ndarray) -> str: ...

# ciede2000.py
def delta_e_2000(lab1: ArrayLike, lab2: ArrayLike) -> np.ndarray: ...
    # 支持广播；返回 float64 ndarray（输入两个 (3,) 时返回 0 维数组，用 float() 取值）
```

## 输入/输出示例
SPEC §6.1 的 6 行 Lab 表、§6.2 的 8 行 Sharma 表（全部可直接写成参数化测试）。
另：`float(delta_e_2000(hex_to_lab("#000000"), hex_to_lab("#272729")))` ≈ 9.7548（Bambu 官方黑 vs eSUN 店铺黑，真实色值）。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_colorspace.py`
- 6 行表：`hex_to_lab(h)` 每个分量 `abs(x - 期望) < 0.02`。
- 往返：6 个 hex 都 `lab_to_hex(hex_to_lab(h)) == h`。
- `hex_to_rgb("#00AE42") == (0, 174, 66)`；`hex_to_rgb("#00ae42") == (0, 174, 66)`；`rgb_to_hex((0, 174, 66)) == "#00AE42"`。
- `hex_to_rgb("00AE42")`、`hex_to_rgb("#00AE4")` → ValueError；`rgb_to_hex((256,0,0))` → ValueError。
- `rgb_to_lab(np.zeros((2,3,3), np.uint8)).shape == (2,3,3)`。
- 随机 1000 个 RGB（`default_rng(0)`）：`lab_to_rgb(rgb_to_lab(x))` 与 x 每分量差 ≤ 1。

`tests/test_ciede2000.py`
- Sharma 8 对：`abs(float(delta_e_2000(a, b)) - 期望) < 1e-4`。
- 对称：8 对反过来算结果相同（差 < 1e-9）；`delta_e_2000(x, x) == 0`。
- 广播：`delta_e_2000(np.array(8 个 lab1), np.array(lab2_0)).shape == (8,)`；`(8,3)` 对 `(8,3)` → `(8,)`，且逐项等于单独计算。
- `abs(float(delta_e_2000(hex_to_lab("#000000"), hex_to_lab("#272729"))) - 9.7548) < 1e-3`。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_colorspace.py tests/test_ciede2000.py -q
```

## 不要做
- 不要引入 colour-science、scikit-image、opencv 等任何库；只用 numpy。
- 不要换白点、不要换矩阵、不要用 CIE76/CIE94 代替。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
