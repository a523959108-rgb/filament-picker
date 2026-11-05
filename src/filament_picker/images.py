from __future__ import annotations

from pathlib import Path

import numpy as np
import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

from .ciede2000 import delta_e_2000
from .config import (
    BG_BORDER_AGREE_DE,
    BG_BORDER_AGREE_FRAC,
    BG_REMOVE_DE,
    BORDER_PX,
    HIGHLIGHT_C,
    HIGHLIGHT_L,
    SHADOW_KEEP_MIN_FRAC,
    SHADOW_L,
)
from .errors import ImageMissingError, ImageUnreadableError

pillow_heif.register_heif_opener()


def load_rgb(path: Path) -> np.ndarray:
    """Load an image as an RGB uint8 array, applying orientation and alpha compositing."""
    try:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened)
            if image.mode in ("RGBA", "LA", "P"):
                rgba = image.convert("RGBA")
                white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                image = Image.alpha_composite(white, rgba)
            image = image.convert("RGB")
            return np.asarray(image, dtype=np.uint8).copy()
    except FileNotFoundError as exc:
        raise ImageMissingError from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageUnreadableError from exc


def resize_long_side(rgb: np.ndarray, long_side: int) -> np.ndarray:
    """Resize an RGB image to the requested maximum side without upscaling."""
    image = Image.fromarray(np.asarray(rgb, dtype=np.uint8))
    image.thumbnail((long_side, long_side), Image.Resampling.BOX)
    return np.asarray(image, dtype=np.uint8).copy()


def foreground_mask(lab: np.ndarray, drop_highlights: bool = True) -> np.ndarray:
    """Return pixels that differ from a uniform border background."""
    values = np.asarray(lab, dtype=np.float64)
    border = np.concatenate(
        (
            values[:BORDER_PX].reshape(-1, 3),
            values[-BORDER_PX:].reshape(-1, 3),
            values[:, :BORDER_PX].reshape(-1, 3),
            values[:, -BORDER_PX:].reshape(-1, 3),
        ),
        axis=0,
    )
    background = np.median(border, axis=0)
    mask = np.ones(values.shape[:2], dtype=bool)
    border_delta = delta_e_2000(border, background)
    if np.mean(border_delta < BG_BORDER_AGREE_DE) >= BG_BORDER_AGREE_FRAC:
        mask &= delta_e_2000(values, background) >= BG_REMOVE_DE
    if drop_highlights:
        chroma = np.hypot(values[..., 1], values[..., 2])
        mask &= ~((values[..., 0] > HIGHLIGHT_L) & (chroma < HIGHLIGHT_C))
    return mask


def apply_shadow_rule(X: np.ndarray) -> np.ndarray:
    """Remove dark shadow pixels when enough non-shadow pixels remain."""
    values = np.asarray(X)
    if len(values) == 0:
        return values
    keep = values[:, 0] >= SHADOW_L
    if keep.mean() >= SHADOW_KEEP_MIN_FRAC:
        return values[keep]
    return values
