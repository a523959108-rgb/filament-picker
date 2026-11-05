# T16 — 色卡 PNG

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M2 | T14 T15 | 半天 | SPEC §9.6 |

## 目标
按 SPEC §9.6 的像素级版式画配色卡 PNG，并生成不可猜的文件名和公网 URL。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T14、T15 验收通过；`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` 与 `-Bold.ttc` 存在（不存在 → 停下报告）。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/card.py`
- `tests/test_card.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
CARD_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_-]{32}\.png$")
def card_height(n: int) -> int: ...                       # 40 + 120 + max(360, 140*n) + 60 + 40
def truncate(s: str, limit: int = 18) -> str: ...         # len(s) > limit → s[:limit-1] + "…"
def new_card_path(root: Path) -> Path: ...                # root/"public"/"cards"/f"{secrets.token_urlsafe(CARD_TOKEN_BYTES)}.png"
def card_url_for(card_path: Path, base_url: str | None) -> str | None: ...   # None → None；否则 base_url.rstrip("/") + "/" + card_path.name
def render_card(image_path: Path, palette: list[PaletteColor], matches: list[dict[str, Any]],
                out_path: Path, today: str) -> Path: ...
    # 字体从 get_settings() 读；mkdir parents；返回 out_path
```

## 输入/输出示例
- `card_height(4) == 820`，`card_height(1) == 620`，`card_height(2) == 620`，`card_height(3) == 620`，`card_height(5) == 960`。
- `truncate("一二三四五六七八九十一二三四五六七八九") == "一二三四五六七八九十一二三四五六七…"`（19 字 → 17 字 + …）。
- `card_url_for(Path("/x/public/cards/abc.png"), "https://cards.example.invalid/c/") == "https://cards.example.invalid/c/abc.png"`（示例域名）。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_card.py`（用 `square_on_white` 合成图 + 手写 palette/matches，不依赖真实目录）
- 上面 3 组函数断言。
- 1 色：palette `[#00AE42]`，matches 首选 hex `#25282A` → 输出 PNG 尺寸 `(1080, 620)`；像素 `(490, 230) == (0, 174, 66)`（目标块中心）；`(630, 230) == (37, 40, 42)`（首选块中心）；`(20, 20) == (255, 255, 255)`。
- 无匹配：matches `[{"target_index": 0, "picks": []}]` → `(630, 200)` 为 `(238, 238, 238)`（#EEEEEE，避开中心的「无」字）。
- 4 色 → 尺寸 `(1080, 820)`；第 i 行目标块中心 `(490, 230 + 140*i)` 等于对应目标色。
- 浅色描边：目标色 `#FFFFFF` → `(440, 200)`（块左边缘）为 `(221, 221, 221)`。
- `new_card_path(tmp_root).name` 匹配 `CARD_NAME_RE`；两次调用不同；父目录是 `tmp_root/public/cards`。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_card.py -q
```

## 不要做
- 不要改版式数字、颜色、字号、文案；不要加 logo、二维码、水印。
- 不要上传图片或启动任何 HTTP 服务（公网托管见 SPEC §14 Q1，未决）。
- 不要用 matplotlib / cairo。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
