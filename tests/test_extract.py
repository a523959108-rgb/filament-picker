from pathlib import Path

import pytest

from filament_picker.errors import ImageMissingError
from filament_picker.extract import ExtractResult, extract_colors
from helpers_images import blank_white, square_on_white, two_tone


def test_extract_square_on_white(tmp_path: Path) -> None:
    result = extract_colors(square_on_white(tmp_path / "square.png"), ())
    assert result == ExtractResult("ok", ("#00AE42",), 1.0, 1.0, 0.0, 14400)


def test_extract_square_effect_penalty(tmp_path: Path) -> None:
    result = extract_colors(square_on_white(tmp_path / "square.png"), ("silk",))
    assert result == ExtractResult("ok", ("#00AE42",), 0.6, 1.0, 0.0, 14400)


def test_extract_blank_white(tmp_path: Path) -> None:
    result = extract_colors(blank_white(tmp_path / "blank.png"), ())
    assert result == ExtractResult("no_foreground", (), 0.0, 0.0, 0.0, 0)


def test_extract_two_tone_as_multi(tmp_path: Path) -> None:
    result = extract_colors(two_tone(tmp_path / "two-tone.png", split=0.6), ("multi",))
    assert result == ExtractResult("ok", ("#C8102E", "#00AE42"), 1.0, 1.0, 0.0, 14400)


def test_extract_two_tone_as_single(tmp_path: Path) -> None:
    result = extract_colors(two_tone(tmp_path / "two-tone.png", split=0.6), ())
    assert result == ExtractResult("ok", ("#C8102E",), 0.6, 0.6, 0.0, 14400)


def test_extract_black_square_keeps_shadow_pixels(tmp_path: Path) -> None:
    result = extract_colors(square_on_white(tmp_path / "black.png", fg="#000000"), ())
    assert result.status == "ok"
    assert result.hexes == ("#000000",)


def test_extract_is_deterministic(tmp_path: Path) -> None:
    path = two_tone(tmp_path / "two-tone.png", split=0.6)
    assert extract_colors(path, ("multi",)) == extract_colors(path, ("multi",))


def test_extract_missing_image() -> None:
    with pytest.raises(ImageMissingError):
        extract_colors(Path("does-not-exist.png"), ())


@pytest.mark.data
def test_extract_real_product_image() -> None:
    path = Path("/workspace/filament-shots/Bambu Lab/PETG_Basic/variant_00_Black.jpg")
    if not path.exists():
        pytest.skip("/workspace/filament-shots 未就绪")
    result = extract_colors(path, ())
    assert result.status == "ok"
    assert len(result.hexes) == 1
    assert 0.0 <= result.confidence <= 1.0


def test_extract_prefers_filament_over_cardboard(tmp_path: Path) -> None:
    """Kraft-cardboard spool flanges must not win over a vivid filament band."""
    from PIL import Image

    path = tmp_path / "cardboard-spool.png"
    im = Image.new("RGB", (200, 200), (0, 0, 0))  # black background
    # cardboard flange (dominant area)
    for x in range(40, 180):
        for y in range(40, 180):
            im.putpixel((x, y), (174, 137, 108))  # ~#AE896C kraft
    # filament crescent (smaller, vivid magenta)
    for x in range(40, 90):
        for y in range(50, 170):
            im.putpixel((x, y), (234, 87, 127))  # ~#EA577F
    im.save(path)

    without_name = extract_colors(path, ())
    with_name = extract_colors(path, (), color_name="Magenta")
    assert without_name.status == "ok"
    assert with_name.status == "ok"
    # Name-aware pick must be the magenta, not kraft brown.
    assert with_name.hexes[0].upper() != "#AE896C"
    r, g, b = (int(with_name.hexes[0][i : i + 2], 16) for i in (1, 3, 5))
    assert r > 180 and b > 80 and g < 150
