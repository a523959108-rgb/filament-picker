from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


def delta_e_2000(lab1: ArrayLike, lab2: ArrayLike) -> np.ndarray:
    first = np.asarray(lab1, dtype=np.float64)
    second = np.asarray(lab2, dtype=np.float64)
    if first.ndim == 0 or second.ndim == 0 or first.shape[-1] != 3 or second.shape[-1] != 3:
        raise ValueError("Lab inputs must have a final dimension of 3")
    first, second = np.broadcast_arrays(first, second)

    l1, a1, b1 = np.moveaxis(first, -1, 0)
    l2, a2, b2 = np.moveaxis(second, -1, 0)
    c1 = np.hypot(a1, b1)
    c2 = np.hypot(a2, b2)
    c_bar = (c1 + c2) / 2
    c_bar_7 = c_bar**7
    g = 0.5 * (1 - np.sqrt(c_bar_7 / (c_bar_7 + 25**7)))

    a1_prime = (1 + g) * a1
    a2_prime = (1 + g) * a2
    c1_prime = np.hypot(a1_prime, b1)
    c2_prime = np.hypot(a2_prime, b2)
    h1_prime = np.mod(np.degrees(np.arctan2(b1, a1_prime)), 360)
    h2_prime = np.mod(np.degrees(np.arctan2(b2, a2_prime)), 360)
    h1_prime = np.where(c1_prime == 0, 0, h1_prime)
    h2_prime = np.where(c2_prime == 0, 0, h2_prime)

    delta_l_prime = l2 - l1
    delta_c_prime = c2_prime - c1_prime
    delta_h = h2_prime - h1_prime
    delta_h = np.where(delta_h > 180, delta_h - 360, delta_h)
    delta_h = np.where(delta_h < -180, delta_h + 360, delta_h)
    delta_h = np.where((c1_prime * c2_prime) == 0, 0, delta_h)
    delta_h_prime = 2 * np.sqrt(c1_prime * c2_prime) * np.sin(np.radians(delta_h / 2))

    l_bar_prime = (l1 + l2) / 2
    c_bar_prime = (c1_prime + c2_prime) / 2
    hue_difference = np.abs(h1_prime - h2_prime)
    hue_sum = h1_prime + h2_prime
    h_bar_prime = np.where(
        (c1_prime * c2_prime) == 0,
        hue_sum,
        np.where(
            hue_difference <= 180,
            hue_sum / 2,
            np.where(hue_sum < 360, (hue_sum + 360) / 2, (hue_sum - 360) / 2),
        ),
    )

    hue_bar_radians = np.radians(h_bar_prime)
    t = (
        1
        - 0.17 * np.cos(hue_bar_radians - np.radians(30))
        + 0.24 * np.cos(2 * hue_bar_radians)
        + 0.32 * np.cos(3 * hue_bar_radians + np.radians(6))
        - 0.20 * np.cos(4 * hue_bar_radians - np.radians(63))
    )
    delta_theta = 30 * np.exp(-(((h_bar_prime - 275) / 25) ** 2))
    c_bar_prime_7 = c_bar_prime**7
    r_c = 2 * np.sqrt(c_bar_prime_7 / (c_bar_prime_7 + 25**7))
    s_l = 1 + 0.015 * (l_bar_prime - 50) ** 2 / np.sqrt(20 + (l_bar_prime - 50) ** 2)
    s_c = 1 + 0.045 * c_bar_prime
    s_h = 1 + 0.015 * c_bar_prime * t
    r_t = -np.sin(np.radians(2 * delta_theta)) * r_c

    delta_l_term = delta_l_prime / s_l
    delta_c_term = delta_c_prime / s_c
    delta_h_term = delta_h_prime / s_h
    result = np.sqrt(
        delta_l_term**2 + delta_c_term**2 + delta_h_term**2 + r_t * delta_c_term * delta_h_term
    )
    return np.asarray(result, dtype=np.float64)
