# filament-picker 实现规格 SPEC（v0.3，给 Codex 执行）

> 对应 PRD：「耗材选色站 PRD v0.3」Page 中的「实现规格（给 Codex 执行）」章节。本文件是仓库内的**唯一权威版本**；Page 是它的摘要。
> 编写日期：2026-11-05（Asia/Tokyo）。所有数字示例均来自 `/workspace/fil/page_rows.json`（sha256 `510566fc…63c61`）的真实行，或明确标注「示例」。
> 标「待校准」的阈值是初始值：Codex **照抄，不准改**；由人看校准报告后决定是否调整。

## 0. 阅读顺序与优先级
1. `docs/AGENTS.md` — 行为规则。
2. 本文件 — 技术决策、数据结构、算法。
3. `docs/tasks/Txx-*.md` — 单个任务。任务文件与本文件冲突时，**停下来报告**，不要自己选。
4. `docs/schemas/*.schema.json` — JSON 结构的权威定义；`docs/schemas/examples/` 是通过校验的样例。
5. `docs/fixtures/` — 由参考实现在真实数据上算出的金标答案（`ids_golden.json` 35 行、`merges_golden.json` 全部 24 处合并、`web-catalog.sample.json` = 4 个示例条目的 export-web 结果）。

## 1. 系统概览
```
page_rows.json (3845 行) ─┐
inventory.json (313 系列) ─┼─ M0: ingest → names/slug/effects → ids(去重+锁定) ─┐
filament-shots/*.jpg ──────┘                                                   │
                                   M1: extract(商品图取色) → calibrate/qa ──────┤
                                                                               ▼
                                              data/build/filament-catalog.json（3821 条）
                                                     │                    │
          钉钉监听器(已部署) → inbox/<msgId>.<ext>     │                    │ M3: export-web
          钉钉助手 → inbox/<id>.request.json           ▼                    ▼
                       M2: worker → palette → matcher → card + reply   web/(Vite+React) + api.py
                            → outbox/<id>.json + public/cards/<token>.png
          钉钉助手读 outbox → sampleMarkdown 回复（图片用 card_url 链接）
```
- 收图：**已打通（离线测试通过，待真机实测）**。监听器 `/home/box/.local/share/dingtalk-listener/listener.py` 收到 picture / richText 时把图存到 `inbox/<msgId>.<ext>`（多图 `<msgId>_1.<ext>`、`<msgId>_2.<ext>`…），转发给钉钉助手的 JSON 带 `image_paths`（失败时带 `image_error`）。msgId 先经 `re.sub(r"[^A-Za-z0-9_.=+-]", "_", msgId)` 清洗。
- 回图：钉钉助手只能发 sampleMarkdown → 色卡 PNG 放在公网可访问的长随机路径，Markdown 里用 `![配色卡](card_url)` 引用；文件 7 天后清理。
- 本仓库**不**包含、不调用任何钉钉代码。worker 只读写共享目录。

## 2. 技术栈（全部锁定，不准改）
### 2.1 Python
- Python **3.11**（`.python-version` 内容为 `3.11`）。盒子上 3.11 由 uv 提供：`/home/box/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11`。
- 建环境命令（固定）：`uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -e '.[dev]'`。
- 运行依赖（`pyproject.toml` `[project] dependencies`，`==` 精确锁定）：

| 包 | 版本 | 用途 | 引入任务 |
|---|---|---|---|
| numpy | 2.4.6 | 数组、k-means、ΔE（2.5.x 需要 Python ≥3.12，禁用） | T01 |
| pillow | 13.0.0 | 读图、缩放、画色卡 | T01 |
| pillow-heif | 1.8.1 | 读 HEIC（钉钉 iPhone 图） | T01 |
| pypinyin | 0.55.0 | 中文转拼音（slug、搜索） | T01 |
| jsonschema | 4.26.0 | 校验 4 个 JSON 结构 | T01 |
| fastapi | 0.162.0 | M3 `/api/plan` | T01（一次写全） |
| uvicorn | 0.54.0 | M3 服务 | T01 |
| python-multipart | 0.0.20 | FastAPI 上传表单 | T01 |

- 开发依赖（`[project.optional-dependencies] dev`）：pytest 9.2.0、ruff 0.17.3、httpx 0.28.1（FastAPI TestClient）。
- **不使用**：scikit-learn、scipy、opencv、colour-science、pydantic（FastAPI 自带的除外）、click/typer（CLI 用 argparse）、requests。
- k-means、sRGB↔Lab、CIEDE2000 **自己用 numpy 写**（SPEC §6、§7）。

> 已验证（2026-11-05）：用本节 pyproject 在盒子上 `uv venv --python 3.11` + `uv pip install -e '.[dev]'` 安装成功（Python 3.11.18）。若将来安装失败，T01 停下报告，不要换版本。

### 2.2 前端（`web/`）
- Node 24.x / npm 11.x；`package-lock.json` 提交。
- dependencies：react 19.3.1、react-dom 19.3.1、culori 4.0.2、minisearch 7.2.0。
- devDependencies：vite 7.3.7、@vitejs/plugin-react 5.2.0、typescript 5.9.3、vitest 4.1.12、jsdom 30.1.3、@testing-library/react 16.3.3、@types/react 19.3.0、@types/react-dom 19.3.0、@types/culori 4.0.1。
- 以上组合已于 2026-11-05 在盒子上 `npm install` 验证可装，`vitest --version` = 4.1.12，`tsc --version` = 5.9.3，`vite --version` = 7.3.7。
- **不用路由库**：两页用 `location.hash`（`#/` 色卡、`#/plan` 图片配色）自己切换。不用 UI 库、不用 CSS 框架，手写 CSS（`web/src/styles.css`）。
- 拼音在 Python 侧预计算好写进 `web-catalog.json`，前端不装拼音库。

### 2.3 pyproject.toml（T01 逐字写入）
```toml
[build-system]
requires = ["setuptools==80.9.0"]
build-backend = "setuptools.build_meta"

[project]
name = "filament-picker"
version = "0.3.0"
requires-python = ">=3.11,<3.12"
dependencies = [
  "numpy==2.4.6",
  "pillow==13.0.0",
  "pillow-heif==1.8.1",
  "pypinyin==0.55.0",
  "jsonschema==4.26.0",
  "fastapi==0.162.0",
  "uvicorn==0.54.0",
  "python-multipart==0.0.20",
]

[project.optional-dependencies]
dev = ["pytest==9.2.0", "ruff==0.17.3", "httpx==0.28.1"]

[project.scripts]
filament-picker = "filament_picker.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
filament_picker = ["schemas/*.json"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = ["data: 需要 data/raw 或 /workspace/filament-shots 的真实数据"]

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests"]
extend-exclude = ["docs"]  # docs/ 里 Markdown 的代码块是示意，不参与 ruff 检查/格式化

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM", "RUF"]
ignore = ["RUF001", "RUF002", "RUF003"]  # 允许中文全角标点出现在字符串/注释里
```

### 2.4 环境变量（只有这些）
| 变量 | 默认值 | 说明 |
|---|---|---|
| `FP_ROOT` | `/home/box/agent-data/shared/filament-picker` | 共享目录根 |
| `FP_CATALOG` | `<repo>/data/build/filament-catalog.json` | worker/api 读取的目录 |
| `FP_CARD_BASE_URL` | 未设置 | 例 `https://cards.example.invalid/c`（示例）。未设置 → `card_url = null`，回复不带图 |
| `FP_SHOTS_DIR` | `/workspace/filament-shots` | 商品图根目录 |
| `FP_FONT_REGULAR` | `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` | 已确认存在 |
| `FP_FONT_BOLD` | `/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc` | 已确认存在 |
| `FP_FONT_INDEX` | `2` | TTC 第 2 个字形 = Noto Sans CJK **SC**（已用 Pillow 验证 Regular/Bold 均是） |

`<repo>` = `Path(__file__).resolve().parents[2]`（即 `src/filament_picker/config.py` 往上两级）。

