from __future__ import annotations

from collections.abc import Sequence
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
from .note_parser import SampleRegion

# A cluster is salient when it is vivid, or near black. Vivid means chroma at
# least this high and no nearer cluster (within CHROMA_PEAK_DE) is more vivid,
# so a shaded duplicate of the same orange does not take its own slot.
SALIENT_CHROMA = 42.0
NEAR_BLACK_L = 22.0
CHROMA_PEAK_DE = 20.0
# Only a low-chroma neighbor closer than this can be displaced to free a slot.
REDUNDANT_DE = 18.0
# Click radius as a fraction of the original image's short side.
POINT_RADIUS_FRAC = 0.04


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


def _chroma(center: np.ndarray) -> float:
    return float(np.hypot(center[1], center[2]))


def _is_salient(index: int, clusters: list[tuple[np.ndarray, float]]) -> bool:
    center = clusters[index][0]
    if float(center[0]) <= NEAR_BLACK_L:
        return True
    chroma = _chroma(center)
    if chroma < SALIENT_CHROMA:
        return False
    for other_index, (other, _) in enumerate(clusters):
        if other_index == index:
            continue
        if _chroma(other) > chroma and float(delta_e_2000(center, other)) < CHROMA_PEAK_DE:
            return False
    return True


def _redundant_index(kept: list[tuple[np.ndarray, float]], flags: list[bool]) -> int | None:
    """Index of a neutral shade that can be dropped, or None.

    The lightest and darkest neutrals stay when they differ by at least
    REDUNDANT_DE, so a cream and a brown are not traded for each other.
    Shades whose L sits between those two, and any near-duplicate pair, can go.
    """
    neutral = [index for index, salient in enumerate(flags) if not salient]
    if len(neutral) < 2:
        return None
    lightest = max(neutral, key=lambda index: float(kept[index][0][0]))
    darkest = min(neutral, key=lambda index: float(kept[index][0][0]))
    endpoints_close = float(delta_e_2000(kept[lightest][0], kept[darkest][0])) < REDUNDANT_DE
    best: tuple[float, float, int] | None = None
    for index in neutral:
        if not endpoints_close and index in (lightest, darkest):
            continue
        center, share = kept[index]
        distances = [
            float(delta_e_2000(center, other))
            for other_index, (other, _) in enumerate(kept)
            if other_index != index
        ]
        min_de = min(distances)
        if min_de >= REDUNDANT_DE:
            continue
        key = (min_de, share, index)
        if best is None or key < best:
            best = key
    return None if best is None else best[2]


def _protect_salient(
    clusters: list[tuple[np.ndarray, float]], n_colors: int
) -> list[tuple[np.ndarray, float]]:
    """Keep vivid and near-black clusters by displacing redundant neutrals.

    Share-ranked truncation drops a 5% orange when four beige shades already
    fill ``n_colors``. Those beiges are interchangeable; the orange is not.
    Clusters below ``SMALL_SHARE`` are still merged earlier, so a 1% speck
    does not get this protection.
    """
    if n_colors < 1 or len(clusters) <= n_colors:
        return clusters
    flags = [_is_salient(index, clusters) for index in range(len(clusters))]
    kept = [[clusters[index], flags[index]] for index in range(n_colors)]
    rest = [[clusters[index], flags[index]] for index in range(n_colors, len(clusters))]
    for index, slot in enumerate(rest):
        if not slot[1]:
            continue
        victim = _redundant_index([row[0] for row in kept], [row[1] for row in kept])
        if victim is None:
            break
        rest[index] = kept[victim]
        kept[victim] = slot
    selected = [row[0] for row in kept]
    displaced = [row[0] for row in rest]
    return _sort_clusters(selected) + displaced


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


def _regions_mask(
    height: int,
    width: int,
    orig_h: int,
    orig_w: int,
    regions: Sequence[SampleRegion],
) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    scale_y = height / orig_h
    scale_x = width / orig_w
    short_side = min(orig_w, orig_h)
    for region in regions:
        if region.space == "px":
            x, y = region.x, region.y
            rect_w = region.w
            rect_h = region.h
            radius = region.r
        else:
            x, y = region.x * orig_w, region.y * orig_h
            rect_w = None if region.w is None else region.w * orig_w
            rect_h = None if region.h is None else region.h * orig_h
            radius = None if region.r is None else region.r * short_side
        if rect_w is not None and rect_h is not None:
            x0 = max(0, int(np.floor(x * scale_x)))
            y0 = max(0, int(np.floor(y * scale_y)))
            x1 = min(width, int(np.ceil((x + rect_w) * scale_x)))
            y1 = min(height, int(np.ceil((y + rect_h) * scale_y)))
            if x1 > x0 and y1 > y0:
                mask[y0:y1, x0:x1] = True
            continue
        if radius is None:
            radius = POINT_RADIUS_FRAC * short_side
        resized_short = min(height, width)
        radius_px = radius * resized_short / short_side
        yy, xx = np.ogrid[:height, :width]
        mask |= (xx - x * scale_x) ** 2 + (yy - y * scale_y) ** 2 <= radius_px**2
    return mask


def plan_palette(
    path: Path,
    n_colors: int,
    keep_small: bool,
    regions: Sequence[SampleRegion] | None = None,
) -> list[PaletteColor]:
    rgb = load_rgb(path)
    if min(rgb.shape[:2]) < PLAN_MIN_SIDE:
        raise ImageTooSmallError

    resized = resize_long_side(rgb, PLAN_LONG_SIDE)
    lab = rgb_to_lab(resized)
    foreground = foreground_mask(lab, drop_highlights=False)
    if regions:
        foreground &= _regions_mask(
            resized.shape[0], resized.shape[1], rgb.shape[0], rgb.shape[1], regions
        )
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
    clusters = _protect_salient(clusters, n_colors)
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
