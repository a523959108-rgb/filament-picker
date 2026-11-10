# Lumina 购买桥接口

Lumina 预览完成后，可把各通道的颜色或耗材名称提交到选色站，由选色站返回耗材目录中的购买推荐。

## 请求

`POST /api/lumina/match`，请求头 `Content-Type: application/json`。

```json
{
  "channels": [
    {"label": "R", "hex": "#E94A39"},
    {"label": "Y", "hex": "#ECEF35", "name": "黄"},
    {"name": "Bambu PLA Basic 白"}
  ],
  "palette": "RYBW",
  "material": "PLA",
  "brand": "bambu-lab",
  "max_alternatives": 3
}
```

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `channels` | array | 必填，1–8 项。每项至少提供 `hex` 或 `name`。 |
| `channels[].label` | string/null | 可选，最多 16 个字符，原样回显。 |
| `channels[].hex` | string/null | 可选，`#RRGGBB` 或 `RRGGBB`，大小写均可。输出统一为大写并带 `#`。 |
| `channels[].name` | string/null | 可选，最多 80 个字符，原样回显。 |
| `palette` | string/null | 可选，`RYBW` 或 `CMYW`，大小写不敏感；输出大写。 |
| `material` | string/null | 可选，按材质大类过滤（取首个字母串，如 Lumina 的 `PLA Basic` → `PLA`），大小写不敏感；过滤后为空则忽略该条件。 |
| `brand` | string/null | 可选，品牌 slug 或名称（`bambu-lab`/`bambulab`/`Bambu Lab` 视为相同）；优先该品牌，无结果时回退全部品牌。 |
| `max_alternatives` | integer | 可选，0–5，默认 3。 |

## 成功响应

HTTP 200：

```json
{
  "schema_version": 1,
  "palette": "RYBW",
  "slots": [
    {
      "index": 0,
      "label": "R",
      "input_hex": "#E94A39",
      "input_name": null,
      "best": {
        "catalog_id": "bambu-lab/pla-matte/scarlet-red-11200",
        "brand": "Bambu Lab",
        "brand_slug": "bambu-lab",
        "series": "PLA Matte",
        "name": "猩红",
        "hex": "#DE4343",
        "delta_e": 5.06,
        "buy_url": "https://mobile.yangkeduo.com/goods.html?goods_id=...",
        "buy_url_kind": "pdd_goods",
        "other_urls": [],
        "price_text": null,
        "source": "tray_map"
      },
      "alternatives": [],
      "note": null
    }
  ],
  "disclaimer": "颜色为屏幕近似，ΔE 为 CIEDE2000，购买前请以商品页实物色为准。"
}
```

响应的 `slots` 顺序与请求一致，`index` 从 0 开始。`best` 可为 `null`，此时 `note` 会说明原因。`alternatives` 按 ΔE 升序，最多返回 `max_alternatives` 项；仅按名称匹配时 ΔE 为 `null`。`hex`、`input_hex` 均为规范化的大写 `#RRGGBB`，没有对应输入时为 `null`；`input_name` 为请求中的原文，没有对应输入时为 `null`。`source` 为 `tray_map`、`nearest` 或 `name`。

购买链接沿用目录的 `purchase_links` 和 `price_text_for`：拼多多商品页优先；没有商品页时使用拼多多搜索页，并把其他商店链接放入 `other_urls`。`buy_url_kind` 为 `pdd_goods`、`pdd_search` 或 `other`。

## 错误

参数不合法时返回 HTTP 422，body 固定为现有 API 使用的 FastAPI 错误结构：

```json
{
  "detail": [
    {"loc": ["body", "channels"], "msg": "channels must contain 1 to 8 items", "type": "value_error"}
  ]
}
```

以下情况均为 422：`channels` 为空或超过 8 项；通道不是对象、同时缺少 `hex` 和 `name`；hex 不是六位 RGB；`label` 超过 16 个字符；`name` 超过 80 个字符；`palette` 不是 `RYBW` 或 `CMYW`；`max_alternatives` 不是整数或不在 0–5 范围内。

