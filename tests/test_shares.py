from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI

from filament_picker.auth import PREVIEW_USER_ENV, AuthStore
from filament_picker.config import TZ
from filament_picker.model_samples import seed_samples
from filament_picker.server import build_server_app
from filament_picker.shares import _FAILURES

USER = "preview-tester"


def _request(app: FastAPI, method: str, path: str, cookie: str = "", **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.request(method, path, headers={"cookie": cookie}, **kwargs)

    return asyncio.run(send())


@pytest.fixture
def preview(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    _FAILURES.clear()
    db = tmp_path / "auth" / "users.sqlite"
    models = tmp_path / "models-private"
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_ROOT", str(models))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECURE", "0")
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_DIRECT", "1")
    monkeypatch.setenv(PREVIEW_USER_ENV, USER)
    password = secrets.token_urlsafe(24)
    AuthStore(db).create_user(USER, password)
    seed_samples(models)
    (models / "originals").mkdir()
    (models / "originals" / "sample-01.3mf").write_bytes(b"3mf-bytes")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>\n', encoding="utf-8")
    app = build_server_app(
        dist, repo_root / "docs/schemas/examples/filament-catalog.example.json", tmp_path, None
    )
    return app, password, models, db


def _cookie(app: FastAPI, password: str) -> str:
    response = _request(
        app, "POST", "/api/models/login", json={"username": USER, "password": password}
    )
    assert response.status_code == 200
    return response.headers["set-cookie"].split(";", 1)[0]


def _share_cookie(response: httpx.Response) -> str:
    header = response.headers["set-cookie"]
    assert "fp_share=" in header
    assert "httponly" in header.lower()
    assert "path=/api/share" in header.lower()
    assert "samesite=strict" in header.lower()
    return header.split(";", 1)[0]


def test_grant_is_hashed_and_private_routes_stay_closed(preview: tuple) -> None:
    app, password, models, db = preview
    cookie = _cookie(app, password)
    assert _request(app, "GET", "/api/models").status_code == 401
    assert _request(app, "GET", "/api/models/sample-01/thumb").status_code == 401
    created = _request(
        app,
        "POST",
        "/api/models/sample-01/shares",
        cookie,
        json={"days": 7, "allow_original": False, "allow_scheme_copy": False},
    )
    assert created.status_code == 200
    body = created.json()
    token = body["link"].split("#", 1)[1]
    assert token not in db.read_bytes().decode(errors="ignore")
    assert _digest_present(db, token)
    listed = _request(app, "GET", "/api/models/sample-01/shares", cookie).json()["items"]
    assert token not in json.dumps(listed)
    assert listed[0]["allow_original"] is False
    opened = _request(app, "POST", "/api/share/open", json={"token": token})
    assert opened.status_code == 200
    assert opened.json()["title"]
    assert "original_url" not in opened.json()
    assert "sample-01" not in opened.text
    assert "location" not in {key.lower() for key in opened.headers}
    share = _share_cookie(opened)
    thumb = _request(app, "GET", "/api/share/thumb", share)
    assert thumb.status_code == 200
    assert thumb.headers["cache-control"] == "no-store"
    assert _request(app, "GET", "/api/models/sample-01/thumb", share).status_code == 401
    assert _request(app, "GET", "/api/models/sample-02", share).status_code == 401
    assert _request(app, "GET", "/api/share/original", share).status_code == 403
    assert _request(app, "GET", "/api/share/scheme-copy", share).status_code == 403
    assert _request(app, "GET", "/api/share/media/not-a-real-shot.png", share).status_code == 404
    favorite = _request(app, "PUT", "/api/models/favorites/sample-01", cookie)
    assert favorite.status_code == 200
    assert (models / "originals" / "sample-01.3mf").read_bytes() == b"3mf-bytes"


def test_revoke_and_expiry_stop_the_session(preview: tuple) -> None:
    app, password, _models, db = preview
    cookie = _cookie(app, password)
    created = _request(app, "POST", "/api/models/sample-01/shares", cookie, json={"days": 1}).json()
    token = created["link"].split("#", 1)[1]
    opened = _request(app, "POST", "/api/share/open", json={"token": token})
    share = _share_cookie(opened)
    assert _request(app, "GET", "/api/share/view", share).status_code == 200
    revoked = _request(app, "POST", f"/api/models/shares/{created['grant_id']}/revoke", cookie)
    assert revoked.status_code == 200
    assert _request(app, "GET", "/api/share/view", share).status_code == 410
    again = _request(app, "POST", "/api/share/open", json={"token": token})
    assert again.status_code == 410
    other = _request(app, "POST", "/api/models/sample-01/shares", cookie, json={"days": 7}).json()
    past = (datetime.now(ZoneInfo(TZ)) - timedelta(minutes=1)).isoformat(timespec="seconds")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE share_grants SET expires_at = ? WHERE grant_id = ?",
            (past, other["grant_id"]),
        )
    expired = _request(
        app, "POST", "/api/share/open", json={"token": other["link"].split("#", 1)[1]}
    )
    assert expired.status_code == 410
    assert expired.json()["detail"] == "链接已过期"


