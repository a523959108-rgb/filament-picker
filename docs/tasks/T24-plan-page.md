# T24 — 图片配色页

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M3 | T22 T23 | 半天 | SPEC §10.2 `#/plan` |

## 目标
前端 `#/plan` 页：上传图片 + 备注 → 调 `/api/plan` → 展示调色板、每个目标色的推荐、同系列方案、所需料槽和色卡图；错误时显示 `message_zh`。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T22、T23 验收通过。

## 要创建/修改的文件（只能动这些）
- `web/src/api.ts`
- `web/src/components/PlanPage.tsx`；修改 `App.tsx`（替换 T20 的占位文字）、`web/src/types.ts`（只追加 PlanResult）
- `web/src/__tests__/fixtures/result.example.json`、`result.error.example.json`（从 `docs/schemas/examples/` 逐字节复制）
- `web/src/__tests__/PlanPage.test.tsx`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```ts
// types.ts 追加：PlanResult（与 result.schema.json 一致的 TS 类型；字段名不改）
// api.ts
export async function postPlan(file: File, note: string, constraints?: Record<string, unknown>): Promise<PlanResult>;
   // FormData: file, note, constraints（JSON.stringify，未给则不加）→ fetch("/api/plan", {method: "POST"})
   // 413 → throw Error("图片超过 10MB")；其他 !ok → throw Error(`HTTP ${status}`)
export function cardSrc(result: PlanResult): string | null;   // card_path 取文件名 → `/api/cards/${name}`；card_path null → null
// components/PlanPage.tsx
export function PlanPage(props: { post?: typeof postPlan }): JSX.Element;   // post 可注入，测试用
   // 表单：<input type="file" accept="image/*">、<textarea placeholder="例：4 色，AMS 一台，只要拓竹 PLA">、按钮「开始配色」
   // 提交中按钮 disabled 且文字「配色中…」
   // ok：标题「配色方案（n 色）」；每个目标一行：目标色块 + hex + 占比%；picks 列表：brand series · name_display、ΔE x.x、label、is_approx 时「近似色」标记、「购买」链接 = url
   //     single_series_option 存在时显示「同系列方案：…（最大 ΔE x.x）」；「需要 {slots_used} 个料槽」；cardSrc 非空时 <img alt="配色卡">
   // error：显示 error.message_zh（class "plan-error"）
```

## 输入/输出示例
用 `result.example.json`（示例请求 + 真实目录算出的 picks）：页面出现「配色方案（1 色）」「#1B1B1D」「100%」「Bambu Lab PLA Tough · 黑色 Black (12101)」「ΔE 4.4」「接近」「同系列方案：Bambu Lab PLA Tough（最大 ΔE 4.4）」「需要 1 个料槽」，配色卡 `src="/api/cards/EXAMPLE_TOKEN.png"`。

## 测试（先写测试 → 运行确认失败 → 再写实现）
`PlanPage.test.tsx`（注入 `post = vi.fn().mockResolvedValue(fixture)`）
- 选文件（`new File([new Uint8Array([137,80,78,71])], "a.png", {type: "image/png"})`）+ 输入备注 + 点「开始配色」→ `post` 被调用一次，前两个参数是 `(file, "4 色")`；上面列出的文字全部出现；`img[alt="配色卡"]` 的 src 正确。
- 第二个 pick 显示「ΔE 6.1」「勉强」，「购买」链接 href = `https://jp.store.bambulab.com/products/pla-aero`。
- 没选文件点按钮 → 不调用 post，显示「请先选择图片」。
- `post` resolve 为 `result.error.example.json` 的内容（同样复制进 fixtures）→ 显示该文件的 `error.message_zh`。
- `post` reject `Error("图片超过 10MB")` → 显示「图片超过 10MB」。
- `cardSrc({...fixture, card_path: null})` 为 null 时不渲染 img。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker/web && npm ci && npm run lint && npm test && npm run build
```

## 不要做
- 不要加路由库、状态管理库、UI/CSS 框架、eslint/prettier，或 §2.2 以外的任何 npm 包。
- 不要改 `package.json` 里的版本号（逐字 §2.2，不带 `^`/`~`）。
- 不要在前端重算 ΔE、重排 picks 或改写 reply_markdown；只展示 result 字段。
- 不要在前端直接读 `card_url`（公网 URL 是给钉钉的；网页走 `/api/cards/`）。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
