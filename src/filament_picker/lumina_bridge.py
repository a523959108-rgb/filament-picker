from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .buy import is_pdd_goods_url, price_text_for, purchase_links
from .catalog import Catalog
from .ciede2000 import delta_e_2000
from .colorspace import hex_to_lab
from .config import REPO_ROOT
from .names import nfkc, parse_color_name

LUMINA_DISCLAIMER = "颜色为屏幕近似，ΔE 为 CIEDE2000，购买前请以商品页实物色为准。"
ALLOWED_PALETTES = frozenset(("RYBW", "CMYW"))
TRAY_MAP_PATH = REPO_ROOT / "data" / "four-color-tray-map.json"
ALLOWED_ORIGIN = "https://stack.filament.ibaozi.com"

_HEX_INPUT_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")
_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class LuminaChannel:
    label: str | None
    hex: str | None
    name: str | None


@dataclass(frozen=True, slots=True)
class LuminaRequest:
    channels: tuple[LuminaChannel, ...]
    palette: str | None
    material: str | None
    brand: str | None
    max_alternatives: int


class LuminaValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("invalid Lumina match request")
        self.errors = errors


@dataclass(frozen=True, slots=True)
class _Candidate:
    entry: dict[str, Any]
    hex: str
    lab: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class _Ranked:
    candidate: _Candidate
    distance: float | None
    name_score: tuple[int, int, int, int, str] | None = None


def _issue(location: list[str | int], message: str) -> dict[str, Any]:
    return {"loc": ["body", *location], "msg": message, "type": "value_error"}


def _normalise_hex(value: str) -> str:
    if _HEX_INPUT_RE.fullmatch(value) is None:
        raise ValueError("hex must be a six-digit RGB value")
    return "#" + value.removeprefix("#").upper()


def _parse_request(payload: Any) -> LuminaRequest:
    if not isinstance(payload, dict):
        raise LuminaValidationError([_issue([], "request body must be an object")])

    errors: list[dict[str, Any]] = []
    raw_channels = payload.get("channels")
    channels: list[LuminaChannel] = []
    if not isinstance(raw_channels, list) or not 1 <= len(raw_channels) <= 8:
        errors.append(_issue(["channels"], "channels must contain 1 to 8 items"))
    elif any(not isinstance(item, dict) for item in raw_channels):
        errors.append(_issue(["channels"], "each channel must be an object"))
    else:
        for index, raw in enumerate(raw_channels):
            label = raw.get("label")
            name = raw.get("name")
            raw_hex = raw.get("hex")
            if label is not None and (not isinstance(label, str) or len(label) > 16):
                errors.append(
                    _issue(
                        ["channels", index, "label"],
                        "label must be at most 16 characters",
                    )
                )
                label = None
            if name is not None and (not isinstance(name, str) or len(name) > 80):
                errors.append(
                    _issue(
                        ["channels", index, "name"],
                        "name must be at most 80 characters",
                    )
                )
                name = None
            if raw_hex is not None and not isinstance(raw_hex, str):
                errors.append(_issue(["channels", index, "hex"], "hex must be a string"))
                raw_hex = None
            normal_hex: str | None = None
            if isinstance(raw_hex, str):
                try:
                    normal_hex = _normalise_hex(raw_hex)
                except ValueError as exc:
                    errors.append(_issue(["channels", index, "hex"], str(exc)))
            if isinstance(name, str) and not name.strip():
                errors.append(_issue(["channels", index, "name"], "name must not be empty"))
                name = None
            if normal_hex is None and name is None:
                errors.append(_issue(["channels", index], "channel requires hex or name"))
            channels.append(LuminaChannel(label, normal_hex, name))

    palette_value = payload.get("palette")
    palette: str | None = None
    if palette_value is not None:
        if not isinstance(palette_value, str) or palette_value.upper() not in ALLOWED_PALETTES:
            errors.append(_issue(["palette"], "palette must be RYBW or CMYW"))
        else:
            palette = palette_value.upper()

    material_value = payload.get("material")
    material: str | None = None
    if material_value is not None:
        if not isinstance(material_value, str) or not material_value.strip():
            errors.append(_issue(["material"], "material must be a non-empty string"))
        else:
            material = material_value.strip().upper()

    brand_value = payload.get("brand")
    brand: str | None = None
    if brand_value is not None:
        if not isinstance(brand_value, str) or not brand_value.strip():
            errors.append(_issue(["brand"], "brand must be a non-empty string"))
        else:
            brand = brand_value.strip().casefold()

    max_value = payload.get("max_alternatives", 3)
    if isinstance(max_value, bool) or not isinstance(max_value, int) or not 0 <= max_value <= 5:
        errors.append(
            _issue(
                ["max_alternatives"],
                "max_alternatives must be an integer from 0 to 5",
            )
        )
        max_value = 3

    if errors:
        raise LuminaValidationError(errors)
    return LuminaRequest(tuple(channels), palette, material, brand, max_value)


