from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np

HEX_RE: re.Pattern[str] = re.compile(r"^#[0-9A-Fa-f]{6}$")

_SRGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ],
    dtype=np.float64,
)
_XYZ_TO_SRGB = np.linalg.inv(_SRGB_TO_XYZ)
_WHITE = np.array([0.95047, 1.0, 1.08883], dtype=np.float64)
_EPSILON = 216 / 24389
_KAPPA = 24389 / 27


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    if HEX_RE.fullmatch(h) is None:
        raise ValueError(f"invalid hex color: {h}")
    return tuple(int(h[index : index + 2], 16) for index in (1, 3, 5))


def rgb_to_hex(rgb: Sequence[int]) -> str:
    values = tuple(rgb)
    if len(values) != 3 or any(
        not isinstance(value, (int, np.integer)) or not 0 <= value <= 255 for value in values
    ):
        raise ValueError(f"invalid RGB color: {rgb}")
    return "#" + "".join(f"{value:02X}" for value in values)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    values = np.asarray(rgb, dtype=np.float64)
    if values.ndim == 0 or values.shape[-1] != 3:
        raise ValueError("RGB input must have a final dimension of 3")
    c = values / 255.0
    c_lin = np.where(
        c <= 0.04045,
        c / 12.92,
        np.power(np.maximum((c + 0.055) / 1.055, 0), 2.4),
    )
    xyz = c_lin @ _SRGB_TO_XYZ.T
    t = xyz / _WHITE
    f = np.where(t > _EPSILON, np.cbrt(t), (_KAPPA * t + 16) / 116)
    fy = f[..., 1]
    return np.stack((116 * fy - 16, 500 * (f[..., 0] - fy), 200 * (fy - f[..., 2])), axis=-1)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    values = np.asarray(lab, dtype=np.float64)
    if values.ndim == 0 or values.shape[-1] != 3:
        raise ValueError("Lab input must have a final dimension of 3")
    l_value, a_value, b_value = np.moveaxis(values, -1, 0)
    fy = (l_value + 16) / 116
    fx = fy + a_value / 500
    fz = fy - b_value / 200
    f = np.stack((fx, fy, fz), axis=-1)
    f_cubed = f**3
    t = np.where(f_cubed > _EPSILON, f_cubed, (116 * f - 16) / _KAPPA)
    xyz = t * _WHITE
    c_lin = xyz @ _XYZ_TO_SRGB.T
    c = np.where(
        c_lin <= 0.0031308,
        12.92 * c_lin,
        1.055 * np.power(np.maximum(c_lin, 0), 1 / 2.4) - 0.055,
    )
    return np.rint(np.clip(c, 0, 1) * 255).astype(np.uint8)


def hex_to_lab(h: str) -> tuple[float, float, float]:
    lab = rgb_to_lab(np.asarray(hex_to_rgb(h), dtype=np.uint8))
    return tuple(float(value) for value in lab)


def lab_to_hex(lab: Sequence[float] | np.ndarray) -> str:
    values = np.asarray(lab, dtype=np.float64)
    return rgb_to_hex(tuple(int(value) for value in lab_to_rgb(values)))