def test_original_download_requires_an_explicit_flag(preview: tuple) -> None:
    app, password, _models, _db = preview
    cookie = _cookie(app, password)
    created = _request(
        app,
        "POST",
        "/api/models/sample-01/shares",
        cookie,
        json={"days": 7, "allow_original": True, "allow_scheme_copy": False},
    ).json()
    opened = _request(
        app, "POST", "/api/share/open", json={"token": created["link"].split("#", 1)[1]}
    )
    assert opened.json()["original_url"] == "/api/share/original"
    downloaded = _request(app, "GET", "/api/share/original", _share_cookie(opened))
    assert downloaded.status_code == 200
    assert downloaded.content == b"3mf-bytes"
    assert "location" not in {key.lower() for key in downloaded.headers}


def test_bad_tokens_are_rate_limited(preview: tuple) -> None:
    _FAILURES.clear()
    app, _password, _models, _db = preview
    token = "a" * 43
    for _ in range(8):
        assert _request(app, "POST", "/api/share/open", json={"token": token}).status_code == 404
    blocked = _request(app, "POST", "/api/share/open", json={"token": token})
    assert blocked.status_code == 429
    _FAILURES.clear()


def test_another_username_cannot_see_or_revoke(preview: tuple) -> None:
    app, password, _models, db = preview
    cookie = _cookie(app, password)
    created = _request(app, "POST", "/api/models/sample-01/shares", cookie, json={"days": 7}).json()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE share_grants SET username = ? WHERE grant_id = ?",
            ("other-user", created["grant_id"]),
        )
    listed = _request(app, "GET", "/api/models/sample-01/shares", cookie).json()["items"]
    assert listed == []
    hidden = _request(app, "POST", f"/api/models/shares/{created['grant_id']}/revoke", cookie)
    assert hidden.status_code == 404


def test_grant_dies_when_ownership_moves(preview: tuple) -> None:
    app, password, models, _db = preview
    cookie = _cookie(app, password)
    created = _request(
        app,
        "POST",
        "/api/models/sample-01/shares",
        cookie,
        json={"days": 7, "allow_scheme_copy": True},
    ).json()
    token = created["link"].split("#", 1)[1]
    with sqlite3.connect(models / "manifest.sqlite") as conn:
        conn.execute("UPDATE models SET owner = ? WHERE id = ?", ("other-user", "sample-01"))
    opened = _request(app, "POST", "/api/share/open", json={"token": token})
    assert opened.status_code == 410
    assert opened.json()["detail"] == "链接已失效"


def test_grant_dies_when_the_owner_account_is_removed(preview: tuple) -> None:
    app, password, _models, db = preview
    cookie = _cookie(app, password)
    created = _request(app, "POST", "/api/models/sample-01/shares", cookie, json={"days": 7}).json()
    token = created["link"].split("#", 1)[1]
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (USER,))
    opened = _request(app, "POST", "/api/share/open", json={"token": token})
    assert opened.status_code == 410
    assert opened.json()["detail"] == "链接已失效"


def _digest_present(db: Path, token: str) -> bool:
    digest = hashlib.sha256(token.encode()).hexdigest()
    text = db.read_text(encoding="utf-8", errors="ignore")
    return digest in text or digest.encode() in db.read_bytes()