def _catalog_entries(catalog: Catalog | Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    if isinstance(catalog, Catalog):
        return catalog.entries
    entries = catalog.get("entries")
    if not isinstance(entries, (list, tuple)):
        return ()
    return tuple(entry for entry in entries if isinstance(entry, dict))


def _candidate(entry: dict[str, Any]) -> _Candidate | None:
    if entry.get("status") != "active":
        return None
    raw_hexes = entry.get("hex")
    if not isinstance(raw_hexes, list) or len(raw_hexes) != 1 or not isinstance(raw_hexes[0], str):
        return None
    try:
        color_hex = _normalise_hex(raw_hexes[0])
    except ValueError:
        return None
    offers = entry.get("offers")
    if not isinstance(offers, list) or not any(
        isinstance(offer, dict) and isinstance(offer.get("url"), str) and bool(offer["url"])
        for offer in offers
    ):
        return None
    return _Candidate(entry, color_hex, hex_to_lab(color_hex))


def _usable_candidates(
    request: LuminaRequest, entries: tuple[dict[str, Any], ...]
) -> tuple[list[_Candidate], bool]:
    all_candidates = [
        candidate for entry in entries if (candidate := _candidate(entry)) is not None
    ]
    if request.material is not None:
        all_candidates = [
            candidate
            for candidate in all_candidates
            if str(candidate.entry.get("material") or "").casefold() == request.material.casefold()
        ]
    if request.brand is None:
        return all_candidates, False
    branded = [
        candidate
        for candidate in all_candidates
        if str(candidate.entry.get("brand_slug") or "").casefold() == request.brand
    ]
    if branded:
        return branded, False
    return all_candidates, True


@lru_cache(maxsize=1)
def load_tray_map(path: Path = TRAY_MAP_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _mapped_id(request: LuminaRequest, index: int) -> str | None:
    if request.palette is None or len(request.channels) != 4:
        return None
    palette = load_tray_map().get("palettes", {}).get(request.palette)
    if not isinstance(palette, dict):
        return None
    slots = palette.get("slots")
    if not isinstance(slots, list) or len(slots) != 4:
        return None
    for channel, slot in zip(request.channels, slots, strict=True):
        if not isinstance(slot, dict) or not isinstance(slot.get("catalog_id"), str):
            return None
        if channel.label is not None and channel.label.upper() != slot.get("slot"):
            return None
    slot = slots[index]
    if not isinstance(slot, dict):
        return None
    return slot["catalog_id"]


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(nfkc(value))}


def _name_score(query: str, candidate: _Candidate) -> tuple[int, int, int, int, str] | None:
    entry = candidate.entry
    query_normal = nfkc(query).casefold()
    name_values = [
        value
        for value in (
            entry.get("name_raw"),
            entry.get("name_en"),
            entry.get("name_zh"),
            entry.get("code"),
        )
        if isinstance(value, str) and value
    ]
    aliases = entry.get("aliases")
    if isinstance(aliases, list):
        name_values.extend(value for value in aliases if isinstance(value, str) and value)
    normal_names = [nfkc(value).casefold() for value in name_values]
    if query_normal in normal_names:
        exact = 0
    elif any(query_normal == value.replace(" ", "") for value in normal_names):
        exact = 1
    elif any(query_normal in value or value in query_normal for value in normal_names):
        exact = 2
    else:
        exact = 3
    parsed = parse_color_name(query)
    parsed_values = [parsed.name_en, parsed.name_zh, parsed.code]
    query_tokens = _tokens(query)
    for value in parsed_values:
        if value:
            query_tokens.update(_tokens(value))
    name_tokens = set().union(*(_tokens(value) for value in name_values)) if name_values else set()
    context_values = [entry.get("brand_name"), entry.get("series_name"), entry.get("material")]
    context_tokens = set().union(
        *(_tokens(value) for value in context_values if isinstance(value, str))
    )
    name_overlap = len(query_tokens & name_tokens)
    context_overlap = len(query_tokens & context_tokens)
    if exact == 3 and name_overlap == 0 and context_overlap == 0:
        return None
    if exact == 3 and name_overlap == 0:
        return None
    name_length = min(
        (len(nfkc(value)) for value in name_values if query_tokens & _tokens(value)),
        default=10_000,
    )
    return (exact, -name_overlap, -context_overlap, name_length, str(entry.get("id") or ""))


def _distance(input_hex: str | None, candidate: _Candidate) -> float | None:
    if input_hex is None:
        return None
    return float(delta_e_2000(hex_to_lab(input_hex), candidate.lab))


def _name_for(entry: dict[str, Any]) -> str:
    for key in ("name_zh", "name_en", "name_raw"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return str(entry.get("id") or "")


def _buy_fields(entry: dict[str, Any]) -> tuple[str, str, list[str], str | None]:
    primary, alternate = purchase_links(entry)
    if is_pdd_goods_url(primary):
        kind = "pdd_goods"
    elif primary.startswith("https://mobile.pinduoduo.com/search_result.html?"):
        kind = "pdd_search"
    else:
        kind = "other"
    other_urls = [alternate] if alternate is not None else []
    return primary, kind, other_urls, price_text_for(entry, primary)


def _result_item(ranked: _Ranked, source: str) -> dict[str, Any]:
    entry = ranked.candidate.entry
    buy_url, buy_kind, other_urls, price_text = _buy_fields(entry)
    return {
        "catalog_id": entry["id"],
        "brand": entry.get("brand_name"),
        "brand_slug": entry.get("brand_slug"),
        "series": entry.get("series_name"),
        "name": _name_for(entry),
        "hex": ranked.candidate.hex,
        "delta_e": None if ranked.distance is None else round(ranked.distance, 2),
        "buy_url": buy_url,
        "buy_url_kind": buy_kind,
        "other_urls": other_urls,
        "price_text": price_text,
        "source": source,
    }


def _slot(
    request: LuminaRequest,
    index: int,
    candidates: list[_Candidate],
    brand_fallback: bool,
) -> dict[str, Any]:
    channel = request.channels[index]
    input_hex = channel.hex
    mapped = _mapped_id(request, index)
    notes: list[str] = []
    if brand_fallback and request.brand is not None:
        notes.append(f"brand {request.brand} 无可用结果，已回退全部品牌")

    if input_hex is not None:
        ranked = sorted(
            (_Ranked(candidate, _distance(input_hex, candidate)) for candidate in candidates),
            key=lambda item: (
                round(item.distance or 0.0, 8),
                str(item.candidate.entry.get("id") or ""),
            ),
        )
        source = "nearest"
    else:
        name_ranked = []
        for candidate in candidates:
            score = _name_score(channel.name or "", candidate)
            if score is not None:
                name_ranked.append(_Ranked(candidate, None, score))
        ranked = sorted(name_ranked, key=lambda item: item.name_score or (9, 0, 0, 10_000, ""))
        source = "name"

    if mapped is not None:
        mapped_candidate = next(
            (candidate for candidate in candidates if candidate.entry.get("id") == mapped),
            None,
        )
        mapped_ranked = next(
            (item for item in ranked if item.candidate.entry.get("id") == mapped),
            None,
        )
        if mapped_ranked is None and mapped_candidate is not None:
            mapped_ranked = _Ranked(mapped_candidate, _distance(input_hex, mapped_candidate))
        if mapped_ranked is not None:
            ranked = [
                mapped_ranked,
                *[item for item in ranked if item.candidate.entry.get("id") != mapped],
            ]
            source = "tray_map"

    if not ranked:
        notes.append("没有找到可购买的匹配耗材")
        note = "；".join(notes)
        return {
            "index": index,
            "label": channel.label,
            "input_hex": input_hex,
            "input_name": channel.name,
            "best": None,
            "alternatives": [],
            "note": note,
        }

    best = _result_item(ranked[0], source)
    if source == "tray_map":
        alternative_source = "nearest" if input_hex is not None else "name"
    else:
        alternative_source = source
    alternatives = [
        _result_item(item, alternative_source) for item in ranked[1 : request.max_alternatives + 1]
    ]
    return {
        "index": index,
        "label": channel.label,
        "input_hex": input_hex,
        "input_name": channel.name,
        "best": best,
        "alternatives": alternatives,
        "note": "；".join(notes) if notes else None,
    }


def match_request(payload: Any, catalog: Catalog | Mapping[str, Any]) -> dict[str, Any]:
    request = _parse_request(payload)
    candidates, brand_fallback = _usable_candidates(request, _catalog_entries(catalog))
    return {
        "schema_version": 1,
        "palette": request.palette,
        "slots": [
            _slot(request, index, candidates, brand_fallback)
            for index in range(len(request.channels))
        ],
        "disclaimer": LUMINA_DISCLAIMER,
    }


def cors_headers(origin: str | None, *, preflight: bool = False) -> dict[str, str]:
    if origin != ALLOWED_ORIGIN:
        return {}
    headers = {"Access-Control-Allow-Origin": ALLOWED_ORIGIN, "Vary": "Origin"}
    if preflight:
        headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        headers["Access-Control-Allow-Headers"] = "Content-Type"
    return headers
