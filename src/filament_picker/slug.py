from __future__ import annotations

import hashlib
import re

from pypinyin import lazy_pinyin

from filament_picker.config import MAX_SLUG_LEN
from filament_picker.names import ParsedName, nfkc


def slug(s: str, maxlen: int = MAX_SLUG_LEN) -> str:
    s = nfkc(s).lower()
    s = "".join(
        "-" + lazy_pinyin(ch)[0] + "-" if re.match(r"[\u3400-\u9fff]", ch) else ch for ch in s
    )
    s = s.replace("&", "-").replace("+", "-plus-")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rsplit("-", 1)[0]
    return s


def series_clean(s: str) -> str:
    return re.sub(r"\s*\(拼多多\)\s*$", "", nfkc(s)).strip()


def series_slug(s: str) -> str:
    return slug(series_clean(s))


def color_segment(parsed: ParsedName, raw: str) -> str:
    base = (
        slug(parsed.name_en) if parsed.name_en else (slug(parsed.name_zh) if parsed.name_zh else "")
    )
    if parsed.code:
        base = (base + "-" if base else "") + slug(parsed.code)
    return base or "x" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def row_id(brand_slug: str, series: str, parsed: ParsedName, raw: str) -> str:
    return f"{brand_slug}/{series_slug(series)}/{color_segment(parsed, raw)}"


def pinyin_fields(name_zh: str | None) -> tuple[str | None, str | None]:
    if name_zh is None:
        return None, None
    cjk_only = re.sub(r"[^\u3400-\u9fff]", "", name_zh)
    pinyin = lazy_pinyin(cjk_only)
    return " ".join(pinyin), "".join(x[0] for x in pinyin)
