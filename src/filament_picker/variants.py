from __future__ import annotations

import re

from .ids import RowInfo
from .ingest import InventorySeries
from .names import nfkc

VARIANT_RE: re.Pattern[str] = re.compile(r"^variant_(\d{2,3})_(.+)\.(jpg|jpeg|png|webp)$", re.I)
VariantIndex = dict[tuple[str, str], dict[str, str]]


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", nfkc(s).lower())


def build_variant_index(inventory: list[InventorySeries]) -> VariantIndex:
    index: VariantIndex = {}
    for series in inventory:
        key = (series.brand, series.series)
        variants = index.setdefault(key, {})
        for path in series.variant_image_paths:
            match = VARIANT_RE.match(path.rsplit("/", 1)[-1])
            if match is not None:
                variants.setdefault(norm_key(match[2]), path)
    return index


def find_variant_image(index: VariantIndex, info: RowInfo) -> str | None:
    variants = index.get((info.row.brand, info.row.series), {})
    candidates = [info.row.color_raw]
    if info.parsed.name_en:
        candidates.append(info.parsed.name_en)
        if info.parsed.code:
            candidates.append(f"{info.parsed.name_en} {info.parsed.code}")
    for candidate in candidates:
        path = variants.get(norm_key(candidate))
        if path is not None:
            return path
    return None
