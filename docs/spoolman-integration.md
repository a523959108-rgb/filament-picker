# Spoolman 集成设计：我的耗材柜

状态：只读库存已接到配色结果。公开站点默认关闭：`FP_SPOOLMAN_ENABLED` 不是 `1` / `true` / `yes` 时，推荐顺序、回复和页面都跟没接库存时一样。本文不修改 `docs/SPEC.md`，也不改 `MATCH_MAX_DE`。

Spoolman（<https://github.com/Donkie/Spoolman>）是 MIT 许可证的自托管耗材库存服务。filament-picker 继续做色卡和选色。库存放在另一台只在局域网或 Tailscale 里能访问的 Spoolman 上，由家里的人自己记账。

## 不做什么

- 不把 Spoolman 的管理员密码、API token，或带账号密码的 URL 放进公开网站、前端包、git、色卡链接。
- 不要求 Spoolman 对公网开放，也不把它和 filament-picker 绑在同一个进程里。
- 不在公开站点上代理 Spoolman 的管理接口。浏览器不直连 Spoolman。
- 不从公开站点改库存。这一版骨架只有 `GET /api/v1/spool`，没有 POST、PUT、DELETE。
- 不做登录后的「我的耗材柜」页面，不部署 Spoolman，不调用打印机。位置和剩余克数也不进公开响应；那一页留到以后，并且只给已登录的人看。
- 不因为没库存就把推荐色从结果里删掉。没货的颜色仍然保留购买链接。有货只是把对应推荐提前。
- 不在公开站（例如 filament.ibaozi.com）打开 `FP_SPOOLMAN_ENABLED`。要读库存的进程只跑在能访问局域网或 Tailscale 上那台 Spoolman 的私有主机。

## 部署

Spoolman 用它自己的官方镜像，单独跑。默认端口是它自己的 `7912`。只监听 LAN，或者只挂在 Tailscale 上。filament-picker 若要读库存，只在私有进程里配置下面的环境变量。公开站点默认不读。

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `FP_SPOOLMAN_ENABLED` | `0` | `1` / `true` / `yes` 才读取。其他非空值直接报错，避免写错被当成开启。 |
| `FP_SPOOLMAN_BASE_URL` | 空 | 根地址，可以带子路径，不包含 `/api/v1`。只允许 `http` 或 `https`。禁止用户名、密码、query、fragment。开启时必填，没有默认主机。 |
| `FP_SPOOLMAN_TIMEOUT_S` | `3` | 单次 GET 的超时秒数，必须是正数。 |

示例（私有主机上的环境，不进前端）：

```text
FP_SPOOLMAN_ENABLED=1
FP_SPOOLMAN_BASE_URL=http://spoolman.tailnet.ts.net:7912
```

以后如果 Spoolman 本身要求鉴权，token 只放在这台私有主机的环境变量里。这一版不读取、不保存任何 token。

## color_id 怎么对应到 Spoolman

filament-picker 的色号是目录条目的 `id`，形如 `bambu-lab/pla-basic/black-10101`，也就是 `{brand_slug}/{series_slug}/{color_segment}`，最长 190。规则在 `docs/SPEC.md` 和 `filament-catalog.schema.json`。

Spoolman 里：

- **filament** 是一种耗材（品牌 + 材料 + 颜色）。
- **spool** 是这一卷实物。剩余克数、位置、是否归档都在 spool 上。同一 filament 可以有多卷。

color_id 写在 filament 上，不写在某一卷上。

| filament-picker | Spoolman | 说明 |
| --- | --- | --- |
| `id`（color_id） | `filament.extra["filament_picker_color_id"]` | 首选。Spoolman 的 extra 值在线上是 JSON 编码字符串，文本字段要再解一次码。 |
| `id` | `filament.external_id` | 没有 extra 键时，若值本身符合 color_id 格式才采用。货号、EAN 这类短码忽略。`external_id` 最长 256，装得下 color_id。两个字段都有时以 extra 为准。 |
| `brand_name` / `brand_slug` | `filament.vendor.name` | 只在兜底匹配时用。接受目录里的品牌原名（如 `Bambu Lab`）和别名（如 `拓竹`、`三绿`）。 |
| `material` | `filament.material` | 大小写不敏感。目录里只有 `PLA` 和 `PETG`。 |
| `hex[0]` | `filament.color_hex` | Spoolman 不带 `#`，可以是 6 位或带 alpha 的 8 位。比较时取前 6 位并加上 `#`。无效色值当成没有颜色。 |
| — | `spool.remaining_weight` | 剩余克数。没有这个字段表示 Spoolman 算不出剩余重量（filament 没写净重）。 |
| — | `spool.location` | 位置，例如 `柜A`。空字符串当成没有位置。 |
| — | `spool.archived` | 归档卷不算出库。缺失或 null 视为未归档。 |

不要把 color_id 塞进 filament 的 `name` 或 `article_number`。这两项最长 64，装不下，也会和给人看的名字混在一起。

操作者以后在 Spoolman 里手工建档（这一版不会自动写入）：

1. vendor 用目录品牌名或别名。
2. filament 写上材料、`color_hex`，并把 color_id 放进 `extra.filament_picker_color_id`。方便的话再把同一值写入 `external_id`。
3. 每一卷 spool 写上剩余重量。Spoolman 只在 filament 有净重，或 spool 有 `initial_weight` 时才返回 `remaining_weight`。

## 读哪些接口

骨架只请求：

```http
GET {FP_SPOOLMAN_BASE_URL}/api/v1/spool
Accept: application/json
```

