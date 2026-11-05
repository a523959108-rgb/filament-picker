from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .ciede2000 import delta_e_2000
from .colorspace import lab_to_hex, rgb_to_lab
from .config import (
    MERGE_DE,
    MIN_PIXELS,
    PLAN_LONG_SIDE,
    PLAN_MAX_SAMPLE,
    PLAN_MIN_SIDE,
    SMALL_SHARE,
)
from .errors import ImageTooSmallError, NoForegroundError
from .images import foreground_mask, load_rgb, resize_long_side
from .kmeans import kmeans, sample_pixels


@dataclass(frozen=True, slots=True)
class PaletteColor:
    index: int
    hex: str
    lab: tuple[float, float, float]
    share: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "hex": self.hex,
            "lab": list(self.lab),
            "share": self.share,
        }


def _merge_clusters(
    clusters: list[tuple[np.ndarray, float]], first: int, second: int
) -> list[tuple[np.ndarray, float]]:
    center_a, share_a = clusters[first]
    center_b, share_b = clusters[second]
    share = share_a + share_b
    center = (center_a * share_a + center_b * share_b) / share
    return [cluster for index, cluster in enumerate(clusters) if index not in (first, second)] + [
        (center, share)
    ]


def _closest_pair(clusters: list[tuple[np.ndarray, float]]) -> tuple[int, int, float]:
    pairs = [
        (float(delta_e_2000(clusters[first][0], clusters[second][0])), first, second)
        for first in range(len(clusters))
        for second in range(first + 1, len(clusters))
    ]
    distance, first, second = min(pairs)
    return first, second, distance


def _merge_similar(clusters: list[tuple[np.ndarray, float]]) -> list[tuple[np.ndarray, float]]:
    while len(clusters) > 1:
        first, second, distance = _closest_pair(clusters)
        if distance >= MERGE_DE:
            break
        clusters = _merge_clusters(clusters, first, second)
    return clusters


def _merge_small(clusters: list[tuple[np.ndarray, float]]) -> list[tuple[np.ndarray, float]]:
    while len(clusters) > 1:
        small = min(
            (index for index, (_, share) in enumerate(clusters) if share < SMALL_SHARE),
            key=lambda index: clusters[index][1],
            default=None,
        )
        if small is None:
            break
        candidates = [index for index in range(len(clusters)) if index != small]
        target = min(
            candidates,
            key=lambda index: float(delta_e_2000(clusters[small][0], clusters[index][0])),
        )
        first, second = sorted((small, target))
        clusters = _merge_clusters(clusters, first, second)
    return clusters


def _sort_clusters(clusters: list[tuple[np.ndarray, float]]) -> list[tuple[np.ndarray, float]]:
    return sorted(clusters, key=lambda cluster: (-round(cluster[1], 2), cluster[0][0]))


def _keep_clusters(
    clusters: list[tuple[np.ndarray, float]], n_colors: int
) -> list[tuple[np.ndarray, float]]:
    kept = clusters[:n_colors]
    for center, share in clusters[n_colors:]:
        target = min(
            range(len(kept)),
            key=lambda index: float(delta_e_2000(center, kept[index][0])),
        )
        target_center, target_share = kept[target]
        kept[target] = (target_center, target_share + share)
    return kept


def plan_palette(path: Path, n_colors: int, keep_small: bool) -> list[PaletteColor]:
    rgb = load_rgb(path)
    if min(rgb.shape[:2]) < PLAN_MIN_SIDE:
        raise ImageTooSmallError

    resized = resize_long_side(rgb, PLAN_LONG_SIDE)
    lab = rgb_to_lab(resized)
    foreground = foreground_mask(lab, drop_highlights=False)
    values = lab[foreground]
    if len(values) < MIN_PIXELS:
        raise NoForegroundError

    values = sample_pixels(values, PLAN_MAX_SAMPLE, seed=0)
    centers, _, shares = kmeans(values, min(16, 2 * n_colors))
    clusters = [(center, float(share)) for center, share in zip(centers, shares, strict=True)]
    clusters = _merge_similar(clusters)
    if not keep_small:
        clusters = _merge_small(clusters)
    clusters = _sort_clusters(clusters)
    clusters = _keep_clusters(clusters, n_colors)

    total = sum(share for _, share in clusters)
    return [
        PaletteColor(
            index=index,
            hex=lab_to_hex(center),
            lab=tuple(round(float(value), 2) for value in center),
            share=round(share / total, 3),
        )
        for index, (center, share) in enumerate(clusters)
    ]
