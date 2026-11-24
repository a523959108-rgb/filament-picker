from __future__ import annotations

import asyncio
import os
import secrets
import struct
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from filament_picker.auth import PREVIEW_USER_ENV, AuthStore
from filament_picker.model_samples import seed_samples
from filament_picker.server import build_server_app

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
    db = tmp_path / "auth" / "users.sqlite"
    models = tmp_path / "models-private"
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_ROOT", str(models))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECURE", "0")
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_DIRECT", "1")
    monkeypatch.setenv("FILAMENT_PICKER_REGISTRATION", "1")
    monkeypatch.setenv(PREVIEW_USER_ENV, USER)
    password = secrets.token_urlsafe(24)
    AuthStore(db).create_user(USER, password)
    seed_samples(models)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>\n', encoding="utf-8")
    app = build_server_app(
        dist, repo_root / "docs/schemas/examples/filament-catalog.example.json", tmp_path, None
    )
    return app, password, models


def _login(app: FastAPI, username: str, password: str) -> str:
    response = _request(
        app, "POST", "/api/models/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.headers["set-cookie"].split(";", 1)[0]


def _stl() -> bytes:
    header = b"x" * 80
    body = b"".join(struct.pack("<12fH", *([0.0] * 12), 0) for _ in range(1))
    return header + struct.pack("<I", 1) + body


def test_registration_is_off_by_default(preview: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _password, _models = preview
    monkeypatch.setenv("FILAMENT_PICKER_REGISTRATION", "0")
    assert _request(app, "GET", "/api/models/registration").json()["enabled"] is False
    assert _request(app, "GET", "/api/models/registration").json()["email_sent"] is False
    refused = _request(
        app,
        "POST",
        "/api/models/register",
        json={"username": "member-one", "password": "long-enough-pw"},
    )
    assert refused.status_code == 403


def test_members_cannot_see_or_share_the_legacy_library(
    preview: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FILAMENT_PICKER_SUBMISSIONS", "1")
    app, password, models = preview
    owner = _login(app, USER, password)
    assert _request(app, "GET", "/api/models", owner).json()["total"] == 8
    created = _request(
        app,
        "POST",
        "/api/models/register",
        json={"username": "member-one", "password": "long-enough-pw", "email": ""},
    )
    assert created.status_code == 200
    assert created.json()["email_sent"] is False
    member = _login(app, "member-one", "long-enough-pw")
    listing = _request(app, "GET", "/api/models", member).json()
    assert listing["total"] == 0
    assert _request(app, "GET", "/api/models/sample-01", member).status_code == 404
    assert _request(app, "GET", "/api/models/sample-01/thumb", member).status_code == 404
    assert _request(app, "GET", "/api/models/sample-01/original", member).status_code == 404
    hidden = _request(app, "POST", "/api/models/sample-01/shares", member, json={"days": 7})
    assert hidden.status_code == 404
    uploaded = _request(
        app,
        "POST",
        "/api/models/submissions",
        member,
        files={"file": ("box.stl", _stl(), "model/stl")},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["status"] == "ready"
    assert body["sha256"]
    own = _request(app, "GET", "/api/models", member).json()
    assert own["total"] == 1
    assert own["items"][0]["id"] == body["model_id"]
    assert _request(app, "GET", f"/api/models/{body['model_id']}", owner).status_code == 404
    assert not (models / "originals" / f"{body['model_id']}.stl").exists()
    stored = models / "accounts" / "member-one" / "originals" / f"{body['model_id']}.stl"
    assert stored.is_file()
    stepped = _request(
        app,
        "POST",
        "/api/models/submissions",
        member,
        files={"file": ("part.step", b"ISO-10303-21;" + b" " * 20, "model/step")},
    )
    assert stepped.status_code == 400
    assert "freecadcmd" in stepped.json()["detail"]
    renamed = _request(
        app,
        "POST",
        "/api/models/submissions",
        member,
        files={"file": ("evil.stl", b"not really a mesh!!!!", "model/stl")},
    )
    assert renamed.status_code == 200
    assert renamed.json()["status"] == "failed"
    assert renamed.json()["retryable"] is True


def test_empty_owner_is_not_claimed_by_a_later_identity(
    preview: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, password, models = preview
    owner = _login(app, USER, password)
    assert _request(app, "GET", "/api/models/sample-01", owner).status_code == 200
    import sqlite3

    with sqlite3.connect(models / "manifest.sqlite") as conn:
        conn.execute("UPDATE models SET owner = '' WHERE id = 'sample-01'")
    monkeypatch.setenv("FILAMENT_PICKER_PREVIEW_USER", "someone-else")
    assert _request(app, "GET", "/api/models/sample-01", owner).status_code == 404


def test_submissions_stay_off_until_their_own_switch(
    preview: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, password, _models = preview
    monkeypatch.delenv("FILAMENT_PICKER_SUBMISSIONS", raising=False)
    owner = _login(app, USER, password)
    response = _request(
        app,
        "POST",
        "/api/models/submissions",
        owner,
        files={"file": ("box.stl", b"solid x\nendsolid x\n", "model/stl")},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "投稿未开放"


def test_step_calls_a_local_converter_only_when_enabled(
    preview: tuple, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app, password, _models = preview
    monkeypatch.setenv("FILAMENT_PICKER_SUBMISSIONS", "1")
    stub = tmp_path / "freecadcmd"
    stub.write_text(
        "#!/bin/sh\nprintf 'solid x\\nfacet normal 0 0 0\\nouter loop\\n"
        "vertex 0 0 0\\nvertex 1 0 0\\nvertex 0 1 0\\n"
        'endloop\\nendfacet\\nendsolid x\\n\' > "$2"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")
    owner = _login(app, USER, password)
    body = b"ISO-10303-21;\nEND-ISO-10303-21;\n"
    closed = _request(
        app,
        "POST",
        "/api/models/submissions",
        owner,
        files={"file": ("part.step", body, "application/step")},
    )
    assert closed.status_code == 400
    assert "默认关闭" in closed.json()["detail"]
    assert "freecadcmd" in closed.json()["detail"]
    monkeypatch.setenv("FILAMENT_PICKER_STEP", "1")
    opened = _request(
        app,
        "POST",
        "/api/models/submissions",
        owner,
        files={"file": ("part.step", body, "application/step")},
    )
    assert opened.status_code == 200
    assert opened.json()["status"] == "ready"
