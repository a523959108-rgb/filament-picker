"""Stream a private 3MF through this server. The browser never sees object storage."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPConnection, HTTPException, HTTPResponse, HTTPSConnection
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote

_SUFFIXES = {".3mf": "model/3mf", ".stl": "model/stl"}
_RANGE = re.compile(r"^bytes=(\d+)-(\d*)$")
_CHUNK = 64 * 1024
_UNAVAILABLE = "原件暂时无法下载"
_UNMAPPED = "没有原件映射"


@dataclass(frozen=True, slots=True)
class ObjectOpen:
    status: int
    media_type: str
    size: int | None
    content_range: str | None
    chunks: Iterator[bytes]
    close: object


class ObjectSource(Protocol):
    def open(self, key: str, range_header: str | None, method: str = "GET") -> ObjectOpen: ...


@dataclass(frozen=True, slots=True)
class CosSettings:
    bucket: str
    region: str
    prefix: str
    secret_id: str
    secret_key: str
    token: str
    timeout: float
    endpoint: str | None
    secure: bool

    @property
    def host(self) -> str:
        if self.endpoint:
            return self.endpoint
        return f"{self.bucket}.cos.{self.region}.myqcloud.com"


def load_cos_settings() -> CosSettings | None:
    bucket = os.environ.get("FILAMENT_PICKER_COS_BUCKET", "").strip()
    secret_id = os.environ.get("FILAMENT_PICKER_COS_SECRET_ID", "").strip()
    secret_key = os.environ.get("FILAMENT_PICKER_COS_SECRET_KEY", "").strip()
    if not bucket or not secret_id or not secret_key:
        return None
    timeout = float(os.environ.get("FILAMENT_PICKER_COS_TIMEOUT_SECONDS", "120"))
    if timeout <= 0:
        raise ValueError("FILAMENT_PICKER_COS_TIMEOUT_SECONDS must be positive")
    prefix = os.environ.get(
        "FILAMENT_PICKER_COS_PREFIX", "filament-picker/3mf-originals/20261107/"
    ).strip("/")
    endpoint = os.environ.get("FILAMENT_PICKER_COS_ENDPOINT", "").strip() or None
    secure = os.environ.get("FILAMENT_PICKER_COS_SECURE", "1" if endpoint is None else "0") != "0"
    return CosSettings(
        bucket=bucket,
        region=os.environ.get("FILAMENT_PICKER_COS_REGION", "ap-shanghai").strip() or "ap-shanghai",
        prefix=prefix,
        secret_id=secret_id,
        secret_key=secret_key,
        token=os.environ.get("FILAMENT_PICKER_COS_TOKEN", "").strip(),
        timeout=timeout,
        endpoint=endpoint,
        secure=secure,
    )


def load_key_overrides(path: str | None = None) -> dict[str, str]:
    raw_path = path if path is not None else os.environ.get("FILAMENT_PICKER_COS_MAP", "").strip()
    if not raw_path:
        return {}
    parsed = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("COS map must be a JSON object")
    overrides: dict[str, str] = {}
    for model_id, item in parsed.items():
        if not isinstance(model_id, str):
            continue
        key = item.get("key") if isinstance(item, dict) else item
        if isinstance(key, str) and safe_object_key(key) is not None:
            overrides[model_id] = safe_object_key(key) or ""
    return {key: value for key, value in overrides.items() if value}


def safe_object_key(value: object) -> str | None:
    """Accept a relative object key. Reject URLs, buckets, and path escape."""
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")):
        return None
    if "\\" in value or "://" in value or value.lower().startswith("cos:"):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.suffix.lower() not in _SUFFIXES:
        return None
    return path.as_posix()


def resolve_object_key(
    model_id: str,
    canonical_id: str,
    stored_path: str,
    overrides: dict[str, str],
) -> str | None:
    for candidate in (overrides.get(model_id), overrides.get(canonical_id), stored_path):
        key = safe_object_key(candidate)
        if key is not None:
            return key
    return None


def content_disposition(filename: str) -> str:
    cleaned = "".join(ch for ch in filename if ch not in '\r\n"\\')
    ascii_name = "".join(ch if 32 <= ord(ch) < 127 else "_" for ch in cleaned) or "model.3mf"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(cleaned)}"


def media_type_for(key: str) -> str:
    return _SUFFIXES.get(PurePosixPath(key).suffix.lower(), "application/octet-stream")


def cos_paths(prefix: str, key: str) -> tuple[str, str]:
    """Return the encoded request path and the raw path used for COS signing.

    The request line must be percent-encoded. Tencent COS compares the signature
    against the unencoded object path, so Chinese characters and spaces are signed raw.
    """
    raw = "/" + f"{prefix.strip('/')}/{key.strip('/')}".strip("/")
    return quote(raw, safe="/"), raw


def sign_request(
    method: str,
    pathname: str,
    host: str,
    secret_id: str,
    secret_key: str,
    now: int,
    expires: int,
    token: str = "",
) -> str:
    """Tencent COS HMAC-SHA1 authorization. The signature stays on this server."""
    key_time = f"{now};{now + expires}"
    sign_key = hmac.new(secret_key.encode(), key_time.encode(), hashlib.sha1).hexdigest()
    pairs = [f"host={quote(host, safe='-_.~')}"]
    names = ["host"]
    if token:
        pairs.append(f"x-cos-security-token={quote(token, safe='-_.~')}")
        names.append("x-cos-security-token")
    order = sorted(zip(names, pairs, strict=True))
    headers = "&".join(pair for _, pair in order)
    header_list = ";".join(name for name, _ in order)
    http_string = f"{method.lower()}\n{pathname}\n\n{headers}\n"
    string_to_sign = f"sha1\n{key_time}\n{hashlib.sha1(http_string.encode()).hexdigest()}\n"
    signature = hmac.new(sign_key.encode(), string_to_sign.encode(), hashlib.sha1).hexdigest()
    return (
        "q-sign-algorithm=sha1"
        f"&q-ak={secret_id}"
        f"&q-sign-time={key_time}"
        f"&q-key-time={key_time}"
        f"&q-header-list={header_list}"
        "&q-url-param-list="
        f"&q-signature={signature}"
    )


class HttpObjectSource:
    def __init__(self, settings: CosSettings) -> None:
        self.settings = settings

    def open(self, key: str, range_header: str | None, method: str = "GET") -> ObjectOpen:
        safe = safe_object_key(key)
        if safe is None:
            raise UpstreamFailure()
        request_path, signature_path = cos_paths(self.settings.prefix, safe)
        now = int(datetime.now(UTC).timestamp())
        headers = {
            "Host": self.settings.host,
            "Authorization": sign_request(
                method,
                signature_path,
                self.settings.host,
                self.settings.secret_id,
                self.settings.secret_key,
                now,
                max(60, int(self.settings.timeout)),
                self.settings.token,
            ),
        }
        if self.settings.token:
            headers["x-cos-security-token"] = self.settings.token
        if range_header:
            headers["Range"] = range_header
        connection = self._connect()
        try:
            connection.request(method, request_path, headers=headers)
            response = connection.getresponse()
        except (OSError, HTTPException, TimeoutError) as exc:
            connection.close()
            raise UpstreamFailure() from exc
        if response.status not in (200, 206):
            _discard(response)
            connection.close()
            raise UpstreamFailure()
        length = _content_length(response)
        content_range = response.getheader("Content-Range")
        if content_range and not content_range.lower().startswith("bytes "):
            content_range = None

        def chunks() -> Iterator[bytes]:
            try:
                while True:
                    piece = response.read(_CHUNK)
                    if not piece:
                        break
                    yield piece
            finally:
                response.close()
                connection.close()

        return ObjectOpen(
            status=response.status,
            media_type=media_type_for(safe),
            size=length,
            content_range=content_range,
            chunks=chunks(),
            close=lambda: (response.close(), connection.close()),
        )

    def _connect(self) -> HTTPConnection:
        host = self.settings.host
        port: int | None = None
        if ":" in host and not host.startswith("["):
            host, raw_port = host.rsplit(":", 1)
            port = int(raw_port)
        if self.settings.secure:
            return HTTPSConnection(host, port or 443, timeout=self.settings.timeout)
        return HTTPConnection(host, port or 80, timeout=self.settings.timeout)


class UpstreamFailure(Exception):
    """Upstream storage failed. The message is never shown to the browser."""


def _content_length(response: HTTPResponse) -> int | None:
    raw = response.getheader("Content-Length")
    if raw is None or not raw.isdigit():
        return None
    return int(raw)


def _discard(response: HTTPResponse) -> None:
    try:
        response.read(1024)
    except (OSError, HTTPException, TimeoutError):
        return


def local_original(root: Path, model_id: str) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", model_id):
        return None
    base = root.resolve()
    directory = base / "originals"
    for suffix in (".3mf", ".stl"):
        candidate = directory / f"{model_id}{suffix}"
        try:
            path = candidate.resolve()
        except OSError:
            continue
        if (
            path.parent == directory
            and not candidate.is_symlink()
            and path.is_file()
            and path.suffix.lower() == suffix
        ):
            return path
    return None


def lookup_download(conn: sqlite3.Connection, model_id: str) -> tuple[sqlite3.Row, str, str] | None:
    """Return the canonical row, the id to name the file, and the stored relative path."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", model_id):
        return None
    row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    if row is not None:
        return row, model_id, str(row["source_relpath"] or "")
    if not _has_table(conn, "model_aliases"):
        return None
    alias = conn.execute(
        "SELECT model_id, rel_path FROM model_aliases WHERE alias_id = ?", (model_id,)
    ).fetchone()
    if alias is None:
        return None
    canonical = conn.execute("SELECT * FROM models WHERE id = ?", (alias["model_id"],)).fetchone()
    if canonical is None:
        return None
    stored = str(alias["rel_path"] or "") or str(canonical["source_relpath"] or "")
    return canonical, model_id, stored


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    found = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return found is not None


