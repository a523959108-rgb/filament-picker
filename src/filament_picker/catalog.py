from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .brands import BRAND_ORDER, BRAND_SLUGS
from .colorspace import hex_to_lab
from .config import HEX_CONF_MANUAL, HEX_CONF_OFFICIAL, HEX_CONF_STORE_SWATCH, REPO_ROOT
from .effects import detect_effects, detect_material
from .ids import RowInfo, build_row_infos, canonical, group_rows
from .ingest import InventorySeries, RawRow
from .validate import validate_json
from .variants import VariantIndex, build_variant_index, find_variant_image

CATALOG_PATH: Path = REPO_ROOT / "data" / "build" / "filament-catalog.json"
OVERRIDES_PATH: Path = REPO_ROOT / "data" / "manual_overrides.json"


class CatalogValidationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Catalog:
    generated_at: str
    entries: tuple[dict[str, Any], ...]
    by_id: dict[str, dict[str, Any]]


def _entry_hex(
    info: RowInfo,
    entry_id: str,
    overrides: dict[str, Any],
) -> tuple[list[str], str | None, float | None]:
    manual = overrides.get("hex", {}).get(entry_id)
    if manual is not None:
        return list(manual["hex"]), "manual", HEX_CONF_MANUAL
    if info.row.hexes:
        hexes = [f"#{value.upper()}" for value in info.row.hexes]
        if info.brand_slug == "bambu-lab":
            return hexes, "official", HEX_CONF_OFFICIAL
        confidence = overrides.get("store_swatch_confidence", {}).get(
            info.brand_slug, HEX_CONF_STORE_SWATCH
        )
        return hexes, "store_swatch", confidence
    return [], None, None


def _round_lab(hex_color: str) -> list[float]:
    return [round(float(value), 2) for value in hex_to_lab(hex_color)]


def build_entry(
    group: list[RowInfo],
    entry_id: str,
    variant_index: VariantIndex,
    overrides: dict[str, Any],
    extracted: dict[str, Any] | None,
) -> dict[str, Any]:
    del extracted
    info = canonical(group)
    parsed = info.parsed
    hexes, hex_source, hex_confidence = _entry_hex(info, entry_id, overrides)
    variant_image = find_variant_image(variant_index, info)
    if variant_image is None:
        for candidate in group:
            variant_image = find_variant_image(variant_index, candidate)
            if variant_image is not None:
                break
    aliases: list[str] = []
    for candidate in group:
        if candidate is not info and candidate.row.color_raw not in aliases:
            aliases.append(candidate.row.color_raw)
    offers: list[dict[str, str | None]] = []
    for candidate in group:
        offer = {
            "channel": candidate.row.channel,
            "url": candidate.row.url,
            "price_text": candidate.row.price_text,
        }
        if offer not in offers:
            offers.append(offer)
    entry: dict[str, Any] = {
        "id": entry_id,
        "dedup_key": info.dedup_key,
        "status": "active",
        "brand_slug": info.brand_slug,
        "brand_name": info.row.brand,
        "series_name": info.row.series,
        "series_slug": info.series_slug,
        "material": detect_material(info.row.series),
        "name_raw": info.row.color_raw,
        "name_en": parsed.name_en,
        "name_zh": parsed.name_zh,
        "code": parsed.code,
        "pinyin": None,
        "pinyin_initials": None,
        "family": info.row.family,
        "effects": list(detect_effects(info.row.series, info.row.color_raw, info.row.family)),
        "hex": hexes,
        "hex_source": hex_source,
        "hex_confidence": hex_confidence,
        "lab": _round_lab(hexes[0]) if hexes else None,
        "offers": offers,
        "variant_image": variant_image,
        "aliases": aliases,
        "source_rows": [candidate.row.row_index for candidate in group],
    }
    if parsed.name_zh is not None:
        from .slug import pinyin_fields

        entry["pinyin"], entry["pinyin_initials"] = pinyin_fields(parsed.name_zh)
    return entry


def build_catalog(
    rows: list[RawRow],
    lock: dict[str, Any],
    inventory: list[InventorySeries],
    overrides: dict[str, Any],
    extracted: dict[str, Any] | None,
    now: str,
    source: dict[str, str],
) -> dict[str, Any]:
    infos = build_row_infos(rows)
    groups = group_rows(infos)
    lock_entries = lock.get("entries")
    if not isinstance(lock_entries, dict):
        raise CatalogValidationError("ids lock has no entries; please run assign-ids first")
    variant_index = build_variant_index(inventory)
    entries: list[dict[str, Any]] = []
    for dedup_key, group in groups.items():
        lock_entry = lock_entries.get(dedup_key)
        if lock_entry is None or lock_entry.get("status") != "active":
            raise CatalogValidationError(
                f"missing active lock entry for {dedup_key}; please run assign-ids first"
            )
        entries.append(build_entry(group, lock_entry["id"], variant_index, overrides, extracted))
    entries.sort(key=lambda entry: entry["id"])
    brands = [
        {"slug": slug, "name": next(name for name, value in BRAND_SLUGS.items() if value == slug)}
        for slug in BRAND_ORDER
    ]
    counts = {
        "entries": len(entries),
        "with_hex": sum(bool(entry["hex"]) for entry in entries),
        "official": sum(entry["hex_source"] == "official" for entry in entries),
        "store_swatch": sum(entry["hex_source"] == "store_swatch" for entry in entries),
        "image_extracted": sum(entry["hex_source"] == "image_extracted" for entry in entries),
        "manual": sum(entry["hex_source"] == "manual" for entry in entries),
    }
    catalog: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": now,
        "source": source,
        "counts": counts,
        "brands": brands,
        "entries": entries,
    }
    errors = validate_json("catalog", catalog)
    if errors:
        raise CatalogValidationError("; ".join(errors[:20]))
    return catalog


def write_catalog(path: Path, catalog: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_catalog(path: Path) -> Catalog:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogValidationError(f"unable to read catalog {path}") from exc
    errors = validate_json("catalog", catalog)
    if errors:
        raise CatalogValidationError("; ".join(errors[:20]))
    entries = tuple(catalog["entries"])
    return Catalog(catalog["generated_at"], entries, {entry["id"]: entry for entry in entries})
