# 公开站与个人控制的边界

记录日期：2026-11-09（Asia/Tokyo）。

本文只记下已经定下来的拆分：公开耗材站做什么，个人打印控制放在哪，两边共享什么数据，以及什么不能嵌进本仓库。算法、阈值和文件名仍以 [`docs/SPEC.md`](SPEC.md) 为准。这里没写的能力，不要当成已承诺的功能。

## 两层

### 公开站

- 代码在本仓库。对外站点是 filament.ibaozi.com。
- 做这些事：选色；购买链接（拼多多优先，没有商品页就用搜索）；打印成本与 OFD 资料；模型浏览（`/models`，要登录）。
- 用手机浏览器就能打开，不要求先装应用。
- 不从公网一键把任务打到用户自己的打印机。

和现有文档的对应关系：

- 选色页、配色页、拼多多购买链接：[`docs/SPEC.md`](SPEC.md) §10.1、§10.2。
- 成本计算器与 OFD 离线结果：[`deploy/DEPLOY.md`](../deploy/DEPLOY.md)。许可在 [`data/ofd/LICENSE`](../data/ofd/LICENSE)。网站运行时不在线拉取 Open Filament Database。
- `/models` 的登录和资源边界：[`docs/model-preview/README.md`](model-preview/README.md)。那份说明里的样例是合成数据；真实模型导入不在该任务范围内。

### 个人控制

- 另一个仓库：`bambu-print-agent`。
- 跑在局域网或 Tailscale 上，不嵌进公开站，也不把那个仓库的代码放进本仓库。
- 负责真实打印机状态、开始打印、队列。

本仓库的实现约束见 [`docs/AGENTS.md`](AGENTS.md)：不 import、不读写 `bambu-print-agent`。[`docs/SPEC.md`](SPEC.md) §14 第 3 条仍然有效：对方仓库里的 `filament_id` / `color_source` 不在这里改。

## 共享数据

| 数据 | 约定 |
| --- | --- |
| 颜色 ID | 与 `bambu-print-agent` 共用。本仓库如何锁定 ID 见 [`docs/SPEC.md`](SPEC.md) §5.7（`data/ids.lock.json`）。对方怎么引用这些 ID，在对方仓库改。 |
| OFD / 目录 | 公开站用本仓库的耗材目录，加上离线导入的 Open Filament Database 结果（打印参数、补色）。 |
| 库存与标签 | 以后可以接 Spoolman 库存和 OpenPrintTag NFC。现在没有实现，公开站不要表现成已经有。 |

## 许可与嵌入

- 不要把 AGPL 项目整份嵌进公开产品。包括 Bambuddy、OctoPrint、Manyfold，以及同类整仓。
- PrintStream 一类界面只可以借鉴交互。PolyForm Noncommercial 不能当本产品的底座。
- 以后做库存时，优先对照 MIT / Apache 的实现（Spoolman、SpoolmanDB），不要把别的许可证整仓拷进来。

## 使用上的默认

- 手机浏览器直接打开色卡，不安装客户端。
- 上传图片或点选颜色之后，给出前若干条耗材推荐。条数以现有匹配参数为准，不在本文新定一个数。
- 推荐上一点就跳到拼多多商品页；没有真实商品页时退回搜索。规则见 [`docs/SPEC.md`](SPEC.md) §10.1。
- 选色、购买链接、成本不要求登录。登录只用于模型库，以及以后的个人库存。
- 默认不要求用户把打印机端口暴露到公网。个人控制走局域网或 Tailscale。

## 本仓库明确不做

- 从公开网页直接控制打印机。状态、开打、队列都不在这里做。
- 在公开服务器上保存用户的打印机凭据。

## 相关文档

- [`docs/SPEC.md`](SPEC.md) §5.7 颜色 ID；§10.1–§10.2 网站与拼多多链接；§14 第 3 条不改 `bambu-print-agent`。
- [`docs/AGENTS.md`](AGENTS.md)：实现时不碰 `bambu-print-agent`。
- [`docs/model-preview/README.md`](model-preview/README.md)：`/models` 登录与私有模型目录。
- [`deploy/DEPLOY.md`](../deploy/DEPLOY.md)、[`data/ofd/LICENSE`](../data/ofd/LICENSE)：OFD 离线数据与 MIT 许可。