## 3. 目录树（最终形态；每个文件归属哪个任务见 §12）
```
filament-picker/
├── AGENTS.md                      # = docs/AGENTS.md 的副本（T01）
├── README.md                      # T01：一段话 + 常用命令
├── pyproject.toml                 # T01
├── .python-version                # T01：3.11
├── .gitignore                     # T01：.venv/ web/node_modules/ web/dist/ data/build/ data/extracted/ data/qa/ __pycache__/ .pytest_cache/ .ruff_cache/
├── docs/                          # 需求（只读）
│   ├── AGENTS.md  SPEC.md
│   ├── tasks/T01-*.md … T25-*.md
│   ├── schemas/{filament-catalog,ids.lock,request,result}.schema.json + examples/
│   └── fixtures/{ids_golden,merges_golden,web-catalog.sample}.json
├── src/filament_picker/
│   ├── __init__.py                # T01：__version__ = "0.3.0"
│   ├── config.py                  # T01：路径、环境变量、全部数值常量（§4）
│   ├── schemas/*.schema.json      # T01：docs/schemas 的逐字节副本
│   ├── validate.py                # T01：load_schema / validate_json
│   ├── errors.py                  # T10：带 code 的异常类（§9.8）
│   ├── ingest.py                  # T02
│   ├── names.py                   # T03
│   ├── slug.py  brands.py         # T04
│   ├── effects.py                 # T05
│   ├── ids.py                     # T06
│   ├── colorspace.py  ciede2000.py# T07
│   ├── variants.py  catalog.py    # T08（catalog.py 由 T12 扩展）
│   ├── kmeans.py                  # T09
│   ├── images.py                  # T10
│   ├── extract.py                 # T11
│   ├── calibrate.py               # T12
│   ├── note_parser.py             # T13
│   ├── palette.py                 # T14
│   ├── matcher.py                 # T15
│   ├── card.py                    # T16
│   ├── reply.py  planner.py       # T17
│   ├── worker.py                  # T18
│   ├── web_export.py              # T20
│   ├── api.py                     # T23
│   ├── server.py                  # T25：API + web/dist 静态文件
│   └── cli.py                     # T01 建骨架，之后各任务只"新增子命令"
├── tests/
│   ├── conftest.py                # T01：repo_root / raw_rows / tmp_root fixtures
│   ├── helpers_images.py          # T10：合成测试图（纯 Pillow 绘制）
│   └── test_*.py                  # 各任务
├── data/
│   ├── raw/page_rows.json         # T02：从 /workspace/fil/ 复制，sha256 必须相符
│   ├── raw/inventory.json         # T02：从 /workspace/filament-shots/ 复制
│   ├── raw/SHA256SUMS             # T02
│   ├── ids.lock.json              # T06 生成并提交
│   ├── manual_overrides.json      # T08：初始 {"schema_version":1,"hex":{},"store_swatch_confidence":{}}
│   ├── build/                     # 生成物，不提交
│   ├── extracted/                 # T12 生成物，不提交
│   └── qa/                        # T12 生成物，不提交
├── scripts/run_worker.sh          # T18
├── scripts/smoke_worker.sh        # T19
├── scripts/build_web.sh           # T25
└── web/                           # T20–T25
    ├── package.json  package-lock.json  tsconfig.json  vite.config.ts  index.html
    ├── public/web-catalog.json    # T20 由 export-web 生成，不提交
    └── src/{main.tsx,App.tsx,config.ts,types.ts,catalog.ts,search.ts,color.ts,api.ts,styles.css}
        src/components/{SwatchGrid,Filters,ColorDetail,CompareBar,PlanPage}.tsx
        src/__tests__/*.test.ts(x)
```

## 4. 常量（`config.py` 逐字定义；前端用到的在 `web/src/config.ts` 同名同值）
| 常量 | 值 | 说明 | 状态 |
|---|---|---|---|
| `TZ` | `"Asia/Tokyo"` | | 锁定 |
| `MAX_SLUG_LEN` | `60` | 单段 slug 最长 | 锁定 |
| `HEX_CONF_OFFICIAL` | `1.0` | | 锁定 |
| `HEX_CONF_STORE_SWATCH` | `0.8` | 可被 manual_overrides 按品牌覆盖 | 待校准 |
| `HEX_CONF_MANUAL` | `0.9` | | 待校准 |
| `SOURCE_RANK` | `{"official":0,"store_swatch":1,"manual":2,"image_extracted":3}` | 排序用 | 锁定 |
| `EXTRACT_LONG_SIDE` | `256` | 取色缩放长边 | 锁定 |
| `BORDER_PX` | `4` | 背景估计边框宽 | 锁定 |
| `BG_BORDER_AGREE_DE` | `10.0` | 边框像素与中位数 ΔE<此值算"一致" | 待校准 |
| `BG_BORDER_AGREE_FRAC` | `0.60` | 一致比例 ≥ 此值才认为有纯背景 | 待校准 |
| `BG_REMOVE_DE` | `12.0` | 与背景 ΔE< 此值的像素删除 | 待校准 |
| `HIGHLIGHT_L` / `HIGHLIGHT_C` | `92.0` / `10.0` | L>92 且 C<10 视为高光删除 | 待校准 |
| `SHADOW_L` | `8.0` | L<8 视为阴影删除… | 待校准 |
| `SHADOW_KEEP_MIN_FRAC` | `0.15` | …但删后剩余 <15% 时不删（黑色耗材） | 待校准 |
| `MIN_PIXELS` | `500` | 前景像素下限 | 锁定 |
| `MAX_SAMPLE` | `20000` | 取色采样上限 | 锁定 |
| `EXTRACT_K_SINGLE` | `3` | 单色耗材 k | 待校准 |
| `EXTRACT_K_MULTI` | `6` | 多色耗材 k | 待校准 |
| `MULTI_MIN_SHARE` / `MULTI_MAX_COLORS` | `0.15` / `3` | | 待校准 |
| `CONF_SPREAD_DE` | `10.0` | 置信度公式中 ΔE 归一化分母 | 待校准 |
| `CONF_PENALTY_EFFECTS` / `CONF_PENALTY_FACTOR` | `("silk","translucent","glow","sparkle")` / `0.6` | 含这些效果时 conf × 0.6 | 待校准 |
| `EXTRACT_MIN_CONF` | `0.40` | 低于此值不写入目录 hex | 待校准 |
| `KMEANS_MAX_ITER` / `KMEANS_TOL` | `20` / `0.01` | | 锁定 |
| `PLAN_LONG_SIDE` | `512` | 配色缩放长边 | 锁定 |
| `PLAN_MAX_SAMPLE` | `40000` | | 锁定 |
| `PLAN_MIN_SIDE` | `64` | 原图短边 <64 → IMAGE_TOO_SMALL | 锁定 |
| `DEFAULT_MAX_COLORS` / `DEFAULT_AMS_SLOTS` | `4` / `4` | | 锁定 |
| `DEFAULT_PER_COLOR` | `2` | | 锁定 |
| `DEFAULT_MATERIALS` | `("PLA",)` | | 锁定 |
| `MERGE_DE` | `6.0` | 调色板聚类合并阈值 | 待校准 |
| `SMALL_SHARE` | `0.02` | 小色块并入阈值 | 待校准 |
| `MATCH_MAX_DE` | `10.0` | 推荐 ΔE 上限 | 待校准 |
| `MATCH_MIN_CONF` | `0.5` | 非官方色参与推荐的最低置信度 | 待校准 |
| `LABEL_THRESHOLDS` | `((2.0,"几乎一样"),(5.0,"接近"),(10.0,"勉强"))` | ΔE < 2 / < 5 / ≤ 10 | 待校准 |
| `MATCH_EXCLUDE_EFFECTS` | `("multi","dual","tri","gradient","color_change","translucent","glow","sparkle","marble","wood")` | | 锁定 |
| `WORKER_POLL_S` | `1.0` | | 锁定 |
| `CLEANUP_INTERVAL_S` / `RETENTION_DAYS` | `3600` / `7` | | 锁定 |
| `CARD_TOKEN_BYTES` | `24` | `secrets.token_urlsafe(24)` → 32 字符 | 锁定 |

## 5. M0 数据与 ID
### 5.1 输入
`page_rows.json`：数组，3845 个对象，每个对象恰好 8 个键：

| 键 | 含义 | 类型 | 真实例 |
|---|---|---|---|
| `b` | 品牌显示名（21 种，见 §5.4） | str | `"Bambu Lab"` |
| `s` | 系列名（318 个品牌+系列组合） | str | `"PETG Basic"` |
| `p` | 价格文本，可能为空串 | str | `"¥2,800 JPY"` |
| `ch` | 渠道说明 | str | `"Bambu Lab 日本官方商城"` |
| `u` | 购买链接 | str | `"https://jp.store.bambulab.com/products/petg-basic"` |
| `c` | 颜色原名（中英混排、可能含色号/重量） | str | `"Black 黑色 (30105)"` |
| `f` | 色系（15 种，见 schema enum） | str | `"黑白灰"` |
| `h` | hex 列表，**不带 #**，长度 0/1/2/4（3245/582/17/1 行） | list[str] | `["000000"]` |

`inventory.json`：dict；本项目只用 `series` 数组（313 项），每项用到 `brand`、`series`、`variant_image_paths`（绝对路径列表，例 `/workspace/filament-shots/Bambu Lab/PETG_Basic/variant_00_Black.jpg`）。
`data/raw/SHA256SUMS`（T02 写入，`sha256sum` 格式）：
```
510566fc490559f6ccd4eaf347f05f61b41ea557fc7c99a4d8ba55f6fed63c61  page_rows.json
b6a775ea341a7a5acfda4a918dd2737281fffe4b56bebb6c86ee6c26aec481cd  inventory.json
```

### 5.2 规范化 `nfkc(s)`
```
nfkc(s) = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()
```
（全角括号 `（）` 经 NFKC 变成 `()`；这一步之后的所有正则都假设半角。）

### 5.3 颜色名解析 `parse_color_name(raw) -> ParsedName(name_en, name_zh, code)`
正则（逐字使用；`CJK = "\u3400-\u9fff"`）：
```python
WEIGHT = re.compile(r"\s*[-/]?\s*\d+(?:\.\d+)?\s*kg\b", re.I)
PCODE  = re.compile(r"\s*\((\d{4,6})\)\s*$")
TCODE  = re.compile(r"(?<=\s)([A-Z]{1,4}\d{2,5}[A-Z]?)\s*$")
ZH     = re.compile(r"[\u3400-\u9fff](?:[\u3400-\u9fff\-·]*[\u3400-\u9fff])?")
```
伪代码：
```
s = nfkc(raw)
s = WEIGHT.sub("", s).strip()
code = None
if m := PCODE.search(s):   code = m[1]; s = s[:m.start()].strip()
elif m := TCODE.search(s): code = m[1]; s = s[:m.start()].strip()
name_zh = " ".join(ZH.findall(s)) or None
en = ZH.sub(" ", s)
en = re.sub(r"\(\s*\)", "", en)
en = re.sub(r"\s+", " ", en).strip(" -/")
if m := re.fullmatch(r"\((.*)\)", en): en = m[1].strip()
name_en = en or None
```
真实例（全部来自 page_rows，参考实现已验证）：

