"""Offline import from the Open Filament Database.

The site never downloads this data. `import_ofd` reads a local snapshot
(json or json.gz) plus an optional OrcaSlicer index, matches filaments to
catalog colors, and writes static JSON. Unmatched rows are counted and skipped.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from .ciede2000 import delta_e_2000
from .colorspace import HEX_RE, hex_to_lab
from .config import (
    HEX_CONF_OFD,
    HEX_CONF_STORE_SWATCH,
    MATCH_MAX_DE,
    REPO_ROOT,
    TZ,
)
from .extract import extract_colors

logger = logging.getLogger(__name__)

ENRICHMENT_PATH: Path = REPO_ROOT / "data" / "ofd" / "enrichment.json"
OFD_LICENSE_NAME = "MIT"
OFD_COPYRIGHT = "Copyright © 2025 OpenFilamentCollective"
OFD_URL = "https://github.com/OpenFilamentCollective/open-filament-database"
ORCA_PRESET_BASE = "https://api.openfilamentdatabase.org/orcaslicer/"

# Historical esun store-swatch calibration (SPEC §14.5): median ΔE 32.4 → 0.3.
ESUN_CONFIDENCE_FLOOR_DE: float = 32.4
ESUN_CONFIDENCE_FLOOR: float = 0.3
# p80 still above MATCH_MAX_DE: keep the remaining swatches out of recommendations.
ESUN_WIDE_TAIL_CONFIDENCE: float = 0.4

# Catalog brand slug → OFD brand slugs. Product lines published under a
# sibling brand (PolyLite, Panchroma, …) are listed explicitly.
BRAND_TO_OFD: dict[str, tuple[str, ...]] = {
    "bambu-lab": ("bambu_lab",),
    "polymaker": (
        "polymaker",
        "polylite",
        "polymide",
        "polysonic",
        "polyflex",
        "panchroma",
        "fiberon",
    ),
    "eryone": ("eryone",),
    "sunlu": ("sunlu",),
    "overture": ("overture",),
    "cailab": ("cai_lab",),
    "elegoo": ("elegoo",),
    "hatchbox": ("hatchbox",),
    "kexcelled": ("kexcelled",),
    "esun": ("esun_3d",),
    "anycubic": ("anycubic",),
    "proto-pasta": ("protopasta",),
    "amolen": ("amolen",),
    "atomic-filament": ("atomic_filament",),
    "creality": ("creality",),
    "jayo": ("jayo",),
    "prusament": ("prusament",),
    "tinmorry": ("tinmorry",),
}

_STOP = frozenset({"pla", "petg", "3d", "filament", "the", "series", "for", "and", "of", "a", "an"})
_CHANNEL_NOTE = re.compile(r"[（(]\s*拼多多\s*[）)]")
_PAREN = re.compile(r"[(（][^)）]*[)）]")
_NON_TOKEN = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
_NON_COLOR = re.compile(r"[^a-z0-9]+")
_GREY = re.compile(r"\bgrey\b")
_COLOR_NOISE = re.compile(r"\b(?:color|colour)\b")


@dataclass(frozen=True, slots=True)
class OfdVariant:
    name: str
    slug: str
    color_hex: str | None
    discontinued: bool


@dataclass(frozen=True, slots=True)
class OfdFilament:
    filament_id: str
    brand_slug: str
    material: str
    name: str
    density: float | None
    nozzle_min: float | None
    nozzle_max: float | None
    bed_min: float | None
    bed_max: float | None
    diameter_mm: float | None
    orca_url: str | None
    variants: tuple[OfdVariant, ...]


@dataclass(frozen=True, slots=True)
class EntryMatch:
    entry_id: str
    print_params: dict[str, Any]
    official_hex: str | None


@dataclass(frozen=True, slots=True)
class MatchResult:
    matches: tuple[EntryMatch, ...]
    stats: dict[str, int]


def series_tokens(name: str) -> tuple[str, ...]:
    """Normalized product-line tokens. Order is not significant to matching."""
    text = unicodedata.normalize("NFKC", name).lower().replace("™", " ").replace("®", " ")
    text = _CHANNEL_NOTE.sub(" ", text)
    text = text.replace("+", " plus ")
    text = _NON_TOKEN.sub(" ", text)
    raw = text.split()
    tokens: list[str] = []
    index = 0
    while index < len(raw):
        if index + 1 < len(raw) and raw[index] == "high" and raw[index + 1] == "speed":
            tokens.append("hs")
            index += 2
            continue
        if index + 1 < len(raw) and raw[index] == "carbon" and raw[index + 1] in {"fiber", "fibre"}:
            tokens.append("cf")
            index += 2
            continue
        token = raw[index]
        if token.endswith("tm") and len(token) > 4:
            token = token[:-2]
        if token not in _STOP and token:
            tokens.append(token)
        index += 1
    return tuple(tokens)


def tokens_match(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """True when two product lines are the same name, ignoring token order.

    A single extra ``plus`` is ignored when both sides still share another
    token (``ePLA-HS`` and ``ePLA+HS``). ``PLA`` does not match ``PLA+``,
    and ``PLA Tough`` does not match ``PLA Tough+`` — the caller prefers an
    exact token match before this fallback.
    """
    if sorted(left) == sorted(right):
        return True
    return _plus_equivalent(left, right)


def _plus_equivalent(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return _drop_plus(left) == sorted(right) or _drop_plus(right) == sorted(left)


def relaxed_series_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Drop an eSUN ``epla`` / ``estars`` prefix when the plain name is all OFD has."""
    relaxed: list[str] = []
    for token in tokens:
        if token == "epla":
            continue
        relaxed.append("stars" if token == "estars" else token)
    return tuple(relaxed)


