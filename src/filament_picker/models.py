from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterator
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
    StreamingResponse,
)

from .auth import COOKIE_NAME, ModelAuth
from .catalog import Catalog
from .ciede2000 import delta_e_2000
from .colorspace import hex_to_lab
from .config import (
    DEFAULT_AMS_SLOTS,
    DEFAULT_MAX_COLORS,
    MATCH_MAX_DE,
    REPO_ROOT,
    SOURCE_RANK,
)
from .matcher import eligible, label_for, name_display
from .model_import import parse_plate_layout
from .note_parser import Params
from .originals import (
    HttpObjectSource,
    RangeNotSatisfiable,
    UpstreamFailure,
    content_disposition,
    filename_for,
    iter_file,
    load_cos_settings,
    load_key_overrides,
    local_original,
    lookup_download,
    media_type_for,
    original_descriptor,
    parse_range,
    read_map_sha,
    resolve_object_key,
)
from .spoolman import annotate_picks, load_spools


def models_root() -> Path:
    return Path(os.environ.get("FILAMENT_PICKER_MODELS_ROOT", REPO_ROOT / "data/models-private"))


_IMAGE_TYPES = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
_MESH_TYPE = "model/gltf-binary"
_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MEDIA_NAME = re.compile(r"^(?:cover\.png|(?:plate|top)_[1-9][0-9]{0,3}\.png)$")
_COLOUR_PARAMS = Params(
    max_colors=DEFAULT_MAX_COLORS,
    ams_slots=DEFAULT_AMS_SLOTS,
    n_colors=1,
    materials=("PLA", "PETG"),
    brands=(),
    allow_approx=True,
    keep_small=False,
    per_color=2,
    note_parsed={},
)


def _column(row: sqlite3.Row, name: str, default: Any) -> Any:
    names = set(row.keys())
    return row[name] if name in names else default


def _public_model(row: sqlite3.Row, *, detail: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        key: row[key]
        for key in ("id", "title", "series", "author", "size_bytes", "plate_count", "created_at")
    } | {
        "colours": json.loads(row["colours"]),
        "thumb_url": f"/api/models/{quote(row['id'], safe='')}/thumb",
        "cover_url": _cover_url(row),
    }
    if detail:
        payload["description"] = _column(row, "description", "")
        payload["images"] = _public_images(row)
    return payload


def _public_images(row: sqlite3.Row) -> list[dict[str, Any]]:
    raw = _column(row, "images", "[]")
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    images: list[dict[str, Any]] = []
    model_id = quote(row["id"], safe="")
    for item in parsed:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        name = item.get("name")
        plate = item.get("plate")
        if not isinstance(name, str) or _MEDIA_NAME.fullmatch(name) is None:
            continue
        if kind == "cover":
            plate = 0
        elif kind not in ("plate", "top") or not isinstance(plate, int):
            continue
        images.append(
            {
                "kind": kind,
                "plate": plate,
                "url": f"/api/models/{model_id}/media/{quote(name, safe='')}",
            }
        )
    return images


def _cover_url(row: sqlite3.Row) -> str | None:
    for image in _public_images(row):
        if image["kind"] == "cover":
            url = image["url"]
            return url if isinstance(url, str) else None
    return None


