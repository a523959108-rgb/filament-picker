# 账号、所有权和投稿

两个开关互不影响，默认都是关：

- `FILAMENT_PICKER_REGISTRATION=0`：没有注册入口，`POST /api/models/register` 返回 403。
- `FILAMENT_PICKER_SUBMISSIONS=0`：画廊不显示投稿表单，`POST /api/models/submissions` 返回 403「投稿未开放」。

不发送邮件，也不做邮箱验证；响应里的 `email_sent` 永远是 false。

历史模型只在第一次启动、迁移 `assign-legacy-owner` 尚未记录时，把当时 `owner` 为空的行写成当时的 `FILAMENT_PICKER_PREVIEW_USER`。这次写入记进 `schema_migrations`。之后改环境变量、读接口、空 `owner` 都不会再把模型划给另一个身份。空 `owner` 对谁都是 404。CLI 导入只在写入时、且该行 owner 仍为空时，填上当时配置的预览账号；重导入不改已经有主的行。

投稿文件在 `accounts/{用户}/`。STL 和 3MF 的解析、派生放在独立进程里，父进程最多等 25 秒，超时后杀掉整个进程组。ZIP 路径里的绝对路径、`..` 和反斜杠会被拒绝。XML 里的 DTD 会被拒绝。组件 `p:path` 若是 URL 或跳出压缩包，只报错，不会去抓。STEP 不是「缺 freecadcmd 所以拒绝」就算完成，见 `deploy/step-converter.md`。

分享在使用时检查创建者是否仍是该模型的所有者、账号是否还在。失去所有权或账号被删后，已发出的链接返回「链接已失效」。分享 cookie 只挂在 `/api/share`，`HttpOnly`、`SameSite=Strict`。

## 部署前备份

在换 wheel 和静态文件之前，由人复制这些东西到带版本号的目录，并记下 `sha256sum`：

- 认证库 `FILAMENT_PICKER_AUTH_DB`
- 模型库 `manifest.sqlite`
- `originals/`、`derived/`、`accounts/`、`scheme-copies/`
- 正在运行的 wheel 和前端静态文件

迁移是加列和加表：`models.owner`、`schema_migrations`、`share_grants`、`share_sessions`、`submissions`。重复执行不会清行。

认证库如果停在「`users` 是 0 行、`users_legacy` 还有旧 Argon2id 行」，那是 `0af7359` 的迁移把改名和建表提交了，却在连接关闭时回滚了复制。原密码哈希还在 `users_legacy`，没有被改写。登录只查 `users`，所以返回 401。修复版会在一个事务里把 `users_legacy` 的用户名和原哈希抄回 `users`，抄完才删除 `users_legacy`。同名行以旧哈希为准，不用间隙里新建的哈希。环境变量不用改，也不要执行 `auth create-user`，那个命令会在表还是空的时候写进一把新密码。

修复前先停进程，把认证库文件整份复制出来并记下 `sha256sum`。再换 wheel、启动。用原来的密码登录一次。不要重置密码。

回滚：再停进程，把那份认证库备份盖回去，装回备份的 wheel，启动。不要 `DELETE FROM users`，不要手工 `DROP TABLE users_legacy`，不要生成新密码。只回滚程序、不盖回认证库备份时，旧程序仍读 `users.password_hash`；修复一旦删掉 `users_legacy`，就只能靠这份备份回到修复前的文件。

## 回滚应用，保留新数据

正常回滚只换回部署前备份的 wheel 和静态文件，并确认两个开关仍是 0。不要删除 `member` 账号、模型、分享、收藏或配色。新表和新列留在库里。旧程序如果读不懂这些列，就不要单独回滚程序；把上面那份备份的库和文件一起换回去。那是一次完整恢复，会丢掉备份点之后的新数据，所以先导出或把站点改成只读，再由人决定。

不要执行 `DELETE FROM users`、`DELETE FROM share_grants` 或 `DELETE FROM schema_migrations` 来「回到单账号」。那些语句会丢掉用户数据，不是这次发布的回滚步骤。

不要在生产打开注册或投稿，也不要替外部的人注册。22 盘原件、真实对象存储和生产 SSH 仍未验证。