| raw | name_en | name_zh | code |
|---|---|---|---|
| `Black 黑色 (30105)` | `Black` | `黑色` | `30105` |
| `UV Color Changing - White to Coral 光变-白变粉 (15100)` | `UV Color Changing - White to Coral` | `光变-白变粉` | `15100` |
| `樱花粉（Sakura Bloom）` | `Sakura Bloom` | `樱花粉` | null |
| `Black Walmut ATM2469 / 1KG` | `Black Walmut` | null | `ATM2469` |
| `Blue&Green-3KG` | `Blue&Green` | null | null |
| `竹 RB009` | null | `竹` | `RB009` |
| `菠菜绿` | null | `菠菜绿` | null |
| `Dual Silk Aubergine (Lime-Magenta)` | `Dual Silk Aubergine (Lime-Magenta)` | null | null |
| `Purple/Blue Green/Burnt Orange 1KG` | `Purple/Blue Green/Burnt Orange` | null | null |
| `Blue&Green&Gold Z007` | `Blue&Green&Gold` | null | `Z007` |

统计（验收用）：有 code 的行 = **467**（bambu-lab 246 行全为 5 位数字；cailab 221 行全为字母+数字，前缀 RB 40、AC 33、G 30、MT 25、SP 24、AS 18、Z 15、SAN 13、ATM 8、BS 4、SS 4、GM 4、GCF/Y/YRB 各 1）。

### 5.4 slug 与品牌表
```
slug(s, maxlen=60):
    s = nfkc(s).lower()
    s = "".join("-" + lazy_pinyin(ch)[0] + "-" if re.match(r"[\u3400-\u9fff]", ch) else ch for ch in s)
    s = s.replace("&", "-").replace("+", "-plus-")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > maxlen: s = s[:maxlen].rsplit("-", 1)[0]
    return s
```
`lazy_pinyin` 用默认参数（无声调，ü 写作 `v`，例 `绿 → lv`）。例：`slug("PLA+ 2.0") = "pla-plus-2-0"`，`slug("菠菜绿") = "bo-cai-lv"`，`slug("Blue&Green") = "blue-green"`。

品牌 slug **查表，不计算**（`brands.py` 的 `BRAND_SLUGS`，21 项，键为 `b` 原文）：

| b | slug | 别名（note_parser 用，§9.2） |
|---|---|---|
| Bambu Lab | bambu-lab | 拓竹, bambu, bambulab |
| Polymaker | polymaker | polymaker |
| Eryone | eryone | eryone |
| SUNLU | sunlu | sunlu, 三绿 |
| Overture | overture | overture |
| 彩多屋 CaiLab | cailab | 彩多屋, cailab |
| Elegoo | elegoo | elegoo, 爱乐酷 |
| Hatchbox | hatchbox | hatchbox |
| Kexcelled | kexcelled | kexcelled |
| eSUN | esun | esun, 易生 |
| Anycubic | anycubic | anycubic, 纵维 |
| Proto-pasta | proto-pasta | proto-pasta, protopasta |
| Amolen | amolen | amolen |
| Atomic Filament | atomic-filament | atomic |
| Creality | creality | creality, 创想 |
| Jayo | jayo | jayo |
| 阿米阿米/RMERME | rmerme | 阿米阿米, rmerme |
| Prusament | prusament | prusament, prusa |
| 天瑞 Tinmorry/Tronhoo | tinmorry | 天瑞, tinmorry, tronhoo |
| 彩格 | caige | 彩格 |
| 没毛病/ByeHassle | byehassle | 没毛病, byehassle |

遇到表外品牌 → `brands.brand_slug(b)` 抛 `UnknownBrandError(b)`（`ids.build_row_infos` 调用时自然抛出），不准自动生成。

### 5.5 系列 slug 与颜色段
```
series_clean(s) = re.sub(r"\s*\(拼多多\)\s*$", "", nfkc(s)).strip()
series_slug     = slug(series_clean(s))
color_segment(p, raw):
    base = slug(p.name_en) if p.name_en else (slug(p.name_zh) if p.name_zh else "")
    if p.code: base = (base + "-" if base else "") + slug(p.code)
    return base or "x" + sha1(raw.encode("utf-8")).hexdigest()[:8]
row_id = f"{brand_slug}/{series_slug}/{color_segment}"
```
例：`PLA哑光（拼多多）` → `pla-ya-guang`；`彩虹丝绸 PLA（RB 系列）` → `cai-hong-si-chou-pla-rb-xi-lie`。
真实 ID 例：`bambu-lab/petg-basic/black-30105`、`bambu-lab/pla-dynamic/uv-color-changing-white-to-coral-15100`、`byehassle/pla-ya-guang/sakura-bloom`、`cailab/pla-metallic/black-walmut-atm2469`、`tinmorry/pla-ya-guang/bo-cai-lv`、`amolen/pla-silk-triple-color/purple-blue-green-burnt-orange`。
全量最长 ID 108 字符；sha1 兜底在真实数据中**从未触发**。

### 5.6 去重
```
dedup_key = f"{brand_slug}|code|{code}"                    if code
          = f"{brand_slug}|{series_slug}|{slug(name_en or name_zh or raw)}"   otherwise
```
同 key 的行合并为一个条目。canonical 行（决定 ID 与显示字段）：
```
sorted(group, key=lambda r: (0 if r.h else 1,
                             1 if any(w in r.ch for w in ("淘宝","拼多多","天猫")) else 0,
                             r.row_index))[0]
```
合并规则：`hex` = canonical 的 h，若为空取组内第一个非空 h；`offers` = 组内按 row_index 顺序的 `{channel: ch, url: u, price_text: p or None}`，完全相同的去重；`aliases` = 组内其他行的 `c` 去重排序；`source_rows` = 组内 row_index 升序。
**验收数字**：3845 行 → **3821** 条，合并 24 处（全部见 `docs/fixtures/merges_golden.json`：CaiLab RB001–RB021（缺 RB012）共 20 处 + Z007 + Z013 海外官网行与淘宝行合并；Eryone `Red&Blue`/`Red&Blue-3KG`、`Blue&Green`/`Blue&Green-3KG`），**ID 冲突 0**。例：`竹 RB009`（淘宝）与 `Bamboo RB009`（海外官网）合并为 `cailab/rainbow-shift-pla/bamboo-rb009`。

### 5.7 ID 锁定（`data/ids.lock.json`，schema 见 `ids.lock.schema.json`）
```
assign_ids(groups, lock, today):
    for key, group in groups:
        if key in lock.entries:            # 已锁：ID 永不改变
            e = lock.entries[key]; e.status = "active"; e.last_seen = today
        else:
            new_id = canonical(group).row_id
            if new_id in {e.id for e in lock.entries.values()}:
                raise IdCollisionError(key, new_id)      # 不准自动加后缀
            lock.entries[key] = {id: new_id, status: "active", first_seen: today, last_seen: today}
    for key not in groups: lock.entries[key].status = "retired"   # 不删除
    lock.updated_at = today; lock.source_sha256 = sha256(page_rows.json)
```
写出时 entries 按 key 字典序、`indent=2`。同一输入跑两次结果逐字节相同（`--today` 相同时）。

### 5.8 效果（effects）与材料
匹配文本 `t = nfkc(s + " " + c).lower()`（系列名 + 颜色原名）。按下表**顺序**检查，命中即加入（不去重以外的处理）：

| effect | 正则（`re.search`） |
|---|---|
| matte | `matte\|哑光\|磨砂` |
| silk | `silk\|丝绸\|丝光` |
| dual | `\bdual\b\|双色` |
| tri | `tri-?colou?r\|triple\|三色` |
| gradient | `gradient\|rainbow\|渐变\|彩虹` |
| glow | `glow\|夜光` |
| translucent | `translucent\|transparent\|\bclear\b\|透明` |
| metallic | `metal\|金属` |
| sparkle | `sparkl\|glitter\|galaxy\|starry\|twinkl\|estars\|闪\|星空` |
| wood | `\bwood\|木纹\|木质` |
| marble | `marble\|大理石` |
| cf | `\bcf\b\|carbon fib\|碳纤` |
| gf | `\bgf\b\|glass fib\|玻纤` |
| color_change | `colou?r[ -]?chang\|变色\|光变\|温变` |
| multi | 当 `f == "多色/渐变"` 时追加 |

验收计数（按行，3845 行）：multi 610、matte 597、silk 592、gradient 250、translucent 246、dual 156、sparkle 137、metallic 107、cf 96、glow 75、tri 59、wood 56、marble 29、gf 28、color_change 5；无任何 effect 的行 1772。
材料：`"PETG" in s.upper()` → `PETG`，否则 `PLA`。按行：PLA 3083 / PETG 762；按条目：PLA 3059 / PETG 762。

