import numpy as np
import pytest

from filament_picker.colorspace import (
    hex_to_lab,
    hex_to_rgb,
    lab_to_hex,
    lab_to_rgb,
    rgb_to_hex,
    rgb_to_lab,
)

LAB_CASES = [
    ("#000000", (0.00, 0.00, 0.00)),
    ("#FFFFFF", (100.00, 0.00, 0.00)),
    ("#FF0000", (53.24, 80.09, 67.20)),
    ("#00AE42", (62.22, -60.41, 43.97)),
    ("#272729", (15.71, 0.49, -1.31)),
    ("#808080", (53.59, 0.00, 0.00)),
]


@pytest.mark.parametrize(("hex_value", "expected"), LAB_CASES)
def test_hex_to_lab_matches_spec(hex_value, expected):
    actual = hex_to_lab(hex_value)
    assert all(abs(value - target) < 0.02 for value, target in zip(actual, expected, strict=False))


@pytest.mark.parametrize("hex_value", [case[0] for case in LAB_CASES])
def test_lab_hex_round_trip(hex_value):
    assert lab_to_hex(hex_to_lab(hex_value)) == hex_value


def test_hex_rgb_conversions():
    assert hex_to_rgb("#00AE42") == (0, 174, 66)
    assert hex_to_rgb("#00ae42") == (0, 174, 66)
    assert rgb_to_hex((0, 174, 66)) == "#00AE42"


def test_invalid_hex_and_rgb_raise_value_error():
    with pytest.raises(ValueError):
        hex_to_rgb("00AE42")
    with pytest.raises(ValueError):
        hex_to_rgb("#00AE4")
    with pytest.raises(ValueError):
        rgb_to_hex((256, 0, 0))


def test_rgb_to_lab_preserves_shape():
    assert rgb_to_lab(np.zeros((2, 3, 3), np.uint8)).shape == (2, 3, 3)


def test_random_rgb_round_trip():
    rng = np.random.default_rng(0)
    rgb = rng.integers(0, 256, size=(1000, 3), dtype=np.uint8)
    converted = lab_to_rgb(rgb_to_lab(rgb))
    assert np.max(np.abs(converted.astype(int) - rgb.astype(int))) <= 1
