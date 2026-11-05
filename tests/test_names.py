import re
from collections import Counter

import pytest

from filament_picker.names import ParsedName, nfkc, parse_color_name

CASES = [
    ("Black 黑色 (30105)", ParsedName("Black", "黑色", "30105")),
    (
        "UV Color Changing - White to Coral 光变-白变粉 (15100)",
        ParsedName("UV Color Changing - White to Coral", "光变-白变粉", "15100"),
    ),
    ("樱花粉（Sakura Bloom）", ParsedName("Sakura Bloom", "樱花粉", None)),
    ("Black Walmut ATM2469 / 1KG", ParsedName("Black Walmut", None, "ATM2469")),
    ("Blue&Green-3KG", ParsedName("Blue&Green", None, None)),
    ("竹 RB009", ParsedName(None, "竹", "RB009")),
    ("菠菜绿", ParsedName(None, "菠菜绿", None)),
    (
        "Dual Silk Aubergine (Lime-Magenta)",
        ParsedName("Dual Silk Aubergine (Lime-Magenta)", None, None),
    ),
    (
        "Purple/Blue Green/Burnt Orange 1KG",
        ParsedName("Purple/Blue Green/Burnt Orange", None, None),
    ),
    ("Blue&Green&Gold Z007", ParsedName("Blue&Green&Gold", None, "Z007")),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_parse_color_name_examples(raw: str, expected: ParsedName) -> None:
    assert parse_color_name(raw) == expected


def test_parse_color_name_matches_golden(golden_ids: list[dict]) -> None:
    for row in golden_ids:
        parsed = parse_color_name(row["raw_name"])
        assert parsed == ParsedName(row["name_en"], row["name_zh"], row["code"])


def test_nfkc_examples() -> None:
    assert nfkc("樱花粉（Sakura Bloom）") == "樱花粉(Sakura Bloom)"
    assert nfkc("  a\u3000 b ") == "a b"


@pytest.mark.data
def test_parse_all_raw_rows(raw_rows: list[dict]) -> None:
    parsed_rows = [(row, parse_color_name(row["c"])) for row in raw_rows]
    with_code = [parsed for _, parsed in parsed_rows if parsed.code is not None]
    assert len(with_code) == 467

    bambu_codes = [
        parsed.code
        for row, parsed in parsed_rows
        if row["b"] == "Bambu Lab" and parsed.code is not None
    ]
    assert len(bambu_codes) == 246
    assert all(re.fullmatch(r"\d{5}", code) for code in bambu_codes)

    cailab_codes = [
        parsed.code
        for row, parsed in parsed_rows
        if row["b"] == "彩多屋 CaiLab" and parsed.code is not None
    ]
    assert len(cailab_codes) == 221
    prefixes = Counter(re.match(r"[A-Z]+", code)[0] for code in cailab_codes)
    assert prefixes["RB"] == 40
    assert prefixes["AC"] == 33
    assert prefixes["G"] == 30
    assert prefixes["MT"] == 25

    for _, parsed in parsed_rows:
        for value in (parsed.name_en, parsed.name_zh, parsed.code):
            if value is not None:
                assert value == value.strip()
