from __future__ import annotations

from typing import Any

from .config import REPO_ROOT


def export_entry(entry: dict[str, Any]) -> dict[str, Any]:
    offers = entry["offers"]
    offer = offers[0] if offers else {}
    price = offer.get("price_text")
    return {
        "id": entry["id"],
        "b": entry["brand_slug"],
        "s": entry["series_name"],
        "m": entry["material"],
        "en": entry["name_en"],
        "zh": entry["name_zh"],
        "code": entry["code"],
        "py": entry["pinyin"],
        "pyi": entry["pinyin_initials"],
        "fam": entry["family"],
        "eff": entry["effects"],
        "hex": entry["hex"],
        "src": entry["hex_source"],
        "conf": entry["hex_confidence"],
        "url": offer.get("url"),
        "price": price if price else None,
    }


def export_web(catalog: dict[str, Any]) -> dict[str, Any]:
    entries = [entry for entry in catalog["entries"] if entry["status"] == "active"]
    exported_entries = [export_entry(entry) for entry in entries]
    used_brands = {entry["b"] for entry in exported_entries}
    brands = [
        {"slug": brand["slug"], "name": brand["name"]}
        for brand in catalog["brands"]
        if brand["slug"] in used_brands
    ]
    return {
        "generated_at": catalog["generated_at"],
        "brands": brands,
        "entries": exported_entries,
    }


DEFAULT_WEB_CATALOG = REPO_ROOT / "web" / "public" / "web-catalog.json"