def _drop_plus(tokens: tuple[str, ...]) -> list[str] | None:
    items = list(tokens)
    if "plus" not in items:
        return None
    items.remove("plus")
    if not items:
        return None
    return sorted(items)


def color_key(name: str) -> str:
    """Normalized color name. Empty when nothing comparable remains."""
    text = unicodedata.normalize("NFKC", name).lower()
    text = _PAREN.sub(" ", text)
    text = _NON_COLOR.sub(" ", text)
    text = _GREY.sub("gray", text)
    text = _COLOR_NOISE.sub(" ", text)
    return " ".join(text.split())


def confidence_from_median(median_de: float) -> float:
    """Map a median ΔE onto esun ``store_swatch_confidence``.

    Median ΔE at or below ``MATCH_MAX_DE`` (10) uses the default store-swatch
    confidence 0.8. The historical floor (median 32.4 → 0.3) is kept. Values
    in between are linear, rounded to 2 decimals.
    """
    if median_de <= MATCH_MAX_DE:
        return HEX_CONF_STORE_SWATCH
    if median_de >= ESUN_CONFIDENCE_FLOOR_DE:
        return ESUN_CONFIDENCE_FLOOR
    span = ESUN_CONFIDENCE_FLOOR_DE - MATCH_MAX_DE
    value = HEX_CONF_STORE_SWATCH - (median_de - MATCH_MAX_DE) / span * (
        HEX_CONF_STORE_SWATCH - ESUN_CONFIDENCE_FLOOR
    )
    return round(float(value), 2)


def esun_store_swatch_confidence(summary: dict[str, float]) -> float:
    """Confidence for eSUN colors that are still store swatches.

    The median alone can land above ``MATCH_MIN_CONF`` (0.5) and let those
    swatches into recommendations. A p80 above ``MATCH_MAX_DE`` means the
    tail is still wide, so the confidence stays at 0.4.
    """
    if float(summary["p80"]) > MATCH_MAX_DE:
        return ESUN_WIDE_TAIL_CONFIDENCE
    return confidence_from_median(float(summary["median"]))


def load_snapshot(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            text = handle.read()
    else:
        text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"OFD snapshot is not an object: {path}")
    return payload


