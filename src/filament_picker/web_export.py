from __future__ import annotations

from typing import Any

from .config import REPO_ROOT

DEFAULT_WEB_CATALOG = REPO_ROOT / "web" / "public" / "web-catalog.json"
SKU_DIR = REPO_ROOT / "web" / "public" / "sku"


def _sku_web_path(entry_id: str) -> str | None:
    """Return /sku/<id>.jpg if a locally cached thumbnail exists."""
    name = entry_id.replace("/", "__") + ".jpg"
    if (SKU_DIR / name).is_file():
        return "/sku/" + name
    return None


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
        "img": _sku_web_path(entry["id"]),
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
