from __future__ import annotations

from typing import Any

from .buy import price_text_for, purchase_links
from .config import REPO_ROOT

DEFAULT_WEB_CATALOG = REPO_ROOT / "web" / "public" / "web-catalog.json"
SKU_DIR = REPO_ROOT / "web" / "public" / "sku"


def _print_params(enrichment: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not enrichment:
        return {}
    raw = enrichment.get("entries")
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if isinstance(key, str) and isinstance(value, dict) and value
    }


def _sku_web_path(entry_id: str) -> str | None:
    """Return /sku/<id>.jpg if a locally cached thumbnail exists."""
    name = entry_id.replace("/", "__") + ".jpg"
    if (SKU_DIR / name).is_file():
        return "/sku/" + name
    return None


def export_entry(
    entry: dict[str, Any], print_params: dict[str, Any] | None = None
) -> dict[str, Any]:
    primary, alt = purchase_links(entry)
    exported: dict[str, Any] = {
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
        "url": primary,
        "alt_url": alt,
        "price": price_text_for(entry, primary),
        "img": _sku_web_path(entry["id"]),
    }
    if print_params:
        exported["print"] = print_params
    return exported


def export_web(catalog: dict[str, Any], enrichment: dict[str, Any] | None = None) -> dict[str, Any]:
    entries = [entry for entry in catalog["entries"] if entry["status"] == "active"]
    print_by_id = _print_params(enrichment)
    exported_entries = [export_entry(entry, print_by_id.get(entry["id"])) for entry in entries]
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
