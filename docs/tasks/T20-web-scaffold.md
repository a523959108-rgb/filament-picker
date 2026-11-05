# T20 — 前端脚手架与 export-web

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M3 | T08 | 半天 | SPEC §2.2、§10.1、§10.2；docs/fixtures/web-catalog.sample.json |

## 目标
Python 侧把目录导出成前端用的精简 `web-catalog.json`；搭好 Vite + React + TS 前端骨架，能加载目录并显示条目数。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T08 验收通过。
- `node --version` 是 v24.x、`npm --version` 是 11.x（不是 → 停下报告，不要换版本）。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/web_export.py`；`src/filament_picker/cli.py`（只新增 `export-web`）
- `tests/test_web_export.py`
- `web/package.json`、`web/package-lock.json`（`npm install` 生成后提交）、`web/tsconfig.json`、`web/vite.config.ts`、`web/index.html`
- `web/src/{main.tsx,App.tsx,config.ts,types.ts,catalog.ts,styles.css}`、`web/src/components/SwatchGrid.tsx`
- `web/src/__tests__/App.test.tsx`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
# web_export.py
def export_entry(entry: dict[str, Any]) -> dict[str, Any]: ...
    # 键顺序：id,b,s,m,en,zh,code,py,pyi,fam,eff,hex,src,conf,url,price
    # b=brand_slug s=series_name m=material py=pinyin pyi=pinyin_initials fam=family eff=effects
    # src=hex_source conf=hex_confidence url=offers[0].url price=offers[0].price_text
def export_web(catalog: dict[str, Any]) -> dict[str, Any]: ...
    # 只导出 status=="active"，保持 catalog.entries 原顺序；
    # brands = catalog["brands"] 中在导出条目里出现过的，保持原顺序，每项 {"slug","name"}
```
CLI：`filament-picker export-web [--catalog PATH] [--out PATH]`，默认 `get_settings().catalog` → `REPO_ROOT/"web"/"public"/"web-catalog.json"`；stdout 最后一行 `entries=<n>`。

```ts
// types.ts —— 与 web-catalog.json 键名一一对应
export interface WebEntry { id: string; b: string; s: string; m: "PLA" | "PETG"; en: string | null; zh: string | null;
  code: string | null; py: string | null; pyi: string | null; fam: string; eff: string[]; hex: string[];
  src: "official" | "store_swatch" | "image_extracted" | "manual" | null; conf: number | null; url: string; price: string | null; }
export interface WebCatalog { generated_at: string; brands: { slug: string; name: string }[]; entries: WebEntry[]; }
// catalog.ts
export async function loadCatalog(url?: string): Promise<WebCatalog>;   // 默认 "./web-catalog.json"；!res.ok → throw Error(`catalog ${res.status}`)
// App.tsx
export default function App(): JSX.Element;   // 读 location.hash：""/"#/" → 色卡页，"#/plan" → 占位文字「图片配色（T24）」；监听 hashchange
// components/SwatchGrid.tsx
export function SwatchGrid(props: { entries: WebEntry[]; brands: { slug: string; name: string }[]; onSelect?: (id: string) => void }): JSX.Element;
   // 顶部「共 {n} 个颜色」；每块 120×120：hex[0] 背景（无 hex → CSS 斜线占位 class "swatch-empty"），下方「品牌名 系列名」（品牌名由 props 传入的 brands 映射，组件签名加 `brands: { slug: string; name: string }[]`）与 zh ?? en
```
`package.json` scripts 逐字：`"dev": "vite"`, `"build": "tsc --noEmit && vite build"`, `"lint": "tsc --noEmit"`, `"test": "vitest run"`。
`vite.config.ts`：`plugins: [react()]`，`server.proxy: {"/api": "http://127.0.0.1:8787"}`，`test: {environment: "jsdom"}`。
`tsconfig.json`：`strict: true`、`jsx: "react-jsx"`、`resolveJsonModule: true`、`moduleResolution: "bundler"`、`noEmit: true`、不加 `vitest/globals`（测试里显式 `import { describe, it, expect, vi } from "vitest"`）。

## 输入/输出示例
`export_web(json.load(open("docs/schemas/examples/filament-catalog.example.json")))` == `docs/fixtures/web-catalog.sample.json`（真实 4 条：Bambu PETG Basic 黑 #000000 ¥2,800 JPY；eSUN PETG-Basic 黑 #272729；CaiLab Bamboo RB009 无 hex；ByeHassle 樱花粉 无 hex）。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_web_export.py`
- 上面的等式（整体 `==`）。
- 把一条改成 `status: "retired"` → 不导出，且若该品牌已无条目则 `brands` 里也去掉。
- 每条导出 entry 的键列表 == 固定顺序。
- `main(["export-web", "--catalog", 示例目录, "--out", str(tmp_path/"w.json")])` 返回 0，stdout 最后一行 `entries=4`。

`web/src/__tests__/App.test.tsx`（vitest + @testing-library/react，`vi.stubGlobal("fetch", ...)` 返回 `docs/fixtures/web-catalog.sample.json` 的内容——用 `import sample from "../../../docs/fixtures/web-catalog.sample.json"`）
- 渲染 `<App/>` 后 `await findByText("共 4 个颜色")`。
- 无 hex 的两条渲染出 `.swatch-empty` 共 2 个。
- `location.hash = "#/plan"` 并派发 hashchange → 出现「图片配色（T24）」。
- fetch 返回 500 → 页面显示「目录加载失败」。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_web_export.py -q && .venv/bin/filament-picker export-web && cd /workspace/dev/filament-picker/web && npm ci && npm run lint && npm test && npm run build
```

## 不要做
- 不要加路由库、状态管理库、UI/CSS 框架、eslint/prettier，或 §2.2 以外的任何 npm 包。
- 不要改 `package.json` 里的版本号（逐字 §2.2，不带 `^`/`~`）。
- 不要提交 `web/public/web-catalog.json`、`web/dist/`、`node_modules/`。
- 不要在前端做拼音转换或色值计算以外的数据加工；导出字段以 Python 为准。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
