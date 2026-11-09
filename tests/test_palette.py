import json
import math
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from filament_picker.ciede2000 import delta_e_2000
from filament_picker.colorspace import hex_to_lab
from filament_picker.errors import ImageTooSmallError, NoForegroundError
from filament_picker.note_parser import SampleRegion
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


def _strips(path: Path) -> Path:
    """Four low-chroma shades plus a smaller orange and a smaller black.

    Shares put the two beiges inside the top 4 and leave orange/black out,
    which is the failure mode of share-only truncation.
    """
    image = Image.new("RGB", (400, 200), "#D2C8BE")
    draw = ImageDraw.Draw(image)
    x = 0
    for width, color in (
        (160, "#D2C8BE"),
        (60, "#62544D"),
        (60, "#A4978D"),
        (60, "#897D75"),
        (32, "#E85D04"),
        (28, "#1A1614"),
    ):
        draw.rectangle((x, 0, x + width - 1, 199), fill=color)
        x += width
    image.save(path, format="PNG")
    return path


def _chroma(lab: tuple[float, float, float]) -> float:
    return math.hypot(lab[1], lab[2])


def _hue(lab: tuple[float, float, float]) -> float:
    return math.degrees(math.atan2(lab[2], lab[1]))


def test_salient_accents_replace_redundant_neutrals(tmp_path: Path) -> None:
    result = _palette(_strips(tmp_path / "strips.png"), 4)
    assert [item.hex for item in result] == ["#D2C8BE", "#62544D", "#E85D04", "#1A1614"]
    assert sum(item.share for item in result) == pytest.approx(1.0, abs=0.002)


def _take(
    result: list[PaletteColor],
    used: set[int],
    predicate: Callable[[PaletteColor], bool],
) -> PaletteColor:
    for item in result:
        if item.index not in used and predicate(item):
            used.add(item.index)
            return item
    raise AssertionError([(item.hex, item.lab, item.share) for item in result])


def test_figurine_keeps_orange_black_brown_and_cream() -> None:
    path = Path(__file__).parent / "fixtures" / "e2e-figurine.png"
    result = plan_palette(path, 4, False)
    assert len(result) == 4
    assert sum(item.share for item in result) == pytest.approx(1.0, abs=0.002)
    used: set[int] = set()
    black = _take(
        result,
        used,
        lambda item: item.lab[0] <= 22 and _chroma(item.lab) <= 12 and item.share >= 0.03,
    )
    cream = _take(
        result,
        used,
        lambda item: item.lab[0] >= 75 and _chroma(item.lab) <= 15 and item.share >= 0.03,
    )
    brown = _take(
        result,
        used,
        lambda item: 30 <= item.lab[0] <= 48 and _chroma(item.lab) <= 15 and item.share >= 0.03,
    )
    orange = _take(
        result,
        used,
        lambda item: _chroma(item.lab) >= 50 and 25 <= _hue(item.lab) <= 70 and item.share >= 0.03,
    )
    assert {black.index, cream.index, brown.index, orange.index} == {0, 1, 2, 3}
    assert plan_palette(path, 4, False) == result


def _half_and_half(path: Path) -> Path:
    image = Image.new("RGB", (200, 200), "#000000")
    ImageDraw.Draw(image).rectangle((100, 0, 199, 199), fill="#C8102E")
    image.save(path, format="PNG")
    return path


def test_regions_sample_only_the_selected_pixels(tmp_path: Path) -> None:
    path = _half_and_half(tmp_path / "half.png")
    both = plan_palette(path, 2, False)
    assert {item.hex for item in both} == {"#000000", "#C8102E"}

    left = plan_palette(
        path,
        2,
        False,
        (SampleRegion(x=0, y=0, w=0.5, h=1),),
    )
    assert [item.hex for item in left] == ["#000000"]

    right_px = plan_palette(
        path,
        2,
        False,
        (SampleRegion(x=100, y=0, space="px", w=100, h=200),),
    )
    assert [item.hex for item in right_px] == ["#C8102E"]

    point = plan_palette(
        path,
        2,
        False,
        (SampleRegion(x=0.75, y=0.5, r=0.12),),
    )
    assert [item.hex for item in point] == ["#C8102E"]

    empty = plan_palette(path, 2, False, ())
    assert [item.hex for item in empty] == [item.hex for item in both]


def test_palette_color_to_dict() -> None:
    item = PaletteColor(2, "#123456", (1.23, 4.56, 7.89), 0.125)
    assert item.to_dict() == {
        "index": 2,
        "hex": "#123456",
        "lab": [1.23, 4.56, 7.89],
        "share": 0.125,
    }
