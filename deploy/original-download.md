# 原件下载（服务器中转）

浏览器只请求同源 `GET /api/models/{id}/original`。服务先校验登录，再按模型或别名找到对象，用环境里的 COS 身份把字节流转给浏览器。响应里没有桶名、对象键、签名 URL，也不会 302 到对象存储。

包版本仍是 `0.3.0`。和现网的差别是这条下载路由。用 wheel 的 SHA-256 区分，不要只看版本号。没有新的 Python 依赖，COS 签名用标准库。

中文、空格和 `+`、`#` 这类对象键：发给 COS 的请求路径做百分号编码，签名里的路径用未编码原文。两边都编码会得到 `SignatureDoesNotMatch`。纯 ASCII 键两边相同。

`models.sha256` 不是原件字节的哈希，不能当作原件校验值，也不要写进映射。响应里的 `sha256` 和 `X-Content-SHA256` 只在 `FILAMENT_PICKER_COS_MAP` 该项带了 64 位十六进制 `sha256` 时才出现。

## 配置

写在服务自己的环境文件里，不要写进仓库：

| 变量 | 作用 |
| --- | --- |
| `FILAMENT_PICKER_COS_BUCKET` | 桶名 |
| `FILAMENT_PICKER_COS_REGION` | 默认 `ap-shanghai` |
| `FILAMENT_PICKER_COS_PREFIX` | 默认 `filament-picker/3mf-originals/20261107/` |
| `FILAMENT_PICKER_COS_SECRET_ID` | 已有密钥 ID |
| `FILAMENT_PICKER_COS_SECRET_KEY` | 已有密钥 |
| `FILAMENT_PICKER_COS_TOKEN` | 临时凭证才需要，可空 |
| `FILAMENT_PICKER_COS_TIMEOUT_SECONDS` | 默认 120 |
| `FILAMENT_PICKER_COS_MAP` | 可选 JSON。键是模型或别名 id，值是相对对象键，或 `{ "key", "sha256" }` |

对象键按这个顺序取，都不把结果返回给浏览器：

1. `FILAMENT_PICKER_COS_MAP` 里的 id，其次规范模型 id。
2. 否则用数据库里已有的 `models.source_relpath`，别名则用 `model_aliases.rel_path`。只接受相对路径且以 `.3mf` 或 `.stl` 结尾。`..`、绝对路径和 URL 都拒绝。
3. 若 `originals/{id}.3mf` 已经在模型目录里，直接读本地文件，不访问 COS。

没有可用键时，详情里的 `original.available` 为 false，按钮保持禁用。这不是「原件丢失」。仓库里没有提交 id 到内容哈希的对照表；如果桶里的对象名是内容哈希而不是 `source_relpath`，必须提供 `FILAMENT_PICKER_COS_MAP`。

不改 `plate_layout`，不新增表，不迁移。`web-catalog.json` 和 `sku/` 不用动。

## 安装与回滚

```sh
"$VENV/bin/pip" install --no-deps --force-reinstall ./filament_picker-0.3.0-py3-none-any.whl
```

然后只重启提供 `/models` 的进程。前端继续用已经批准的 `c520977`。那个版本会在 `original.available` 且 `url` 以 `/api/models/` 开头时启用「下载3MF」。

回滚：装回上一只 wheel（SHA-256 `9927e6c48b1ee94fce53a9cc89267e0a4de0cc8c8bb83834c8b0fa7fa985c9bb`），重启同一进程。清单、色卡和静态目录都不用改。