### 5.9 hex 来源
- `h` 非空：`hex = ["#" + v.upper() for v in h]`；`brand_slug == "bambu-lab"` → `official`（置信度 1.0），否则 `store_swatch`（置信度 = `manual_overrides.store_swatch_confidence.get(brand_slug, 0.8)`）。
- `h` 为空且 M1 取色成功且 confidence ≥ `EXTRACT_MIN_CONF` → `image_extracted`，置信度 = confidence。
- `manual_overrides.hex[id]` 存在 → 覆盖为 `manual`（`{"hex":["#RRGGBB"],"note":"..."}`），置信度 0.9。优先级：manual > official > store_swatch > image_extracted。
- `lab` = `hex[0]` 的 Lab（§6），保留 2 位小数；无 hex 时 null。
- 条目统计（M0 结束时）：official 246、store_swatch 354、无 hex 3221（其中有商品图可取色 2101，无图 1120）。

### 5.10 拼音字段
```
cjk_only = re.sub(r"[^\u3400-\u9fff]", "", name_zh)
pinyin = " ".join(lazy_pinyin(cjk_only))          # "樱花粉" → "ying hua fen"
pinyin_initials = "".join(x[0] for x in lazy_pinyin(cjk_only))   # → "yhf"
```
name_zh 为 null → 两者均 null。

### 5.11 商品图匹配（`variants.py`：`build_variant_index` / `find_variant_image`）
```
VARIANT_RE = re.compile(r"^variant_(\d{2,3})_(.+)\.(jpg|jpeg|png|webp)$", re.I)
norm_key(s) = re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", nfkc(s).lower())
index[(brand, series)] = {norm_key(m[2]): path  for path in variant_image_paths if (m := VARIANT_RE.match(basename(path)))}   # 同 key 保留第一个
find(row): 依次尝试 norm_key(c)、norm_key(name_en)、norm_key(name_en + " " + code)，第一个命中的 path；都不中 → None
```
（Bambu 的图名是 `variant_00_Black.jpg`，行名是 `Black 黑色 (30105)`，所以必须用 name_en 再试一次。）
验收：有商品图的行 = **2457**（其中 bambu-lab 43 行；无 hex 的 2101 行）。合并条目取 canonical 行的图，没有则取组内第一张。

### 5.12 目录组装（`catalog.build_catalog`）
字段顺序与 `filament-catalog.schema.json` 的 required 顺序一致；`entries` 按 `id` 字典序；`brands` 按 §5.4 表顺序；`counts` 按实际计算。写出后必须用 schema 校验通过，否则抛 `CatalogValidationError`。

## 6. 颜色空间与 CIEDE2000（`colorspace.py`、`ciede2000.py`）
### 6.1 sRGB → Lab（D65，2°）
```
c = rgb / 255.0                                   # shape (...,3) float64
c_lin = where(c <= 0.04045, c/12.92, ((c+0.055)/1.055) ** 2.4)
M = [[0.4124564, 0.3575761, 0.1804375],
     [0.2126729, 0.7151522, 0.0721750],
     [0.0193339, 0.1191920, 0.9503041]]
xyz = c_lin @ M.T
t = xyz / [0.95047, 1.0, 1.08883]
eps = 216/24389 ; kappa = 24389/27
f = where(t > eps, cbrt(t), (kappa*t + 16)/116)
L = 116*f_y - 16 ; a = 500*(f_x - f_y) ; b = 200*(f_y - f_z)
```
Lab → sRGB：上式逆运算（`t = f**3 if f**3 > eps else (116f-16)/kappa`，`M` 的逆矩阵用 `numpy.linalg.inv(M)`，gamma 逆：`c<=0.0031308 → 12.92c，否则 1.055c^(1/2.4)-0.055`），结果 `clip(0,1)`，`round(c*255)` 转整数。
`hex_to_rgb("#00AE42") -> (0,174,66)`；`rgb_to_hex((0,174,66)) -> "#00AE42"`（大写）。
测试向量（本公式在盒子上计算，容差 0.02）：

| hex | L | a | b |
|---|---|---|---|
| #000000 | 0.00 | 0.00 | 0.00 |
| #FFFFFF | 100.00 | 0.00 | 0.00 |
| #FF0000 | 53.24 | 80.09 | 67.20 |
| #00AE42（Bambu Green 10501 官方色） | 62.22 | -60.41 | 43.97 |
| #272729（eSUN PETG-Basic Black 店铺色） | 15.71 | 0.49 | -1.31 |
| #808080 | 53.59 | 0.00 | 0.00 |

往返：对上表每个 hex，`lab_to_hex(hex_to_lab(h)) == h`。

### 6.2 CIEDE2000（kL=kC=kH=1）
`delta_e_2000(lab1, lab2) -> ndarray`，支持广播（`(N,3)` 对 `(3,)`、`(N,3)` 对 `(N,3)`）。按 Sharma, Wu, Dalal (2005) 公式逐步实现：
```
C1 = hypot(a1,b1); C2 = hypot(a2,b2); Cbar = (C1+C2)/2
G = 0.5*(1 - sqrt(Cbar^7/(Cbar^7 + 25^7)))
a1p = (1+G)*a1; a2p = (1+G)*a2
C1p = hypot(a1p,b1); C2p = hypot(a2p,b2)
h1p = degrees(atan2(b1,a1p)) mod 360 ; h2p 同理（C'=0 时 h'=0）
dLp = L2-L1 ; dCp = C2p-C1p
dhp = 0 if C1p*C2p==0 else (h2p-h1p, 若 >180 减 360, 若 <-180 加 360)
dHp = 2*sqrt(C1p*C2p)*sin(radians(dhp/2))
Lbp = (L1+L2)/2 ; Cbp = (C1p+C2p)/2
hbp = h1p+h2p                         if C1p*C2p==0
    = (h1p+h2p)/2                     if |h1p-h2p|<=180
    = (h1p+h2p+360)/2                 if |h1p-h2p|>180 and h1p+h2p<360
    = (h1p+h2p-360)/2                 otherwise
T = 1 - 0.17cos(hbp-30) + 0.24cos(2hbp) + 0.32cos(3hbp+6) - 0.20cos(4hbp-63)
dTheta = 30*exp(-((hbp-275)/25)^2)
RC = 2*sqrt(Cbp^7/(Cbp^7+25^7))
SL = 1 + 0.015*(Lbp-50)^2/sqrt(20+(Lbp-50)^2) ; SC = 1+0.045*Cbp ; SH = 1+0.015*Cbp*T
RT = -sin(radians(2*dTheta))*RC
dE = sqrt((dLp/SL)^2 + (dCp/SC)^2 + (dHp/SH)^2 + RT*(dCp/SC)*(dHp/SH))
```
测试向量（Sharma 2005 数据集中的对，已用 colour-science 交叉验证，容差 1e-4）：

| Lab1 | Lab2 | ΔE00 |
|---|---|---|
| (50, 2.6772, -79.7751) | (50, 0, -82.7485) | 2.0425 |
| (50, 3.1571, -77.2803) | (50, 0, -82.7485) | 2.8615 |
| (50, 2.8361, -74.0200) | (50, 0, -82.7485) | 3.4412 |
| (50, 0, 0) | (50, -1, 2) | 2.3669 |
| (50, 2.5, 0) | (50, 0, -2.5) | 4.3065 |
| (50, 2.5, 0) | (73, 25, -18) | 27.1492 |
| (60.2574, -34.0099, 36.2677) | (60.4626, -34.1751, 39.4387) | 1.2644 |
| (22.7233, 20.0904, -46.6940) | (23.0331, 14.9730, -42.5619) | 2.0373 |

另：对称性 `dE(x,y)==dE(y,x)`；`dE(x,x)==0`。

## 7. k-means（`kmeans.py`，在 Lab 欧氏空间）
```
sample_pixels(X, max_n, seed=0):
    if len(X) <= max_n: return X
    rng = default_rng(seed); return X[rng.choice(len(X), max_n, replace=False)]

kmeans(X, k, seed=0, max_iter=20, tol=0.01) -> (centers (k',3), labels (n,), shares (k',))
    rng = default_rng(seed)
    k = min(k, number of unique rows in X)
    centers = [X[rng.integers(len(X))]]
    while len(centers) < k:                       # k-means++
        d2 = min over centers of squared euclidean distance
        centers.append(X[rng.choice(len(X), p=d2/d2.sum())])
    repeat max_iter times:
        labels = argmin squared distance (平局取小下标)
        new = mean of each cluster；空簇保留旧中心
        shift = max |new - centers| ; centers = new
        if shift < tol: break
    labels = 最终中心再分配一次
    shares = bincount(labels, minlength=k)/n
    return centers, labels, shares
```
测试：两团点（Lab (20,0,0) 和 (80,0,0) 各 500 点，±0.5 噪声 seed 1）k=2 → 两中心与真值距离 <1，shares 各 0.5±0.01；同输入两次结果完全相同；全相同点 k=4 → 返回 1 个中心。

## 8. M1 商品图取色（`images.py`、`extract.py`）
### 8.1 读图 `load_rgb(path) -> np.ndarray(H,W,3) uint8`
```
pillow_heif.register_heif_opener()  (模块加载时一次)
im = Image.open(path); im = ImageOps.exif_transpose(im)
if im.mode in ("RGBA","LA","P"): 先 convert("RGBA")，再 alpha 合成到白底 (255,255,255)
im = im.convert("RGB")
失败（FileNotFoundError）→ ImageMissingError；其他 PIL 异常(UnidentifiedImageError, OSError) → ImageUnreadableError
```
### 8.2 前景掩码 `foreground_mask(lab, drop_highlights=True) -> bool (H,W)`（取色与配色共用）
```
border = concat(lab[:4], lab[-4:], lab[:, :4], lab[:, -4:]) reshaped (-1,3)
bg = median(border, axis=0)
mask = ones
if mean(dE(border,bg) < BG_BORDER_AGREE_DE) >= BG_BORDER_AGREE_FRAC:
    mask &= dE(lab, bg) >= BG_REMOVE_DE
if drop_highlights:
    C = hypot(a,b)
    mask &= ~((L > HIGHLIGHT_L) & (C < HIGHLIGHT_C))
return mask
```
`foreground_mask` **只做背景/高光**，**不**删阴影。阴影由独立函数 `apply_shadow_rule(X)` 处理（见下），只在取色（§8.3）里调用；配色（§9）只用掩码、不删阴影（用户图里的黑是真颜色）。

