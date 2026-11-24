from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

from .auth import COOKIE_NAME, ModelAuth, configured_preview_user, registration_enabled
from .catalog import Catalog
from .ciede2000 import delta_e_2000
from .colorspace import hex_to_lab
from .config import (
    DEFAULT_AMS_SLOTS,
    DEFAULT_MAX_COLORS,
    MATCH_MAX_DE,
    REPO_ROOT,
    SOURCE_RANK,
    TZ,
)
from .library import delete_favorite, get_scheme, list_favorites, put_favorite, put_scheme
from .matcher import eligible, label_for, name_display
from .mesh_derive import (
    DeriveError,
    derive_file,
    derived_file,
    derived_index,
    model_lock,
)
from .model_import import parse_plate_layout
from .note_parser import Params
from .originals import (
    HttpObjectSource,
    OriginalTooLarge,
    OriginalUnavailable,
    RangeNotSatisfiable,
    UpstreamFailure,
    content_disposition,
    content_sha256,
    filename_for,
    iter_file,
    load_cos_settings,
    load_key_overrides,
    local_original,
    lookup_download,
    materialize_original,
    media_type_for,
    original_descriptor,
    parse_range,
    publishable_sha,
    read_map_sha,
    resolve_object_key,
)
from .scheme_copy import SchemeCopyError, scheme_copy_path, store_scheme_copy
from .shares import (
    COOKIE_NAME as SHARE_COOKIE,
)
from .shares import (
    create_grant,
    grant_from_cookie,
    list_grants,
    may_share_model,
    open_token,
    revoke_grant,
)
from .spoolman import annotate_picks, load_spools
from .submissions import (
    SubmissionError,
    accept_upload,
    list_submissions,
    retry_submission,
    submissions_enabled,
)


def _distinct_materials(conn: sqlite3.Connection, has_layout: bool, username: str) -> list[str]:
    if not has_layout:
        return []
    found: set[str] = set()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
    query = "SELECT plate_layout FROM models WHERE owner = ?" if "owner" in columns else None
    rows = conn.execute(query, (username,)) if query else []
    for (raw,) in rows:
        plates = parse_plate_layout(raw)
        if not plates:
            continue
        for plate in plates:
            for filament in plate.get("filaments", []):
                kind = filament.get("type")
                if isinstance(kind, str) and kind:
                    found.add(kind)
    return sorted(found)


_MAX_UPLOAD = 32 * 1024 * 1024


def models_root() -> Path:
    return Path(os.environ.get("FILAMENT_PICKER_MODELS_ROOT", REPO_ROOT / "data/models-private"))


def _account_original(root: Path, username: str, model_id: str) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", username):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", model_id):
        return None
    directory = root.resolve() / "accounts" / username / "originals"
    for suffix in (".3mf", ".stl"):
        candidate = directory / f"{model_id}{suffix}"
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if candidate.resolve().parent != directory:
            continue
        return candidate
    return None


_IMAGE_TYPES = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
_MESH_TYPE = "model/gltf-binary"
_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SORTS = ("id", "created_at", "plate_count", "colour_count")
_ORDERS = ("asc", "desc")
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


