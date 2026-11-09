"""Read-only Spoolman client for optional stock ranking.

Off unless FP_SPOOLMAN_ENABLED is set. Planner, the plan API, and model color
matches call load_spools(); a failure returns no spools and leaves results as
they were. See docs/spoolman-integration.md. Tests mock HTTP. This module has
no default host and does not call a live Spoolman.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from .brands import BRAND_ALIASES, BRAND_SLUGS
from .ciede2000 import delta_e_2000
from .colorspace import hex_to_lab
from .config import MATCH_MAX_DE

COLOR_ID_EXTRA_KEY = "filament_picker_color_id"
SPOOLMAN_DEFAULT_TIMEOUT_S = 3.0
logger = logging.getLogger(__name__)

_COLOR_ID_RE = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:-[a-z0-9]+)*$"
)
_TRUE = {"1", "true", "yes"}
_FALSE = {"0", "false", "no", ""}
_HEX_DIGITS = set("0123456789ABCDEF")

MatchKind = Literal["color_id", "brand_material_color", "none"]


class SpoolmanError(RuntimeError):
    """Spoolman is enabled, but the response cannot be used."""


@dataclass(frozen=True, slots=True)
class SpoolmanSettings:
    enabled: bool
    base_url: str | None
    timeout_s: float


@dataclass(frozen=True, slots=True)
class SpoolSnapshot:
    spool_id: int
    filament_id: int
    color_id: str | None
    vendor_name: str | None
    material: str | None
    color_hex: str | None
    remaining_weight_g: float | None
    location: str | None
    archived: bool

    @property
    def in_stock(self) -> bool:
        weight = self.remaining_weight_g
        return (not self.archived) and weight is not None and weight > 0


@dataclass(frozen=True, slots=True)
class StockHint:
    color_id: str
    in_stock: bool
    nearby_in_stock: bool
    match: MatchKind
    remaining_weight_g: float | None
    location: str | None
    spool_id: int | None


def spoolman_settings() -> SpoolmanSettings:
    enabled = _parse_enabled(os.environ.get("FP_SPOOLMAN_ENABLED", "0"))
    raw_url = os.environ.get("FP_SPOOLMAN_BASE_URL", "").strip()
    base_url = _normalize_base_url(raw_url) if raw_url else None
    if enabled and base_url is None:
        raise ValueError("FP_SPOOLMAN_BASE_URL is required when FP_SPOOLMAN_ENABLED=1")
    timeout_s = _parse_timeout(os.environ.get("FP_SPOOLMAN_TIMEOUT_S", ""))
    return SpoolmanSettings(enabled, base_url, timeout_s)


def spool_list_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/v1/spool"


def vendor_brand_slug(vendor_name: str | None) -> str | None:
    if vendor_name is None:
        return None
    stripped = vendor_name.strip()
    if stripped in BRAND_SLUGS:
        return BRAND_SLUGS[stripped]
    folded = stripped.casefold()
    for name, slug in BRAND_SLUGS.items():
        if name.casefold() == folded or slug == folded:
            return slug
    for slug, aliases in BRAND_ALIASES.items():
        for alias in aliases:
            if alias.casefold() == folded:
                return slug
    return None


def parse_spool(item: Any) -> SpoolSnapshot:
    if not isinstance(item, dict):
        raise SpoolmanError("Spoolman spool must be an object")
    filament = item.get("filament")
    if not isinstance(filament, dict):
        raise SpoolmanError("Spoolman spool is missing filament")
    return SpoolSnapshot(
        spool_id=_required_int(item.get("id"), "spool id"),
        filament_id=_required_int(filament.get("id"), "filament id"),
        color_id=_color_id_from_filament(filament),
        vendor_name=_vendor_name(filament),
        material=_material(filament),
        color_hex=_color_hex(filament),
        remaining_weight_g=_optional_float(item.get("remaining_weight"), "remaining_weight"),
        location=_location(item),
        archived=_archived(item),
    )


class SpoolmanClient:
    def __init__(
        self,
        settings: SpoolmanSettings,
        opener: Callable[[str, float], bytes] | None = None,
    ) -> None:
        self.settings = settings
        self._opener = _http_get if opener is None else opener

    def list_spools(self) -> tuple[SpoolSnapshot, ...]:
        if not self.settings.enabled:
            return ()
        if self.settings.base_url is None:
            raise SpoolmanError("Spoolman is enabled without a base URL")
        body = self._opener(spool_list_url(self.settings.base_url), self.settings.timeout_s)
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SpoolmanError("Spoolman returned invalid JSON") from exc
        if not isinstance(payload, list):
            raise SpoolmanError("Spoolman spool list must be a JSON array")
        return tuple(parse_spool(item) for item in payload)


def stock_hint(entry: Mapping[str, Any], spools: Sequence[SpoolSnapshot]) -> StockHint:
    color_id = entry.get("id")
    if not isinstance(color_id, str):
        raise ValueError("catalog entry is missing id")
    exact = _pick_exact([spool for spool in spools if spool.color_id == color_id])
    if exact is not None:
        return StockHint(
            color_id=color_id,
            in_stock=exact.in_stock,
            nearby_in_stock=False,
            match="color_id",
            remaining_weight_g=exact.remaining_weight_g,
            location=exact.location,
            spool_id=exact.spool_id,
        )
    nearby = _pick_nearby(entry, spools)
    if nearby is not None:
        return StockHint(
            color_id=color_id,
            in_stock=False,
            nearby_in_stock=nearby.in_stock,
            match="brand_material_color",
            remaining_weight_g=nearby.remaining_weight_g,
            location=nearby.location,
            spool_id=nearby.spool_id,
        )
    return StockHint(color_id, False, False, "none", None, None, None)


def load_spools(
    settings: SpoolmanSettings | None = None,
    opener: Callable[[str, float], bytes] | None = None,
) -> tuple[SpoolSnapshot, ...]:
    """Return spools, or () when Spoolman is off, unreachable, or misconfigured.

    Callers keep today's recommendations in that case. The warning is for the
    private host log; it is not copied into the plan response.
    """
    try:
        resolved = spoolman_settings() if settings is None else settings
        return SpoolmanClient(resolved, opener).list_spools()
    except (SpoolmanError, ValueError, OSError) as exc:
        logger.warning("Spoolman stock unavailable: %s", exc)
        return ()


def annotate_picks(
    picks: Sequence[Mapping[str, Any]],
    entries_by_id: Mapping[str, Mapping[str, Any]],
    spools: Sequence[SpoolSnapshot],
) -> list[dict[str, Any]]:
    """Reorder picks when spools were read. Empty spools leave the rows unchanged.

    The attached stock object is only the two public booleans. Remaining grams,
    location, and spool id stay on the server.
    """
    if not spools:
        return [dict(pick) for pick in picks]
    annotated = annotate_recommendations(picks, entries_by_id, spools)
    for item in annotated:
        stock = item["stock"]
        item["stock"] = {
            "in_stock": bool(stock["in_stock"]),
            "nearby_in_stock": bool(stock["nearby_in_stock"]),
        }
    return annotated


def in_stock_hints(
    color_ids: Sequence[str],
    entries_by_id: Mapping[str, Mapping[str, Any]],
    spools: Sequence[SpoolSnapshot],
) -> dict[str, dict[str, bool]]:
    """Map color ids that are actually in stock. Nearby colors are omitted."""
    hints: dict[str, dict[str, bool]] = {}
    if not spools:
        return hints
    for color_id in color_ids:
        if color_id in hints:
            continue
        entry = entries_by_id.get(color_id)
        if entry is None:
            continue
        hint = stock_hint(entry, spools)
        if hint.in_stock and hint.match == "color_id":
            hints[color_id] = {"in_stock": True, "nearby_in_stock": False}
    return hints


def annotate_recommendations(
    matches: Sequence[Mapping[str, Any]],
    entries_by_id: Mapping[str, Mapping[str, Any]],
    spools: Sequence[SpoolSnapshot],
) -> list[dict[str, Any]]:
    """Copy matcher rows, attach stock, and stable-sort in-stock rows first.

    Out-of-stock recommendations stay in the list. This function does not fetch
    Spoolman and does not drop a color that still has a buy link.
    """
    annotated: list[dict[str, Any]] = []
    for match in matches:
        color_id = match.get("id")
        if not isinstance(color_id, str):
            raise ValueError("recommendation is missing id")
        entry = entries_by_id.get(color_id)
        hint = (
            stock_hint(entry, spools)
            if entry is not None
            else StockHint(color_id, False, False, "none", None, None, None)
        )
        annotated.append({**dict(match), "stock": _stock_dict(hint)})
    annotated.sort(key=_sort_rank)
    return annotated


def _parse_enabled(raw: str) -> bool:
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError("FP_SPOOLMAN_ENABLED must be 0 or 1")


def _parse_timeout(raw: str) -> float:
    if raw.strip() == "":
        return SPOOLMAN_DEFAULT_TIMEOUT_S
    try:
        timeout_s = float(raw)
    except ValueError as exc:
        raise ValueError("FP_SPOOLMAN_TIMEOUT_S must be a positive number") from exc
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("FP_SPOOLMAN_TIMEOUT_S must be a positive number")
    return timeout_s


def _normalize_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("FP_SPOOLMAN_BASE_URL must not contain credentials")
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("FP_SPOOLMAN_BASE_URL must be an http(s) URL")
    if parsed.query or parsed.fragment:
        raise ValueError("FP_SPOOLMAN_BASE_URL must not contain a query or fragment")
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def _is_color_id(value: str) -> bool:
    return len(value) <= 190 and _COLOR_ID_RE.fullmatch(value) is not None


def _decode_extra_text(raw: str) -> str:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, str):
        return parsed
    return raw


def _color_id_from_filament(filament: Mapping[str, Any]) -> str | None:
    extra = filament.get("extra", {})
    if extra is None:
        extra = {}
    if not isinstance(extra, dict):
        raise SpoolmanError("Spoolman filament extra must be an object")
    if COLOR_ID_EXTRA_KEY in extra:
        raw = extra[COLOR_ID_EXTRA_KEY]
        if not isinstance(raw, str):
            raise SpoolmanError("Spoolman filament_picker_color_id must be a string")
        decoded = _decode_extra_text(raw)
        if not _is_color_id(decoded):
            raise SpoolmanError("Spoolman filament_picker_color_id is not a color_id")
        return decoded
    external_id = filament.get("external_id")
    if isinstance(external_id, str) and _is_color_id(external_id):
        return external_id
    if external_id is not None and not isinstance(external_id, str):
        raise SpoolmanError("Spoolman external_id must be a string")
    return None


def _vendor_name(filament: Mapping[str, Any]) -> str | None:
    vendor = filament.get("vendor")
    if vendor is None:
        return None
    if not isinstance(vendor, dict):
        raise SpoolmanError("Spoolman vendor must be an object")
    name = vendor.get("name")
    if name is None:
        return None
    if not isinstance(name, str):
        raise SpoolmanError("Spoolman vendor name must be a string")
    stripped = name.strip()
    return stripped or None


def _material(filament: Mapping[str, Any]) -> str | None:
    value = filament.get("material")
    if value is None:
        return None
    if not isinstance(value, str):
        raise SpoolmanError("Spoolman material must be a string")
    stripped = value.strip()
    return stripped or None


def _color_hex(filament: Mapping[str, Any]) -> str | None:
    multi = filament.get("multi_color_hexes")
    if isinstance(multi, str) and multi.strip():
        return None
    value = filament.get("color_hex")
    if value is None:
        return None
    if not isinstance(value, str):
        raise SpoolmanError("Spoolman color_hex must be a string")
    text = value.strip().removeprefix("#").upper()
    if len(text) not in {6, 8} or any(char not in _HEX_DIGITS for char in text):
        return None
    return "#" + text[:6]


def _location(item: Mapping[str, Any]) -> str | None:
    value = item.get("location")
    if value is None:
        return None
    if not isinstance(value, str):
        raise SpoolmanError("Spoolman location must be a string")
    return value or None


def _archived(item: Mapping[str, Any]) -> bool:
    value = item.get("archived")
    if value is None:
        return False
    if not isinstance(value, bool):
        raise SpoolmanError("Spoolman archived must be a boolean")
    return value


def _required_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpoolmanError(f"Spoolman {field} must be an integer")
    return value


def _optional_float(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpoolmanError(f"Spoolman {field} must be a number")
    return float(value)


def _http_get(url: str, timeout_s: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise SpoolmanError(f"Spoolman returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SpoolmanError("Spoolman request failed") from exc


def _pick_exact(spools: Sequence[SpoolSnapshot]) -> SpoolSnapshot | None:
    if not spools:
        return None
    return min(
        spools,
        key=lambda spool: (
            0 if spool.in_stock else 1,
            -(spool.remaining_weight_g if spool.remaining_weight_g is not None else 0.0),
            spool.spool_id,
        ),
    )


def _pick_nearby(entry: Mapping[str, Any], spools: Sequence[SpoolSnapshot]) -> SpoolSnapshot | None:
    hexes = entry.get("hex")
    if not isinstance(hexes, list) or len(hexes) != 1 or not isinstance(hexes[0], str):
        return None
    brand = entry.get("brand_slug")
    material = entry.get("material")
    if not isinstance(brand, str) or not isinstance(material, str):
        return None
    target = hex_to_lab(hexes[0])
    material_key = material.casefold()
    best: tuple[tuple[int, float, int], SpoolSnapshot] | None = None
    for spool in spools:
        if spool.color_hex is None or spool.material is None:
            continue
        if vendor_brand_slug(spool.vendor_name) != brand:
            continue
        if spool.material.casefold() != material_key:
            continue
        distance = float(delta_e_2000(target, hex_to_lab(spool.color_hex)))
        if distance > MATCH_MAX_DE:
            continue
        rank = (0 if spool.in_stock else 1, distance, spool.spool_id)
        if best is None or rank < best[0]:
            best = (rank, spool)
    return None if best is None else best[1]


def _stock_dict(hint: StockHint) -> dict[str, Any]:
    return {
        "in_stock": hint.in_stock,
        "nearby_in_stock": hint.nearby_in_stock,
        "match": hint.match,
        "remaining_weight_g": hint.remaining_weight_g,
        "location": hint.location,
        "spool_id": hint.spool_id,
    }


def _sort_rank(item: Mapping[str, Any]) -> int:
    stock = item["stock"]
    if stock["match"] == "color_id" and stock["in_stock"]:
        return 0
    if stock["match"] == "brand_material_color" and stock["nearby_in_stock"]:
        return 1
    return 2