#### `apply_shadow_rule(X: (n,3) Lab) -> (m,3) Lab`
在掩码选出的像素 `X` 上：`keep = X[:,0] >= SHADOW_L`；若 `n>0` 且 `keep.mean() >= SHADOW_KEEP_MIN_FRAC` 则返回 `X[keep]`，否则返回 `X` 原样（黑色耗材整体很暗时不删）。`n == 0` → 原样。

### 8.3 单张取色 `extract_colors(path, effects) -> ExtractResult`
```
rgb = load_rgb(path); 缩放 thumbnail((256,256), Image.Resampling.BOX)
lab = rgb_to_lab(rgb); X = apply_shadow_rule(lab[foreground_mask(lab, drop_highlights=True)])
if len(X) < MIN_PIXELS: return ExtractResult(status="no_foreground", ...)
X = sample_pixels(X, MAX_SAMPLE, seed=0)
multi = any(e in effects for e in ("multi","dual","tri","gradient"))
if not multi:
    centers, labels, shares = kmeans(X, EXTRACT_K_SINGLE)
    j = argmax(shares); spread = median(dE(X[labels==j], centers[j]))
    conf = shares[j] * (1 - min(1, spread/CONF_SPREAD_DE))
    hexes = [lab_to_hex(centers[j])]
else:
    centers, labels, shares = kmeans(X, EXTRACT_K_MULTI)
    keep = 按 share 降序、share >= MULTI_MIN_SHARE 的前 MULTI_MAX_COLORS 个（至少 1 个：若无达标则取最大的 1 个）
    spread = median(dE(X[labels∈keep], 各自中心))
    conf = sum(shares[keep]) * (1 - min(1, spread/CONF_SPREAD_DE))
    hexes = [lab_to_hex(centers[i]) for i in keep]
if any(e in effects for e in CONF_PENALTY_EFFECTS): conf *= CONF_PENALTY_FACTOR
return ExtractResult(status="ok", hexes, confidence=round(conf,3), share=round(主簇或保留簇share之和,3), spread=round(spread,2), n_pixels=len(X))
```
### 8.4 校准基线（参考实现，2026-11-05 在盒子上跑的真实结果）
- 校准集 = 有官方 hex 且有商品图的条目 = **43 条 Bambu Lab**。按 §8.3 参数，提取色与官方色 ΔE00：中位数 **8.0**、P80 **16.0**。
- Anycubic 店铺色 141 条：中位数 11.1、P80 19.6。eSUN 店铺色 166 条：中位数 **31.7**（店铺示意色与商品图严重不一致，见 §14 Q5）。
- 置信度分布（Bambu+Anycubic）：P25 0.37 / P50 0.44 / P75 0.51；conf ≥ 0.5 的样本 ΔE 中位数 7.5，conf < 0.5 的 12.1 —— 置信度确实有区分度。
- 结论：商品图取色是"近似色"，只能以 `image_extracted` 身份参与推荐，并且必须标注「近似色」。

## 9. M2 钉钉 MVP
### 9.1 共享目录协议（`FP_ROOT`）
```
FP_ROOT/
├── inbox/        监听器写图片：<key>.<ext> 或 <key>_<i>.<ext>；钉钉助手写 <key>.request.json
├── processing/   worker 认领中的请求
├── done/         成功处理的请求
├── failed/       处理出错的请求（outbox 仍有 status=error 的结果）
├── outbox/       <key>.json（result，钉钉助手读取）
├── public/cards/ <token>.png（对外静态托管目录）
└── logs/         worker.log（JSON lines）
```
- `key` = request_id = 监听器清洗后的 msgId（`re.sub(r"[^A-Za-z0-9_.=+-]", "_", msgId)`）。
- **钉钉助手写请求**：先写 `inbox/<key>.request.json.tmp`，再 `rename` 成 `inbox/<key>.request.json`（原子）。worker 只认 `*.request.json`。
- **钉钉助手读结果**：轮询 `outbox/<key>.json`，存在即完整（worker 用 tmp+`os.replace` 写）。建议钉钉助手 90 秒未见结果就回复「处理超时，请稍后重试」（钉钉助手侧逻辑，不在本仓库）。
- `request.json` 中**禁止**出现 sessionWebhook（schema 已禁止）。`context` 原样回写。
- 多图：v1 只用 `image_paths[0]`，其余忽略并写 warning `EXTRA_IMAGES_IGNORED:<n>`。

### 9.2 备注解析 `parse_note(text) -> NoteParse(values, warnings)`
`t = nfkc(text).lower()`；中文数字表 `CN = {"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}`。
| 键 | 规则（按顺序，第一个命中生效） |
|---|---|
| max_colors | `(\d{1,2}\|[一二两三四五六七八九十])\s*(?:个\|种)?\s*(?:颜色\|色)(?![差号])` ；否则 `(\d{1,2})\s*colou?rs?\b` |
| ams_slots | ① `(\d{1,2})\s*个?\s*(?:料槽\|槽位\|槽\|slots?)` → 值；② `(\d\|[一二两三四])\s*(?:台\|个\|套)\s*ams` 或 `ams\s*(?:lite\s*)?(\d\|[一二两三四])\s*(?:台\|个\|套)` → 4×N；③ 文本含 `ams` → 4 |
| materials | `(?<![a-z])pla(?![a-z])` → PLA；`(?<![a-z])petg(?![a-z])` → PETG；输出顺序固定 `["PLA","PETG"]` 过滤 |
| brands | 按 §5.4 表顺序，任一别名（小写）是 `t` 的子串 → 加入该 slug |
| allow_approx | `只要官方\|官方色\|official only\|only official` → False |
| keep_small | `保留细节\|小色块\|keep small` → True |

数值越界（max_colors/ams_slots 不在 1–16）→ 不写入 values，warnings 追加 `NOTE_VALUE_OUT_OF_RANGE:<键>=<值>`。
例（全部是测试用例）：

| note | values |
|---|---|
| `帮我配 4 色，AMS 一台，只要拓竹 PLA` | `{"max_colors":4,"ams_slots":4,"materials":["PLA"],"brands":["bambu-lab"]}` |
| `黑白两色就行` | `{"max_colors":2}` |
| `8个槽 PETG 保留细节` | `{"ams_slots":8,"materials":["PETG"],"keep_small":true}` |
| `两台AMS，只要官方色` | `{"ams_slots":8,"allow_approx":false}` |
| `display 用的` | `{}` |
| `20色` | `{}`，warnings `["NOTE_VALUE_OUT_OF_RANGE:max_colors=20"]` |
| `` | `{}` |

参数合并 `resolve_params(constraints, note) -> Params`：每个键取 **constraints > note.values > 默认值**；`n_colors = min(max_colors, ams_slots)`；默认 `max_colors=4, ams_slots=4, materials=["PLA"], brands=[], allow_approx=True, keep_small=False, per_color=2`。

取样区域不从备注解析。`request.regions` 与 `constraints.regions` 都能给，**constraints.regions 优先**（键不存在才用顶层）；缺省或 `[]` 表示整张图。数组最多 16 项，每项：

| 字段 | 含义 |
|---|---|
| space | `norm`（默认，相对原图宽高，0–1）或 `px`（原图像素） |
| x, y | 矩形左上角，或点击点 |
| w, h | 都有才是矩形；都没有才是点 |
| r | 仅点使用。`norm` 时是短边的比例，`px` 时是像素。缺省为短边的 4% |

多个区域取像素并集，并且仍然套用前景掩码。`result.params` 只有真的用了区域才带回 `regions`，没有则省略该键。钉钉侧只写这个 JSON，不另做选区 UI。

