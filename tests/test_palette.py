import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from filament_picker.ciede2000 import delta_e_2000
from filament_picker.colorspace import hex_to_lab
from filament_picker.errors import ImageTooSmallError, NoForegroundError
from filament_picker.palette import PaletteColor, plan_palette
from filament_picker.validate import validate_json
from helpers_images import blank_white, quadrants, square_on_white, tiny


def _palette(path: Path, n_colors: int, keep_small: bool = False) -> list[PaletteColor]:
    return plan_palette(path, n_colors, keep_small)


def test_quadrants_four_colors(tmp_path: Path) -> None:
    result = _palette(quadrants(tmp_path / "quadrants.png"), 4)
    assert [item.hex for item in result] == ["#000000", "#C8102E", "#00AE42", "#FFFFFF"]
    assert [item.share for item in result] == pytest.approx([0.25] * 4, abs=0.002)
    assert [item.index for item in result] == [0, 1, 2, 3]
    for item in result:
        expected = tuple(round(value, 2) for value in hex_to_lab(item.hex))
        assert item.lab == expected


def test_quadrants_two_colors_merges_remaining_clusters(tmp_path: Path) -> None:
    result = _palette(quadrants(tmp_path / "quadrants.png"), 2)
    assert [item.hex for item in result] == ["#000000", "#C8102E"]
    assert [item.share for item in result] == pytest.approx([0.5, 0.5], abs=0.002)


def test_square_is_one_color(tmp_path: Path) -> None:
    result = _palette(square_on_white(tmp_path / "square.png"), 4)
    assert [item.hex for item in result] == ["#00AE42"]
    assert [item.share for item in result] == pytest.approx([1.0], abs=0.002)
    assert result[0].lab == tuple(round(value, 2) for value in hex_to_lab("#00AE42"))


def _green_with_small_blue(path: Path) -> Path:
    square_on_white(path)
    with Image.open(path) as image:
        draw = ImageDraw.Draw(image)
        draw.rectangle((94, 94, 105, 105), fill="#0000FF")
        image.save(path, format="PNG")
    return path


def test_small_blue_is_merged_by_default(tmp_path: Path) -> None:
    result = _palette(_green_with_small_blue(tmp_path / "blue.png"), 4)
    assert len(result) == 1
    assert result[0].share == pytest.approx(1.0, abs=0.002)
    assert delta_e_2000(hex_to_lab(result[0].hex), hex_to_lab("#00AE42")) < 2


def test_small_blue_can_be_kept(tmp_path: Path) -> None:
    result = _palette(_green_with_small_blue(tmp_path / "blue.png"), 4, True)
    assert [item.hex for item in result] == ["#00AE42", "#0000FF"]
    assert [item.share for item in result] == pytest.approx([0.99, 0.01], abs=0.002)


def test_palette_errors(tmp_path: Path) -> None:
    with pytest.raises(ImageTooSmallError):
        plan_palette(tiny(tmp_path / "tiny.png"), 4, False)
    with pytest.raises(NoForegroundError):
        plan_palette(blank_white(tmp_path / "blank.png"), 4, False)


def test_palette_is_deterministic_and_serializable(tmp_path: Path) -> None:
    path = quadrants(tmp_path / "quadrants.png")
    first = _palette(path, 4)
    second = _palette(path, 4)
    assert first == second
    assert sum(item.share for item in first) == pytest.approx(1.0, abs=0.002)

    result = json.loads(Path("docs/schemas/examples/result.example.json").read_text())
    result["palette"] = [item.to_dict() for item in first]
    assert validate_json("result", result) == []


def test_palette_color_to_dict() -> None:
    item = PaletteColor(2, "#123456", (1.23, 4.56, 7.89), 0.125)
    assert item.to_dict() == {
        "index": 2,
        "hex": "#123456",
        "lab": [1.23, 4.56, 7.89],
        "share": 0.125,
    }