def load_orca_urls(path: Path) -> dict[str, str]:
    """Map OFD filament id → absolute OrcaSlicer preset URL."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError(f"OrcaSlicer index has no profiles: {path}")
    urls: dict[str, str] = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        filament_id = profile.get("id")
        relative = profile.get("path")
        if isinstance(filament_id, str) and isinstance(relative, str) and relative:
            urls[filament_id] = ORCA_PRESET_BASE + relative.lstrip("/")
    return urls


def filaments_from_payload(
    payload: dict[str, Any], orca_urls: dict[str, str] | None = None
) -> tuple[OfdFilament, ...]:
    """PLA/PETG filaments from an OFD ``all.json`` document."""
    brands = {
        brand["id"]: brand
        for brand in payload.get("brands", [])
        if isinstance(brand, dict) and isinstance(brand.get("id"), str)
    }
    variants_by_filament: dict[str, list[OfdVariant]] = defaultdict(list)
    for variant in payload.get("variants", []):
        if not isinstance(variant, dict):
            continue
        filament_id = variant.get("filament_id")
        name = variant.get("name")
        if not isinstance(filament_id, str) or not isinstance(name, str):
            continue
        slug = variant.get("slug")
        variants_by_filament[filament_id].append(
            OfdVariant(
                name=name,
                slug=slug if isinstance(slug, str) else "",
                color_hex=_normalize_hex(variant.get("color_hex")),
                discontinued=bool(variant.get("discontinued")),
            )
        )
    diameters = _diameters_by_filament(payload)
    orca = orca_urls or {}
    filaments: list[OfdFilament] = []
    for filament in payload.get("filaments", []):
        if not isinstance(filament, dict):
            continue
        material = filament.get("material")
        if material not in {"PLA", "PETG"}:
            continue
        brand = brands.get(filament.get("brand_id"))
        filament_id = filament.get("id")
        name = filament.get("name")
        if brand is None or not isinstance(filament_id, str) or not isinstance(name, str):
            continue
        filaments.append(
            OfdFilament(
                filament_id=filament_id,
                brand_slug=str(brand.get("slug") or ""),
                material=str(material),
                name=name,
                density=_optional_float(filament.get("density")),
                nozzle_min=_optional_float(filament.get("min_print_temperature")),
                nozzle_max=_optional_float(filament.get("max_print_temperature")),
                bed_min=_optional_float(filament.get("min_bed_temperature")),
                bed_max=_optional_float(filament.get("max_bed_temperature")),
                diameter_mm=diameters.get(filament_id),
                orca_url=orca.get(filament_id),
                variants=tuple(variants_by_filament.get(filament_id, ())),
            )
        )
    return tuple(filaments)


def match_catalog(entries: list[dict[str, Any]], filaments: tuple[OfdFilament, ...]) -> MatchResult:
    """Match catalog entries to OFD filaments by brand, material, and name."""
    by_brand: dict[str, list[OfdFilament]] = defaultdict(list)
    for filament in filaments:
        by_brand[filament.brand_slug].append(filament)

    series_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if entry.get("status") not in {None, "active"}:
            continue
        key = (
            str(entry.get("brand_slug") or ""),
            str(entry.get("material") or ""),
            str(entry.get("series_name") or ""),
        )
        series_groups[key].append(entry)

    used_filament_ids: set[str] = set()
    matches: list[EntryMatch] = []
    matched_series = 0
    skipped_entries = 0
    color_matches = 0
    skipped_variants = 0
    considered_variants = 0

    for (brand, material, series_name), group in series_groups.items():
        filament = _match_filament(brand, material, series_name, by_brand)
        if filament is None:
            skipped_entries += len(group)
            continue
        used_filament_ids.add(filament.filament_id)
        matched_series += 1
        params = _print_params(filament)
        variant_by_color = _variant_index(filament)
        considered_variants += len(filament.variants)
        matched_variant_ids: set[int] = set()
        for entry in group:
            official = _match_color(entry, variant_by_color, matched_variant_ids)
            if official is not None:
                color_matches += 1
            if params or official is not None:
                matches.append(EntryMatch(str(entry["id"]), params, official))
            else:
                skipped_entries += 1
        skipped_variants += len(filament.variants) - len(matched_variant_ids)

    mapped_slugs = {slug for slugs in BRAND_TO_OFD.values() for slug in slugs}
    in_scope = [filament for filament in filaments if filament.brand_slug in mapped_slugs]
    skipped_filaments = sum(
        1 for filament in in_scope if filament.filament_id not in used_filament_ids
    )
    for filament in in_scope:
        if filament.filament_id not in used_filament_ids:
            skipped_variants += len(filament.variants)
            considered_variants += len(filament.variants)

    stats = {
        "ofd_filaments": len(in_scope),
        "ofd_variants": considered_variants,
        "matched_series": matched_series,
        "skipped_filaments": skipped_filaments,
        "matched_entries": len(matches),
        "skipped_entries": skipped_entries,
        "color_matches": color_matches,
        "skipped_variants": skipped_variants,
    }
    return MatchResult(tuple(matches), stats)


def apply_matches(
    catalog: dict[str, Any], result: MatchResult
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Fill missing hex, replace esun store swatches, and collect print params.

    Returns the updated catalog, print-param map, and esun comparison rows
    (old swatch vs official hex) recorded before replacement.
    """
    by_id = {entry["id"]: entry for entry in catalog["entries"]}
    print_params: dict[str, Any] = {}
    comparisons: list[dict[str, Any]] = []
    filled = 0
    replaced = 0
    for match in result.matches:
        entry = by_id.get(match.entry_id)
        if entry is None:
            continue
        if match.print_params:
            print_params[match.entry_id] = match.print_params
        if match.official_hex is None:
            continue
        action = _apply_hex(entry, match.official_hex, comparisons)
        if action == "filled":
            filled += 1
        elif action == "replaced":
            replaced += 1
    _recount(catalog)
    stats = dict(result.stats)
    stats["hex_filled"] = filled
    stats["esun_replaced"] = replaced
    return catalog, print_params, comparisons


