import re

import pytest

from filament_picker.brands import brand_slug
from filament_picker.names import ParsedName, parse_color_name
from filament_picker.slug import color_segment, pinyin_fields, row_id, series_slug, slug


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PLA+ 2.0", "pla-plus-2-0"),
        ("菠菜绿", "bo-cai-lv"),
        ("Blue&Green", "blue-green"),
        ("a" * 30 + " " + "b" * 40, "a" * 30),
        ("x" * 70, "x" * 60),
    ],
)
def test_slug_examples(value: str, expected: str) -> None:
    assert slug(value) == expected


def test_series_slug_examples() -> None:
    assert series_slug("PLA哑光（拼多多）") == "pla-ya-guang"
    assert series_slug("彩虹丝绸 PLA（RB 系列）") == "cai-hong-si-chou-pla-rb-xi-lie"


def test_pinyin_fields() -> None:
    assert pinyin_fields("樱花粉") == ("ying hua fen", "yhf")
    assert pinyin_fields(None) == (None, None)


def test_color_segment_fallback_is_stable() -> None:
    parsed = ParsedName(None, None, None)
    first = color_segment(parsed, "???")
    second = color_segment(parsed, "???")
    assert first == second
    assert first.startswith("x")
    assert len(first) == 9


def test_golden_ids(golden_ids: list[dict]) -> None:
    for row in golden_ids:
        parsed = parse_color_name(row["raw_name"])
        assert series_slug(row["series"]) == row["series_slug"]
        assert row_id(row["brand_slug"], row["series"], parsed, row["raw_name"]) == row["row_id"]


@pytest.mark.data
def test_all_raw_row_ids(raw_rows: list[dict]) -> None:
    lengths: list[int] = []
    fallback_count = 0
    for row in raw_rows:
        parsed = parse_color_name(row["c"])
        current = row_id(brand_slug(row["b"]), row["s"], parsed, row["c"])
        lengths.append(len(current))
        if re.fullmatch(r"x[0-9a-f]{8}", color_segment(parsed, row["c"])):
            fallback_count += 1
    assert max(lengths) == 108
    assert fallback_count == 0
