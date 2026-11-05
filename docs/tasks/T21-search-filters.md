# T21 — 色卡浏览：搜索与筛选

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M3 | T20 | 半天 | SPEC §10.2 |

## 目标
色卡页加上 MiniSearch 全文搜索（中文、英文、拼音、拼音首字母、色号）和筛选（品牌、材料、色系、只看有色值、只看官方色）。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T20 验收通过。

## 要创建/修改的文件（只能动这些）
- `web/src/search.ts`
- `web/src/components/Filters.tsx`；修改 `App.tsx`、`SwatchGrid.tsx`
- `web/src/__tests__/search.test.ts`、`web/src/__tests__/Filters.test.tsx`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```ts
// search.ts
export interface FilterState { brands: string[]; materials: ("PLA" | "PETG")[]; families: string[]; onlyHex: boolean; onlyOfficial: boolean; }
export const EMPTY_FILTER: FilterState;            // 全空 / false
export function buildIndex(entries: WebEntry[]): MiniSearch<WebEntry>;
   // fields ["en","zh","py","pyi","code","b","s"]，storeFields ["id"]，
   // searchOptions {prefix: true, fuzzy: 0.2, boost: {zh: 2, en: 2, code: 3}}（SPEC §10.2 逐字）
export function defaultOrder(entries: WebEntry[], brands: { slug: string }[]): WebEntry[];
   // 品牌表顺序 → s（localeCompare "zh"）→ id
export function applyFilters(entries: WebEntry[], f: FilterState): WebEntry[];
   // 各维度之间 AND；同一维度内 OR；空数组 = 不限；onlyHex: hex.length>0；onlyOfficial: src==="official"
export function query(index: MiniSearch<WebEntry>, catalog: WebCatalog, q: string, f: FilterState): WebEntry[];
   // q.trim()==="" → defaultOrder；否则按 MiniSearch 得分降序；最后 applyFilters
// components/Filters.tsx
export function Filters(props: { brands: { slug: string; name: string }[]; families: string[];
  value: FilterState; onChange: (f: FilterState) => void }): JSX.Element;
```
色系 15 项从 `config.ts` 的 `FAMILIES` 读（与 catalog schema `family` enum 同顺序同文字）。

## 输入/输出示例
用 `web-catalog.sample.json`（真实 4 条）：

| 查询 | 结果 ids |
|---|---|
| `黑色` / `hei` / `hs` / `30105` | `["bambu-lab/petg-basic/black-30105"]` |
| `sakura` / `樱花` | `["byehassle/pla-ya-guang/sakura-bloom"]` |
| `rb009` | `["cailab/rainbow-shift-pla/bamboo-rb009"]` |
| `""`（空） | bambu-lab…, cailab…, esun…, byehassle…（品牌表顺序） |

## 测试（先写测试 → 运行确认失败 → 再写实现）
`search.test.ts`
- 上表每行 `query(...).map(e => e.id)` 严格相等。
- `black` → 结果包含 bambu 与 esun 两条（顺序不断言）。
- 过滤：`materials ["PETG"]` → 2 条；`onlyHex` → 2 条；`onlyOfficial` → 1 条（bambu）；`brands ["esun"], materials ["PLA"]` → 0 条；`families ["粉"]` → byehassle 1 条。
- `query(index, cat, "黑色", {...EMPTY_FILTER, onlyOfficial: true})` → bambu 1 条。
- `FAMILIES.length === 15`。

`Filters.test.tsx`
- 渲染 App，勾选「只看官方色」→ 出现「共 1 个颜色」；在搜索框输入 `樱花` → 「共 0 个颜色」（官方色仍勾选）；取消勾选 → 「共 1 个颜色」。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker/web && npm ci && npm run lint && npm test && npm run build
```

## 不要做
- 不要加路由库、状态管理库、UI/CSS 框架、eslint/prettier，或 §2.2 以外的任何 npm 包。
- 不要改 `package.json` 里的版本号（逐字 §2.2，不带 `^`/`~`）。
- 不要自己写分词/拼音/模糊匹配；只用 MiniSearch 的选项。
- 不要做分页、虚拟滚动（3821 条直接渲染，性能问题记录后再议）。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