### 9.3 配色规划 `plan_palette(path, n_colors, keep_small) -> list[PaletteColor]`
```
rgb = load_rgb(path)
if min(rgb.shape[:2]) < PLAN_MIN_SIDE: raise ImageTooSmallError
thumbnail((512,512), BOX) ; lab = rgb_to_lab
X = lab[foreground_mask(lab, drop_highlights=False)]   # 配色不删高光、不删阴影（用户图里的白和黑是真颜色）
if len(X) < MIN_PIXELS: raise NoForegroundError
X = sample_pixels(X, PLAN_MAX_SAMPLE, seed=0)
centers, labels, shares = kmeans(X, min(16, 2*n_colors))
clusters = [(center, share)]
loop: 找 ΔE00 最小的一对；若 < MERGE_DE 则合并（center = share 加权平均 Lab，share 相加），继续；否则停
if not keep_small:
    loop: 若存在 share < SMALL_SHARE 且簇数 > 1：取 share 最小者，并入 ΔE 最近的簇（加权合并）
clusters 按 share 降序（平局按 L 升序）
显著色换入（`_protect_salient`，`keep_small` 真假都做）：将被占比截掉、但属于显著色的簇换进前 n 个。显著色 = L* ≤ 22（近黑），或彩度 ≥ 42 且 CHROMA_PEAK_DE=20 内没有更艳的簇（高彩度的峰，避免同一块橙的暗部重复占槽）。换入时只挤掉冗余的非显著色：它与另一颗保留色 ΔE00 < 18。非显著色里最亮和最暗的两颗，若彼此 ΔE00 ≥ 18 则留下（米白和棕都留），只挤中间的过渡灰；若这两颗本身就很近，则按「更近、再占比更小」挤掉一颗。挤不掉就保持按占比的前 n 个。`share < SMALL_SHARE`（0.02）的簇在上一步已经并掉，不会走到这里——所以 1% 蓝点在 `keep_small=false` 时仍并入邻色。
kept = clusters[:n_colors]; 其余每个的 share 加到 ΔE 最近的 kept 上（中心不变）
share 重新归一化到和为 1，round 3 位；hex = lab_to_hex(center)；lab round 2 位
若调用方传入 regions：在前景掩码上再与这些区域的并集相交，只对相交像素做上面的 k-means。`plan_palette(path, n_colors, keep_small, regions=None)`，`regions` 缺省等价于不限制。
return [PaletteColor(index=i, hex, lab, share) ...]
```
测试图（`tests/helpers_images.py` 用 Pillow 画，**不用真实图**）：
- `quadrants(size=400)`：四象限纯色，左上 `#000000`、右上 `#FFFFFF`、左下 `#00AE42`、右下 `#C8102E`，无外框（边框像素四色各占约 1/4，不满足 60% 一致 → 不去背景）。
- `square_on_white(fg="#00AE42", size=200, inner=120)`：白底居中方块。
- `tiny(32×32)`：触发 IMAGE_TOO_SMALL。
- `blank_white(200)`：触发 NO_FOREGROUND。
- `two_tone(left="#C8102E", right="#00AE42", size=200, inner=120, split=0.6)`：白底居中方块，左 60% 红右 40% 绿（多色取色测试）。
- `rgba_square(200)`：透明底 + 不透明绿方块（读图合成白底测试）。

### 9.4 匹配 `match_palette(palette, catalog, params) -> MatchResult`
候选过滤 `eligible(entry, params)`，全部为真才入选：
```
entry.status == "active" and len(entry.hex) == 1
entry.material in params.materials
not params.brands or entry.brand_slug in params.brands
not (set(entry.effects) & MATCH_EXCLUDE_EFFECTS)
entry.hex_source == "official" or (params.allow_approx and entry.hex_confidence >= MATCH_MIN_CONF)
```
每个目标色：用 `PaletteColor.lab`（已 round 2 位）与候选条目的 `lab` 算 ΔE00，过滤 `ΔE <= MATCH_MAX_DE`，排序键 `(round(ΔE,4), SOURCE_RANK[hex_source], id)`，取前 `per_color` 个为 picks。`delta_e` 输出 round 2 位；`label` 用未取整 ΔE 查 `LABEL_THRESHOLDS`（<2、<5、≤10）；`is_approx = hex_source != "official"`。`url` / `alt_url` 按 §10.1 的拼多多优先规则从 `offers` 算出（`url` 必为 `https?://`；`alt_url` 没有则为 null）。`price_text` 取提供 `url` 的那条 offer，主链接不是任一 offer 时取 `offers[0]`（无 offers → null；`price_text` 为空串 `""` 时也输出 null，即 `price_text or None`）。
`name_display(entry)`（定义在 `matcher.py`）= `" ".join(非空的 name_zh, name_en)`，有 code 时追加 ` ({code})`；两者都空 → `name_raw`。例：`黑色 Black (30105)`、`Sakura Bloom` 条目 → `樱花粉 Sakura Bloom`。
- 某目标无 pick → warning `NO_MATCH_FOR_COLOR:<index>`；所有目标都无 pick → 抛 `NoMatchError`。
- `slots_used` = 各目标首选 id 去重后的个数。
- `single_series_option`：按 `(brand_slug, series_slug)` 分组候选；对每组求每个目标的最小 ΔE；所有目标都 ≤ MATCH_MAX_DE 的组里，取 `max` 最小者（平局：均值小者，再平局：`brand_slug/series_slug` 字典序小者）；无满足组 → null。
真实数据金标（只用 M0 目录，即 official + store_swatch；参考实现计算）：
| 目标 | 参数 | 前 3 名（id, ΔE） |
|---|---|---|
| #000000 | PLA, brands=[bambu-lab], allow_approx=False | `bambu-lab/pla-aero/black-14103` 0.0；`bambu-lab/pla-basic/black-10101` 0.0；`bambu-lab/pla-cf/black-14100` 0.0 |
| #00AE42 | 同上 | `bambu-lab/pla-basic/bambu-green-10501` 0.0；`bambu-lab/pla-lite/green-16501` 4.70；`bambu-lab/pla-cf/matcha-green-14500` 9.24 |
| #C8102E | PLA, allow_approx=False | `bambu-lab/pla-lite/red-16200` 4.47；`bambu-lab/pla-silk-plus/candy-red-13205` 5.07；`bambu-lab/pla-matte/dark-red-11202` 5.20 |
| #FFA3B5 | PLA, allow_approx=True | `anycubic/pla-silk/pink` 3.21；`anycubic/pla-basic/pink` 5.14；`anycubic/pla-plus/pink` 5.14 |
M0 目录中可参与推荐的条目共 484 条（official PLA 131 / PETG 54，store_swatch PLA 233 / PETG 66）。

### 9.5 worker（`worker.py`）
CLI：`filament-picker worker --root <FP_ROOT> [--once] [--catalog PATH]`。
```
启动：确保 7 个子目录存在（mkdir parents, exist_ok）；加载目录（失败 → 进程退出码 2，日志 CATALOG_ERROR）
loop:
    reqs = sorted(inbox.glob("*.request.json"), key=lambda p: (p.stat().st_mtime, p.name))
    for req in reqs:
        dst = processing/req.name
        try: os.rename(req, dst) except FileNotFoundError: continue        # 被别人认领
        result = process_request(dst, catalog, root)                       # 永不抛异常
        write_json_atomic(outbox/f"{result.request_id}.json", result)      # tmp + os.replace
        os.replace(dst, (done if result.status=="ok" else failed)/req.name)
    若距上次清理 >= CLEANUP_INTERVAL_S: cleanup(root, now)
    若目录文件 mtime 变化：重新加载
    if --once: break
    sleep(WORKER_POLL_S)
SIGTERM/SIGINT：处理完当前请求后退出，退出码 0
```
`process_request`：读 JSON（失败或 schema 不符 → INVALID_REQUEST；request_id 取文件名去掉 `.request.json`）→ `planner.run_plan(...)` → 返回 result。**唯一允许 `except Exception` 的地方**：`process_request` 最外层，转成 INTERNAL 并把 traceback 写日志（不写进 result）。
`cleanup(root, now)`：对 `inbox, done, failed, outbox, public/cards` 下的**普通文件**（不递归、不删目录），`now - mtime > RETENTION_DAYS*86400` 的删除；返回删除数。
`scripts/run_worker.sh`：
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/filament-picker worker --root "${FP_ROOT:-/home/box/agent-data/shared/filament-picker}"
```

### 9.6 色卡 PNG（`card.py`）`render_card(image_path, palette, matches, out_path, today) -> Path`
- 画布宽 1080，白底 `#FFFFFF`，外边距 40。高度 `H = 40 + 120 + max(360, 140*n) + 60 + 40`（n = 调色板色数）。
- 页眉（y 40–160）：标题「配色方案（n 色）」Bold 44px `#111111` 于 (40,48)；副标题「按图片主色推荐 · {YYYY-MM-DD}」Regular 24px `#666666` 于 (40,108)。
- 左栏：原图缩略图放进 360×360 框（x 40–400，y 160–520），等比缩放居中，留白填 `#F5F5F5`。
- 右栏每行高 140，第 i 行 y0 = 160 + 140*i：
  - 目标色块 100×100 圆角 12，左上角 (440, y0+20)，填目标 hex；块下方不写字。
  - 推荐色块 100×100 圆角 12，(580, y0+20)，填首选 hex；无匹配时填 `#EEEEEE` 并在块中央写「无」（Regular 32px `#999999`，`anchor="mm"` 于块中心）。
  - 文字 x=700：第 1 行 `{brand_name} {series_name}` Bold 26px `#111111`（y0+22），超过 18 个字符截断为前 17 个字符 + "…"；第 2 行 `name_display` Regular 24px `#333333`（y0+58），同样 18 字符截断；第 3 行 `ΔE {delta_e:.1f} · {label}` + （is_approx 时）` · 近似色` Regular 22px `#666666`（y0+92）。
  - 色块浅色（L>90）时加 1px `#DDDDDD` 描边。
- 页脚：「颜色仅供参考，屏幕显示与实物有差异」Regular 20px `#999999`，左对齐 x=40，y = H-40-40。
- 字体：`ImageFont.truetype(FP_FONT_BOLD/REGULAR, size, index=FP_FONT_INDEX)`；保存 PNG（`optimize=True`）。
- 文件名：`public/cards/{secrets.token_urlsafe(CARD_TOKEN_BYTES)}.png`；`card_url = FP_CARD_BASE_URL.rstrip("/") + "/" + 文件名`（未设置 → null）。

