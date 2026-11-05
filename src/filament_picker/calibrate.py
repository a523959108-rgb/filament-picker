from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import numpy as np

from .catalog import Catalog
from .ciede2000 import delta_e_2000
from .colorspace import hex_to_lab
from .config import REPO_ROOT
from .errors import ImageMissingError, ImageUnreadableError
from .extract import extract_colors

EXTRACTED_PATH: Path = REPO_ROOT / "data" / "extracted" / "extracted.json"
CALIBRATION_PATH: Path = REPO_ROOT / "data" / "qa" / "calibration.csv"
QA_SAMPLE_PATH: Path = REPO_ROOT / "data" / "qa" / "sample.html"


def _empty_result(image: str, error: str) -> dict[str, Any]:
    return {
        "image": image,
        "status": "skipped",
        "hexes": [],
        "confidence": 0,
        "share": 0,
        "spread": 0,
        "n_pixels": 0,
        "error": error,
    }


def run_extract(catalog: Catalog, now: str, limit: int | None = None) -> dict[str, Any]:
    candidates = sorted(
        (entry for entry in catalog.entries if entry.get("variant_image") is not None),
        key=lambda entry: entry["id"],
    )
    if limit is not None:
        candidates = candidates[:limit]

    results: dict[str, Any] = {}
    for entry in candidates:
        image = str(entry["variant_image"])
        try:
            extracted = extract_colors(Path(image), entry.get("effects", []))
        except (ImageMissingError, ImageUnreadableError) as exc:
            results[entry["id"]] = _empty_result(image, exc.code)
            continue
        results[entry["id"]] = {
            "image": image,
            "status": extracted.status,
            "hexes": list(extracted.hexes),
            "confidence": extracted.confidence,
            "share": extracted.share,
            "spread": extracted.spread,
            "n_pixels": extracted.n_pixels,
            "error": None,
        }
    return {"generated_at": now, "results": results}


def calibrate(catalog: Catalog, extracted: dict[str, Any]) -> list[dict[str, Any]]:
    extracted_results = extracted.get("results", {})
    rows: list[dict[str, Any]] = []
    for entry in sorted(catalog.entries, key=lambda item: item["id"]):
        source = entry.get("hex_source")
        catalog_hexes = entry.get("hex", [])
        result = extracted_results.get(entry["id"])
        if source not in {"official", "store_swatch"} or len(catalog_hexes) != 1:
            continue
        if not isinstance(result, dict) or result.get("status") != "ok":
            continue
        extracted_hexes = result.get("hexes", [])
        if not extracted_hexes:
            continue
        delta = float(delta_e_2000(hex_to_lab(catalog_hexes[0]), hex_to_lab(extracted_hexes[0])))
        rows.append(
            {
                "id": entry["id"],
                "hex_source": source,
                "catalog_hex": catalog_hexes[0],
                "extracted_hex": extracted_hexes[0],
                "delta_e": round(delta, 2),
                "confidence": result.get("confidence", 0),
            }
        )
    return rows


def _brand_slug(row: dict[str, Any]) -> str:
    brand = row.get("brand_slug")
    if isinstance(brand, str):
        return brand
    identifier = str(row["id"])
    brand = identifier.split("/", 1)[0]
    return "bambu" if brand == "bambu-lab" else brand


def _summary_line(prefix: str, values: list[float]) -> str:
    array = np.asarray(values, dtype=np.float64)
    return (
        f"{prefix} n={len(values)} median={np.median(array):.1f} p80={np.percentile(array, 80):.1f}"
    )


def summarize(rows: list[dict[str, Any]]) -> list[str]:
    store_values: dict[str, list[float]] = {}
    official_values: list[float] = []
    for row in rows:
        value = float(row["delta_e"])
        if row["hex_source"] == "official":
            official_values.append(value)
        elif row["hex_source"] == "store_swatch":
            store_values.setdefault(_brand_slug(row), []).append(value)

    lines = [
        _summary_line(f"store_swatch {brand}", store_values[brand])
        for brand in sorted(store_values)
    ]
    if official_values:
        lines.append(_summary_line("bambu", official_values))
    else:
        lines.append("bambu n=0 median=nan p80=nan")
    return lines


def _color_block(color: str, label: str) -> str:
    escaped_color = html.escape(str(color), quote=True)
    escaped_label = html.escape(label)
    return (
        f'<span title="{escaped_label}: {escaped_color}" '
        f'style="display:inline-block;width:32px;height:32px;background:{escaped_color};'
        'border:1px solid #888;margin:2px"></span>'
    )


def qa_sample(
    catalog: Catalog, extracted: dict[str, Any], n: int = 50, seed: int = 20261105
) -> str:
    extracted_results = extracted.get("results", {})
    by_id = {entry["id"]: entry for entry in catalog.entries}
    candidate_ids = sorted(
        entry_id
        for entry_id, result in extracted_results.items()
        if result.get("status") == "ok" and entry_id in by_id
    )
    count = min(n, len(candidate_ids))
    if count:
        chosen_indexes = np.random.default_rng(seed).choice(
            len(candidate_ids), size=count, replace=False
        )
        chosen_ids = sorted(candidate_ids[int(index)] for index in chosen_indexes)
    else:
        chosen_ids = []

    lines = [
        "<!doctype html>",
        '<html><head><meta charset="utf-8"><title>filament-picker QA sample</title></head><body>',
    ]
    for entry_id in chosen_ids:
        entry = by_id[entry_id]
        result = extracted_results[entry_id]
        image = html.escape(str(result.get("image", entry.get("variant_image", ""))), quote=True)
        blocks = "".join(_color_block(color, "extracted") for color in result.get("hexes", []))
        catalog_blocks = "".join(_color_block(color, "catalog") for color in entry.get("hex", []))
        lines.append(
            '<div style="margin:8px 0">'
            f'<img src="file://{image}" width="160"> '
            f"<span>extracted {blocks}</span> "
            f"<span>catalog {catalog_blocks}</span> "
            f"<span>{html.escape(entry_id)} "
            f"confidence={float(result.get('confidence', 0)):.3f}</span>"
            "</div>"
        )
    lines.append("</body></html>")
    return "\n".join(lines) + "\n"
