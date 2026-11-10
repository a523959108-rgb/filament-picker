from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .auth import warn_if_preview_user_unconfigured
from .card import CARD_NAME_RE
from .catalog import load_catalog
from .config import TZ
from .lumina_bridge import LuminaValidationError, cors_headers, match_request
from .models import mount_model_preview
from .planner import run_plan
from .spoolman import in_stock_hints, load_spools

_STOCK_ID_LIMIT = 32

MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
ALLOWED_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/heic": "heic",
}


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _read_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="图片超过 10MB")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_constraints(value: str | None) -> Any:
    if value is None:
        return {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


@asynccontextmanager
async def _app_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    warn_if_preview_user_unconfigured()
    yield


def create_app(
    catalog_path: Path,
    root: Path,
    card_base_url: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> FastAPI:
    catalog = load_catalog(catalog_path)
    now_fn = now or (lambda: datetime.now(ZoneInfo(TZ)))
    app = FastAPI(lifespan=_app_lifespan)
    mount_model_preview(app, catalog)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "catalog_generated_at": catalog.generated_at}

    @app.options("/api/lumina/match")
    async def lumina_match_options(request: Request) -> JSONResponse:
        return JSONResponse({}, headers=cors_headers(request.headers.get("origin"), preflight=True))

    @app.post("/api/lumina/match")
    async def lumina_match(request: Request) -> JSONResponse:
        headers = cors_headers(request.headers.get("origin"))
        try:
            payload = await request.json()
        except (ValueError, UnicodeError):
            detail = {
                "detail": [
                    {
                        "loc": ["body"],
                        "msg": "request body must be valid JSON",
                        "type": "value_error",
                    }
                ]
            }
            return JSONResponse(
                detail,
                status_code=422,
                headers=headers,
            )
        try:
            result = match_request(payload, catalog)
        except LuminaValidationError as exc:
            return JSONResponse({"detail": exc.errors}, status_code=422, headers=headers)
        return JSONResponse(result, headers=headers)

    @app.get("/api/stock")
    async def stock(ids: str = "") -> dict[str, Any]:
        requested: list[str] = []
        for part in ids.split(","):
            color_id = part.strip()
            if not color_id or color_id in requested:
                continue
            requested.append(color_id)
            if len(requested) == _STOCK_ID_LIMIT:
                break
        hints = in_stock_hints(requested, catalog.by_id, load_spools())
        return {"ok": True, "hints": hints}

    @app.post("/api/plan")
    async def plan(
        file: UploadFile = File(...),  # noqa: B008
        note: str = Form(""),
        constraints: str | None = Form(None),
    ) -> dict[str, Any]:
        try:
            content = _read_upload(file)
        finally:
            file.file.close()

        extension = ALLOWED_EXT.get(file.content_type or "", "bin")
        inbox = root / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        path = inbox / f"web-{uuid.uuid4().hex}.{extension}"
        path.write_bytes(content)

        request_id = path.stem
        request = {
            "schema_version": 1,
            "request_id": request_id,
            "created_at": _iso(now_fn()),
            "image_paths": [str(path)],
            "note": note,
            "constraints": _parse_constraints(constraints),
            "context": {},
        }
        return run_plan(request, catalog, root, now_fn, card_base_url)

    @app.get("/api/cards/{name}")
    async def card(name: str) -> FileResponse:
        if not CARD_NAME_RE.fullmatch(name):
            raise HTTPException(status_code=404)
        path = root / "public" / "cards" / name
        if not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="image/png")

    return app
