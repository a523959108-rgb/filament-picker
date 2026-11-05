from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .colorspace import hex_to_lab
from .config import CARD_TOKEN_BYTES, get_settings
from .palette import PaletteColor

CARD_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_-]{32}\.png$")


def card_height(n: int) -> int:
    return 40 + 120 + max(360, 140 * n) + 60 + 40


def truncate(s: str, limit: int = 18) -> str:
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def new_card_path(root: Path) -> Path:
    return root / "public" / "cards" / f"{secrets.token_urlsafe(CARD_TOKEN_BYTES)}.png"


def card_url_for(card_path: Path, base_url: str | None) -> str | None:
    if base_url is None:
        return None
    return f"{base_url.rstrip('/')}/{card_path.name}"


def _font(path: Path, size: int, index: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size, index=index)


def _draw_color_block(
    draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color: str, light: bool
) -> None:
    outline = "#DDDDDD" if light else None
    draw.rounded_rectangle(box, radius=12, fill=color, outline=outline, width=1)


def _is_light(color: str) -> bool:
    return hex_to_lab(color)[0] > 90


def render_card(
    image_path: Path,
    palette: list[PaletteColor],
    matches: list[dict[str, Any]],
    out_path: Path,
    today: str,
) -> Path:
    settings = get_settings()
    n_colors = len(palette)
    height = card_height(n_colors)
    image = Image.new("RGB", (1080, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)

    draw.text(
        (40, 48),
        f"配色方案（{n_colors} 色）",
        fill="#111111",
        font=_font(settings.font_bold, 44, settings.font_index),
    )
    draw.text(
        (40, 108),
        f"按图片主色推荐 · {today}",
        fill="#666666",
        font=_font(settings.font_regular, 24, settings.font_index),
    )

    draw.rectangle((40, 160, 399, 519), fill="#F5F5F5")
    with Image.open(image_path) as opened:
        source = opened.convert("RGB")
        thumbnail = ImageOps.contain(source, (360, 360), method=Image.Resampling.LANCZOS)
    left = 40 + (360 - thumbnail.width) // 2
    top = 160 + (360 - thumbnail.height) // 2
    image.paste(thumbnail, (left, top))

    matches_by_index = {match["target_index"]: match for match in matches}
    for index, target in enumerate(palette):
        y0 = 160 + 140 * index
        _draw_color_block(
            draw,
            (440, y0 + 20, 539, y0 + 119),
            target.hex,
            _is_light(target.hex),
        )
        match = matches_by_index.get(target.index, {"picks": []})
        picks = match.get("picks", [])
        pick = picks[0] if picks else None
        if pick is None:
            _draw_color_block(draw, (580, y0 + 20, 679, y0 + 119), "#EEEEEE", True)
            draw.text(
                (630, y0 + 70),
                "无",
                fill="#999999",
                font=_font(settings.font_regular, 32, settings.font_index),
                anchor="mm",
            )
            continue

        pick_hex = str(pick["hex"])
        _draw_color_block(draw, (580, y0 + 20, 679, y0 + 119), pick_hex, _is_light(pick_hex))
        title = truncate(f"{pick['brand_name']} {pick['series_name']}")
        name = truncate(str(pick["name_display"]))
        delta = f"ΔE {float(pick['delta_e']):.1f} · {pick['label']}"
        if pick.get("is_approx"):
            delta += " · 近似色"
        draw.text(
            (700, y0 + 22),
            title,
            fill="#111111",
            font=_font(settings.font_bold, 26, settings.font_index),
        )
        draw.text(
            (700, y0 + 58),
            name,
            fill="#333333",
            font=_font(settings.font_regular, 24, settings.font_index),
        )
        draw.text(
            (700, y0 + 92),
            delta,
            fill="#666666",
            font=_font(settings.font_regular, 22, settings.font_index),
        )

    draw.text(
        (40, height - 80),
        "颜色仅供参考，屏幕显示与实物有差异",
        fill="#999999",
        font=_font(settings.font_regular, 20, settings.font_index),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG", optimize=True)
    return out_path
