from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .card import card_url_for, new_card_path, render_card
from .catalog import Catalog, CatalogValidationError
from .errors import ERROR_MESSAGES, FPError, InvalidRequestError
from .matcher import match_palette
from .note_parser import parse_note, resolve_params
from .palette import plan_palette
from .reply import build_reply_markdown
from .validate import validate_json


def _default_params() -> dict[str, Any]:
    return resolve_params(None, parse_note("")).to_dict()


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _elapsed_ms(started: datetime, finished: datetime) -> int:
    return max(0, round((finished - started).total_seconds() * 1000))


def _constraints_with_regions(request: dict[str, Any]) -> Any:
    """Prefer constraints.regions; otherwise lift request.regions into constraints."""
    constraints = request.get("constraints")
    if not isinstance(constraints, dict):
        return constraints
    if "regions" not in constraints and isinstance(request.get("regions"), list):
        return {**constraints, "regions": request["regions"]}
    return constraints


def error_result(
    request: dict[str, Any],
    code: str,
    finished_at: str,
    elapsed_ms: int,
    params: dict[str, Any],
    catalog_generated_at: str | None,
    warnings: list[str],
) -> dict[str, Any]:
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        request_id = "invalid"
    created_at = request.get("created_at")
    if not isinstance(created_at, str):
        created_at = finished_at
    context = request.get("context")
    if not isinstance(context, dict):
        context = {}
    error = {"code": code, "message_zh": ERROR_MESSAGES.get(code, ERROR_MESSAGES["INTERNAL"])}
    result: dict[str, Any] = {
        "schema_version": 1,
        "request_id": request_id,
        "status": "error",
        "created_at": created_at,
        "finished_at": finished_at,
        "elapsed_ms": elapsed_ms,
        "error": error,
        "params": params or _default_params(),
        "palette": [],
        "matches": [],
        "single_series_option": None,
        "slots_used": 0,
        "card_path": None,
        "card_url": None,
        "reply_markdown": error["message_zh"],
        "warnings": warnings,
        "context": context,
        "catalog_generated_at": catalog_generated_at,
    }
    return result


def run_plan(
    request: dict[str, Any],
    catalog: Catalog,
    root: Path,
    now: Callable[[], datetime],
    card_base_url: str | None,
) -> dict[str, Any]:
    started = now()
    finished: datetime | None = None
    params_dict = _default_params()
    warnings: list[str] = []
    try:
        if validate_json("request", request):
            raise InvalidRequestError()
        image_paths = request["image_paths"]
        if len(image_paths) > 1:
            warnings.append(f"EXTRA_IMAGES_IGNORED:{len(image_paths) - 1}")
        note = parse_note(request.get("note", ""))
        warnings.extend(note.warnings)
        params = resolve_params(_constraints_with_regions(request), note)
        params_dict = params.to_dict()
        palette = plan_palette(
            Path(image_paths[0]), params.n_colors, params.keep_small, params.regions
        )
        matched = match_palette(palette, catalog, params)
        warnings.extend(matched.warnings)
        card_path: Path | None = None
        card_url: str | None = None
        if any(match["picks"] for match in matched.matches):
            card_path = new_card_path(root)
            finished_for_card = started.date().isoformat()
            render_card(
                Path(image_paths[0]),
                palette,
                matched.matches,
                card_path,
                finished_for_card,
            )
            card_url = card_url_for(card_path, card_base_url)
        finished = now()
        result: dict[str, Any] = {
            "schema_version": 1,
            "request_id": request["request_id"],
            "status": "ok",
            "created_at": request["created_at"],
            "finished_at": _iso(finished),
            "elapsed_ms": _elapsed_ms(started, finished),
            "error": None,
            "params": params_dict,
            "palette": [color.to_dict() for color in palette],
            "matches": matched.matches,
            "single_series_option": matched.single_series_option,
            "slots_used": matched.slots_used,
            "card_path": str(card_path) if card_path is not None else None,
            "card_url": card_url,
            "reply_markdown": "",
            "warnings": warnings,
            "context": request.get("context", {}),
            "catalog_generated_at": catalog.generated_at,
        }
        result["reply_markdown"] = build_reply_markdown(result)
        errors = validate_json("result", result)
        if errors:
            return error_result(
                request,
                "INTERNAL",
                _iso(finished),
                _elapsed_ms(started, finished),
                params_dict,
                catalog.generated_at,
                warnings,
            )
        return result
    except (FPError, CatalogValidationError) as exc:
        finished = now()
        return error_result(
            request,
            exc.code if isinstance(exc, FPError) else "CATALOG_ERROR",
            _iso(finished),
            _elapsed_ms(started, finished),
            params_dict,
            catalog.generated_at,
            warnings,
        )