### 9.7 回复 Markdown（`reply.py`）`build_reply_markdown(result) -> str`
成功时逐字模板（`{}` 为替换，`[可选]` 行按条件出现，行尾无空格，行间 `\n`）：
```
### 配色方案（{n} 色）
[若 card_url] ![配色卡]({card_url})
[对每个目标 i]
{i+1}. `{hex}` 占比 {round(share*100)}%
   - 推荐：{brand_name} {series_name} · {name_display}（ΔE {delta_e:.1f}，{label}[，近似色]）[购买]({url})[若 alt_url][原链接]({alt_url})
   [对第 2、3 个 pick] - 备选：同上格式
   [若无 pick] - 暂无 ΔE ≤ 10 的耗材
[若 single_series_option] **同系列方案**：{brand_name} {series_name}（最大 ΔE {max_delta_e:.1f}）
[若任何 pick 的 is_approx] > 近似色 = 颜色来自店铺示意色或商品图取色，不是官方色值，请以实物为准。
需要 {slots_used} 个料槽。
```
- `url` 为 null 时省略整个 `[购买](…)`；`alt_url` 为 http(s) 字符串时在购买链接后紧接 `[原链接](…)`，否则省略。`label` 后面的「，近似色」仅在 `is_approx` 为真时出现。
- **金标**：`build_reply_markdown(docs/schemas/examples/result.example.json 的内容)` 必须逐字等于该文件里的 `reply_markdown`（该例的 palette/request 是示例，picks 与 ΔE 是用 M0 真实目录对 `#1B1B1D` 按 §9.4 算出的）。

失败时 = `error.message_zh` 单行。
### 9.8 错误码与文案（逐字）
| code | 触发 | message_zh |
|---|---|---|
| INVALID_REQUEST | request JSON 解析失败或 schema 不符 | 请求格式不对，请重新发一次图片。 |
| IMAGE_MISSING | image_paths[0] 不存在 | 没找到这张图片，可能已过期，请重新发送。 |
| IMAGE_UNREADABLE | Pillow 打不开 | 这张图片打不开，请换成 PNG 或 JPG 再发。 |
| IMAGE_TOO_SMALL | 短边 < 64 | 图片太小了，请发原图。 |
| NO_FOREGROUND | 前景像素 < 500 | 没能从图里分出主体颜色，请换一张背景更干净的图。 |
| NO_MATCH | 所有目标都无 pick | 在当前条件下没找到足够接近的耗材，可以放宽品牌/材料，或去掉「只要官方」。 |
| CATALOG_ERROR | 目录文件缺失/校验失败 | 色卡数据加载失败，请稍后再试。 |
| INTERNAL | 其他异常 | 处理时出错了，请稍后再试。 |

### 9.9 `planner.run_plan(request: dict, catalog: Catalog, root: Path, now: Callable[[], datetime], card_base_url: str | None) -> dict`
`created_at` 原样复制 `request.created_at`（schema 规定）。`now()` 在开始时调用一次得到 `t0`，结束时再调用一次得到 `finished_at`（`isoformat(timespec="seconds")`）；`elapsed_ms = max(0, round((finished - t0).total_seconds()*1000))`。测试里传固定时钟（例：`iter([t0, t0+1.84s]).__next__`）。
组装顺序：parse_note → resolve_params → plan_palette → match_palette → render_card（仅 status ok 且有 ≥1 pick）→ build_reply_markdown → 填 result 全部字段 → schema 校验（失败视为 INTERNAL）。`/api/plan` 与 worker 共用此函数。

## 10. M3 网站
### 10.1 `web-catalog.json`（`filament-picker export-web --out web/public/web-catalog.json`）
只导出 `status == "active"` 的条目，键名缩短。购买链接优先拼多多，由 `buy.purchase_links` 决定，不改 `filament-catalog` 里的原始 `offers`：

- `offers` 中已有真实商品页（主机名为 `mobile.pinduoduo.com` / `pinduoduo.com` / `mobile.yangkeduo.com` / `yangkeduo.com` 及其 `www`，路径含 `goods`，且 `goods_id` 为纯数字）→ `url` 用第一条这样的链接，不改写、不编造 `goods_id`。
- 否则 `url` 为 `https://mobile.pinduoduo.com/search_result.html?search_key=` 加上百分号编码的关键词。关键词 = 品牌检索名 + 系列（系列已含 PLA/PETG 则不再重复材料；去掉系列名里的「（拼多多）」）+ 颜色（有 `name_zh` 用中文，否则 `name_en`）。不把色号写进关键词。
- 品牌检索名：`BRAND_ALIASES` 里第一个含汉字的别名；没有汉字别名时用 `buy.BRAND_SEARCH_NAMES`（`polymaker` → 宝丽玛，`eryone` → 艾瑞欧，`kexcelled` → 凯想）；再没有则用 `brand_name`。
- GitHub 上的 `filaments_color_codes` 色号表不是购买链接，不能当 `url` 或 `alt_url`。
- `alt_url`：按 offer 顺序，第一条既不是主链接、也不是拼多多商品页、也不是上述 GitHub 色号表的 URL；没有则为 null。
- `price` 仍来自提供主链接的那条 offer；主链接是搜索页时用 `offers[0].price_text`（空串作 null）。

键顺序：`id,b,s,m,en,zh,code,py,pyi,fam,eff,hex,src,conf,url,alt_url,price,img`。

```json
{"generated_at": "...", "brands": [{"slug":"bambu-lab","name":"Bambu Lab"}],
 "entries": [{"id":"bambu-lab/petg-basic/black-30105","b":"bambu-lab","s":"PETG Basic","m":"PETG",
   "en":"Black","zh":"黑色","code":"30105","py":"hei se","pyi":"hs","fam":"黑白灰","eff":[],
   "hex":["#000000"],"src":"official","conf":1.0,
   "url":"https://mobile.pinduoduo.com/search_result.html?search_key=...",
   "alt_url":"https://jp.store.bambulab.com/products/petg-basic","price":"¥2,800 JPY"}]}
```
（上例为真实条目的导出形状；`url` 的关键词是「拓竹 PETG Basic 黑色」。已有拼多多商品页的条目 `url` 保持原商品链接，`alt_url` 为 null。）
### 10.2 页面
- `#/` 色卡浏览：顶部搜索框 + 筛选（品牌多选、材料 PLA/PETG、色系 15 项、"只看有色值"、"只看官方色"）；下方色块网格（每块 120×120，显示 hex 色块、品牌系列、名称；无 hex 显示斜线占位）。
- 搜索：MiniSearch `fields: ["en","zh","py","pyi","code","b","s"]`，`storeFields: ["id"]`，`searchOptions: {prefix: true, fuzzy: 0.2, boost: {zh: 2, en: 2, code: 3}}`。空查询按 品牌表顺序 → 系列名 → id 排序。
- 点色块 → 详情抽屉：大色块、hex、来源徽章（official「官方色值」/store_swatch「店铺示意色（近似）」/image_extracted「商品图取色（近似，置信度 0.xx）」/manual「人工校对」）、购买链接（`url`，拼多多优先；GitHub 色号表显示「暂未上架」）和有 `alt_url` 时的「原链接」、"相似色"前 8（culori `differenceCiede2000()`，只在单 hex、非 multi 条目中找，ΔE ≤ 10）。配色页每个推荐同样显示「购买」（`url`）和有 `alt_url` 时的「原链接」。
- 对比栏：最多 4 个，显示两两 ΔE（保留 1 位）。
- `#/plan` 图片配色：上传图片 + 备注输入 → `POST /api/plan` → 渲染调色板与推荐（结构同 result.json）+ 色卡图（`/api/cards/<文件名>`）。选图后可在预览上拖红框或点击；区域以 `constraints.regions`（`space=norm`）随下一次配色提交。已有结果后再改选区会立刻重算。不画选区则用整张图。
### 10.3 `api.py`（FastAPI）
- `GET /api/health` → `{"ok": true, "catalog_generated_at": "..."}`
- `POST /api/plan`（multipart：`file` 必填 ≤ 10MB，`note` 可选，`constraints` 可选 JSON 字符串）→ 把图存 `FP_ROOT/inbox/web-<uuid4hex>.<ext>`，调用 `run_plan`，返回 result JSON（HTTP 200；status=error 也是 200）；超 10MB → 413。
- `GET /api/cards/{name}`：只允许 `^[A-Za-z0-9_-]{32}\.png$`，从 `public/cards/` 返回，否则 404。
- `filament-picker serve --host 127.0.0.1 --port 8787`：挂载 API + `web/dist` 静态文件（`/` → index.html）。

## 11. CLI 总表（`filament-picker <子命令>`，argparse，子命令由对应任务新增）
| 子命令 | 任务 | 作用 | 正常输出（stdout 最后一行） |
|---|---|---|---|
| `--version` | T01 | | `filament-picker 0.3.0` |
| `validate <schema名> <json文件>` | T01 | schema 名 ∈ catalog/lock/request/result | `OK` / 非零退出并打印错误 |
| `ingest` | T02 | 校验 data/raw sha256 并统计 | `rows=3845 brands=21 series=318` |
| `assign-ids [--today YYYY-MM-DD]` | T06 | 更新 data/ids.lock.json | `keys=3821 new=<n> retired=<n> collisions=0` |
| `build-catalog [--extracted PATH]` | T08/T12 | 写 data/build/filament-catalog.json | `entries=3821 with_hex=<n> official=246 store_swatch=354 image_extracted=<n>` |
| `extract [--limit N]` | T12 | 批量取色写 data/extracted/extracted.json | `ok=<n> no_foreground=<n> skipped=<n>` |
| `calibrate` | T12 | 写 data/qa/calibration.csv | `bambu n=40 median=<x> p80=<y>` |
| `qa-sample [--n 50]` | T12 | 写 data/qa/sample.html | `wrote data/qa/sample.html` |
| `plan <image> [--note TEXT] [--out DIR]` | T17 | 本地跑一次，打印 result JSON | （JSON） |
| `worker --root DIR [--once]` | T18 | | 日志 |
| `export-web [--out PATH]` | T20 | | `entries=<n>` |
| `serve [--host] [--port]` | T25 | | uvicorn 日志 |

