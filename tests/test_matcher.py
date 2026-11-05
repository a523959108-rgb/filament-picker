from __future__ import annotations

import json
from pathlib import Path

import pytest

from filament_picker.catalog import Catalog, build_catalog
from filament_picker.colorspace import hex_to_lab
from filament_picker.errors import NoMatchError
from filament_picker.ingest import load_inventory, load_rows, sha256_file
from filament_picker.matcher import MatchResult, eligible, label_for, match_palette, name_display
from filament_picker.note_parser import parse_note, resolve_params
from filament_picker.palette import PaletteColor
from filament_picker.validate import validate_json


@pytest.fixture(scope="session")
def catalog(repo_root: Path) -> Catalog:
    rows_path = repo_root / "data/raw/page_rows.json"
    inventory_path = repo_root / "data/raw/inventory.json"
    lock_path = repo_root / "data/ids.lock.json"
    rows = load_rows(rows_path)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    inventory = load_inventory(inventory_path)
    source = {
        "page_rows_sha256": sha256_file(rows_path),
        "inventory_sha256": sha256_file(inventory_path),
        "ids_lock_sha256": sha256_file(lock_path),
    }
    data = build_catalog(rows, lock, inventory, {}, None, "2026-11-05T12:00:00+09:00", source)
    return Catalog(
        generated_at=data["generated_at"],
        entries=tuple(data["entries"]),
        by_id={entry["id"]: entry for entry in data["entries"]},
    )


def _palette_color(index: int, hex_value: str) -> PaletteColor:
    return PaletteColor(
        index=index,
        hex=hex_value,
        lab=tuple(round(value, 2) for value in hex_to_lab(hex_value)),
        share=1.0,
    )


@pytest.mark.data
def test_matcher_golden_table(catalog: Catalog) -> None:
    cases = (
        (
            _palette_color(0, "#000000"),
            resolve_params(
                {
                    "materials": ["PLA"],
                    "brands": ["bambu-lab"],
                    "allow_approx": False,
                    "per_color": 3,
                },
                parse_note(""),
            ),
            [
                ("bambu-lab/pla-aero/black-14103", 0.0),
                ("bambu-lab/pla-basic/black-10101", 0.0),
                ("bambu-lab/pla-cf/black-14100", 0.0),
            ],
        ),
        (
            _palette_color(0, "#00AE42"),
            resolve_params(
                {
                    "materials": ["PLA"],
                    "brands": ["bambu-lab"],
                    "allow_approx": False,
                    "per_color": 3,
                },
                parse_note(""),
            ),
            [
                ("bambu-lab/pla-basic/bambu-green-10501", 0.0),
                ("bambu-lab/pla-lite/green-16501", 4.70),
                ("bambu-lab/pla-cf/matcha-green-14500", 9.24),
            ],
        ),
        (
            _palette_color(0, "#C8102E"),
            resolve_params(
                {"materials": ["PLA"], "allow_approx": False, "per_color": 3}, parse_note("")
            ),
            [
                ("bambu-lab/pla-lite/red-16200", 4.47),
                ("bambu-lab/pla-silk-plus/candy-red-13205", 5.07),
                ("bambu-lab/pla-matte/dark-red-11202", 5.20),
            ],
        ),
        (
            _palette_color(0, "#FFA3B5"),
            resolve_params(
                {"materials": ["PLA"], "allow_approx": True, "per_color": 3}, parse_note("")
            ),
            [
                ("anycubic/pla-silk/pink", 3.21),
                ("anycubic/pla-basic/pink", 5.14),
                ("anycubic/pla-plus/pink", 5.14),
            ],
        ),
    )
    for palette_color, params, expected in cases:
        result = match_palette([palette_color], catalog, params)
        assert [(pick["id"], pick["delta_e"]) for pick in result.matches[0]["picks"]] == expected


