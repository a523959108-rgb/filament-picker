from collections import Counter

import pytest

from filament_picker.effects import MULTI_FAMILY, detect_effects, detect_material


@pytest.mark.parametrize(
    ("series", "color_raw", "family", "expected"),
    [
        (
            "PLA Silk Dual-Color",
            "Red&Blue",
            MULTI_FAMILY,
            ("silk", "dual", "multi"),
        ),
        ("PETG Basic", "Black 黑色 (30105)", "黑白灰", ()),
    ],
)
def test_detect_effects_examples(
    series: str, color_raw: str, family: str, expected: tuple[str, ...]
) -> None:
    assert detect_effects(series, color_raw, family) == expected


@pytest.mark.parametrize(
    ("series", "expected"),
    [("PETG-Basic", "PETG"), ("PLA哑光（拼多多）", "PLA")],
)
def test_detect_material_examples(series: str, expected: str) -> None:
    assert detect_material(series) == expected


def test_detect_effects_matches_golden(golden_ids: list[dict], raw_rows: list[dict]) -> None:
    for row in golden_ids:
        family = raw_rows[row["row_index"]]["f"]
        assert list(detect_effects(row["series"], row["raw_name"], family)) == row["effects"]
        assert detect_material(row["series"]) == row["material"]


@pytest.mark.data
def test_detect_effects_all_raw_rows(raw_rows: list[dict]) -> None:
    effects = [detect_effects(row["s"], row["c"], row["f"]) for row in raw_rows]
    counts = Counter(effect for row_effects in effects for effect in row_effects)
    assert counts == Counter(
        {
            "multi": 610,
            "matte": 624,
            "silk": 592,
            "gradient": 250,
            "translucent": 246,
            "dual": 156,
            "sparkle": 137,
            "metallic": 107,
            "cf": 96,
            "glow": 75,
            "tri": 59,
            "wood": 56,
            "marble": 29,
            "gf": 28,
            "color_change": 5,
        }
    )
    assert sum(not row_effects for row_effects in effects) == 1772


@pytest.mark.data
def test_detect_material_all_raw_rows(raw_rows: list[dict]) -> None:
    materials = Counter(detect_material(row["s"]) for row in raw_rows)
    assert materials == Counter({"PLA": 3110, "PETG": 762})
