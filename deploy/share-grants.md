# 限时分享

默认没有分享。历史模型不会因为这次迁移变成公开。只有已登录、并且 `may_share_model` 允许的账号能为一个模型创建链接。当前这个函数只放行已经能打开模型库的预览账号；以后多账号时在这里改成按所有者判断，缺省仍应拒绝。

链接形如 `/models/s#令牌`。令牌只在创建响应里出现一次，库存的是 SHA-256。匿名打开后换成 HttpOnly cookie，后续封面、盘图、GLB、正视都再查这张 cookie。撤销或过期后这些请求失败。原件和配色副本默认不包含；创建时必须单独勾选。

迁移是给登录库加 `share_grants` 和 `share_sessions`，`CREATE TABLE IF NOT EXISTS`，可重复执行。不改收藏表和展示色表。

回滚：

```sql
DROP TABLE IF EXISTS share_sessions;
DROP TABLE IF EXISTS share_grants;
```

然后换回部署前备份的 wheel 和静态文件，重启提供 `/models` 的进程。不要删 `favorites` 或 `display_schemes`。不要把旧交接记录里的 wheel 哈希当成当前生产回滚版本。

不要在生产库创建真实分享，也不要把链接发给别人。匿名暴力尝试超过 8 次会在 60 秒内返回 429。
