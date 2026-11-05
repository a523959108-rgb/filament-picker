from __future__ import annotations

from pathlib import Path

from PIL import Image

from filament_picker.card import (
    CARD_NAME_RE,
    card_height,
    card_url_for,
    new_card_path,
    render_card,
    truncate,
)
from filament_picker.palette import PaletteColor
from helpers_images import square_on_white


def _palette(*colors: str) -> list[PaletteColor]:
    return [
        PaletteColor(index, color, (0.0, 0.0, 0.0), 1.0 / len(colors))
        for index, color in enumerate(colors)
    ]


def _matches(*picks: dict[str, object] | None) -> list[dict[str, object]]:
    return [
        {"target_index": index, "picks": [] if pick is None else [pick]}
        for index, pick in enumerate(picks)
    ]


def _pick(hex_value: str, *, index: int = 0, approx: bool = False) -> dict[str, object]:
    return {
        "id": f"brand/series/color-{index}",
        "brand_name": "Brand",
        "series_name": "Series",
        "name_display": "Color",
        "hex": hex_value,
        "hex_source": "store_swatch" if approx else "official",
        "delta_e": 1.23,
        "label": "几乎一样",
        "is_approx": approx,
        "url": None,
        "price_text": None,
    }


def test_card_helpers(tmp_path: Path) -> None:
    assert card_height(4) == 820
    assert card_height(1) == 620
    assert card_height(2) == 620
    assert card_height(3) == 680
    assert card_height(5) == 960
    assert (
        truncate("一二三四五六七八九十一二三四五六七八九") == "一二三四五六七八九十一二三四五六七…"
    )
    assert (
        card_url_for(Path("/x/public/cards/abc.png"), "https://cards.example.invalid/c/")
        == "https://cards.example.invalid/c/abc.png"
    )
    assert card_url_for(Path("/x/public/cards/abc.png"), None) is None

    first = new_card_path(tmp_path)
    second = new_card_path(tmp_path)
    assert CARD_NAME_RE.fullmatch(first.name)
    assert CARD_NAME_RE.fullmatch(second.name)
    assert first != second
    assert first.parent == tmp_path / "public" / "cards"


def test_render_card_one_color(tmp_path: Path) -> None:
    image_path = square_on_white(tmp_path / "input.png")
    out_path = tmp_path / "public" / "cards" / "card.png"
    result = render_card(
        image_path,
        _palette("#00AE42"),
        _matches(_pick("#25282A")),
        out_path,
        "2026-11-05",
    )
    assert result == out_path
    with Image.open(result) as image:
        assert image.size == (1080, 620)
        assert image.getpixel((490, 230))[:3] == (0, 174, 66)
        assert image.getpixel((630, 230))[:3] == (37, 40, 42)
        assert image.getpixel((20, 20))[:3] == (255, 255, 255)


def test_render_card_without_match(tmp_path: Path) -> None:
    image_path = square_on_white(tmp_path / "input.png")
    out_path = tmp_path / "card.png"
    render_card(image_path, _palette("#00AE42"), _matches(None), out_path, "2026-11-05")
    with Image.open(out_path) as image:
        assert image.getpixel((630, 200))[:3] == (238, 238, 238)


def test_render_card_four_colors(tmp_path: Path) -> None:
    image_path = square_on_white(tmp_path / "input.png")
    colors = ("#00AE42", "#C8102E", "#000000", "#FFFFFF")
    out_path = tmp_path / "card.png"
    render_card(
        image_path,
        _palette(*colors),
        _matches(*[_pick(color, index=index) for index, color in enumerate(colors)]),
        out_path,
        "2026-11-05",
    )
    with Image.open(out_path) as image:
        assert image.size == (1080, 820)
        for index, color in enumerate(colors):
            expected = tuple(bytes.fromhex(color[1:]))
            assert image.getpixel((490, 230 + 140 * index))[:3] == expected


def test_render_card_light_target_has_border(tmp_path: Path) -> None:
    image_path = square_on_white(tmp_path / "input.png")
    out_path = tmp_path / "card.png"
    render_card(image_path, _palette("#FFFFFF"), _matches(_pick("#000000")), out_path, "2026-11-05")
    with Image.open(out_path) as image:
        assert image.getpixel((440, 200))[:3] == (221, 221, 221)
