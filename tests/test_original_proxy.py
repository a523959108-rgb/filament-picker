from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from fastapi import FastAPI

from filament_picker.auth import PREVIEW_USER_ENV, AuthStore
from filament_picker.model_samples import seed_samples
from filament_picker.server import build_server_app

PREVIEW_TEST_USER = "preview-tester"

_BUCKET = "filament-backup-1385670520"
_PREFIX = "filament-picker/3mf-originals/20261107"
_BODY = b"3mf-bytes-" + b"abc" * 1000
_SECRET = "SUPERSECRET-do-not-leak"


class _Store(ThreadingHTTPServer):
    files: dict[str, bytes]
    seen: list[str]
    mode: str


def _server() -> _Store:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._serve(False)

        def do_HEAD(self) -> None:
            self._serve(True)

        def _serve(self, head: bool) -> None:
            server: _Store = self.server  # type: ignore[assignment]
            server.seen.append(self.path)
            if server.mode == "redirect":
                self.send_response(302)
                self.send_header(
                    "Location", f"https://{_BUCKET}.cos.ap-shanghai.myqcloud.com/secret"
                )
                self.end_headers()
                return
            if server.mode == "fail":
                body = f"{_SECRET} {_BUCKET} {self.path}".encode()
                self.send_response(500)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if not head:
                    self.wfile.write(body)
                return
            key = unquote(self.path.split("?", 1)[0]).lstrip("/")
            payload = server.files.get(key)
            if payload is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            start, end = 0, len(payload) - 1
            status = 200
            if "Range" in self.headers:
                raw = self.headers["Range"].removeprefix("bytes=")
                start_text, end_text = raw.split("-", 1)
                start = int(start_text)
                end = int(end_text) if end_text else len(payload) - 1
                status = 206
            piece = payload[start : end + 1]
            self.send_response(status)
            self.send_header("Content-Length", str(len(piece)))
            self.send_header("Content-Type", "application/xml")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
            self.end_headers()
            if not head:
                self.wfile.write(piece)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    httpd = _Store(("127.0.0.1", 0), Handler)
    httpd.files = {_PREFIX + "/library/sample.3mf": _BODY}
    httpd.seen = []
    httpd.mode = "ok"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _configure(monkeypatch: pytest.MonkeyPatch, httpd: _Store) -> None:
    host, port = httpd.server_address[:2]
    monkeypatch.setenv("FILAMENT_PICKER_COS_BUCKET", _BUCKET)
    monkeypatch.setenv("FILAMENT_PICKER_COS_REGION", "ap-shanghai")
    monkeypatch.setenv("FILAMENT_PICKER_COS_PREFIX", _PREFIX + "/")
    monkeypatch.setenv("FILAMENT_PICKER_COS_SECRET_ID", "test-id")
    monkeypatch.setenv("FILAMENT_PICKER_COS_SECRET_KEY", _SECRET)
    monkeypatch.setenv("FILAMENT_PICKER_COS_ENDPOINT", f"{host}:{port}")
    monkeypatch.setenv("FILAMENT_PICKER_COS_SECURE", "0")
    monkeypatch.setenv("FILAMENT_PICKER_COS_TIMEOUT_SECONDS", "2")


