# 叠色子域部署说明（未执行）

**等志远明确说「现在部署」再动手。** 本文只写步骤，不改生产 nginx，不改主站 `filament.ibaozi.com` 的 server 块。

## 目标

| 项 | 值 |
|----|----|
| 主站 | `https://filament.ibaozi.com/`（色卡首页；新增「打开叠色」按钮） |
| 叠色子域 | `https://stack.filament.ibaozi.com/` → 落地 `/#/stack` |
| 代码 | 本仓库 `main` 合并后的 HEAD（含 `#/stack`、成本页、真链、色卡对照） |
| 引擎 | **不**把 Lumina/GPL 嵌进公网；子域只出站内壳 + 色卡推荐；3MF 由本机回传 |

主站按钮在生产主机名下会链到 `https://stack.filament.ibaozi.com/#/stack`；本地 / 预览仍用同源 `#/stack`。

## 包怎么出（与既有 dist 包一致）

在合并后的 commit 上：

```bash
cd web && npm ci && npm run build
tar -czf fp-<shortsha>-dist.tgz -C dist .
```

静态根里需要有：`index.html`、`assets/`、`web-catalog.json`、`sku/`、`stack-smoke/`、`four-color-tray-map.json`（若 build 已拷入 public）。

## DNS / TLS（运维）

1. 为 `stack.filament.ibaozi.com` 加解析，指到与主站相同的边缘 / 机器。
2. 证书纳入该名字（已有通配或单独签发均可），**reload 前**确认链完整。
3. 主站证书与 server_name **不要动**，除非只是给同一份 cert 加 SAN。

## nginx（新 server 块，示例）

见同目录 `nginx-stack-subdomain.example.conf`。

要点：

- **新建** `server_name stack.filament.ibaozi.com;`，不要改 `filament.ibaozi.com` 块。
- `root` 可与主站共用同一 `web/dist`，或放同版本的一份拷贝。
- `location = / { return 302 /#/stack; }` 保证子域裸打开即叠色页。
- gzip / `/assets/` / `web-catalog.json` 缓存头与主站惯例一致。
- 改完：`nginx -t` → 备份 conf → reload。回滚即删掉该 server 块并 reload。

## 主站静态（可与子域同一次发版）

主站只换同一份 dist（含首页「打开叠色」按钮）。**不必**为叠色改主站 location；按钮是前端链出去的。

若本次 dist 还含真链/成本页等，按既有 `DEPLOY.md` / 打包 HANDOFF 换主站静态 + 必要时重启 `filament-picker serve`；环境变量与 `FP_*` 仍不动。

## 校验（部署后）

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://filament.ibaozi.com/
curl -sI https://stack.filament.ibaozi.com/ | head -n 20   # 期望 302 → /#/stack 或 200
curl -s -o /dev/null -w '%{http_code}\n' https://stack.filament.ibaozi.com/web-catalog.json
curl -s -o /dev/null -w '%{http_code}\n' https://stack.filament.ibaozi.com/stack-smoke/preview.png
```

浏览器：

1. 主站首页可见「打开叠色」，点击进入子域叠色页。
2. 子域直接打开即叠色 UI（烟测预览 / 导入回传 / 四槽推荐）。
3. 主站色卡浏览、`#/plan`、`#/cost`、模型预览登录门行为与发版前一致。

## 明确不要做

- 不要 force-push。
- 不要把 Lumina / opencv / scipy 装进公网机器。
- 不要改主站 server_name、不要删主站 model-proxy / limit_req。
- 未听到「现在部署」前，只合并代码 + 留本文即可。
