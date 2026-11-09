from __future__ import annotations

from typing import Any

APPROX_NOTE: str = "> 近似色 = 颜色来自店铺示意色或商品图取色，不是官方色值，请以实物为准。"


def _pick_text(pick: dict[str, Any], prefix: str) -> str:
    text = (
        f"{prefix}：{pick['brand_name']} {pick['series_name']} · {pick['name_display']}"
        f"（ΔE {float(pick['delta_e']):.1f}，{pick['label']}"
    )
    if pick.get("is_approx"):
        text += "，近似色"
    stock = pick.get("stock")
    if isinstance(stock, dict) and stock.get("in_stock") is True:
        text += "，库存有"
    text += "）"
    if pick.get("url") is not None:
        text += f"[购买]({pick['url']})"
    alt = pick.get("alt_url")
    if isinstance(alt, str) and alt.startswith(("http://", "https://")):
        text += f"[原链接]({alt})"
    return text


def build_reply_markdown(result: dict[str, Any]) -> str:
    if result.get("status") == "error":
        return str(result["error"]["message_zh"])

    palette = result.get("palette", [])
    lines = [f"### 配色方案（{len(palette)} 色）"]
    if result.get("card_url"):
        lines.append(f"![配色卡]({result['card_url']})")

    matches = {match["target_index"]: match for match in result.get("matches", [])}
    has_approx = False
    for index, target in enumerate(palette):
        lines.append(f"{index + 1}. `{target['hex']}` 占比 {round(target['share'] * 100)}%")
        picks = matches.get(target["index"], {}).get("picks", [])
        if not picks:
            lines.append("   - 暂无 ΔE ≤ 10 的耗材")
            continue
        for pick_index, pick in enumerate(picks):
            has_approx = has_approx or bool(pick.get("is_approx"))
            prefix = "推荐" if pick_index == 0 else "备选"
            lines.append("   - " + _pick_text(pick, prefix))

    option = result.get("single_series_option")
    if option is not None:
        lines.append(
            f"**同系列方案**：{option['brand_name']} {option['series_name']}"
            f"（最大 ΔE {float(option['max_delta_e']):.1f}）"
        )
    if has_approx:
        lines.append(APPROX_NOTE)
    lines.append(f"需要 {result['slots_used']} 个料槽。")
    return "\n".join(lines)
