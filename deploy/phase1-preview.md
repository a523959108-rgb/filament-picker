# 第一阶段预览：新界面和私人库增强

这是开发预览，不是生产上线。基线是已部署的后端 `67435e2` 和前端 `e2b942e`。本分支在其上增加界面和接口，不改生产机器，不合并。

## 本轮已实现

- 深色响应式界面：耗材选色、模型画廊、详情、登录，以及原有的拍照找耗材、图片配色、打印成本、叠色入口。
- 画廊每页 12/24/48、跳页、按真实 id 或标题搜索、按系列、作者、盘内材料类型筛选。
- 排序只用已有字段：编号、入库时间、盘数、颜色数。没有打印耗时，也没有虚构的 MDL 编号。
- 单一登录账号下的服务端收藏，换浏览器只要还用这个账号就能看到。
- 模型对比读取真实详情。颜色差是计算值。相同槽号不当成同一个零件。
- 槽位展示色可保存和清空。不改原件，不表示零件已换料。没有对应槽位会拒绝。
- 规格索引只列色卡目录里的参考值，缺的显示未知。
- 复制仍需登录的站内地址。
- 已有 GLB 时才出现归位、线框、剖切。没有网格就不显示这些按钮。
- 公开 `web-catalog.json` 可由浏览器缓存。`/api/` 和 `/models` 不进入这个缓存。
- 下载仍要求登录、`original.available`，以及同源 `/api/models/.../original`。没有映射哈希就不显示已校验。

## 接口

`GET /api/models` 增加查询参数 `material`、`sort`、`order`。`sort` 只能是 `id`、`created_at`、`plate_count`、`colour_count`。`order` 是 `asc` 或 `desc`。`q` 同时匹配标题和 id。响应里的 `series`、`authors`、`materials` 仍是可选项；本次请求的条件在 `query` 对象里。

收藏：`GET /api/models/favorites`，`PUT` 和 `DELETE /api/models/favorites/{id}`。

展示色：`GET` 和 `PUT /api/models/{id}/scheme`。请求体是 `{ "slots": [{ "plate_index", "slot", "hex" }] }`。空数组表示清除。

这些路由都在原有登录墙后面。未登录是 401。

## 数据与回滚

收藏和展示色是登录库里的新表 `favorites`、`display_schemes`，第一次使用时 `CREATE TABLE IF NOT EXISTS`。不改 `manifest.sqlite`，不改原件，不改 COS 对象。

回滚应用：装回 `67435e2` 的 wheel 和 `e2b942e` 的前端包，并在登录库执行：

```sql
DROP TABLE IF EXISTS display_schemes;
DROP TABLE IF EXISTS favorites;
```

不执行 DROP 也只是留下两张闲表，旧版本不会读它们。

## 尚未实现（批准的后续，不是本轮）

- 从真实原件离线生成网格和正视图。当前不能声称每个模型都有 GLB。
- 可下载的改色 3MF 副本。将来若做，必须另存，不覆盖原件和哈希，仍由服务器中转，且不能把改颜色说成改了物理材料。
- 投稿、注册、多账号、免登录分享。
- 仪器光谱、遥测、现场色差和打印机实测温度。
- 按打印耗时排序。库里没有这个字段。
- 36 条限额。全库继续分页，不隐藏已入库模型。
