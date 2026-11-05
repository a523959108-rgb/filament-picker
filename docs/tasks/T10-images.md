# T10 — 异常类、读图与前景掩码

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M1 | T07 | 半天 | SPEC §8.1–§8.2、§9.8 |

## 目标
定义带错误码的异常类；实现读图（EXIF 旋转、透明合成白底、HEIC）、缩放、前景掩码和阴影规则；写合成测试图工具。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T07 验收通过（掩码用 ΔE）。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/errors.py`
- `src/filament_picker/images.py`
- `tests/helpers_images.py`
- `tests/test_errors.py`、`tests/test_images.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
测试中用 `from helpers_images import quadrants, ...` 导入（`tests/` 下不建 `__init__.py`，依赖 pytest 默认的 prepend 导入模式把 `tests/` 放进 sys.path）。

```python
# errors.py
ERROR_MESSAGES: dict[str, str]          # SPEC §9.8 的 8 个 code → message_zh，逐字，按表顺序
class FPError(Exception):
    code: ClassVar[str] = "INTERNAL"
    @property
    def message_zh(self) -> str: ...    # ERROR_MESSAGES[self.code]
class InvalidRequestError(FPError):  code = "INVALID_REQUEST"
class ImageMissingError(FPError):    code = "IMAGE_MISSING"
class ImageUnreadableError(FPError): code = "IMAGE_UNREADABLE"
class ImageTooSmallError(FPError):   code = "IMAGE_TOO_SMALL"
class NoForegroundError(FPError):    code = "NO_FOREGROUND"
class NoMatchError(FPError):         code = "NO_MATCH"
class InternalError(FPError):        code = "INTERNAL"
# CATALOG_ERROR 没有对应子类：catalog.CatalogValidationError（T08）由 planner（T17）转换成这个 code。

# images.py
def load_rgb(path: Path) -> np.ndarray: ...                         # (H,W,3) uint8；SPEC §8.1
def resize_long_side(rgb: np.ndarray, long_side: int) -> np.ndarray: ...
    # Image.fromarray → thumbnail((long_side, long_side), Image.Resampling.BOX) → np.asarray；小图不放大
def foreground_mask(lab: np.ndarray, drop_highlights: bool = True) -> np.ndarray: ...  # (H,W) bool；SPEC §8.2
def apply_shadow_rule(X: np.ndarray) -> np.ndarray: ...
    # X: (n,3) Lab；keep = X[:,0] >= SHADOW_L；keep.mean() >= SHADOW_KEEP_MIN_FRAC → X[keep]，否则 X 原样
    # n == 0 → 原样返回

# tests/helpers_images.py（全部用 Pillow 画，保存为 PNG，返回路径）
def quadrants(path: Path, size: int = 400) -> Path        # 左上 #000000 右上 #FFFFFF 左下 #00AE42 右下 #C8102E
def square_on_white(path: Path, fg: str = "#00AE42", size: int = 200, inner: int = 120) -> Path
def two_tone(path: Path, left: str = "#C8102E", right: str = "#00AE42", size: int = 200, inner: int = 120, split: float = 0.6) -> Path
    # 白底居中 inner×inner 方块，方块左侧 round(inner*split) 列为 left，其余为 right
def tiny(path: Path, size: int = 32) -> Path              # 纯 #00AE42
def blank_white(path: Path, size: int = 200) -> Path
def rgba_square(path: Path, size: int = 200) -> Path      # 透明底 (0,0,0,0) + 居中 120×120 不透明 #00AE42
```

## 输入/输出示例
- `load_rgb(rgba_square(...))[0, 0].tolist() == [255, 255, 255]`（透明合成白底），中心像素 `[0, 174, 66]`。
- `square_on_white` 200×200 → `foreground_mask(...)` 为 True 的像素正好 `120*120 = 14400` 个。
- `quadrants` 400×400：边框四色各约 1/4，不满足 60% 一致，不去背景；`drop_highlights=True` 时白色象限被删，掩码均值 0.75；`False` 时 1.0。
（全部是合成图，非真实照片）

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_errors.py`
- `len(ERROR_MESSAGES) == 8`，键顺序 == SPEC §9.8 表顺序；每条文案逐字比对（参数化 8 行）。
- 7 个子类：`issubclass(X, FPError)`；`ImageTooSmallError().code == "IMAGE_TOO_SMALL"`；`ImageTooSmallError().message_zh == "图片太小了，请发原图。"`。
- `"CATALOG_ERROR" in ERROR_MESSAGES`，且没有名为 `CatalogError` 的类。

`tests/test_images.py`
- RGBA：如上两条像素断言。
- `load_rgb(tmp_path/"nope.png")` → `ImageMissingError`；写入 `b"not an image"` 的 `x.png` → `ImageUnreadableError`。
- EXIF：Pillow 画 300 宽 × 200 高的 JPEG，`exif[0x0112] = 6` 保存；`load_rgb(...).shape == (300, 200, 3)`。
- `resize_long_side(np.zeros((1000, 500, 3), np.uint8), 256).shape == (256, 128, 3)`；`resize_long_side(np.zeros((100, 50, 3), np.uint8), 256).shape == (100, 50, 3)`。
- 方块：`foreground_mask(rgb_to_lab(load_rgb(square_on_white(...)))).sum() == 14400`。
- 四象限：`foreground_mask(lab).mean() == pytest.approx(0.75, abs=0.005)`；`foreground_mask(lab, drop_highlights=False).mean() == 1.0`。
- 空白图：`foreground_mask(lab).sum() == 0`。
- 阴影：`X = 90 行 L=50 + 10 行 L=5` → `apply_shadow_rule(X).shape == (90, 3)`；`X = 100 行 L=2`（黑色耗材）→ 原样 100 行；`X = 10 行 L=50 + 90 行 L=5`（keep 比例 0.10 < 0.15）→ 原样 100 行；空数组 → 空数组。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_errors.py tests/test_images.py -q
```

## 不要做
- 不要在测试里使用 `/workspace/filament-shots/` 的真实图片（真实图片只在 T12 用）。
- 不要新增错误码或改文案；不要给 `CatalogValidationError` 改父类。
- 不要实现取色（T11）或配色（T14）。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
