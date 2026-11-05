import pytest

from filament_picker.brands import (
    BRAND_ALIASES,
    BRAND_ORDER,
    BRAND_SLUGS,
    UnknownBrandError,
    brand_slug,
)


def test_brand_tables() -> None:
    assert len(BRAND_SLUGS) == 21 == len(BRAND_ALIASES) == len(BRAND_ORDER)
    assert BRAND_ORDER[0] == "bambu-lab"
    assert BRAND_ORDER[-1] == "byehassle"


def test_aliases_are_lowercase() -> None:
    for aliases in BRAND_ALIASES.values():
        assert all(alias == alias.lower() for alias in aliases)


def test_unknown_brand() -> None:
    with pytest.raises(UnknownBrandError):
        brand_slug("Foo")


@pytest.mark.data
def test_all_raw_brands(raw_rows: list[dict]) -> None:
    for brand in {row["b"] for row in raw_rows}:
        assert brand_slug(brand) in BRAND_ORDER