class ModelPreview:
    def __init__(self, catalog: Catalog | None = None) -> None:
        self.auth = ModelAuth()
        self.root = models_root()
        self.direct = os.environ.get("FILAMENT_PICKER_MODELS_DIRECT", "1") == "1"
        self.catalog = catalog
        self._candidates: list[dict[str, Any]] | None = None

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
        path = self._guarded_file(rel, {".png", ".webp", ".jpg", ".jpeg"}, ("thumbs",))
        return self._image_response(path, rel)

    def mesh(self, model_id: str) -> Response:
        self.record(model_id)
        rel = self._mesh_rel(model_id)
        path = self._guarded_file(rel, {".glb"}, ("meshes",), detail="网格不存在")
        return self._binary_response(path, rel, _MESH_TYPE)

    def mesh_url(self, model_id: str) -> str | None:
        try:
            rel = self._mesh_rel(model_id)
            self._guarded_file(rel, {".glb"}, ("meshes",), detail="网格不存在")
        except HTTPException:
            return None
        return f"/api/models/{quote(model_id, safe='')}/glb"

    def _mesh_rel(self, model_id: str) -> PurePosixPath:
        if _MODEL_ID.fullmatch(model_id) is None:
            raise HTTPException(status_code=404, detail="网格不存在")
        return PurePosixPath("meshes") / f"{model_id}.glb"

    def original_payload(self, model_id: str) -> dict[str, Any]:
        target = self._download_target(model_id)
        if target is None:
            return original_descriptor(False, model_id, None, None, None)
        row, requested, _stored, local, key = target
        chosen = local.name if local is not None else key
        if chosen is None:
            return original_descriptor(False, requested, None, None, None)
        size = local.stat().st_size if local is not None else None
        payload = original_descriptor(
            True,
            requested,
            filename_for(str(row["title"]), chosen),
            size,
            media_type_for(chosen),
        )
        payload["sha256"] = read_map_sha(None, requested) or read_map_sha(None, str(row["id"]))
        return payload

    def original_response(self, model_id: str, request: Request) -> Response:
        target = self._download_target(model_id)
        if target is None:
            raise HTTPException(status_code=404, detail="模型不存在")
        row, requested, _stored, local, key = target
        if local is None and key is None:
            raise HTTPException(status_code=404, detail="没有原件映射")
        filename = filename_for(str(row["title"]), local.name if local is not None else str(key))
        headers = {
            "Content-Disposition": content_disposition(filename),
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex, nofollow",
        }
        digest = read_map_sha(None, requested) or read_map_sha(None, str(row["id"]))
        if digest:
            headers["X-Content-SHA256"] = digest
        if local is not None:
            return self._local_original(local, request, headers)
        return self._remote_original(str(key), request, headers)

    def _download_target(
        self, model_id: str
    ) -> tuple[sqlite3.Row, str, str, Path | None, str | None] | None:
        with closing(self._connect()) as conn:
            found = lookup_download(conn, model_id)
        if found is None:
            return None
        row, requested, stored = found
        local = local_original(self.root, requested) or local_original(self.root, str(row["id"]))
        try:
            overrides = load_key_overrides()
        except (OSError, ValueError, json.JSONDecodeError):
            overrides = {}
        key = resolve_object_key(requested, str(row["id"]), stored, overrides)
        if local is None and (key is None or load_cos_settings() is None):
            key = None
        return row, requested, stored, local, key

    def _local_original(self, path: Path, request: Request, headers: dict[str, str]) -> Response:
        size = path.stat().st_size
        try:
            bounds = parse_range(request.headers.get("range"), size)
        except RangeNotSatisfiable:
            raise HTTPException(status_code=416, detail="范围无效") from None
        start, end = (0, size - 1) if bounds is None else bounds
        if bounds is not None:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
        media_type = media_type_for(path.name)
        status = 200 if bounds is None else 206
        if request.method == "HEAD":
            return Response(status_code=status, headers=headers, media_type=media_type)
        return StreamingResponse(
            iter_file(path, start, end),
            status_code=200 if bounds is None else 206,
            media_type=media_type,
            headers=headers,
        )

    def _remote_original(self, key: str, request: Request, headers: dict[str, str]) -> Response:
        settings = load_cos_settings()
        if settings is None:
            raise HTTPException(status_code=404, detail="没有原件映射")
        range_header = request.headers.get("range")
        if range_header is not None and not re.fullmatch(r"bytes=\d+-\d*", range_header.strip()):
            raise HTTPException(status_code=416, detail="范围无效")
        method = "HEAD" if request.method == "HEAD" else "GET"
        try:
            opened = HttpObjectSource(settings).open(
                key, range_header.strip() if range_header else None, method
            )
        except UpstreamFailure:
            raise HTTPException(status_code=502, detail="原件暂时无法下载") from None
        if opened.size is not None:
            headers["Content-Length"] = str(opened.size)
        if opened.content_range:
            headers["Content-Range"] = opened.content_range
        media_type = media_type_for(key)
        if method == "HEAD":
            if callable(opened.close):
                opened.close()
            return Response(status_code=opened.status, headers=headers, media_type=media_type)

        def generate() -> Iterator[bytes]:
            try:
                yield from opened.chunks
            finally:
                if callable(opened.close):
                    opened.close()

        return StreamingResponse(
            generate(), status_code=opened.status, media_type=media_type, headers=headers
        )

    def media(self, model_id: str, name: str) -> Response:
        if _MEDIA_NAME.fullmatch(name) is None:
            raise HTTPException(status_code=404, detail="图片不存在")
        images = _public_images(self.record(model_id))
        if not any(image["url"].endswith("/" + quote(name, safe="")) for image in images):
            raise HTTPException(status_code=404, detail="图片不存在")
        rel = PurePosixPath("images") / model_id / name
        path = self._guarded_file(rel, {".png"}, ("images", model_id))
        return self._image_response(path, rel)

    def _guarded_file(
        self,
        rel: PurePosixPath,
        suffixes: set[str],
        parents: tuple[str, ...],
        *,
        detail: str = "图片不存在",
    ) -> Path:
        base = self.root.resolve()
        candidate = base.joinpath(*rel.parts)
        path = candidate.resolve()
        expected = base.joinpath(*parents)
        if (
            rel.is_absolute()
            or ".." in rel.parts
            or "\\" in str(rel)
            or len(rel.parts) != len(parents) + 1
            or rel.parts[: len(parents)] != parents
            or path.parent != expected
            or candidate.is_symlink()
            or path.suffix.lower() not in suffixes
            or not path.is_file()
        ):
            raise HTTPException(status_code=404, detail=detail)
        return path

    def _image_response(self, path: Path, rel: PurePosixPath) -> Response:
        return self._binary_response(path, rel, _IMAGE_TYPES[path.suffix.lower()])

    def _binary_response(self, path: Path, rel: PurePosixPath, media_type: str) -> Response:
        if self.direct:
            return FileResponse(path, media_type=media_type)
        return Response(
            media_type=media_type,
            headers={"X-Accel-Redirect": "/internal-models/" + quote(rel.as_posix(), safe="/")},
        )

    def match_colours(self, colours: list[str]) -> list[dict[str, Any]]:
        candidates = self._colour_candidates()
        matches: list[dict[str, Any]] = []
        for colour in colours:
            picks: list[dict[str, Any]] = []
            try:
                lab = hex_to_lab(colour)
            except ValueError:
                lab = None
            if lab is not None:
                ranked = sorted(
                    (
                        (distance, entry)
                        for entry in candidates
                        if isinstance(entry.get("lab"), list)
                        and len(entry["lab"]) == 3
                        and (distance := float(delta_e_2000(lab, entry["lab"]))) <= MATCH_MAX_DE
                    ),
                    key=lambda item: (
                        round(item[0], 4),
                        SOURCE_RANK.get(item[1].get("hex_source"), 9),
                        item[1]["id"],
                    ),
                )
                picks = [
                    {
                        "id": entry["id"],
                        "name": name_display(entry),
                        "brand_name": entry.get("brand_name", ""),
                        "series_name": entry.get("series_name", ""),
                        "hex": entry["hex"][0],
                        "delta_e": round(distance, 2),
                        "label": label_for(distance),
                    }
                    for distance, entry in ranked[: _COLOUR_PARAMS.per_color]
                ]
            matches.append({"hex": colour, "picks": picks})
        spools = load_spools()
        if spools and self.catalog is not None:
            entries = self.catalog.by_id
            for match in matches:
                match["picks"] = annotate_picks(match["picks"], entries, spools)
        return matches

    def _colour_candidates(self) -> list[dict[str, Any]]:
        if self._candidates is not None:
            return self._candidates
        catalog = self.catalog
        if catalog is None:
            self._candidates = []
            return self._candidates
        self._candidates = [entry for entry in catalog.entries if eligible(entry, _COLOUR_PARAMS)]
        return self._candidates