## 12. 任务清单（按依赖顺序；一次只做一个）
| 任务 | 里程碑 | 标题 | 前置 | 主要文件 |
|---|---|---|---|---|
| T01 | M0 | 仓库脚手架、常量与 schema 校验 | — | pyproject.toml, config.py, validate.py, cli.py, schemas/ |
| T02 | M0 | 原始数据快照与读取 | T01 | ingest.py, data/raw/ |
| T03 | M0 | 颜色名解析 | T01 | names.py |
| T04 | M0 | slug、品牌表与系列 slug | T03 | slug.py, brands.py |
| T05 | M0 | 效果标签与材料 | T03 | effects.py |
| T06 | M0 | 去重、canonical 与 ID 锁定 | T02 T04 | ids.py, data/ids.lock.json |
| T07 | M0 | 颜色空间与 CIEDE2000 | T01 | colorspace.py, ciede2000.py |
| T08 | M0 | 商品图匹配与目录组装 build-catalog | T05 T06 T07 | variants.py, catalog.py, data/manual_overrides.json |
| T09 | M1 | k-means | T01 | kmeans.py |
| T10 | M1 | 异常类、读图与前景掩码 | T07 | errors.py, images.py, tests/helpers_images.py |
| T11 | M1 | 单张商品图取色 | T09 T10 | extract.py |
| T12 | M1 | 批量取色、校准与抽检 | T08 T11 | calibrate.py, catalog.py(扩展) |
| T13 | M2 | 备注解析与参数合并 | T04 | note_parser.py |
| T14 | M2 | 配色规划 | T09 T10 | palette.py |
| T15 | M2 | 耗材匹配 | T08 T13 T14 | matcher.py |
| T16 | M2 | 色卡 PNG | T14 T15 | card.py |
| T17 | M2 | 回复 Markdown、run_plan 与 plan 命令 | T16 | reply.py, planner.py |
| T18 | M2 | inbox→outbox worker 与清理 | T17 | worker.py, scripts/run_worker.sh |
| T19 | M2 | M2 端到端测试与冒烟脚本 | T18 | tests/test_e2e_worker.py, scripts/smoke_worker.sh |
| T20 | M3 | 前端脚手架与 export-web | T08 | web/*, web_export.py |
| T21 | M3 | 色卡浏览：搜索与筛选 | T20 | web/src/search.ts, Filters, SwatchGrid |
| T22 | M3 | 颜色详情、相似色与对比 | T21 | web/src/color.ts, ColorDetail, CompareBar |
| T23 | M3 | FastAPI /api/plan | T17 | api.py |
| T24 | M3 | 图片配色页 | T22 T23 | PlanPage.tsx |
| T25 | M3 | 生产构建与 serve | T24 | cli.py(serve), scripts/build_web.sh |

共 25 个任务：M0 8 个（T01–T08）、M1 4 个（T09–T12）、M2 7 个（T13–T19）、M3 6 个（T20–T25）。

## 13. 审查检查点（开发助手在每个里程碑结束时逐项检查）
通用（每个任务都查）：报告格式完整；只改了任务列出的文件（`git diff --stat` 对照）；验收命令我**亲自重跑**一遍；`ruff check`、`ruff format --check`、全量 `pytest -q` 通过；没有新增依赖（`pyproject.toml`/`package.json` 无 diff，T01/T20 除外）；新增/修改的 CLI 子命令只出现在本任务列出的那一个；`config.py` 常量与 SPEC §4 逐项一致；没有 `TODO`、裸 except、无种子随机、网络调用（`rg -n "requests|urllib|http://|https://" src/` 只应命中常量与测试数据）。

**M0 结束（T01–T08）**
- [ ] `filament-picker ingest` 输出 `rows=3845 brands=21 series=318`；sha256 与 §5.1 一致。
- [ ] `docs/fixtures/ids_golden.json` 35 行全部逐字段一致（name_en/name_zh/code/series_slug/row_id/dedup_key/effects/material）。
- [ ] `merges_golden.json` 24 处合并完全一致，canonical id 一致。
- [ ] `assign-ids` 连跑两次，第二次 `new=0`，`data/ids.lock.json` 无 diff；手工删掉 page_rows 副本中一行（在临时目录）后该 key 变 retired 而不是被删除（看测试）。
- [ ] `build-catalog` 输出 `entries=3821 with_hex=600 official=246 store_swatch=354 image_extracted=0`；`validate catalog` 通过。
- [ ] 抽 10 条随机条目人工看：名称拆分、拼音、offers、variant_image 路径真实存在。

**M1 结束（T09–T12）**
- [ ] CIEDE2000 8 组 Sharma 向量、Lab 6 组向量测试存在且未放宽容差。
- [ ] `calibrate` 输出 `bambu n=40`，median ≤ 10.0（参考实现 8.0 / p80 14.6；有商品图的 Bambu official 共 43，其中 3 条多色丝绸 `len(hex)>1` 不进单色 ΔE 校准）；把 calibration.csv 中 ΔE 最大的 5 条图片打开看原因，记录进 PRD。
- [ ] `extract` 统计：ok / no_foreground / skipped 之和 = 2457（有商品图的条目：无 hex 2101 + official 43 + store_swatch 313）。
- [ ] `qa-sample` 生成的 HTML 人工看 50 条：标记明显错误的条数，>10 条则在校准会上讨论阈值（**Codex 不改阈值**）。
- [ ] 重新 `build-catalog --extracted ...` 后 `image_extracted` 条目置信度都 ≥ 0.40；schema 校验通过；ID 与 M0 完全一致（lock 无 diff）。

**M2 结束（T13–T19）**
- [ ] note_parser 7 个表格用例 + 越界 warning 全部有测试。
- [ ] 真实数据金标匹配表（§9.4）4 行有测试且一致。
- [ ] 打开 3 张生成的色卡 PNG 人工看：中文不乱码（SC 字形）、截断正确、浅色描边、页脚文案逐字一致。
- [ ] `scripts/smoke_worker.sh` 在临时 root 下跑通：request → outbox JSON 通过 result schema，request 移到 done/；错误图移到 failed/ 且 outbox 有 status=error。
- [ ] 认领原子性：两个 `--once` worker 并发跑同一 inbox，每个请求只处理一次（看测试）。
- [ ] cleanup 只删 7 天前的普通文件，不碰目录、不越出 root（看测试用 os.utime 伪造时间）。
- [ ] 确认没有任何代码引用钉钉、sessionWebhook、bambu-print-agent。
- [ ] 与钉钉助手的约定（§9.1）由我转述给钉钉助手；真机实测前不宣称"已上线"。

**M3 结束（T20–T25）**
- [ ] `npm ci && npm run lint && npm test && npm run build` 全过；`package.json` 版本与 §2.2 逐字一致。
- [ ] 搜「黑色」「hei」「hs」「30105」「Sakura」都能找到对应真实条目（有测试）。
- [ ] 详情抽屉来源徽章文案逐字一致；近似色有提示。
- [ ] `/api/plan` 上传测试图返回通过 result schema 的 JSON；>10MB 返回 413；`/api/cards/../x` 返回 404。
- [ ] `serve` 起来后浏览器手动走一遍两页；记录截图到 PRD。

## 14. 需要志远决定的问题（Codex 遇到相关处一律停下）
1. **色卡公网托管**：`public/cards/` 由什么对外提供 https（域名/服务）？`FP_CARD_BASE_URL` 取什么？未定前回复只发文字。
2. **仓库**：默认独立仓库 `/workspace/dev/filament-picker`，是否 `git init`、是否推远端？
3. **bambu-print-agent 的 `filament_id` / `color_source` 改动**：本仓库不碰；何时、由谁去改？
4. **网站（M3）托管方式与域名**。
5. **eSUN 店铺示意色** — 已定：`store_swatch_confidence.esun = 0.3`（校准 median ΔE 32.4，低于 MATCH_MIN_CONF 0.5，不参与推荐）。
6. **覆盖率**：有色值 600/3821（15.7%）；商品图取色即使全部成功上限 2701/3821（70.7%），达不到 PRD 的 80%；1120 条无商品图。接受，还是补图/人工录入？
7. **钉钉真机实测**：监听器离线测试已过，什么时候在真群里发图实测？
8. **并列排序**：ΔE 相同时按 id 排序，导致 `pla-aero` 排在 `pla-basic` 前。是否加"系列优先级"（如 Basic/Matte 优先）？
9. **「待校准」阈值**：M1 校准报告出来后由你签字确认或调整。
10. **钉钉助手侧**写 request.json / 读 outbox / 90 秒超时回复——由钉钉助手实现（本仓库不做），需要你同意这份约定后我转给它。
11. 多图只取第一张，可以吗？