def _write_map(tmp: Path, mapping: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp / "cos-map.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    monkeypatch.setenv("FILAMENT_PICKER_COS_MAP", str(path))


def _request(app: FastAPI, method: str, path: str, cookie: str = "", **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            merged = {"cookie": cookie}
            extra = kwargs.pop("headers", None)
            if extra:
                merged.update(extra)
            return await client.request(method, path, headers=merged, **kwargs)

    return asyncio.run(send())


@pytest.fixture
def preview(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    db = tmp_path / "auth" / "users.sqlite"
    models = tmp_path / "models-private"
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_ROOT", str(models))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECURE", "0")
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_DIRECT", "1")
    monkeypatch.setenv(PREVIEW_USER_ENV, PREVIEW_TEST_USER)
    password = secrets.token_urlsafe(24)
    AuthStore(db).create_user(PREVIEW_TEST_USER, password)
    seed_samples(models)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>\n', encoding="utf-8")
    (dist / "web-catalog.json").write_text("{}\n", encoding="utf-8")
    app = build_server_app(
        dist, repo_root / "docs/schemas/examples/filament-catalog.example.json", tmp_path, None
    )
    return app, password, models, db


def _login(app: FastAPI, password: str) -> httpx.Response:
    return _request(
        app,
        "POST",
        "/api/models/login",
        json={"username": PREVIEW_TEST_USER, "password": password},
    )


def _cookie(response: httpx.Response) -> str:
    return response.headers["set-cookie"].split(";", 1)[0]


def _quiet(text: str) -> None:
    assert _BUCKET not in text
    assert _SECRET not in text
    assert "myqcloud" not in text
    assert "library/sample.3mf" not in text
    assert "Location" not in text


def test_remote_download_streams_bytes_without_leaking_storage(
    preview: tuple, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app, password, _models, _db = preview
    httpd = _server()
    _configure(monkeypatch, httpd)
    digest = hashlib.sha256(_BODY).hexdigest()
    _write_map(
        tmp_path,
        {"sample-01": {"key": "library/sample.3mf", "sha256": digest}},
        monkeypatch,
    )
    cookie = _cookie(_login(app, password))
    detail = _request(app, "GET", "/api/models/sample-01", cookie)
    original = detail.json()["original"]
    assert original["available"] is True
    assert original["url"] == "/api/models/sample-01/original"
    assert original["filename"].endswith(".3mf")
    assert original["sha256"] == digest
    _quiet(detail.text)
    response = _request(app, "GET", original["url"], cookie)
    assert response.status_code == 200
    assert response.content == _BODY
    assert response.headers["x-content-sha256"] == digest
    assert response.headers["content-type"].startswith("model/3mf")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert "location" not in {key.lower() for key in response.headers}
    _quiet(response.text)
    assert httpd.seen
    head = _request(app, "HEAD", original["url"], cookie)
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == str(len(_BODY))
    partial = _request(app, "GET", original["url"], cookie, headers={"range": "bytes=0-3"})
    assert partial.status_code == 206
    assert partial.content == _BODY[:4]
    assert partial.headers["content-range"] == f"bytes 0-3/{len(_BODY)}"
    httpd.shutdown()


def test_download_failures_stay_on_our_origin(
    preview: tuple, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app, password, _models, _db = preview
    httpd = _server()
    _configure(monkeypatch, httpd)
    _write_map(tmp_path, {"sample-01": "library/sample.3mf"}, monkeypatch)
    cookie = _cookie(_login(app, password))
    assert _request(app, "GET", "/api/models/sample-01/original").status_code == 401
    assert _request(app, "GET", "/api/models/missing/original", cookie).status_code == 404
    _write_map(tmp_path, {"sample-01": "../secret.3mf"}, monkeypatch)
    hidden = _request(app, "GET", "/api/models/sample-01/original", cookie)
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "没有原件映射"
    assert httpd.seen == []
    _write_map(tmp_path, {"sample-01": "library/missing.3mf"}, monkeypatch)
    missing = _request(app, "GET", "/api/models/sample-01/original", cookie)
    assert missing.status_code == 502
    assert missing.json()["detail"] == "原件暂时无法下载"
    _quiet(missing.text)
    httpd.mode = "fail"
    _write_map(tmp_path, {"sample-01": "library/sample.3mf"}, monkeypatch)
    failed = _request(app, "GET", "/api/models/sample-01/original", cookie)
    assert failed.status_code == 502
    _quiet(failed.text)
    httpd.mode = "redirect"
    redirected = _request(app, "GET", "/api/models/sample-01/original", cookie)
    assert redirected.status_code == 502
    assert "location" not in {key.lower() for key in redirected.headers}
    _quiet(redirected.text)
    httpd.shutdown()


def test_unicode_object_streams_and_catalog_hash_is_not_the_file_hash(
    preview: tuple, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app, password, models, _db = preview
    httpd = _server()
    _configure(monkeypatch, httpd)
    chinese = "系列/拉布布 01.3mf"
    special = "特殊/a+b #c.3mf"
    httpd.files[_PREFIX + "/" + chinese] = b"unicode-body"
    httpd.files[_PREFIX + "/Rayan-Universal1211.3mf"] = b"ascii-body"
    httpd.files[_PREFIX + "/" + special] = b"special-body"
    _write_map(
        tmp_path,
        {
            "sample-01": chinese,
            "sample-02": "Rayan-Universal1211.3mf",
            "sample-03": special,
        },
        monkeypatch,
    )
    import sqlite3

    wrong = "c6f39338" + "ab" * 28
    with sqlite3.connect(models / "manifest.sqlite") as conn:
        conn.execute("UPDATE models SET sha256 = ? WHERE id = 'sample-01'", (wrong,))
    cookie = _cookie(_login(app, password))
    detail = _request(app, "GET", "/api/models/sample-01", cookie).json()["original"]
    assert detail["sha256"] is None
    chinese_download = _request(app, "GET", "/api/models/sample-01/original", cookie)
    assert chinese_download.status_code == 200
    assert chinese_download.content == b"unicode-body"
    assert "x-content-sha256" not in {key.lower() for key in chinese_download.headers}
    assert any("%E6%8B%89%E5%B8%83%E5%B8%83%2001.3mf" in path for path in httpd.seen)
    assert all("拉布布" not in path for path in httpd.seen)
    ascii_download = _request(app, "GET", "/api/models/sample-02/original", cookie)
    assert ascii_download.status_code == 200
    assert ascii_download.content == b"ascii-body"
    assert any(path.endswith("/Rayan-Universal1211.3mf") for path in httpd.seen)
    special_download = _request(app, "GET", "/api/models/sample-03/original", cookie)
    assert special_download.status_code == 200
    assert special_download.content == b"special-body"
    assert any("a%2Bb%20%23c.3mf" in path for path in httpd.seen)
    assert all("a+b" not in path and "#" not in path for path in httpd.seen)
    _quiet(chinese_download.text)
    _quiet(special_download.text)
    httpd.shutdown()


def test_local_hash_is_the_file_and_identity_digest_is_not_verification(
    preview: tuple, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app, password, models, _db = preview
    payload = b"local-original-not-the-row-id"
    directory = models / "originals"
    directory.mkdir()
    (directory / "sample-01.3mf").write_bytes(payload)
    identity = hashlib.sha256(b"sample-01").hexdigest()
    content = hashlib.sha256(payload).hexdigest()
    import sqlite3

    with sqlite3.connect(models / "manifest.sqlite") as conn:
        conn.execute("UPDATE models SET sha256 = ? WHERE id = 'sample-01'", (identity,))
    _write_map(
        tmp_path,
        {"sample-01": {"key": "library/sample.3mf", "sha256": identity}},
        monkeypatch,
    )
    cookie = _cookie(_login(app, password))
    original = _request(app, "GET", "/api/models/sample-01", cookie).json()["original"]
    assert original["sha256"] == content
    assert original["sha256"] != identity
    downloaded = _request(app, "GET", "/api/models/sample-01/original", cookie)
    assert downloaded.status_code == 200
    assert downloaded.content == payload
    assert downloaded.headers["x-content-sha256"] == content
    ranged = _request(
        app, "GET", "/api/models/sample-01/original", cookie, headers={"range": "bytes=0-3"}
    )
    assert ranged.status_code == 206
    assert "x-content-sha256" not in {key.lower() for key in ranged.headers}


def test_remote_identity_digest_is_not_advertised_as_content_hash(
    preview: tuple, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app, password, _models, _db = preview
    httpd = _server()
    _configure(monkeypatch, httpd)
    identity = hashlib.sha256(b"sample-01").hexdigest()
    _write_map(
        tmp_path,
        {"sample-01": {"key": "library/sample.3mf", "sha256": identity}},
        monkeypatch,
    )
    cookie = _cookie(_login(app, password))
    original = _request(app, "GET", "/api/models/sample-01", cookie).json()["original"]
    assert original["sha256"] is None
    downloaded = _request(app, "GET", "/api/models/sample-01/original", cookie)
    assert downloaded.status_code == 200
    assert downloaded.content == _BODY
    assert "x-content-sha256" not in {key.lower() for key in downloaded.headers}
    httpd.shutdown()


def test_alias_and_local_file_do_not_use_object_storage(
    preview: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, password, models, _db = preview
    payload = b"local-original"
    directory = models / "originals"
    directory.mkdir()
    (directory / "sample-01.3mf").write_bytes(payload)
    import sqlite3

    with sqlite3.connect(models / "manifest.sqlite") as conn:
        conn.execute(
            "CREATE TABLE model_aliases (alias_id TEXT PRIMARY KEY, model_id TEXT NOT NULL, "
            "rel_path TEXT NOT NULL DEFAULT '')"
        )
        conn.execute(
            "INSERT INTO model_aliases (alias_id, model_id, rel_path) VALUES (?, ?, ?)",
            ("alias-01", "sample-01", "library/alias.3mf"),
        )
    cookie = _cookie(_login(app, password))
    response = _request(app, "GET", "/api/models/alias-01/original", cookie)
    assert response.status_code == 200
    assert response.content == payload
    assert "myqcloud" not in response.text
    ranged = _request(
        app, "GET", "/api/models/sample-01/original", cookie, headers={"range": "bytes=0-4"}
    )
    assert ranged.status_code == 206
    assert ranged.content == payload[:5]
    bad = _request(
        app, "GET", "/api/models/sample-01/original", cookie, headers={"range": "bytes=9-1"}
    )
    assert bad.status_code == 416


def test_chinese_key_is_requested_encoded_and_signed_raw() -> None:
    from filament_picker.originals import cos_paths, sign_request

    prefix = "filament-picker/3mf-originals/20261107"
    raw_key = "系列/拉布布 01.3mf"
    request_path, signature_path = cos_paths(prefix, raw_key)
    assert signature_path == f"/{prefix}/{raw_key}"
    assert request_path == (
        "/filament-picker/3mf-originals/20261107/"
        "%E7%B3%BB%E5%88%97/%E6%8B%89%E5%B8%83%E5%B8%83%2001.3mf"
    )
    assert "拉布布" not in request_path
    assert " " not in request_path
    ascii_request, ascii_signature = cos_paths(prefix, "Rayan-Universal1211.3mf")
    assert ascii_request == ascii_signature
    assert ascii_request.endswith("/Rayan-Universal1211.3mf")
    host = "filament-backup-1385670520.cos.ap-shanghai.myqcloud.com"
    signed = sign_request("GET", signature_path, host, "AKIDexample", "secret-one", 1700000000, 120)
    assert signed == (
        "q-sign-algorithm=sha1&q-ak=AKIDexample&q-sign-time=1700000000;1700000120"
        "&q-key-time=1700000000;1700000120&q-header-list=host&q-url-param-list="
        "&q-signature=3e5646f43f4f8b337f479a0d0b7b35274b57e3a4"
    )
    encoded_signed = sign_request(
        "GET", request_path, host, "AKIDexample", "secret-one", 1700000000, 120
    )
    assert encoded_signed != signed
    special_key = "特殊/a+b #c.3mf"
    special_request, special_signature = cos_paths(prefix, special_key)
    assert special_signature == f"/{prefix}/{special_key}"
    assert special_request.endswith("/%E7%89%B9%E6%AE%8A/a%2Bb%20%23c.3mf")
    assert "+" not in special_request and "#" not in special_request
    special_signed = sign_request(
        "GET",
        special_signature,
        "example.cos.ap-shanghai.myqcloud.com",
        "AKIDexample",
        "secret-one",
        1700000000,
        120,
    )
    assert special_signed.endswith("q-signature=6f0c16ec225b0b3d424e8540846cc8668c036dbd")


def test_object_key_uses_stored_path_or_map_and_rejects_escape() -> None:
    from filament_picker.originals import resolve_object_key

    assert resolve_object_key("a", "a", "library/a.3mf", {}) == "library/a.3mf"
    assert resolve_object_key("a", "a", "../x.3mf", {}) is None
    assert resolve_object_key("a", "b", "nope", {"a": "mapped/a.3mf"}) == "mapped/a.3mf"
    assert resolve_object_key("alias", "canon", "alias.3mf", {"canon": "canon.3mf"}) == "canon.3mf"
    assert resolve_object_key("alias", "canon", "other.3mf", {"alias": "alias.3mf"}) == "alias.3mf"


def test_sign_request_changes_when_the_secret_changes() -> None:
    from filament_picker.originals import sign_request

    host = "bucket.cos.ap-shanghai.myqcloud.com"
    first = sign_request("GET", "/a.3mf", host, "id", "secret-one", 10, 60)
    second = sign_request("GET", "/a.3mf", host, "id", "secret-two", 10, 60)
    assert first.startswith("q-sign-algorithm=sha1&q-ak=id&")
    assert first != second
    assert "secret-one" not in first
