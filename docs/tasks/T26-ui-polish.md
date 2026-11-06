# T26 — UI 修补：隐藏价格、GitHub 色号表改「暂未上架」、页间导航

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M3 修补 | T25 | 1 小时 | SPEC §10.2；T22、T24 任务卡 |

## 目标
三项小修补（志远定）：
1. 颜色详情不再显示价格（配色页本来就不显示价格，保持）。
2. 购买链接若指向 GitHub 色号表，不要做成可点链接，改成灰色文案「暂未上架」；色卡详情与配色页的购买入口都要如此。
3. 色卡页（`#/`）与配色页（`#/plan`）互相加入口，方便跳转。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- HEAD 含提交 `eafc8bf`（或之后的 `T25: 生产构建与 serve`）。**不要**在沙箱里重跑 T25 验收来判断前置（沙箱内 FastAPI TestClient 会挂起，属已知环境限制；外部已验收）。
- `node --version` 是 v24.x、`npm --version` 是 11.x。

## 要创建/修改的文件（只能动这些）
- `web/src/purchase.ts`（新建）
- 修改 `web/src/components/ColorDetail.tsx`、`web/src/components/PlanPage.tsx`、`web/src/App.tsx`、`web/src/styles.css`
- 修改 `web/src/__tests__/ColorDetail.test.tsx`、`web/src/__tests__/PlanPage.test.tsx`、`web/src/__tests__/App.test.tsx`
- 新建 `web/src/__tests__/purchase.test.ts`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```ts
// purchase.ts
export function isGithubColorTableUrl(url: string): boolean;
  // 解析 URL：host 为 github.com 或 raw.githubusercontent.com（大小写不敏感），
  // 且 pathname 含 "filaments_color_codes"（大小写不敏感）→ true；非法 URL → false。
export function purchaseHref(url: string): string | null;
  // isGithubColorTableUrl(url) → null；否则返回原 url（空串 / 仅空白 → null）。
```

`ColorDetail`：
- **不渲染** `entry.price`（任何形式都不出现价格文案）。
- 购买入口：`purchaseHref(entry.url)` 非 null → `<a href=... target="_blank" rel="noreferrer">购买链接</a>`；
  为 null 且 `entry.url` 非空 → `<span className="purchase-unavailable">暂未上架</span>`；
  `entry.url` 为空串 → 整段购买入口不渲染。

`PlanPage` 每个 pick：
- `purchaseHref(pick.url)` 非 null → `<a href=...>购买</a>`；
  为 null → `<span className="purchase-unavailable">暂未上架</span>`（不渲染 `<a>`）。
- 不要显示 `price_text`。

导航（两页都要有）：
- 色卡页（`route` 不是 `#/plan`）顶部（`<h1>` 旁或紧随其后）放
  `<a href="#/plan" className="nav-link">图片配色</a>`。
- 配色页顶部（`<h1>` 旁或紧随其后）放
  `<a href="#/" className="nav-link">色卡浏览</a>`。
- `styles.css` 给 `.purchase-unavailable` 灰色样式（`color: #888` 即可）、`.nav-link` 基本可点样式；不要引 UI 库。

## 输入/输出示例
| url | isGithubColorTableUrl | purchaseHref |
|---|---|---|
| `https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/filament/filaments_color_codes.json` | true | null |
| `https://raw.githubusercontent.com/bambulab/BambuStudio/master/resources/profiles/BBL/filament/filaments_color_codes.json` | true | null |
| `https://jp.store.bambulab.com/products/petg-basic` | false | 原 url |
| `https://github.com/bambulab/BambuStudio`（无 filaments_color_codes） | false | 原 url |
| `not a url` | false | null（空/非法按 null 处理：`purchaseHref` 对无法 `new URL` 的输入返回 null） |

真实 fixture：`result.example.json` 里 `bambu-lab/pla-tough/black-12101` 的 url 是 GitHub 色号表 → 配色页应出现「暂未上架」、不应有指向该 url 的「购买」链接；`bambu-lab/pla-aero/black-14103` 仍是可点「购买」。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`purchase.test.ts`
- 上表 5 行用例（`isGithubColorTableUrl` + `purchaseHref`）。
- `purchaseHref("")` / `purchaseHref("   ")` → null。

`ColorDetail.test.tsx`（在现有用例上改/加）
- Bambu PETG Basic 仍有「购买链接」指向店铺；详情文本**不含** `¥` / `JPY` / `2,800`（即不显示价格）。
- 新增：把选中条目的 url 换成 GitHub 色号表（可在测试里直接 render `ColorDetail`，或 stub catalog 改一条）→ 出现「暂未上架」、无 `role="link"` 名「购买链接」。

`PlanPage.test.tsx`
- 「renders the second pick and its purchase link」保留（pla-aero 店铺链接仍可点）。
- 新增或改：提交 fixture 后，第一 pick（pla-tough，GitHub 色号表）→ 文本含「暂未上架」；`queryByRole("link", {name:"购买"})` 的 href 集合里**没有**含 `filaments_color_codes` 的链接（允许第二 pick 仍有「购买」）。

`App.test.tsx`
- 色卡页能 `findByRole("link", { name: "图片配色" })`，`href` 为 `#/plan`（或绝对路径以 `#/plan` 结尾）。
- hash 切到 `#/plan` 后能找到「色卡浏览」链接，`href` 以 `#/` 结尾（不是 `#/plan`）。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker/web && npm ci && npm run lint && npm test && npm run build
```

## 不要做
- 不要改 Python / CLI / worker / api / schemas / fixtures 内容（测试里临时构造的对象除外）。
- 不要改 `package.json` 版本；不要新增 npm 包。
- 不要显示价格（色卡详情、配色页都不显示）。
- 不要部署、不要启动常驻 worker、不要碰钉钉。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`，但 `docs/QUESTIONS.md` 追加阻塞问题除外）。
- 不要联网（`npm ci` 用离线缓存即可；沙箱里 esbuild postinstall EPERM 时可用 `--ignore-scripts` 自测，外部会原样复跑）。
- 不要为了让测试变绿去改断言里的数字或放宽容差；对不上 → 停下按 AGENTS.md §5 报告。
