from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from .auth import COOKIE_NAME, ModelAuth
from .config import REPO_ROOT


def models_root() -> Path:
    return Path(os.environ.get("FILAMENT_PICKER_MODELS_ROOT", REPO_ROOT / "data/models-private"))


def _public_model(row: sqlite3.Row) -> dict[str, Any]:
    return {
        key: row[key]
        for key in ("id", "title", "series", "author", "size_bytes", "plate_count", "created_at")
    } | {
        "colours": json.loads(row["colours"]),
        "thumb_url": f"/api/models/{quote(row['id'], safe='')}/thumb",
    }


class ModelPreview:
    def __init__(self) -> None:
        self.auth = ModelAuth()
        self.root = models_root()
        self.direct = os.environ.get("FILAMENT_PICKER_MODELS_DIRECT", "1") == "1"

    def _connect(self) -> sqlite3.Connection:
        path = self.root / "manifest.sqlite"
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def listing(
        self, page: int, page_size: int, q: str, series: str, author: str
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "series": [],
            "authors": [],
        }
        if not (self.root / "manifest.sqlite").is_file():
            return result
        clauses = []
        params = []
        if q:
            clauses.append("title LIKE ? ESCAPE '\\'")
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        for name, value in (("series", series), ("author", author)):
            if value:
                clauses.append(f"{name} = ?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with closing(self._connect()) as conn:
            result["total"] = conn.execute(
                "SELECT COUNT(*) FROM models" + where, params
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM models" + where + " ORDER BY id LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            )
            result["items"] = [_public_model(row) for row in rows]
            for column, key in (("series", "series"), ("author", "authors")):
                result[key] = [
                    row[0]
                    for row in conn.execute(
                        f"SELECT DISTINCT {column} FROM models "
                        f"WHERE {column} != '' ORDER BY {column}"
                    )
                ]
        return result

    def record(self, model_id: str) -> sqlite3.Row:
        if (self.root / "manifest.sqlite").is_file():
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
            if row is not None:
                return row
        raise HTTPException(status_code=404, detail="模型不存在")

    def thumbnail(self, model_id: str) -> Response:
        rel = PurePosixPath(self.record(model_id)["thumb_path"])
        base = self.root.resolve()
        candidate = base / rel
        path = candidate.resolve()
        if (
            len(rel.parts) != 2
            or rel.parts[0] != "thumbs"
            or "\\" in str(rel)
            or path.parent != base / "thumbs"
            or candidate.is_symlink()
            or path.suffix.lower() not in (".png", ".webp")
            or not path.is_file()
        ):
            raise HTTPException(status_code=404, detail="缩略图不存在")
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/webp"
        if self.direct:
            return FileResponse(path, media_type=media_type)
        return Response(
            media_type=media_type,
            headers={"X-Accel-Redirect": "/internal-models/" + quote(rel.as_posix(), safe="/")},
        )


def mount_model_preview(app: FastAPI) -> None:
    preview = ModelPreview()
    app.state.model_preview = preview
    router = APIRouter(prefix="/api/models")

    @app.middleware("http")
    async def protect_models(request: Request, call_next: Any) -> Response:
        path = request.url.path
        api = path == "/api/models" or path.startswith("/api/models/")
        page = path == "/models" or path.startswith("/models/")
        if not (api or page):
            return await call_next(request)
        login = (path == "/api/models/login" and request.method == "POST") or (
            path.rstrip("/") == "/models/login" and request.method in ("GET", "HEAD")
        )
        username = None if login else preview.auth.username(request.cookies.get(COOKIE_NAME))
        request.state.model_username = username
        if not login and username is None:
            response = (
                JSONResponse({"detail": "需要登录"}, status_code=401)
                if api
                else RedirectResponse("/models/login", status_code=302)
            )
        else:
            response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots() -> str:
        return (
            "User-agent: *\nDisallow: /models\nDisallow: /api/models\nDisallow: /internal-models\n"
        )

    @router.post("/login")
    async def login(request: Request) -> Response:
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            raise HTTPException(status_code=400, detail="登录请求无效") from None
        if not isinstance(body, dict) or any(
            not isinstance(body.get(key), str) or not body[key] for key in ("username", "password")
        ):
            raise HTTPException(status_code=400, detail="登录请求无效")
        # Argon2 is CPU intensive; keep it off the event loop.
        from starlette.concurrency import run_in_threadpool

        token = await run_in_threadpool(
            preview.auth.login,
            request.client.host if request.client else "unknown",
            body["username"],
            body["password"],
        )
        response = JSONResponse({"username": body["username"]})
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=preview.auth.ttl,
            httponly=True,
            secure=preview.auth.secure,
            samesite="lax",
            path="/",
        )
        return response

    @router.post("/logout")
    def logout(request: Request) -> Response:
        preview.auth.store.revoke_session(request.cookies[COOKIE_NAME])
        response = JSONResponse({"ok": True})
        response.delete_cookie(
            COOKIE_NAME, path="/", httponly=True, secure=preview.auth.secure, samesite="lax"
        )
        return response

    @router.get("/me")
    def me(request: Request) -> dict[str, str]:
        return {"username": request.state.model_username}

    @router.get("")
    @router.get("/")
    def listing(
        page: int = Query(1, ge=1, le=1_000_000),
        page_size: int = Query(12, ge=1, le=100),
        q: str = "",
        series: str = "",
        author: str = "",
    ) -> dict[str, Any]:
        return preview.listing(page, page_size, q, series, author)

    @router.get("/{model_id}/thumb")
    def thumbnail(model_id: str) -> Response:
        return preview.thumbnail(model_id)

    @router.get("/{model_id}")
    def detail(model_id: str) -> dict[str, Any]:
        return _public_model(preview.record(model_id))

    app.include_router(router)
