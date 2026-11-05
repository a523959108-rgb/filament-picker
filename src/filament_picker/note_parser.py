from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .brands import BRAND_ALIASES, BRAND_ORDER
from .config import DEFAULT_AMS_SLOTS, DEFAULT_MATERIALS, DEFAULT_MAX_COLORS, DEFAULT_PER_COLOR
from .names import nfkc

CN_NUM: dict[str, int] = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_MAX_COLORS_ZH = re.compile(
    r"(\d{1,2}|[一二两三四五六七八九十])\s*(?:个|种)?\s*(?:颜色|色)(?![差号])"
)
_MAX_COLORS_EN = re.compile(r"(\d{1,2})\s*colou?rs?\b")
_AMS_SLOTS = re.compile(r"(\d{1,2})\s*个?(?:料槽|槽位|槽|slots?)")
_AMS_COUNT_BEFORE = re.compile(r"(\d|[一二两三四])\s*(?:台|个|套)\s*ams")
_AMS_COUNT_AFTER = re.compile(r"ams\s*(?:lite\s*)?(\d|[一二两三四])\s*(?:台|个|套)")
_MATERIAL_PLA = re.compile(r"(?<![a-z])pla(?![a-z])")
_MATERIAL_PETG = re.compile(r"(?<![a-z])petg(?![a-z])")


@dataclass(frozen=True, slots=True)
class NoteParse:
    values: dict[str, Any]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Params:
    max_colors: int
    ams_slots: int
    n_colors: int
    materials: tuple[str, ...]
    brands: tuple[str, ...]
    allow_approx: bool
    keep_small: bool
    per_color: int
    note_parsed: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_colors": self.max_colors,
            "ams_slots": self.ams_slots,
            "n_colors": self.n_colors,
            "materials": list(self.materials),
            "brands": list(self.brands),
            "allow_approx": self.allow_approx,
            "keep_small": self.keep_small,
            "per_color": self.per_color,
            "note_parsed": dict(self.note_parsed),
        }


def _number(value: str) -> int:
    if value in CN_NUM:
        return CN_NUM[value]
    return int(value)


def _set_bounded(values: dict[str, Any], warnings: list[str], key: str, value: int) -> None:
    if 1 <= value <= 16:
        values[key] = value
    else:
        warnings.append(f"NOTE_VALUE_OUT_OF_RANGE:{key}={value}")


def parse_note(text: str) -> NoteParse:
    t = nfkc(text).lower()
    values: dict[str, Any] = {}
    warnings: list[str] = []

    max_match = _MAX_COLORS_ZH.search(t) or _MAX_COLORS_EN.search(t)
    if max_match is not None:
        _set_bounded(values, warnings, "max_colors", _number(max_match[1]))

    slots_match = _AMS_SLOTS.search(t)
    if slots_match is not None:
        _set_bounded(values, warnings, "ams_slots", int(slots_match[1]))
    else:
        count_match = _AMS_COUNT_BEFORE.search(t) or _AMS_COUNT_AFTER.search(t)
        if count_match is not None:
            _set_bounded(values, warnings, "ams_slots", 4 * _number(count_match[1]))
        elif "ams" in t:
            values["ams_slots"] = 4

    materials: list[str] = []
    if _MATERIAL_PLA.search(t):
        materials.append("PLA")
    if _MATERIAL_PETG.search(t):
        materials.append("PETG")
    if materials:
        values["materials"] = materials

    brands = [slug for slug in BRAND_ORDER if any(alias in t for alias in BRAND_ALIASES[slug])]
    if brands:
        values["brands"] = brands

    if re.search(r"只要官方|官方色|official only|only official", t):
        values["allow_approx"] = False

    if re.search(r"保留细节|小色块|keep small", t):
        values["keep_small"] = True

    ordered_values = {
        key: values[key]
        for key in ("max_colors", "ams_slots", "materials", "brands", "allow_approx", "keep_small")
        if key in values
    }
    return NoteParse(values=ordered_values, warnings=tuple(warnings))


def resolve_params(constraints: dict[str, Any] | None, note: NoteParse) -> Params:
    explicit = constraints or {}

    max_colors = explicit.get("max_colors", note.values.get("max_colors", DEFAULT_MAX_COLORS))
    ams_slots = explicit.get("ams_slots", note.values.get("ams_slots", DEFAULT_AMS_SLOTS))
    materials = explicit.get("materials", note.values.get("materials", DEFAULT_MATERIALS))
    brands = explicit.get("brands", note.values.get("brands", ()))
    allow_approx = explicit.get("allow_approx", note.values.get("allow_approx", True))
    keep_small = explicit.get("keep_small", note.values.get("keep_small", False))
    per_color = explicit.get("per_color", DEFAULT_PER_COLOR)

    return Params(
        max_colors=int(max_colors),
        ams_slots=int(ams_slots),
        n_colors=min(int(max_colors), int(ams_slots)),
        materials=tuple(materials),
        brands=tuple(brands),
        allow_approx=bool(allow_approx),
        keep_small=bool(keep_small),
        per_color=int(per_color),
        note_parsed=dict(note.values),
    )
