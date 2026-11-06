from filament_picker.calibrate import series_color_collapse
from filament_picker.catalog import Catalog


def _entry(eid: str, brand: str, series: str, name: str) -> dict:
    return {
        "id": eid,
        "brand_slug": brand,
        "series_slug": series,
        "series_name": series,
        "name_en": name,
        "name_zh": None,
        "name_raw": name,
        "hex": [],
        "hex_source": None,
        "status": "active",
        "material": "PLA",
        "effects": [],
        "variant_image": None,
    }


def _catalog(entries: list[dict]) -> Catalog:
    return Catalog(
        generated_at="2026-11-06T00:00:00+09:00",
        entries=tuple(entries),
        by_id={e["id"]: e for e in entries},
    )


def test_series_color_collapse_detects_shared_brown() -> None:
    entries = [
        _entry(
            f"polymaker/ht-pla-pro/{n.lower().replace(' ', '-')}",
            "polymaker",
            "ht-pla-pro",
            n,
        )
        for n in ("Blue", "Pink", "Magenta", "Orange", "Green")
    ]
    extracted = {
        "results": {
            e["id"]: {
                "status": "ok",
                "hexes": ["#AE896C"],
                "confidence": 0.41,
            }
            for e in entries
        }
    }
    hits = series_color_collapse(_catalog(entries), extracted)
    assert len(hits) == 1
    assert hits[0]["n_close"] == 5
    assert hits[0]["brand_slug"] == "polymaker"


def test_series_color_collapse_allows_distinct_colors() -> None:
    pairs = [
        ("Blue", "#2E5084"),
        ("Pink", "#E39EB4"),
        ("Magenta", "#EA577F"),
        ("Orange", "#E57831"),
        ("Green", "#33A865"),
    ]
    entries = [
        _entry(f"polymaker/ht-pla-pro/{n.lower()}", "polymaker", "ht-pla-pro", n) for n, _ in pairs
    ]
    extracted = {
        "results": {
            e["id"]: {"status": "ok", "hexes": [hx], "confidence": 0.5}
            for e, (_, hx) in zip(entries, pairs, strict=True)
        }
    }
    assert series_color_collapse(_catalog(entries), extracted) == []