def esun_extract_deltas(
    catalog: dict[str, Any], sku_dir: Path, official_hex_by_id: dict[str, str]
) -> list[float]:
    """ΔE between a SKU photo extract and the OFD official hex, for esun only."""
    deltas: list[float] = []
    for entry_id, official in sorted(official_hex_by_id.items()):
        if not entry_id.startswith("esun/"):
            continue
        image = sku_dir / (entry_id.replace("/", "__") + ".jpg")
        if not image.is_file():
            continue
        entry = next((item for item in catalog["entries"] if item["id"] == entry_id), None)
        if entry is None:
            continue
        try:
            extracted = extract_colors(image, entry.get("effects") or [])
        except (OSError, ValueError) as exc:
            logger.warning("esun extract skipped %s: %s", entry_id, exc)
            continue
        if extracted.status != "ok" or len(extracted.hexes) != 1:
            continue
        deltas.append(float(delta_e_2000(hex_to_lab(official), hex_to_lab(extracted.hexes[0]))))
    return deltas


def swatch_deltas(comparisons: list[dict[str, Any]]) -> list[float]:
    return [
        float(delta_e_2000(hex_to_lab(row["swatch_hex"]), hex_to_lab(row["official_hex"])))
        for row in comparisons
    ]


def summarize_deltas(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    array = np.asarray(values, dtype=np.float64)
    return {
        "n": float(len(values)),
        "median": round(float(np.median(array)), 2),
        "p80": round(float(np.percentile(array, 80)), 2),
    }


def build_enrichment(
    *,
    payload: dict[str, Any],
    snapshot_sha256: str,
    generated_at: str,
    stats: dict[str, Any],
    print_params: dict[str, Any],
    coverage_before: dict[str, int],
    coverage_after: dict[str, int],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "source": {
            "name": "Open Filament Database",
            "license": OFD_LICENSE_NAME,
            "copyright": OFD_COPYRIGHT,
            "url": OFD_URL,
            "dataset_version": str(payload.get("version") or ""),
            "dataset_generated_at": str(payload.get("generated_at") or ""),
            "snapshot_sha256": snapshot_sha256,
        },
        "stats": stats,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "esun_calibration": calibration,
        "entries": {key: print_params[key] for key in sorted(print_params)},
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def coverage(entries: list[dict[str, Any]]) -> dict[str, int]:
    with_hex = sum(1 for entry in entries if entry.get("hex"))
    return {"entries": len(entries), "with_hex": with_hex}


def import_ofd(
    snapshot: Path,
    catalog: dict[str, Any],
    *,
    orca_index: Path | None = None,
    sku_dir: Path | None = None,
    now: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], float | None]:
    """Match a snapshot onto a catalog dict. Returns catalog, enrichment, new esun confidence."""
    payload = load_snapshot(snapshot)
    orca_urls = load_orca_urls(orca_index) if orca_index is not None else {}
    filaments = filaments_from_payload(payload, orca_urls)
    before = coverage(catalog["entries"])
    result = match_catalog(catalog["entries"], filaments)
    updated, print_params, comparisons = apply_matches(catalog, result)
    after = coverage(updated["entries"])
    swatch = swatch_deltas(comparisons)
    method = "store_swatch_vs_official"
    deltas = swatch
    official_by_id = {
        row["id"]: row["official_hex"] for row in comparisons if row.get("official_hex")
    }
    # Also compare colors that were already OFD or just filled, when photos exist.
    for match in result.matches:
        if match.official_hex and match.entry_id.startswith("esun/"):
            official_by_id.setdefault(match.entry_id, match.official_hex)
    if sku_dir is not None and sku_dir.is_dir() and official_by_id:
        extracted = esun_extract_deltas(updated, sku_dir, official_by_id)
        if extracted:
            method = "sku_extract_vs_official"
            deltas = extracted
    summary = summarize_deltas(deltas)
    confidence: float | None = None
    if summary is not None:
        confidence = esun_store_swatch_confidence(summary)
    generated_at = now or datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
    calibration: dict[str, Any] = {
        "method": method,
        "historical_median_delta_e": ESUN_CONFIDENCE_FLOOR_DE,
        "historical_confidence": ESUN_CONFIDENCE_FLOOR,
        "compared": summary,
        "swatch_vs_official": summarize_deltas(swatch),
        "confidence_after": confidence,
    }
    stats = dict(result.stats)
    stats["hex_filled"] = after["with_hex"] - before["with_hex"]
    stats["esun_replaced"] = sum(1 for row in comparisons)
    enrichment = build_enrichment(
        payload=payload,
        snapshot_sha256=sha256_file(snapshot),
        generated_at=generated_at,
        stats=stats,
        print_params=print_params,
        coverage_before=before,
        coverage_after=after,
        calibration=calibration,
    )
    return updated, enrichment, confidence


def update_esun_confidence(overrides: dict[str, Any], confidence: float) -> dict[str, Any]:
    store = overrides.setdefault("store_swatch_confidence", {})
    if not isinstance(store, dict):
        raise ValueError("store_swatch_confidence must be an object")
    store["esun"] = confidence
    return overrides


def _apply_hex(
    entry: dict[str, Any], official_hex: str, comparisons: list[dict[str, Any]]
) -> str | None:
    if entry.get("hex_source") == "manual":
        return None
    if not entry.get("hex"):
        _set_ofd_hex(entry, official_hex)
        return "filled"
    if (
        entry.get("brand_slug") == "esun"
        and entry.get("hex_source") == "store_swatch"
        and isinstance(entry.get("hex"), list)
        and len(entry["hex"]) == 1
    ):
        comparisons.append(
            {
                "id": entry["id"],
                "swatch_hex": entry["hex"][0],
                "official_hex": official_hex,
            }
        )
        _set_ofd_hex(entry, official_hex)
        return "replaced"
    return None


def _set_ofd_hex(entry: dict[str, Any], official_hex: str) -> None:
    entry["hex"] = [official_hex]
    entry["hex_source"] = "ofd"
    entry["hex_confidence"] = HEX_CONF_OFD
    entry["lab"] = [round(float(value), 2) for value in hex_to_lab(official_hex)]


def _recount(catalog: dict[str, Any]) -> None:
    entries = catalog["entries"]
    catalog["counts"] = {
        "entries": len(entries),
        "with_hex": sum(bool(entry.get("hex")) for entry in entries),
        "official": sum(entry.get("hex_source") == "official" for entry in entries),
        "store_swatch": sum(entry.get("hex_source") == "store_swatch" for entry in entries),
        "image_extracted": sum(entry.get("hex_source") == "image_extracted" for entry in entries),
        "manual": sum(entry.get("hex_source") == "manual" for entry in entries),
        "ofd": sum(entry.get("hex_source") == "ofd" for entry in entries),
    }


def _match_filament(
    brand: str,
    material: str,
    series_name: str,
    by_brand: dict[str, list[OfdFilament]],
) -> OfdFilament | None:
    slugs = BRAND_TO_OFD.get(brand)
    if not slugs or material not in {"PLA", "PETG"}:
        return None
    wanted = series_tokens(series_name)
    candidates = [
        filament
        for slug in slugs
        for filament in by_brand.get(slug, [])
        if filament.material == material
    ]
    return _choose_filament(candidates, wanted)


def _choose_filament(candidates: list[OfdFilament], wanted: tuple[str, ...]) -> OfdFilament | None:
    stages: list[list[OfdFilament]] = [
        [
            filament
            for filament in candidates
            if sorted(series_tokens(filament.name)) == sorted(wanted)
        ],
        [
            filament
            for filament in candidates
            if _plus_equivalent(wanted, series_tokens(filament.name))
        ],
    ]
    relaxed = relaxed_series_tokens(wanted)
    if relaxed != wanted:
        stages.append(
            [
                filament
                for filament in candidates
                if sorted(series_tokens(filament.name)) == sorted(relaxed)
                or _plus_equivalent(relaxed, series_tokens(filament.name))
            ]
        )
    for stage in stages:
        found = {filament.filament_id: filament for filament in stage}
        if len(found) == 1:
            return next(iter(found.values()))
        if len(found) > 1:
            return None
    return None


def _variant_index(filament: OfdFilament) -> dict[str, list[OfdVariant]]:
    index: dict[str, list[OfdVariant]] = defaultdict(list)
    for variant in filament.variants:
        for key in {color_key(variant.name), color_key(variant.slug.replace("_", " "))}:
            if key:
                index[key].append(variant)
    return index


def _match_color(
    entry: dict[str, Any],
    variant_by_color: dict[str, list[OfdVariant]],
    matched_variant_ids: set[int],
) -> str | None:
    keys: list[str] = []
    for field in ("name_en", "name_raw"):
        value = entry.get(field)
        if isinstance(value, str) and value:
            key = color_key(value)
            if key and key not in keys:
                keys.append(key)
    variants: list[OfdVariant] = []
    seen: set[int] = set()
    for key in keys:
        for variant in variant_by_color.get(key, []):
            identity = id(variant)
            if identity not in seen:
                seen.add(identity)
                variants.append(variant)
    if not variants:
        return None
    active = [variant for variant in variants if not variant.discontinued]
    pool = active or variants
    hexes = {variant.color_hex for variant in pool if variant.color_hex}
    if len(hexes) != 1:
        return None
    for variant in pool:
        matched_variant_ids.add(id(variant))
    return next(iter(hexes))


def _print_params(filament: OfdFilament) -> dict[str, Any]:
    params: dict[str, Any] = {}
    nozzle = _range(filament.nozzle_min, filament.nozzle_max)
    bed = _range(filament.bed_min, filament.bed_max)
    if nozzle is not None:
        params["nozzle_c"] = nozzle
    if bed is not None:
        params["bed_c"] = bed
    if filament.density is not None:
        params["density_g_cm3"] = filament.density
    if filament.diameter_mm is not None:
        params["diameter_mm"] = filament.diameter_mm
    if filament.orca_url:
        params["orca_url"] = filament.orca_url
    return params


def _range(low: float | None, high: float | None) -> list[float] | None:
    if low is None or high is None:
        return None
    return [low, high]


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _normalize_hex(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("#"):
        text = "#" + text
    if HEX_RE.fullmatch(text) is None:
        return None
    return text.upper()


def _diameters_by_filament(payload: dict[str, Any]) -> dict[str, float]:
    variant_filament: dict[str, str] = {}
    for variant in payload.get("variants", []):
        if not isinstance(variant, dict):
            continue
        variant_id = variant.get("id")
        filament_id = variant.get("filament_id")
        if isinstance(variant_id, str) and isinstance(filament_id, str):
            variant_filament[variant_id] = filament_id
    buckets: dict[str, list[float]] = defaultdict(list)
    for size in payload.get("sizes", []):
        if not isinstance(size, dict):
            continue
        diameter = _optional_float(size.get("diameter"))
        variant_id = size.get("variant_id")
        if diameter is None or not isinstance(variant_id, str):
            continue
        filament_id = variant_filament.get(variant_id)
        if filament_id is not None:
            buckets[filament_id].append(round(diameter, 2))
    chosen: dict[str, float] = {}
    for filament_id, values in buckets.items():
        diameter = _mode(values)
        if diameter is not None:
            chosen[filament_id] = diameter
    return chosen


def _mode(values: list[float]) -> float | None:
    if not values:
        return None
    counts = Counter(values)
    best_count = counts.most_common(1)[0][1]
    leaders = [value for value, count in counts.items() if count == best_count]
    if len(leaders) != 1:
        return None
    return leaders[0]
