# 发布清单

这份清单给操作的人逐项打勾。本轮没有对生产执行删除或迁移。

## 代码和构建

- 分支 `cursor/phase1-chroma-preview-d7e2`，提交以本轮 `git rev-parse HEAD` 为准。
- wheel：在仓库根目录 `uv build --wheel --out-dir <目录>`。不要沿用旧哈希。
- 前端：在 `web/` 执行 `npm run build`，再把 `web/dist` 打成 tar。记录两个包的 SHA-256。
- 生产静态文件和 wheel 的来源必须是这次构建，不是更早一轮的 `d2dbf823` 或 `c8b1e0fd`。

## 默认安全开关

上线前确认进程环境是：

- `FILAMENT_PICKER_REGISTRATION=0`
- `FILAMENT_PICKER_SUBMISSIONS=0`
- `FILAMENT_PICKER_STEP=0`
- `FILAMENT_PICKER_PREVIEW_USER` 已设成现有预览账号，且不是占位符 `change-me-preview-user`
- `FILAMENT_PICKER_SESSION_SECRET` 已设，`FILAMENT_PICKER_SESSION_SECURE=1`

## 备份和完整性

按 `deploy/accounts.md` 复制认证库、模型库、原件、派生、账号目录、配色副本、正在运行的代码，并保存 `sha256sum`。备份完成前不要换文件。

## 迁移和回滚

- 首次启动会做一次 `assign-legacy-owner`。之后空 owner 不会再被当前环境变量认领。
- 回滚应用：换回备份的 wheel 和静态文件，开关保持关闭，新账号和新行留着。
- 只有旧程序读不了新列时，才把备份的库和文件一起恢复。先导出或只读，再由人确认。不要删除真实账号、模型或分享。

## 健康检查

- 未登录 `GET /api/models` 是 401。
- `GET /api/models/registration` 里 `enabled` 和 `submissions` 都是 false，`email_sent` 是 false。
- 预览账号能打开自己的模型；另一个账号打开同一 id 是 404。
- 没有分享 cookie 时 `GET /api/share/thumb` 是 401。
- 页面带 `noindex`。

## 生产上仍不能打勾

- 22 盘原件 `87f61f2c8f1331d9` 没有原文件，未做派生或配色副本。
- 真实 COS 桶没有用生产凭证测过。测试里的 HTTP 桩不是桶。
- 生产机 SSH 和 `FQDN:22` 仍不可达。不要把本机预览当成生产验收。
