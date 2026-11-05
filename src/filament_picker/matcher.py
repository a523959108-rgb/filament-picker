from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog import Catalog
from .ciede2000 import delta_e_2000
from .config import (
    LABEL_THRESHOLDS,
    MATCH_EXCLUDE_EFFECTS,
    MATCH_MAX_DE,
    MATCH_MIN_CONF,
    SOURCE_RANK,
)
from .errors import NoMatchError
from .note_parser import Params
from .palette import PaletteColor


@dataclass(frozen=True, slots=True)
class MatchResult:
    matches: list[dict[str, Any]]
    single_series_option: dict[str, Any] | None
    slots_used: int
    warnings: tuple[str, ...]


def eligible(entry: dict[str, Any], params: Params) -> bool:
    if entry.get("status") != "active" or len(entry.get("hex", [])) != 1:
        return False
    if entry.get("material") not in params.materials:
        return False
    if params.brands and entry.get("brand_slug") not in params.brands:
        return False
    if set(entry.get("effects", ())) & set(MATCH_EXCLUDE_EFFECTS):
        return False
    if entry.get("hex_source") == "official":
        return True
    return bool(
        params.allow_approx
        and entry.get("hex_confidence") is not None
        and entry["hex_confidence"] >= MATCH_MIN_CONF
    )


def label_for(delta_e: float) -> str | None:
    for index, (limit, label) in enumerate(LABEL_THRESHOLDS):
        if delta_e < limit or (index == len(LABEL_THRESHOLDS) - 1 and delta_e <= limit):
            return label
    return None


def name_display(entry: dict[str, Any]) -> str:
    parts = [value for value in (entry.get("name_zh"), entry.get("name_en")) if value]
    display = " ".join(parts) if parts else entry.get("name_raw", "")
    code = entry.get("code")
    if code:
        display = f"{display} ({code})"
    return display


def _distance(target: PaletteColor, entry: dict[str, Any]) -> float:
    return float(delta_e_2000(target.lab, entry["lab"]))


def _pick(entry: dict[str, Any], distance: float) -> dict[str, Any]:
    offers = entry.get("offers", [])
    offer = offers[0] if offers else None
    return {
        "id": entry["id"],
        "brand_name": entry["brand_name"],
        "series_name": entry["series_name"],
        "name_display": name_display(entry),
        "hex": entry["hex"][0],
        "hex_source": entry["hex_source"],
        "delta_e": round(distance, 2),
        "label": label_for(distance),
        "is_approx": entry["hex_source"] != "official",
        "url": offer["url"] if offer is not None else None,
        "price_text": offer["price_text"] or None if offer is not None else None,
    }


def _single_series_option(
    targets: list[PaletteColor], candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in candidates:
        key = (entry["brand_slug"], entry["series_slug"])
        groups.setdefault(key, []).append(entry)

    options: list[tuple[float, float, str, dict[str, Any]]] = []
    for (brand_slug, series_slug), entries in groups.items():
        distances = [[(_distance(target, entry), entry) for entry in entries] for target in targets]
        best = [min(values, key=lambda item: (item[0], item[1]["id"])) for values in distances]
        minimums = [distance for distance, _ in best]
        if any(distance > MATCH_MAX_DE for distance in minimums):
            continue
        representative = entries[0]
        picks = [
            {
                "target_index": target.index,
                "id": entry["id"],
                "delta_e": round(distance, 2),
            }
            for target, (distance, entry) in zip(targets, best, strict=True)
        ]
        option = {
            "brand_name": representative["brand_name"],
            "series_name": representative["series_name"],
            "max_delta_e": round(maximum := max(minimums), 2),
            "picks": picks,
        }
        options.append(
            (maximum, sum(minimums) / len(minimums), f"{brand_slug}/{series_slug}", option)
        )

    if not options:
        return None
    return min(options, key=lambda item: (item[0], item[1], item[2]))[3]


def match_palette(palette: list[PaletteColor], catalog: Catalog, params: Params) -> MatchResult:
    candidates = [entry for entry in catalog.entries if eligible(entry, params)]
    matches: list[dict[str, Any]] = []
    warnings: list[str] = []
    chosen_ids: set[str] = set()

    for target in palette:
        ranked = sorted(
            (
                (distance, entry)
                for entry in candidates
                if (distance := _distance(target, entry)) <= MATCH_MAX_DE
            ),
            key=lambda item: (round(item[0], 4), SOURCE_RANK[item[1]["hex_source"]], item[1]["id"]),
        )
        picks = [_pick(entry, distance) for distance, entry in ranked[: params.per_color]]
        if picks:
            chosen_ids.add(picks[0]["id"])
        else:
            warnings.append(f"NO_MATCH_FOR_COLOR:{target.index}")
        matches.append({"target_index": target.index, "picks": picks})

    if not any(match["picks"] for match in matches):
        raise NoMatchError()

    return MatchResult(
        matches=matches,
        single_series_option=_single_series_option(palette, candidates),
        slots_used=len(chosen_ids),
        warnings=tuple(warnings),
    )