def original_descriptor(
    available: bool,
    model_id: str,
    filename: str | None,
    size: int | None,
    media_type: str | None,
) -> dict[str, object]:
    return {
        "available": available,
        "reason": None if available else "unavailable",
        "filename": filename,
        "size_bytes": size,
        "sha256": None,
        "media_type": media_type,
        "url": f"/api/models/{quote(model_id, safe='')}/original" if available else None,
    }


def filename_for(title: str, key: str) -> str:
    suffix = PurePosixPath(key).suffix.lower() or ".3mf"
    stem = title.strip() or "model"
    stem = stem[:80]
    return f"{stem}{suffix}"


def parse_range(header: str | None, size: int | None) -> tuple[int, int] | None:
    if not header:
        return None
    match = _RANGE.fullmatch(header.strip())
    if match is None or size is None:
        raise RangeNotSatisfiable()
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else size - 1
    if start > end or start >= size:
        raise RangeNotSatisfiable()
    return start, min(end, size - 1)


class RangeNotSatisfiable(Exception):
    pass


def iter_file(path: Path, start: int, end: int) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining:
            piece = handle.read(min(_CHUNK, remaining))
            if not piece:
                break
            remaining -= len(piece)
            yield piece


def content_sha256(path: Path) -> str:
    """SHA-256 of the file bytes. This is the only hash that verifies a download."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publishable_sha(digest: str | None, *model_ids: str) -> str | None:
    """Drop a claim that is only the identity digest of a model id.

    ``models.sha256`` is ``sha256(id)``. It names the row. It is not the
    original file, and it must not be shown as a passed content check.
    """
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
        return None
    lowered = digest.lower()
    identity = {hashlib.sha256(item.encode()).hexdigest() for item in model_ids if item}
    if lowered in identity:
        return None
    return lowered


def read_map_sha(path: str | None, model_id: str) -> str | None:
    raw_path = path if path is not None else os.environ.get("FILAMENT_PICKER_COS_MAP", "").strip()
    if not raw_path:
        return None
    try:
        parsed = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    item = parsed.get(model_id) if isinstance(parsed, dict) else None
    if not isinstance(item, dict):
        return None
    digest = item.get("sha256")
    if isinstance(digest, str) and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        return digest.lower()
    return None