@pytest.mark.data
def test_match_palette_matches_result_example(catalog: Catalog, repo_root: Path) -> None:
    example = json.loads(
        (repo_root / "docs/schemas/examples/result.example.json").read_text(encoding="utf-8")
    )
    params = resolve_params({}, parse_note("帮我配 4 色，AMS 一台，只要拓竹 PLA"))
    result = match_palette([_palette_color(0, "#1B1B1D")], catalog, params)
    assert result.matches == example["matches"]
    assert result.single_series_option == example["single_series_option"]
    assert result.slots_used == 1
    assert result.warnings == ()


@pytest.mark.data
def test_eligible_count(catalog: Catalog) -> None:
    params = resolve_params({"materials": ["PLA", "PETG"]}, parse_note(""))
    assert sum(eligible(entry, params) for entry in catalog.entries) == 484


@pytest.mark.parametrize(
    ("delta_e", "expected"),
    (
        (1.99, "几乎一样"),
        (2.0, "接近"),
        (4.99, "接近"),
        (5.0, "勉强"),
        (10.0, "勉强"),
        (10.01, None),
    ),
)
def test_label_for(delta_e: float, expected: str | None) -> None:
    assert label_for(delta_e) == expected


@pytest.mark.data
def test_name_display(catalog: Catalog) -> None:
    assert name_display(catalog.by_id["bambu-lab/petg-basic/black-30105"]) == "黑色 Black (30105)"
    assert (
        name_display(catalog.by_id["byehassle/pla-ya-guang/sakura-bloom"]) == "樱花粉 Sakura Bloom"
    )
    assert name_display(catalog.by_id["cailab/rainbow-shift-pla/bamboo-rb009"]) == "Bamboo (RB009)"
    assert name_display({"name_zh": None, "name_en": None, "code": None, "name_raw": "X"}) == "X"


def test_eligible_filters_effects_confidence_and_approx() -> None:
    base = {
        "status": "active",
        "hex": ["#000000"],
        "material": "PLA",
        "brand_slug": "bambu-lab",
        "effects": [],
        "hex_source": "official",
        "hex_confidence": 1.0,
    }
    params = resolve_params({}, parse_note(""))
    assert eligible({**base, "effects": ["multi"]}, params) is False
    assert eligible({**base, "hex_source": "store_swatch", "hex_confidence": 0.8}, params) is True
    no_approx = resolve_params({"allow_approx": False}, parse_note(""))
    assert (
        eligible({**base, "hex_source": "store_swatch", "hex_confidence": 0.8}, no_approx) is False
    )
    assert eligible({**base, "hex_source": "store_swatch", "hex_confidence": 0.49}, params) is False
    assert eligible({**base, "hex_source": "store_swatch", "hex_confidence": 0.5}, params) is True


@pytest.mark.data
def test_no_match_warnings_and_error(catalog: Catalog) -> None:
    params = resolve_params({"materials": ["PLA"], "brands": ["bambu-lab"]}, parse_note(""))
    palette = [_palette_color(0, "#1B1B1D"), _palette_color(1, "#FF00FF")]
    result = match_palette(palette, catalog, params)
    assert "NO_MATCH_FOR_COLOR:1" in result.warnings
    with pytest.raises(NoMatchError):
        match_palette([palette[1]], catalog, params)


@pytest.mark.data
def test_match_result_validates_in_result_example(catalog: Catalog, repo_root: Path) -> None:
    result_json = json.loads(
        (repo_root / "docs/schemas/examples/result.example.json").read_text(encoding="utf-8")
    )
    matched = match_palette(
        [_palette_color(0, "#1B1B1D")],
        catalog,
        resolve_params({}, parse_note("帮我配 4 色，AMS 一台，只要拓竹 PLA")),
    )
    result_json["matches"] = matched.matches
    result_json["single_series_option"] = matched.single_series_option
    result_json["slots_used"] = matched.slots_used
    result_json["warnings"] = list(matched.warnings)
    assert validate_json("result", result_json) == []


def test_match_result_dataclass_shape() -> None:
    result = MatchResult([], None, 0, ())
    assert result.matches == []