def mount_model_preview(app: FastAPI, catalog: Catalog | None = None) -> None:
    preview = ModelPreview(catalog)
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

    @router.get("/{model_id}/glb")
    def mesh(model_id: str) -> Response:
        return preview.mesh(model_id)

    @router.get("/{model_id}/media/{name}")
    def media(model_id: str, name: str) -> Response:
        return preview.media(model_id, name)

    @router.get("/{model_id}")
    def detail(model_id: str) -> dict[str, Any]:
        row = preview.record(model_id)
        payload = _public_model(row, detail=True)
        payload["colour_matches"] = preview.match_colours(payload["colours"])
        plates = parse_plate_layout(_column(row, "plate_layout", ""))
        if plates is not None:
            by_hex = {item["hex"]: item["picks"] for item in payload["colour_matches"]}
            extra = [
                filament["hex"]
                for plate in plates
                for filament in plate["filaments"]
                if isinstance(filament.get("hex"), str) and filament["hex"] not in by_hex
            ]
            for item in preview.match_colours(list(dict.fromkeys(extra))):
                by_hex[item["hex"]] = item["picks"]
            for plate in plates:
                for filament in plate["filaments"]:
                    colour = filament.get("hex")
                    filament["picks"] = by_hex.get(colour, []) if isinstance(colour, str) else []
        payload["plates"] = plates
        payload["mesh_url"] = preview.mesh_url(row["id"])
        payload["original"] = preview.original_payload(row["id"])
        return payload

    @router.api_route("/{model_id}/original", methods=["GET", "HEAD"])
    def original(model_id: str, request: Request) -> Response:
        return preview.original_response(model_id, request)

    app.include_router(router)
