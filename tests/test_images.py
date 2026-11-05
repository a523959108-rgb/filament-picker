from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from filament_picker.colorspace import rgb_to_lab
from filament_picker.errors import ImageMissingError, ImageUnreadableError
from filament_picker.images import apply_shadow_rule, foreground_mask, load_rgb, resize_long_side
from helpers_images import blank_white, quadrants, rgba_square, square_on_white


def test_load_rgb_rgba_composites_transparency(tmp_path: Path):
    rgb = load_rgb(rgba_square(tmp_path / "rgba.png"))
    assert rgb[0, 0].tolist() == [255, 255, 255]
    assert rgb[100, 100].tolist() == [0, 174, 66]


def test_load_rgb_missing_and_unreadable(tmp_path: Path):
    with pytest.raises(ImageMissingError):
        load_rgb(tmp_path / "nope.png")
    unreadable = tmp_path / "x.png"
    unreadable.write_bytes(b"not an image")
    with pytest.raises(ImageUnreadableError):
        load_rgb(unreadable)


def test_load_rgb_applies_exif_orientation(tmp_path: Path):
    image = Image.new("RGB", (300, 200), "#00AE42")
    exif = image.getexif()
    exif[0x0112] = 6
    path = tmp_path / "rotated.jpg"
    image.save(path, format="JPEG", exif=exif.tobytes())
    assert load_rgb(path).shape == (300, 200, 3)


def test_resize_long_side_downscales_without_upscaling():
    assert resize_long_side(np.zeros((1000, 500, 3), np.uint8), 256).shape == (256, 128, 3)
    assert resize_long_side(np.zeros((100, 50, 3), np.uint8), 256).shape == (100, 50, 3)


def test_foreground_mask_square():
    rgb = load_rgb(square_on_white(Path("square.png")))
    try:
        assert foreground_mask(rgb_to_lab(rgb)).sum() == 14400
    finally:
        Path("square.png").unlink()


def test_foreground_mask_quadrants(tmp_path: Path):
    lab = rgb_to_lab(load_rgb(quadrants(tmp_path / "quadrants.png")))
    assert foreground_mask(lab).mean() == pytest.approx(0.75, abs=0.005)
    assert foreground_mask(lab, drop_highlights=False).mean() == 1.0


def test_foreground_mask_blank_white(tmp_path: Path):
    lab = rgb_to_lab(load_rgb(blank_white(tmp_path / "blank.png")))
    assert foreground_mask(lab).sum() == 0


def test_apply_shadow_rule():
    first = np.vstack((np.full((90, 3), 50.0), np.full((10, 3), 5.0)))
    assert apply_shadow_rule(first).shape == (90, 3)
    black = np.full((100, 3), 2.0)
    assert apply_shadow_rule(black).shape == (100, 3)
    mostly_shadow = np.vstack((np.full((10, 3), 50.0), np.full((90, 3), 5.0)))
    assert apply_shadow_rule(mostly_shadow).shape == (100, 3)
    empty = np.empty((0, 3))
    assert apply_shadow_rule(empty).shape == (0, 3)
