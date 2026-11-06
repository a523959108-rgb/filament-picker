"""Pinduoduo-first purchase links.

A real goods page already stored on an offer is kept as the buy URL. Every other
color points at a public Pinduoduo search page. The previous store or official
URL is kept as an alternate when it is an actual page. GitHub color-code tables
are not purchase links, and goods ids are never invented.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from .brands import BRAND_ALIASES

PDD_SEARCH_PREFIX: str = "https://mobile.pinduoduo.com/search_result.html?search_key="

# Brands whose aliases have no Chinese name. Values are the names used on Pinduoduo.
# Brands with a CJK alias in BRAND_ALIASES reuse that alias instead of this table.
BRAND_SEARCH_NAMES: dict[str, str] = {
    "polymaker": "宝丽玛",
    "eryone": "艾瑞欧",
    "kexcelled": "凯想",
}

_PDD_HOSTS = frozenset(
    {
        "mobile.pinduoduo.com",
        "pinduoduo.com",
        "www.pinduoduo.com",
        "mobile.yangkeduo.com",
        "yangkeduo.com",
        "www.yangkeduo.com",
    }
)
_GITHUB_HOSTS = frozenset({"github.com", "raw.githubusercontent.com"})
_CHANNEL_NOTES = ("（拼多多）", "(拼多多)")


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def brand_search_name(brand_slug: str, brand_name: str) -> str:
    """Chinese or common brand name for a Pinduoduo search."""
    override = BRAND_SEARCH_NAMES.get(brand_slug)
    if override:
        return override
    for alias in BRAND_ALIASES.get(brand_slug, ()):
        if _has_cjk(alias):
            return alias
    return brand_name or brand_slug


def is_pdd_goods_url(url: str) -> bool:
    """True for a Pinduoduo/Yangkeduo goods page with a numeric goods_id."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host not in _PDD_HOSTS or "goods" not in parsed.path.lower():
        return False
    goods_ids = parse_qs(parsed.query).get("goods_id", [])
    return any(item.isdigit() for item in goods_ids)


def is_github_color_table_url(url: str) -> bool:
    """True for a GitHub-hosted filaments_color_codes table, not a store page."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    return host in _GITHUB_HOSTS and "filaments_color_codes" in parsed.path.lower()


def _clean_series(series: str) -> str:
    text = series
    for note in _CHANNEL_NOTES:
        text = text.replace(note, " ")
    return " ".join(text.split())


def search_query(entry: dict[str, Any]) -> str:
    """Brand + series (and material when the series omits it) + color."""
    brand = brand_search_name(
        str(entry.get("brand_slug") or ""),
        str(entry.get("brand_name") or ""),
    )
    series = _clean_series(str(entry.get("series_name") or ""))
    material = str(entry.get("material") or "").strip()
    color = entry.get("name_zh") or entry.get("name_en") or ""
    color = str(color).strip()
    parts: list[str] = []
    if brand:
        parts.append(brand)
    if material and material.casefold() not in series.casefold():
        parts.append(material)
    if series:
        parts.append(series)
    joined = " ".join(parts)
    if color and color.casefold() not in joined.casefold():
        parts.append(color)
    return " ".join(parts)


def pdd_search_url(query: str) -> str:
    return PDD_SEARCH_PREFIX + quote(query, safe="")


def _offer_urls(entry: dict[str, Any]) -> list[str]:
    offers = entry.get("offers")
    if not isinstance(offers, list):
        return []
    urls: list[str] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        url = offer.get("url")
        if isinstance(url, str) and url:
            urls.append(url)
    return urls


def purchase_links(entry: dict[str, Any]) -> tuple[str, str | None]:
    """Return (primary buy URL, alternate store URL or None)."""
    urls = _offer_urls(entry)
    goods = [url for url in urls if is_pdd_goods_url(url)]
    primary = goods[0] if goods else pdd_search_url(search_query(entry))
    alt: str | None = None
    for url in urls:
        if url == primary or is_pdd_goods_url(url) or is_github_color_table_url(url):
            continue
        alt = url
        break
    return primary, alt


def price_text_for(entry: dict[str, Any], primary: str) -> str | None:
    """Price of the offer that supplied `primary`, otherwise offers[0]."""
    offers = entry.get("offers")
    if not isinstance(offers, list) or not offers:
        return None
    chosen = offers[0]
    for offer in offers:
        if isinstance(offer, dict) and offer.get("url") == primary:
            chosen = offer
            break
    if not isinstance(chosen, dict):
        return None
    price = chosen.get("price_text")
    if not isinstance(price, str) or price == "":
        return None
    return price
