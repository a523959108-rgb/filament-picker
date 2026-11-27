from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
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
    monkeypatch.setenv(PREVIEW_USER_ENV, USER)
    password = secrets.token_urlsafe(24)
    AuthStore(db).create_user(USER, password)
    seed_samples(models)
    manifest = models / "manifest.sqlite"
    with sqlite3.connect(manifest) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
        if "plate_layout" not in columns:
            conn.execute("ALTER TABLE models ADD COLUMN plate_layout TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "UPDATE models SET colours = ?, plate_layout = ? WHERE id = 'sample-01'",
            (
                json.dumps(["#112233", "#FFFFFF", "#000000"]),
                json.dumps(
                    [
                        {
                            "index": 1,
                            "name": "盘面",
                            "objects": ["a.stl", "a.stl"],
                            "filaments": [
                                {
                                    "slot": 1,
                                    "hex": "#112233",
                                    "type": "PLA",
                                    "vendor": "",
                                    "settings_id": "",
                                    "used_g": None,
                                },
                                {
                                    "slot": 2,
                                    "hex": "#112233",
                                    "type": "",
                                    "vendor": "",
                                    "settings_id": "",
                                    "used_g": None,
                                },
                            ],
                        }
                    ]
                ),
            ),
        )
        conn.execute("UPDATE models SET colours = '[]' WHERE id = 'sample-02'")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>\n', encoding="utf-8")
    app = build_server_app(
        dist, repo_root / "docs/schemas/examples/filament-catalog.example.json", tmp_path, None
    )
    return app, password, db


def _cookie(app: FastAPI, password: str) -> str:
    response = _request(
        app, "POST", "/api/models/login", json={"username": USER, "password": password}
    )
    assert response.status_code == 200
    return response.headers["set-cookie"].split(";", 1)[0]


def test_listing_searches_real_id_and_sorts_known_fields(preview: tuple) -> None:
    app, password, _db = preview
    cookie = _cookie(app, password)
    found = _request(app, "GET", "/api/models", cookie, params={"q": "sample-01"}).json()
    assert [item["id"] for item in found["items"]] == ["sample-01"]
    assert found["query"] == {
        "q": "sample-01",
        "series": "",
        "author": "",
        "material": "",
        "sort": "id",
        "order": "asc",
    }
    ranked = _request(
        app,
        "GET",
        "/api/models",
        cookie,
        params={"sort": "colour_count", "order": "desc", "page_size": 2},
    ).json()
    assert ranked["items"][0]["id"] == "sample-01"
    assert ranked["items"][1]["id"] != "sample-02"
    material = _request(app, "GET", "/api/models", cookie, params={"material": "PLA"}).json()
    assert [item["id"] for item in material["items"]] == ["sample-01"]
    assert "PLA" in material["materials"]
    assert _request(app, "GET", "/api/models?sort=duration", cookie).status_code == 422
    anonymous = _request(app, "GET", "/api/models?sort=created_at")
    assert anonymous.status_code == 401


def test_favorites_stay_on_the_single_account(preview: tuple) -> None:
    app, password, db = preview
    cookie = _cookie(app, password)
    assert _request(app, "PUT", "/api/models/favorites/sample-01").status_code == 401
    added = _request(app, "PUT", "/api/models/favorites/sample-01", cookie)
    assert added.status_code == 200
    assert _request(app, "PUT", "/api/models/favorites/nope", cookie).status_code == 404
    assert _request(app, "PUT", "/api/models/favorites/bad.id", cookie).status_code == 400
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO favorites (username, model_id, created_at) "
            "VALUES ('other', 'sample-02', 't')"
        )
    listed = _request(app, "GET", "/api/models/favorites", cookie).json()["items"]
    assert [item["model_id"] for item in listed] == ["sample-01"]
    assert _request(app, "DELETE", "/api/models/favorites/sample-01", cookie).status_code == 200
    assert _request(app, "GET", "/api/models/favorites", cookie).json()["items"] == []
    with sqlite3.connect(db) as conn:
        left = conn.execute("SELECT model_id FROM favorites WHERE username = 'other'").fetchone()
    assert left[0] == "sample-02"


def test_display_scheme_does_not_invent_slots(preview: tuple) -> None:
    app, password, _db = preview
    cookie = _cookie(app, password)
    saved = _request(
        app,
        "PUT",
        "/api/models/sample-01/scheme",
        cookie,
        json={"slots": [{"plate_index": 1, "slot": 2, "hex": "#abcdef"}]},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["note"].startswith("仅展示色")
    assert body["slots"] == [{"plate_index": 1, "slot": 2, "hex": "#ABCDEF"}]
    again = _request(app, "GET", "/api/models/sample-01/scheme", cookie).json()
    assert again["slots"] == body["slots"]
    missing = _request(
        app,
        "PUT",
        "/api/models/sample-01/scheme",
        cookie,
        json={"slots": [{"plate_index": 1, "slot": 9, "hex": "#abcdef"}]},
    )
    assert missing.status_code == 400
    no_map = _request(
        app,
        "PUT",
        "/api/models/sample-02/scheme",
        cookie,
        json={"slots": [{"plate_index": 1, "slot": 1, "hex": "#abcdef"}]},
    )
    assert no_map.status_code == 409
    cleared = _request(app, "PUT", "/api/models/sample-01/scheme", cookie, json={"slots": []})
    assert cleared.status_code == 200 and cleared.json()["slots"] == []
    assert _request(app, "GET", "/api/models/sample-01/scheme").status_code == 401
