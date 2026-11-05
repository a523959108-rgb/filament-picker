# T22 — 颜色详情、相似色与对比

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M3 | T21 | 半天 | SPEC §10.2 |

## 目标
点色块打开详情抽屉（大色块、hex、来源徽章、全部购买链接、相似色前 8）；加对比栏（最多 4 个，显示两两 ΔE）。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T21 验收通过。

## 要创建/修改的文件（只能动这些）
- `web/src/color.ts`
- `web/src/components/ColorDetail.tsx`、`web/src/components/CompareBar.tsx`；修改 `App.tsx`
- `web/src/__tests__/color.test.ts`、`web/src/__tests__/ColorDetail.test.tsx`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```ts
// color.ts（culori 4.0.2：import { differenceCiede2000 } from "culori"）
export function hexDelta(a: string, b: string): number;          // differenceCiede2000()(a, b)
export function similar(target: WebEntry, entries: WebEntry[], limit?: number): { entry: WebEntry; delta: number }[];
   // limit 默认 8；只在 hex.length===1 且 !eff.includes("multi") 且 id!==target.id 的条目里找；delta ≤ 10；按 delta 升序、id 升序
   // target 自身没有单一 hex → []
export function sourceBadge(src: WebEntry["src"], conf: number | null): string;
   // official → "官方色值"；store_swatch → "店铺示意色（近似）"；image_extracted → `商品图取色（近似，置信度 ${conf.toFixed(2)}）`；manual → "人工校对"；null → "无色值"
// components/ColorDetail.tsx
export function ColorDetail(props: { entry: WebEntry; catalog: WebCatalog; onClose: () => void;
  onCompare: (id: string) => void }): JSX.Element;
// components/CompareBar.tsx
export function CompareBar(props: { entries: WebEntry[]; onRemove: (id: string) => void }): JSX.Element;
   // 最多 4 个（App 里第 5 个忽略并提示「最多对比 4 个」）；两两 ΔE = hexDelta(条目A.hex[0], 条目B.hex[0]).toFixed(1)，任一无 hex 显示 "—"
```

## 输入/输出示例
真实数据：`hexDelta("#000000", "#272729")`（Bambu PETG 黑 vs eSUN PETG 黑）≈ 9.75（参考实现 CIEDE2000 = 9.7548）。
`similar(bambu 黑, sample.entries)` → `[{entry: esun 黑, delta ≈ 9.75}]`（另外两条无 hex）。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`color.test.ts`
- `hexDelta("#000000", "#272729")` 在 `(9.6, 9.9)` 之间；`hexDelta("#00AE42", "#00AE42") === 0`。
- `similar(bambu, sample.entries)` 长度 1、id 是 `esun/petg-basic/black`；`similar(cailab, ...)` 为 `[]`。
- 构造 12 条单 hex 条目（`#000000`…逐渐变亮的灰），`similar` 返回 ≤ 8 条且 delta 非降序；含 `eff: ["multi"]` 的条目不出现。
- `sourceBadge` 5 种输入逐字断言（image_extracted 用 conf 0.5 → `商品图取色（近似，置信度 0.50）`）。

`ColorDetail.test.tsx`
- 点击 bambu 黑色块 → 抽屉显示 `#000000`、「官方色值」、链接 `href` = `https://jp.store.bambulab.com/products/petg-basic`、相似色里有 eSUN。
- 点 esun → 徽章「店铺示意色（近似）」。
- 把 bambu 与 esun 加入对比 → CompareBar 显示 `9.8`。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker/web && npm ci && npm run lint && npm test && npm run build
```

## 不要做
- 不要加路由库、状态管理库、UI/CSS 框架、eslint/prettier，或 §2.2 以外的任何 npm 包。
- 不要改 `package.json` 里的版本号（逐字 §2.2，不带 `^`/`~`）。
- 不要自己实现 CIEDE2000（前端用 culori）；不要改阈值 10 / 前 8。
- 不要显示 ΔE 以外的相似度指标。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
