# 草稿，未发送，需志远确认后由志远本人发送

**建议收件渠道（来自 Lumina README）：** Lumina-Layers GitHub 仓库的公开 Issue/Discussions、官方 Discord 社区 <https://discord.gg/57whRe3C8G> 或官方 QQ 社区 <https://qm.qq.com/q/vocxOMTnj2>。请由志远选择一个正式渠道发送；本草稿不包含任何私人邮箱、电话或其他个人信息。

---

## 中文草稿

**主题：申请在自托管 filament-picker 实例中接入/镜像 Lumina 官方耗材云库**

Lumina-Layers 开发组您好：

我们是耗材选色站 **filament-picker（filament.ibaozi.com）**，一个非商业、小规模的公益站点。站点主要帮助用户按已有耗材目录选择颜色，并为开源打印工作流整理可复核的数据。以下身份信息请先由志远确认后再发送：

- 发送人署名：**[待志远确认]**
- 项目/组织称呼：**[待志远确认]**
- 所在地或时区（如需要）：**[待志远确认]**
- 公开项目页面：<https://filament.ibaozi.com>

我们计划部署 Lumina 的自托管 fork，代码地址为 <https://github.com/a523959108-rgb/filament-lumina>。部署在我们自己的服务器上，遵守 AGPL-3.0-only，保留 Lumina-Layers 的版权和署名，并在站点文档和生成物说明中按要求标注 Lumina。我们不会把官方访问凭证写入公开仓库，也不会把官方数据重新包装成闭源服务。

目前我们想申请贵组确认以下事项：

1. 是否允许这个自托管实例在获得授权的前提下接入或镜像 Lumina 官方耗材云库 Registry（包括官方耗材档案和相关元数据）？
2. 如果可以，适用的授权条件、署名文本/链接、允许的用途和数据保留范围是什么？
3. 对同步频率、缓存时间、请求并发、限流和错误重试是否有建议或硬性上限？我们愿意默认低频、缓存优先，并按贵组要求调整。
4. 官方耗材资料是否区分可匿名读取、需要 token 的频道和仅供维护者操作的接口？我们只会使用明确授权的读取方式，不会尝试绕过权限。
5. 如果暂时不能开放 Registry 接入，是否可以只在自托管实例中使用我们自己的离线材料 seed，并在以后按贵组发布的公开规则申请？

我们能回馈的内容包括：

- 提供真实部署环境中的可复现安装记录、兼容性问题和最小复现资料；
- 将选色站目录中的官方色号、来源和更新日期以可审计方式整理，发现错误时及时报告；
- 在获得许可后，按贵组指定格式贡献经过实际梯度色卡校准的耗材档案或测试结果；
- 遵守公开 Registry 的频率和署名要求，不进行商业转售，不把 Registry 当作用户数据采集渠道；
- 在站点文档、README 和相关截图中保留 Lumina-Layers 名称、项目链接及贵组指定的归属说明。

请告知合适的授权流程、技术文档或需要我们先完成的审核步骤。感谢你们维护 Lumina-Layers 及其材料生态。

此致

**[待志远确认的署名]**  
filament-picker 项目  
<https://filament.ibaozi.com>

---

## English draft

**Subject: Request to connect or mirror the official Lumina materials Registry from a self-hosted filament-picker instance**

Hello Lumina-Layers development team,

We maintain **filament-picker (filament.ibaozi.com)**, a non-commercial, small public-interest service that helps users choose colors from available filament catalogs and keeps reproducible data for open-source printing workflows. Please confirm the following identity details before sending:

- Sender name/signature: **[To be confirmed by Zhiyuan]**
- Project or organization name: **[To be confirmed by Zhiyuan]**
- Location or time zone, if needed: **[To be confirmed by Zhiyuan]**
- Public project page: <https://filament.ibaozi.com>

We plan to deploy a self-hosted fork of Lumina at <https://github.com/a523959108-rgb/filament-lumina>. The deployment will run on infrastructure we control. We will comply with AGPL-3.0-only, preserve Lumina-Layers copyright and attribution, and identify Lumina in our site documentation and generated-output notes. We will not place credentials in a public repository or turn official data into a closed-source resale service.

We would like to ask for your guidance and, if required, written permission on the following points:

1. May this self-hosted instance connect to or mirror the official Lumina materials Registry, including official material archives and metadata, under an authorized arrangement?
2. If so, what terms apply for use, attribution text/links, permitted purposes, and retention of mirrored data?
3. What synchronization interval, cache lifetime, concurrency, rate limits, and retry behavior should we follow? We are happy to use low-frequency, cache-first synchronization and adopt stricter limits.
4. Are there separate rules for anonymous read access, token-protected channels, and maintainer-only endpoints? We will use only explicitly authorized read methods and will not bypass access controls.
5. If Registry access is not available yet, may we use only our own offline material seed in the self-hosted instance and apply later through the public process you specify?

We can contribute back by:

- sharing reproducible installation logs, compatibility findings, and minimal reports from a real self-hosted deployment;
- publishing auditable color-code provenance and update dates from our catalog and reporting corrections promptly;
- contributing gradient-card-calibrated material archives or test results in the format you approve;
- respecting public Registry rate and attribution rules, with no commercial resale and no use of the Registry as a user-data collection channel; and
- keeping the Lumina-Layers name, project link, and any attribution wording you require in our documentation, README, and deployment screenshots.

Please let us know the appropriate authorization process, technical documentation, or review steps we should complete first. Thank you for maintaining Lumina-Layers and its material ecosystem.

Best regards,

**[Signature to be confirmed by Zhiyuan]**  
filament-picker project  
<https://filament.ibaozi.com>