def _with_card_preview(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    """Tell the gallery whether the card image is a cover, a derived stand-in, or a fixture."""
    model_id = str(item["id"])
    cover = item.get("cover_url")
    if isinstance(cover, str) and cover:
        item["preview_url"] = cover
        item["preview_kind"] = "cover"
        return item
    index = derived_index(root, model_id)
    ready = index is not None and index.get("status") == "ready"
    quoted = quote(model_id, safe="")
    if ready and index is not None:
        name = "front.png"
        if index.get("scope") == "plate":
            plates = [
                plate
                for plate in (index.get("plates") or [])
                if isinstance(plate, dict) and isinstance(plate.get("index"), int)
            ]
            if plates:
                name = f"front-{plates[0]['index']}.png"
        if derived_file(root, model_id, name) is not None:
            item["preview_url"] = f"/api/models/{quoted}/derived/{name}"
            item["preview_kind"] = "derived"
            return item
    item["preview_url"] = item["thumb_url"]
    item["preview_kind"] = "fixture" if model_id.startswith("sample-") else "thumb"
    return item


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
        self,
        page: int,
        page_size: int,
        q: str,
        series: str,
        author: str,
        material: str = "",
        sort: str = "id",
        order: str = "asc",
        username: str = "",
    ) -> dict[str, Any]:
        if sort not in _SORTS or order not in _ORDERS:
            raise HTTPException(status_code=422, detail="排序无效")
        result: dict[str, Any] = {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "series": [],
            "authors": [],
            "materials": [],
            "submissions": submissions_enabled(),
            "query": {
                "q": q,
                "series": series,
                "author": author,
                "material": material,
                "sort": sort,
                "order": order,
            },
        }
        if not (self.root / "manifest.sqlite").is_file():
            return result
        self.ensure_owners()
        with closing(self._connect()) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
            clauses: list[str] = []
            params: list[object] = []
            if q:
                escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                like = f"%{escaped}%"
                clauses.append("(title LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\')")
                params.extend((like, like))
            for name, value in (("series", series), ("author", author)):
                if value:
                    clauses.append(f"{name} = ?")
                    params.append(value)
            if material:
                if "plate_layout" not in columns:
                    clauses.append("0")
                else:
                    clauses.append(
                        "json_valid(plate_layout) AND plate_layout != '' AND EXISTS ("
                        "SELECT 1 FROM json_each(models.plate_layout) AS plate "
                        "JOIN json_each(json_extract(plate.value, '$.filaments')) AS filament "
                        "WHERE json_extract(filament.value, '$.type') = ?)"
                    )
                    params.append(material)
            clauses.append("owner = ?")
            params.append(username)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            colour_expr = (
                "CASE WHEN json_valid(colours) AND json_type(colours) = 'array' "
                "THEN json_array_length(colours) END"
            )
            sort_expr = {
                "id": "id",
                "created_at": "created_at",
                "plate_count": "plate_count",
                "colour_count": colour_expr,
            }[sort]
            direction = "ASC" if order == "asc" else "DESC"
            result["total"] = conn.execute(
                "SELECT COUNT(*) FROM models" + where, params
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM models"
                + where
                + f" ORDER BY {sort_expr} IS NULL, {sort_expr} {direction}, id ASC "
                "LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            )
            result["items"] = [_with_card_preview(self.root, _public_model(row)) for row in rows]
            for column, key in (("series", "series"), ("author", "authors")):
                result[key] = [
                    row[0]
                    for row in conn.execute(
                        f"SELECT DISTINCT {column} FROM models "
                        f"WHERE owner = ? AND {column} != '' ORDER BY {column}",
                        (username,),
                    )
                ]
            result["materials"] = _distinct_materials(conn, "plate_layout" in columns, username)
        return result

    def ensure_owners(self) -> None:
        path = self.root / "manifest.sqlite"
        owner = configured_preview_user()
        if not path.is_file() or not owner:
            return
        conn = sqlite3.connect(path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
            if "owner" not in columns:
                conn.execute("ALTER TABLE models ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            done = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE id = 'assign-legacy-owner'"
            ).fetchone()
            if done is None:
                conn.execute("UPDATE models SET owner = ? WHERE owner = ''", (owner,))
                conn.execute(
                    "INSERT INTO schema_migrations (id, applied_at) "
                    "VALUES ('assign-legacy-owner', ?)",
                    (datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds"),),
                )
            conn.commit()
        finally:
            conn.close()

    def _row_owner(self, row: sqlite3.Row) -> str:
        owner = _column(row, "owner", "")
        if isinstance(owner, str) and owner:
            return owner
        return ""

    def _fetch(self, model_id: str) -> sqlite3.Row | None:
        if not (self.root / "manifest.sqlite").is_file():
            return None
        with closing(self._connect()) as conn:
            return conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()

    def record(self, model_id: str, username: str) -> sqlite3.Row:
        self.ensure_owners()
        row = self._fetch(model_id)
        if row is None or self._row_owner(row) != username:
            raise HTTPException(status_code=404, detail="模型不存在")
        return row

    def grant_row(self, model_id: str, grant_username: str) -> sqlite3.Row:
        self.ensure_owners()
        if not self.auth.store.user_exists(grant_username):
            raise HTTPException(status_code=410, detail="链接已失效")
        row = self._fetch(model_id)
        if row is None or self._row_owner(row) != grant_username:
            raise HTTPException(status_code=410, detail="链接已失效")
        return row

    def thumbnail_of(self, row: sqlite3.Row) -> Response:
        rel = PurePosixPath(row["thumb_path"])
        path = self._guarded_file(rel, {".png", ".webp", ".jpg", ".jpeg"}, ("thumbs",))
        return self._image_response(path, rel)

    def mesh_of(self, row: sqlite3.Row) -> Response:
        rel = self._mesh_rel(str(row["id"]))
        path = self._guarded_file(rel, {".glb"}, ("meshes",), detail="网格不存在")
        return self._binary_response(path, rel, _MESH_TYPE)

    def mesh_url(self, model_id: str) -> str | None:
        try:
            rel = self._mesh_rel(model_id)
            self._guarded_file(rel, {".glb"}, ("meshes",), detail="网格不存在")
        except HTTPException:
            return None
        return f"/api/models/{quote(model_id, safe='')}/glb"

    def derived_payload(self, model_id: str) -> dict[str, Any]:
        index = derived_index(self.root, model_id)
        ready = (
            index is not None
            and index.get("status") == "ready"
            and derived_file(self.root, model_id, "model.glb") is not None
        )
        if not ready or index is None:
            return {
                "mesh_derived": False,
                "front_views": [],
                "derive_note": None,
                "derive_error": None if index is None else index.get("error"),
            }
        quoted = quote(model_id, safe="")
        note = str(index.get("note") or "")
        views: list[dict[str, Any]] = []
        if index.get("scope") == "plate":
            for plate in index.get("plates") or []:
                if not isinstance(plate, dict) or not isinstance(plate.get("index"), int):
                    continue
                views.append(
                    {
                        "scope": "plate",
                        "plate": plate["index"],
                        "url": f"/api/models/{quoted}/derived/front-{plate['index']}.png",
                        "note": note,
                    }
                )
        else:
            views.append(
                {
                    "scope": "overall",
                    "plate": None,
                    "url": f"/api/models/{quoted}/derived/front.png",
                    "note": note,
                }
            )
        return {
            "mesh_derived": True,
            "mesh_url": f"/api/models/{quoted}/derived/model.glb",
            "front_views": views,
            "derive_note": note,
            "derive_error": None,
        }

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
        payload["sha256"] = self._download_sha(requested, str(row["id"]), local)
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
        digest = self._download_sha(requested, str(row["id"]), local)
        ranged = request.headers.get("range")
        if digest and not (local is not None and ranged):
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
        if local is None:
            local = _account_original(self.root, self._row_owner(row), str(row["id"]))
        try:
            overrides = load_key_overrides()
        except (OSError, ValueError, json.JSONDecodeError):
            overrides = {}
        key = resolve_object_key(requested, str(row["id"]), stored, overrides)
        if local is None and (key is None or load_cos_settings() is None):
            key = None
        return row, requested, stored, local, key

    def _download_sha(self, requested: str, canonical: str, local: Path | None) -> str | None:
        if local is not None:
            return content_sha256(local)
        claim = read_map_sha(None, requested) or read_map_sha(None, canonical)
        return publishable_sha(claim, requested, canonical)

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

    def media_of(self, row: sqlite3.Row, name: str) -> Response:
        if _MEDIA_NAME.fullmatch(name) is None:
            raise HTTPException(status_code=404, detail="图片不存在")
        images = _public_images(row)
        if not any(image["url"].endswith("/" + quote(name, safe="")) for image in images):
            raise HTTPException(status_code=404, detail="图片不存在")
        rel = PurePosixPath("images") / str(row["id"]) / name
        path = self._guarded_file(rel, {".png"}, ("images", str(row["id"])))
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
        share_api = path == "/api/share" or path.startswith("/api/share/")
        if not (api or page or share_api):
            return await call_next(request)
        share_page = path.rstrip("/") == "/models/s" and request.method in ("GET", "HEAD")
        register_page = path.rstrip("/") == "/models/register" and request.method in ("GET", "HEAD")
        register_api = path == "/api/models/registration" and request.method == "GET"
        register_post = path == "/api/models/register" and request.method == "POST"
        login = (path == "/api/models/login" and request.method == "POST") or (
            path.rstrip("/") == "/models/login" and request.method in ("GET", "HEAD")
        )
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            origin = request.headers.get("origin")
            if origin:
                from urllib.parse import urlsplit

                if urlsplit(origin).netloc != request.url.netloc:
                    return JSONResponse({"detail": "跨站请求已拒绝"}, status_code=403)
        username = (
            None
            if login or share_page or share_api or register_page or register_api or register_post
            else preview.auth.username(request.cookies.get(COOKIE_NAME))
        )
        request.state.model_username = username
        if (
            not login
            and not share_page
            and not share_api
            and not register_page
            and not register_api
            and not register_post
            and username is None
        ):
            response = (
                JSONResponse({"detail": "需要登录"}, status_code=401)
                if api
                else RedirectResponse("/models/login", status_code=302)
            )
        else:
            response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots() -> str:
        return (
            "User-agent: *\nDisallow: /models\nDisallow: /api/models\n"
            "Disallow: /api/share\nDisallow: /internal-models\n"
        )

    @router.get("/registration")
    def registration() -> dict[str, bool]:
        return {
            "enabled": registration_enabled(),
            "submissions": submissions_enabled(),
            "email_sent": False,
            "email_verification": False,
        }

    @router.post("/register")
    async def register(request: Request) -> dict[str, object]:
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            raise HTTPException(status_code=400, detail="注册请求无效") from None
        if not isinstance(body, dict) or not isinstance(body.get("username"), str):
            raise HTTPException(status_code=400, detail="注册请求无效")
        password = body.get("password")
        email = body.get("email")
        if email is not None and not isinstance(email, str):
            raise HTTPException(status_code=400, detail="邮箱格式无效")
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(
            preview.auth.register,
            request.client.host if request.client else "unknown",
            body["username"],
            password if isinstance(password, str) else "",
            email or None,
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

    @router.get("/submissions")
    def submission_list(request: Request) -> dict[str, Any]:
        items = list_submissions(preview.root / "manifest.sqlite", request.state.model_username)
        return {"items": items}

    @router.post("/submissions")
    async def submission_create(request: Request) -> dict[str, Any]:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=400, detail="需要上传文件")
        data = await upload.read(_MAX_UPLOAD + 1)
        if len(data) > _MAX_UPLOAD:
            raise HTTPException(status_code=413, detail="文件超过 32MB")
        try:
            return accept_upload(
                preview.root,
                preview.root / "manifest.sqlite",
                request.state.model_username,
                getattr(upload, "filename", "") or "",
                data,
            )
        except SubmissionError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from None

    @router.post("/submissions/{submission_id}/retry")
    def submission_retry(submission_id: str, request: Request) -> dict[str, Any]:
        try:
            return retry_submission(
                preview.root,
                preview.root / "manifest.sqlite",
                request.state.model_username,
                submission_id,
            )
        except SubmissionError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from None

    @router.get("/me")
    def me(request: Request) -> dict[str, str]:
        return {"username": request.state.model_username}

    @router.get("")
    @router.get("/")
    def listing(
        request: Request,
        page: int = Query(1, ge=1, le=1_000_000),
        page_size: int = Query(12, ge=1, le=100),
        q: str = "",
        series: str = "",
        author: str = "",
        material: str = "",
        sort: str = "id",
        order: str = "asc",
    ) -> dict[str, Any]:
        return preview.listing(
            page, page_size, q, series, author, material, sort, order, request.state.model_username
        )

    @router.get("/favorites")
    def favorites(request: Request) -> dict[str, Any]:
        return {"items": list_favorites(request.state.model_username)}

    @router.put("/favorites/{model_id}")
    def favorite_add(model_id: str, request: Request) -> dict[str, bool]:
        if _MODEL_ID.fullmatch(model_id) is None:
            raise HTTPException(status_code=400, detail="模型编号无效")
        preview.record(model_id, request.state.model_username)
        put_favorite(request.state.model_username, model_id)
        return {"ok": True}

    @router.delete("/favorites/{model_id}")
    def favorite_remove(model_id: str, request: Request) -> dict[str, bool]:
        delete_favorite(request.state.model_username, model_id)
        return {"ok": True}

    @router.get("/{model_id}/thumb")
    def thumbnail(model_id: str, request: Request) -> Response:
        return preview.thumbnail_of(preview.record(model_id, request.state.model_username))

    @router.get("/{model_id}/glb")
    def mesh(model_id: str, request: Request) -> Response:
        return preview.mesh_of(preview.record(model_id, request.state.model_username))

    @router.get("/{model_id}/media/{name}")
    def media(model_id: str, name: str, request: Request) -> Response:
        return preview.media_of(preview.record(model_id, request.state.model_username), name)

    @router.get("/{model_id}/scheme")
    def scheme_get(model_id: str, request: Request) -> dict[str, Any]:
        if _MODEL_ID.fullmatch(model_id) is None:
            raise HTTPException(status_code=400, detail="模型编号无效")
        preview.record(model_id, request.state.model_username)
        return get_scheme(request.state.model_username, model_id)

    @router.get("/{model_id}/shares")
    def share_list(model_id: str, request: Request) -> dict[str, Any]:
        row = preview.record(model_id, request.state.model_username)
        if not may_share_model(request.state.model_username, model_id, preview._row_owner(row)):
            raise HTTPException(status_code=403, detail="不能分享这个模型")
        return {"items": list_grants(request.state.model_username, model_id)}

    @router.post("/{model_id}/shares")
    async def share_create(model_id: str, request: Request) -> dict[str, Any]:
        row = preview.record(model_id, request.state.model_username)
        if not may_share_model(request.state.model_username, model_id, preview._row_owner(row)):
            raise HTTPException(status_code=403, detail="不能分享这个模型")
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            raise HTTPException(status_code=400, detail="分享请求无效") from None
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="分享请求无效")
        created = create_grant(
            request.state.model_username,
            model_id,
            preview._row_owner(row),
            days=body.get("days", 7),
            allow_original=body.get("allow_original", False),
            allow_scheme_copy=body.get("allow_scheme_copy", False),
        )
        token = created.pop("token")
        created["link"] = "/models/s#" + token
        return created

    @router.post("/shares/{grant_id}/revoke")
    def share_revoke(grant_id: str, request: Request) -> dict[str, bool]:
        revoke_grant(request.state.model_username, grant_id)
        return {"ok": True}

    @router.put("/{model_id}/scheme")
    async def scheme_put(model_id: str, request: Request) -> dict[str, Any]:
        if _MODEL_ID.fullmatch(model_id) is None:
            raise HTTPException(status_code=400, detail="模型编号无效")
        row = preview.record(model_id, request.state.model_username)
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            raise HTTPException(status_code=400, detail="展示色格式无效") from None
        if not isinstance(body, dict) or "slots" not in body:
            raise HTTPException(status_code=400, detail="展示色格式无效")
        plates = parse_plate_layout(_column(row, "plate_layout", ""))
        return put_scheme(request.state.model_username, model_id, body.get("slots"), plates)

    @router.post("/{model_id}/scheme-copy")
    def scheme_copy_create(model_id: str, request: Request) -> dict[str, Any]:
        if _MODEL_ID.fullmatch(model_id) is None:
            raise HTTPException(status_code=400, detail="模型编号无效")
        preview.record(model_id, request.state.model_username)
        slots = get_scheme(request.state.model_username, model_id)["slots"]
        target = preview._download_target(model_id)
        local = None if target is None else target[3]
        key = None if target is None or local is not None else target[4]
        if local is None and key is None:
            raise HTTPException(status_code=409, detail="没有这份 3MF 原件，没有生成副本")
        try:
            with model_lock(model_id), materialize_original(preview.root, local, key) as source:
                if source.suffix.lower() != ".3mf":
                    raise HTTPException(status_code=422, detail="只有 3MF 能另存配色副本")
                return store_scheme_copy(request.state.model_username, model_id, source, slots)
        except OriginalUnavailable:
            raise HTTPException(status_code=409, detail="没有这份 3MF 原件，没有生成副本") from None
        except OriginalTooLarge:
            raise HTTPException(status_code=413, detail="原件过大，没有生成副本") from None
        except UpstreamFailure:
            raise HTTPException(status_code=502, detail="原件暂时无法读取，没有生成副本") from None
        except SchemeCopyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from None

    @router.post("/{model_id}/derive")
    async def derive_create(model_id: str, request: Request) -> dict[str, Any]:
        if _MODEL_ID.fullmatch(model_id) is None:
            raise HTTPException(status_code=400, detail="模型编号无效")
        preview.record(model_id, request.state.model_username)
        force = False
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                body = await request.json()
            except (ValueError, UnicodeError):
                body = None
            if isinstance(body, dict) and body.get("force") is True:
                force = True
        target = preview._download_target(model_id)
        local = None if target is None else target[3]
        key = None if target is None or local is not None else target[4]
        if local is None and key is None:
            raise HTTPException(status_code=409, detail="没有这份 3MF 原件，没有派生")
        try:
            with model_lock(model_id), materialize_original(preview.root, local, key) as source:
                if source.suffix.lower() != ".3mf":
                    raise HTTPException(status_code=422, detail="只有 3MF 能派生网格")
                return derive_file(preview.root, model_id, source, force=force)
        except OriginalUnavailable:
            raise HTTPException(status_code=409, detail="没有这份 3MF 原件，没有派生") from None
        except OriginalTooLarge:
            raise HTTPException(status_code=413, detail="原件过大，没有派生") from None
        except UpstreamFailure:
            raise HTTPException(status_code=502, detail="原件暂时无法读取，没有派生") from None
        except DeriveError as exc:
            raise HTTPException(status_code=422, detail=exc.detail) from None

    @router.get("/{model_id}/derived/{name}")
    def derived_asset(model_id: str, name: str, request: Request) -> Response:
        if _MODEL_ID.fullmatch(model_id) is None:
            raise HTTPException(status_code=404, detail="派生文件不存在")
        preview.record(model_id, request.state.model_username)
        path = derived_file(preview.root, model_id, name)
        if path is None:
            raise HTTPException(status_code=404, detail="派生文件不存在")
        media = "model/gltf-binary" if path.suffix.lower() == ".glb" else "image/png"
        headers = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}
        if preview.direct:
            return FileResponse(path, media_type=media, headers=headers)
        rel = PurePosixPath("derived") / model_id / path.name
        redirect = "/internal-models/" + quote(rel.as_posix(), safe="/")
        return Response(
            media_type=media,
            headers={**headers, "X-Accel-Redirect": redirect},
        )

    @router.get("/{model_id}/scheme-copy")
    def scheme_copy_download(model_id: str, request: Request) -> Response:
        if _MODEL_ID.fullmatch(model_id) is None:
            raise HTTPException(status_code=400, detail="模型编号无效")
        preview.record(model_id, request.state.model_username)
        found = scheme_copy_path(request.state.model_username, model_id)
        if found is None:
            raise HTTPException(status_code=404, detail="还没有配色副本")
        path, record = found
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != record["sha256"]:
            raise HTTPException(status_code=409, detail="副本校验和不匹配")
        headers = {
            "Content-Disposition": content_disposition(str(record["filename"])),
            "X-Content-SHA256": digest,
            "Cache-Control": "no-store",
        }
        return Response(content=payload, media_type="model/3mf", headers=headers)

    @router.get("/{model_id}")
    def detail(model_id: str, request: Request) -> dict[str, Any]:
        row = preview.record(model_id, request.state.model_username)
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
        derived = preview.derived_payload(row["id"])
        payload["mesh_url"] = derived.get("mesh_url") or preview.mesh_url(row["id"])
        payload["mesh_derived"] = derived["mesh_derived"]
        payload["front_views"] = derived["front_views"]
        payload["derive_note"] = derived["derive_note"]
        payload["derive_error"] = derived["derive_error"]
        payload["original"] = preview.original_payload(row["id"])
        return payload

    @router.api_route("/{model_id}/original", methods=["GET", "HEAD"])
    def original(model_id: str, request: Request) -> Response:
        preview.ensure_owners()
        target = preview._download_target(model_id)
        if target is None or preview._row_owner(target[0]) != request.state.model_username:
            raise HTTPException(status_code=404, detail="模型不存在")
        return preview.original_response(model_id, request)

    share_router = APIRouter(prefix="/api/share")

    def _share_grant(request: Request) -> dict[str, Any]:
        return grant_from_cookie(request.cookies.get(SHARE_COOKIE))

    def _share_payload(grant: dict[str, Any]) -> dict[str, Any]:
        row = preview.grant_row(grant["model_id"], grant["username"])
        images = []
        for image in _public_images(row):
            name = str(image["url"]).rsplit("/", 1)[-1]
            images.append({**image, "url": "/api/share/media/" + name})
        derived = preview.derived_payload(str(row["id"]))
        fronts = []
        for view in derived["front_views"]:
            name = str(view["url"]).rsplit("/", 1)[-1]
            fronts.append({**view, "url": "/api/share/derived/" + name})
        plates = parse_plate_layout(_column(row, "plate_layout", ""))
        if plates is not None:
            for plate in plates:
                for filament in plate["filaments"]:
                    filament.pop("picks", None)
        payload: dict[str, Any] = {
            "title": row["title"],
            "author": row["author"],
            "plate_count": row["plate_count"],
            "expires_at": grant["expires_at"],
            "allow_original": grant["allow_original"],
            "allow_scheme_copy": grant["allow_scheme_copy"],
            "thumb_url": "/api/share/thumb",
            "images": images,
            "front_views": fronts,
            "mesh_url": "/api/share/glb"
            if derived["mesh_derived"] or preview.mesh_url(str(row["id"]))
            else None,
            "plates": plates,
            "note": "这是一份限时分享，不是公开模型。",
        }
        if grant["allow_original"]:
            payload["original_url"] = "/api/share/original"
        if grant["allow_scheme_copy"]:
            payload["scheme_copy_url"] = "/api/share/scheme-copy"
        return payload

    def _share_session(response: Response, grant: dict[str, Any], session: str) -> None:
        remaining = datetime.fromisoformat(grant["expires_at"]) - datetime.now(ZoneInfo(TZ))
        response.set_cookie(
            SHARE_COOKIE,
            session,
            max_age=max(1, int(remaining.total_seconds())),
            httponly=True,
            secure=preview.auth.secure,
            samesite="strict",
            path="/api/share",
        )

    @share_router.post("/open")
    async def share_open(request: Request) -> Response:
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            raise HTTPException(status_code=400, detail="链接无效") from None
        token = body.get("token") if isinstance(body, dict) else None
        grant, session = open_token(request.client.host if request.client else "unknown", token)
        response = JSONResponse(_share_payload(grant))
        _share_session(response, grant, session)
        return response

    @share_router.get("/view")
    def share_view(request: Request) -> dict[str, Any]:
        return _share_payload(_share_grant(request))

    @share_router.get("/thumb")
    def share_thumb(request: Request) -> Response:
        grant = _share_grant(request)
        return preview.thumbnail_of(preview.grant_row(grant["model_id"], grant["username"]))

    @share_router.get("/media/{name}")
    def share_media(name: str, request: Request) -> Response:
        grant = _share_grant(request)
        return preview.media_of(preview.grant_row(grant["model_id"], grant["username"]), name)

    @share_router.get("/glb")
    def share_glb(request: Request) -> Response:
        grant = _share_grant(request)
        row = preview.grant_row(grant["model_id"], grant["username"])
        derived = derived_file(preview.root, grant["model_id"], "model.glb")
        if derived is not None:
            return FileResponse(
                derived,
                media_type="model/gltf-binary",
                headers={"Cache-Control": "no-store"},
            )
        return preview.mesh_of(row)

    @share_router.get("/derived/{name}")
    def share_derived(name: str, request: Request) -> Response:
        grant = _share_grant(request)
        preview.grant_row(grant["model_id"], grant["username"])
        path = derived_file(preview.root, grant["model_id"], name)
        if path is None or path.suffix.lower() != ".png":
            raise HTTPException(status_code=404, detail="派生文件不存在")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})

    @share_router.api_route("/original", methods=["GET", "HEAD"])
    def share_original(request: Request) -> Response:
        grant = _share_grant(request)
        if not grant["allow_original"]:
            raise HTTPException(status_code=403, detail="这份分享不能下载原件")
        preview.grant_row(grant["model_id"], grant["username"])
        return preview.original_response(grant["model_id"], request)

    @share_router.get("/scheme-copy")
    def share_scheme_copy(request: Request) -> Response:
        grant = _share_grant(request)
        if not grant["allow_scheme_copy"]:
            raise HTTPException(status_code=403, detail="这份分享不能下载配色副本")
        preview.grant_row(grant["model_id"], grant["username"])
        found = scheme_copy_path(grant["username"], grant["model_id"])
        if found is None:
            raise HTTPException(status_code=404, detail="还没有配色副本")
        path, record = found
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != record["sha256"]:
            raise HTTPException(status_code=409, detail="副本校验和不匹配")
        headers = {
            "Content-Disposition": content_disposition(str(record["filename"])),
            "X-Content-SHA256": digest,
            "Cache-Control": "no-store",
        }
        return Response(content=payload, media_type="model/3mf", headers=headers)

    app.include_router(router)
    app.include_router(share_router)