响应是 spool 对象数组。每一项里嵌着 filament、vendor，以及计算出来的 `remaining_weight`（克）。家里的柜子体积很小，先整表拉回再在本地过滤。以后如果卷数变多，可以再改成 Spoolman 的查询参数，例如 `filament.material` 或 `extra.filament_picker_color_id`。那不是这一版的事。

有库存的定义：未归档，并且 `remaining_weight` 是大于 0 的数。重量缺失或为 0 都不算出库，避免把没称过的卷推荐成「柜里有」。

多色 filament（`multi_color_hexes` 非空）不参加下面的颜色兜底，只认 color_id。目录条目若 `hex` 不是恰好一个，同样不参加兜底。

## 有库存时怎么推荐

配色结果仍然由现有 matcher 决定。库存只给这些结果加一个 `stock` 注解，并稳定排序：

1. **这支色号在柜里**：某卷的 color_id 相同，且该卷有库存。`stock.match` 为 `color_id`，`stock.in_stock` 为 true。同一色号有多卷时，取有库存且剩余克数更多的那一卷；克数相同取 spool id 较小者。
2. **柜里有接近的一卷**：没有任何卷写了这个 color_id，但有一卷品牌、材料都对得上，并且和目录第一色的 CIEDE2000 ΔE 不超过现有的 `MATCH_MAX_DE`（10）。`stock.match` 为 `brand_material_color`，`stock.in_stock` 仍为 false，`stock.nearby_in_stock` 为 true。这只表示「柜里有一支接近的」，不能说成就是这个色号。同一品牌同一材料下的两个黑色（例如 PLA Basic 和 PLA Matte）会落在这里。
3. **其余推荐保持原顺序**。包括明确没货的同一色号。已经写了 color_id 但剩余为 0 或已归档时，停在第 1 类的「没货」，不再退回去用接近色冒充这一支。

没库存的推荐不删除。公开页面上的购买链接照旧。

`stock` 的形状：

```json
{
  "in_stock": false,
  "nearby_in_stock": true,
  "match": "brand_material_color",
  "remaining_weight_g": 700.0,
  "location": "柜B",
  "spool_id": 5
}
```

`in_stock` 只在 `match == "color_id"` 且那一卷剩余重量大于 0 时为 true。

公开响应不带上面这整份对象。配色结果和 `/api/stock` 只留下两个布尔值，避免把柜子位置、剩余克数和 spool id 发给浏览器：

```json
{ "in_stock": true, "nearby_in_stock": false }
```

`nearby_in_stock` 为 true 时，这支推荐可以排到完全没注解的颜色前面，但页面不显示「库存有」。不能把接近色说成就是这个 color_id。

## 接在哪

仍只有原来的三个环境变量，没有新开关，也没有把 Spoolman 地址或密码放进前端包。关闭时 `load_spools()` 不连接，直接当没有卷。配置不合法、超时、HTTP 错误或响应无法解析时同样返回空元组，并写一条 warning。这两种情况下配色请求继续返回，顺序和字段跟没读到库存时一样，不把异常原文放进 JSON。

| 位置 | 行为 |
| --- | --- |
| `planner.run_plan` | matcher 给出 picks 之后、画色卡和写回复之前调用。读到卷才重排，并按新的第一名重算 `slots_used`。CLI 和 worker 都走这里。 |
| `POST /api/plan` | picks 上可选 `stock`。结果 schema 允许这个对象，不要求它出现。回复里只有 `in_stock` 为 true 时追加「库存有」。 |
| `GET /api/stock?ids=` | 逗号分隔的 color_id，最多 32 个。只返回真正有货的色号。关闭或失败时 HTTP 200，`{"ok": true, "hints": {}}`。 |
| `web` 图片配色 | `stock.in_stock === true` 时在该推荐旁显示「库存有」。购买链接保留。 |
| `web` 颜色详情 | 打开时请求 `/api/stock`。失败或没有这条 hint 时不显示徽章。 |
| 已登录的模型配色 | `ModelPreview.match_colours` 用同一套重排。详情里同样只在 `in_stock` 时写「库存有」。 |

颜色详情和模型页都不直连 Spoolman。浏览器只打 filament-picker 自己的接口。

## 代码放在哪

| 文件 | 作用 |
| --- | --- |
| `src/filament_picker/spoolman.py` | 环境变量、只读客户端、响应解析、`load_spools`、`annotate_picks`、`in_stock_hints`。默认关闭。关闭时不发起连接。 |
| `src/filament_picker/planner.py` | 配色结果上的排序和公开 `stock`。 |
| `src/filament_picker/api.py` | `GET /api/stock`。`POST /api/plan` 经 `run_plan` 带上库存。 |
| `src/filament_picker/models.py` | 登录后的模型原配色使用同一排序。 |
| `src/filament_picker/reply.py` | 有货的推荐在括号里加「库存有」。 |
| `web/src/components/PlanPage.tsx`、`ColorDetail.tsx`、`ModelPreview.tsx` | 「库存有」徽章。 |
| `tests/test_spoolman.py` | 用注入的 opener 或替身 `urlopen` 测解析和排序。 |
| `tests/test_spoolman_plan.py` | 假 HTTP：开启时有货提前、关闭时不连接、Spoolman 挂了仍返回原方案、缺剩余重量不算有货、接近色不算同一个 color_id。 |

不要另加开关，也不要改 `MATCH_MAX_DE`。颜色兜底继续用这个现成阈值。

## 以后才做

- 登录后的库存汇总页：列出剩余克数和位置。这一版没有做。公开响应继续不带这两项。
- 可选：用 color_id 批量给 Spoolman 建 filament。那是写接口，要另开任务，并且仍然只跑在私有主机上。