## CORS

仅允许精确的 Origin `https://stack.filament.ibaozi.com`。允许 `POST` 和 `OPTIONS`，允许请求头 `Content-Type`，不携带 credentials。允许 Origin 的预检和实际 `/api/lumina/match` 响应带 `Access-Control-Allow-Origin`；其他 Origin 不带该响应头（但都带 `Vary: Origin`，防止共享缓存串用）。CORS 处理只作用于 `/api/lumina/` 路径，其他 API 路由不改变响应头。

## 匹配规则与限制

- 提供 hex 时，在状态为 `active`、有 hex、有可售 offer 的目录条目中计算 CIEDE2000。候选按以下键排序：ΔE（先四舍五入到两位小数）升序；有拼多多商品页（`pdd_goods`）优先；普通耗材优先于特殊料；请求的 `brand` 优先（没有请求品牌且命中托盘映射时使用映射的 `brand_preference`）；命中托盘映射时 `series_preference`（当前为 `PLA Basic`）优先；最后按 `catalog_id` 字典序。ΔE 输出保留两位小数。
- 特殊料依据目录已有字段判断：`series_name`、`name_raw`、`name_en`、`name_zh` 中含 `Translucent`、`Transparent`、`Clear`、`透明`、`半透`、`Dynamic`、`Color Changing`、`Silk Dual`、`Dual Color`、`Gradient`、`渐变`、`Rainbow`、`Multicolor` 等标记，或 `effects` 含 `translucent`、`gradient`、`color_change`、`multi` 的条目会排在普通耗材之后。
- `best` 与 alternatives 去重：同一 hex 只保留一个条目；同品牌同系列同名也只保留一个条目。`best` 不会再次出现在 alternatives 中。
- 提供 palette 且正好四个通道时，按以下规则把通道对应到 `data/four-color-tray-map.json` 的槽位（Lumina LUT 的通道顺序与托盘映射不同，例如 Lumina 是 W,R,Y,B、映射是 R,Y,B,W，所以**不按位置对应**）：① 四个通道都带 `label` 且都能匹配时按 label 对应（槽位字母、映射中英文名，或常用颜色词 Red/Yellow/Blue/White/Cyan/Magenta 及 红/黄/蓝/白/青/品红，大小写不敏感）；② 否则（含 label 匹配失败）四个通道都带 hex 时，取使四个通道与槽位 hex 的 CIEDE2000 总和最小的一一对应，若任一通道 ΔE 超过 30 则不使用映射；③ 只有名字、无 label 无 hex 时按映射的槽位顺序对应。对应成功的槽位优先使用映射的 `catalog_id`，`source` 为 `tray_map`，ΔE 仍按输入 hex 计算。托盘映射条目不可用或对应失败时回退普通最近邻。
- 命中托盘映射时，alternatives 先按 `brand_preference` 保留同品牌候选，不足数量时再补其他品牌；每组内部仍按上述排序键排序。
- 只有 name 时按现有名称规范化逻辑匹配，`source` 为 `name`，ΔE 为 `null`；同时有 hex 和 name 时以 hex 为准。
- `brand` 先限制到指定品牌；该品牌没有可用结果时回退全部品牌，并在 `note` 中说明。`material` 按目录材质过滤，大小写不敏感。
- 托盘映射的 `status` 为 `pending_manual_confirm` 时，槽位 `note` 为「该映射待人工确认」；`status` 为 `same_brand_fallback` 时，`note` 会说明 LUT 名义色 ΔE 超阈并已换同品牌近色。该说明与品牌回退说明以「；」连接。
- 无 hex 或无可售 offer 的条目不参与推荐；目录条目必须为 `active`，并至少有一个可用购买 URL。
- 请求最多 8 个通道，alternatives 最多 5 个；接口不访问外部网络，购买链接来自目录快照或拼多多搜索 URL。
