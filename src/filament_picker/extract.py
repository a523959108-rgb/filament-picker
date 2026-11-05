from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from .ciede2000 import delta_e_2000
from .colorspace import lab_to_hex, rgb_to_lab
from .config import (
    CONF_PENALTY_EFFECTS,
    CONF_PENALTY_FACTOR,
    CONF_SPREAD_DE,
    EXTRACT_K_MULTI,
    EXTRACT_K_SINGLE,
    EXTRACT_LONG_SIDE,
    MAX_SAMPLE,
    MIN_PIXELS,
    MULTI_MAX_COLORS,
    MULTI_MIN_SHARE,
)
from .images import apply_shadow_rule, foreground_mask, load_rgb, resize_long_side
from .kmeans import kmeans, sample_pixels


@dataclass(frozen=True, slots=True)
class ExtractResult:
    status: Literal["ok", "no_foreground"]
    hexes: tuple[str, ...]
    confidence: float
    share: float
    spread: float
    n_pixels: int


MULTI_EFFECTS: tuple[str, ...] = ("multi", "dual", "tri", "gradient")


def _cluster_spread(
    X: np.ndarray, labels: np.ndarray, centers: np.ndarray, indices: Sequence[int]
) -> float:
    selected = np.isin(labels, np.asarray(indices, dtype=np.int64))
    if not np.any(selected):
        return 0.0
    distances = np.empty(int(selected.sum()), dtype=np.float64)
    offset = 0
    for index in indices:
        members = X[labels == index]
        if len(members) == 0:
            continue
        count = len(members)
        distances[offset : offset + count] = delta_e_2000(members, centers[index])
        offset += count
    return float(np.median(distances[:offset])) if offset else 0.0


def extract_colors(path: Path, effects: Sequence[str]) -> ExtractResult:
    rgb = resize_long_side(load_rgb(path), EXTRACT_LONG_SIDE)
    lab = rgb_to_lab(rgb)
    X = apply_shadow_rule(lab[foreground_mask(lab, drop_highlights=True)])
    if len(X) < MIN_PIXELS:
        return ExtractResult("no_foreground", (), 0.0, 0.0, 0.0, 0)

    X = sample_pixels(X, MAX_SAMPLE, seed=0)
    multi = any(effect in MULTI_EFFECTS for effect in effects)
    if multi:
        centers, labels, shares = kmeans(X, EXTRACT_K_MULTI)
        order = np.argsort(-shares)
        keep = [int(index) for index in order if shares[index] >= MULTI_MIN_SHARE][
            :MULTI_MAX_COLORS
        ]
        if not keep:
            keep = [int(order[0])]
    else:
        centers, labels, shares = kmeans(X, EXTRACT_K_SINGLE)
        keep = [int(np.argmax(shares))]

    spread = _cluster_spread(X, labels, centers, keep)
    share = float(np.sum(shares[keep]))
    confidence = share * (1.0 - min(1.0, spread / CONF_SPREAD_DE))
    if any(effect in CONF_PENALTY_EFFECTS for effect in effects):
        confidence *= CONF_PENALTY_FACTOR
    hexes = tuple(lab_to_hex(centers[index]) for index in keep)
    return ExtractResult(
        "ok",
        hexes,
        round(confidence, 3),
        round(share, 3),
        round(spread, 2),
        len(X),
    )
