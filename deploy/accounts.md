# 账号、所有权和投稿

`FILAMENT_PICKER_REGISTRATION` 默认 `0`。关闭时没有注册入口，`POST /api/models/register` 返回 403。设为 `1` 才允许新账号。不发送邮件，也不做邮箱验证；响应里的 `email_sent` 永远是 false。

历史模型在第一次启动迁移 `assign-legacy-owner` 时划给 `FILAMENT_PICKER_PREVIEW_USER`。之后只有 `models.owner` 等于当前登录名的人能列表、打开、看缩略图、派生、下载、分享和收藏。新账号看不到这些原件。投稿写在 `accounts/{用户}/`，不进共享 `originals/`，也不进别人的库。

STEP 在没有本机 `freecadcmd` 时直接拒绝，不会把改了扩展名的文件当成已解析。

分享在使用时检查创建者是否仍是该模型的所有者、账号是否还在。失去所有权或账号被删后，已发出的链接返回「链接已失效」。

迁移可重复执行。回滚：

```sql
DELETE FROM schema_migrations WHERE id = 'assign-legacy-owner';
```

模型库里的 `owner` 列可以留着。认证库如果要从多账号回到只有预览账号，先停掉注册，再删除 `role = 'member'` 的用户及其 `share_grants`。不要删除 `favorites` 和 `display_schemes` 里预览账号的行。然后换回部署前备份的 wheel 和静态文件。

不要把这次开关在生产打开，也不要替外部的人注册。22 盘原件、真实对象存储和生产 SSH 仍未验证。
