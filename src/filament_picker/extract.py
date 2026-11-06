from __future__ import annotations

import re
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

# Packaging (kraft cardboard spool flanges) sits in this Lab band and often
# outvotes the filament. Prefer other clusters unless the color name is warm/brown.
_CARDBOARD_L_MIN = 45.0
_CARDBOARD_L_MAX = 75.0
_CARDBOARD_C_MIN = 12.0
_CARDBOARD_C_MAX = 35.0
_NEUTRAL_C_MAX = 12.0

_NAME_EXPECT: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bblack\b|黑", re.I), "neutral_dark"),
    (re.compile(r"\bwhite\b|白", re.I), "neutral_light"),
    (re.compile(r"\bgr[ae]y\b|灰", re.I), "neutral_mid"),
    (
        re.compile(
            r"\bbrown\b|\bbeige\b|\bwood\b|\bkhaki\b|\btan\b|\bearth\b|棕|米|卡其|木|杏",
            re.I,
        ),
        "warm_brown",
    ),
    (re.compile(r"\bred\b|红|赤", re.I), "red"),
    (re.compile(r"\bpink\b|\bmagenta\b|\brose\b|粉|品红", re.I), "pink"),
    (re.compile(r"\borange\b|橙|橘", re.I), "orange"),
    (re.compile(r"\byellow\b|黄", re.I), "yellow"),
    (re.compile(r"\bgreen\b|绿", re.I), "green"),
    (re.compile(r"\bteal\b|\bcyan\b|青", re.I), "cyan"),
    (re.compile(r"\bblue\b|蓝", re.I), "blue"),
    (re.compile(r"\bpurple\b|\bviolet\b|紫", re.I), "purple"),
)

_HUE_TARGETS: dict[str, tuple[float, float]] = {
    "red": (0.0, 40.0),
    "orange": (40.0, 80.0),
    "yellow": (70.0, 110.0),
    "green": (110.0, 170.0),
    "cyan": (170.0, 220.0),
    "blue": (220.0, 280.0),
    "purple": (280.0, 330.0),
    "pink": (330.0, 40.0),  # wraps
}


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


def _is_cardboard_lab(L: float, a: float, b: float) -> bool:
    chroma = float(np.hypot(a, b))
    return (
        _CARDBOARD_L_MIN <= L <= _CARDBOARD_L_MAX
        and _CARDBOARD_C_MIN <= chroma <= _CARDBOARD_C_MAX
        and a > 0
        and b > 8
        and b >= a * 0.5
    )


def _expect_from_name(color_name: str | None) -> str | None:
    if not color_name:
        return None
    for pattern, tag in _NAME_EXPECT:
        if pattern.search(color_name):
            return tag
    return None


def _hue_in_range(hue: float, lo: float, hi: float) -> bool:
    if lo <= hi:
        return lo <= hue <= hi
    return hue >= lo or hue <= hi


def _score_cluster(L: float, a: float, b: float, share: float, expect: str | None) -> float:
    chroma = float(np.hypot(a, b))
    hue = float(np.degrees(np.arctan2(b, a))) % 360.0
    cardboard = _is_cardboard_lab(L, a, b)
    score = share

    if expect == "warm_brown":
        if cardboard or (a > 0 and b > 5):
            score += 0.5
        return score

    if cardboard:
        score -= 0.8

    if expect == "neutral_dark":
        return score + (0.6 if L < 30 and chroma < 20 else -0.3)
    if expect == "neutral_light":
        return score + (0.6 if L > 70 and chroma < 25 else -0.3)
    if expect == "neutral_mid":
        return score + (0.5 if 30 <= L <= 70 and chroma < 20 else -0.2)

    if expect in _HUE_TARGETS:
        lo, hi = _HUE_TARGETS[expect]
        in_hue = _hue_in_range(hue, lo, hi)
        score += 0.15 * min(chroma, 80.0) / 20.0
        if in_hue and chroma > 15:
            score += 0.5
        return score

    # No name hint: prefer chromatic filament over kraft cardboard.
    score += 0.1 * min(chroma, 80.0) / 20.0
    return score


def _pick_single_cluster(centers: np.ndarray, shares: np.ndarray, color_name: str | None) -> int:
    expect = _expect_from_name(color_name)
    best_i = int(np.argmax(shares))
    best_score = -1e18
    for index in range(len(centers)):
        L, a, b = (float(centers[index, 0]), float(centers[index, 1]), float(centers[index, 2]))
        score = _score_cluster(L, a, b, float(shares[index]), expect)
        if score > best_score:
            best_score = score
            best_i = index

    # If the name implies a vivid hue but the pick is still cardboard-like /
    # strongly disagreeing, fall back to the highest-chroma non-cardboard cluster.
    if expect in _HUE_TARGETS:
        L, a, b = (float(centers[best_i, 0]), float(centers[best_i, 1]), float(centers[best_i, 2]))
        chroma = float(np.hypot(a, b))
        hue = float(np.degrees(np.arctan2(b, a))) % 360.0
        lo, hi = _HUE_TARGETS[expect]
        disagree = _is_cardboard_lab(L, a, b) or (chroma > 15 and not _hue_in_range(hue, lo, hi))
        if disagree:
            alt = [
                i
                for i in range(len(centers))
                if not _is_cardboard_lab(
                    float(centers[i, 0]), float(centers[i, 1]), float(centers[i, 2])
                )
                and float(np.hypot(centers[i, 1], centers[i, 2])) > _NEUTRAL_C_MAX
            ]
            if alt:
                best_i = max(alt, key=lambda i: float(np.hypot(centers[i, 1], centers[i, 2])))
    return best_i


def extract_colors(
    path: Path,
    effects: Sequence[str],
    color_name: str | None = None,
) -> ExtractResult:
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
        keep = [_pick_single_cluster(centers, shares, color_name)]

    spread = _cluster_spread(X, labels, centers, keep)
    share = float(np.sum(shares[keep]))
    # When packaging (cardboard) dominates share, the filament cluster is a
    # minority. Don't let packaging share drag confidence below EXTRACT_MIN_CONF
    # if the chosen cluster itself is tight.
    dominant_share = float(np.max(shares)) if len(shares) else share
    if (not multi) and share + 1e-9 < dominant_share and spread <= CONF_SPREAD_DE:
        confidence = min(1.0, 0.55 + 0.45 * (1.0 - min(1.0, spread / CONF_SPREAD_DE)))
    else:
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
