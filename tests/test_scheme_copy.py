from __future__ import annotations

import asyncio
import hashlib
import io
import json
import secrets
import sqlite3
import stat
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from filament_picker.auth import PREVIEW_USER_ENV, AuthStore
from filament_picker.model_samples import seed_samples
from filament_picker.scheme_copy import SchemeCopyError, build_scheme_copy, synthetic_3mf
from filament_picker.server import build_server_app

USER = "preview-tester"
CAVEAT = "只改了耗材颜色记录，没有改切片路径。不能直接打印，需要重新切片。"


def _request(app: FastAPI, method: str, path: str, cookie: str = "", **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.request(method, path, headers={"cookie": cookie}, **kwargs)

    return asyncio.run(send())


def _cookie(app: FastAPI, password: str) -> str:
    response = _request(
        app, "POST", "/api/models/login", json={"username": USER, "password": password}
    )
    assert response.status_code == 200
    return response.headers["set-cookie"].split(";", 1)[0]


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
    plates = [
        {
            "index": 1,
            "name": "盘面",
            "objects": ["a.stl"],
            "filaments": [
                {
                    "slot": 1,
                    "hex": "#111111",
                    "type": "PLA",
                    "vendor": "",
                    "settings_id": "",
                    "used_g": None,
                },
                {
                    "slot": 2,
                    "hex": "#222222",
                    "type": "PLA",
                    "vendor": "",
                    "settings_id": "",
                    "used_g": None,
                },
            ],
        }
    ]
    with sqlite3.connect(manifest) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
        if "plate_layout" not in columns:
            conn.execute("ALTER TABLE models ADD COLUMN plate_layout TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "UPDATE models SET plate_layout = ? WHERE id = 'sample-01'",
            (json.dumps(plates),),
        )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>\n', encoding="utf-8")
    app = build_server_app(
        dist, repo_root / "docs/schemas/examples/filament-catalog.example.json", tmp_path, None
    )
    return app, password, models


def _settings(payload: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return json.loads(archive.read("Metadata/project_settings.config"))


def _entry(payload: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return archive.read(name)


def test_copy_rewrites_only_mapped_colour_lists() -> None:
    source = synthetic_3mf(["#111111", "#222222"])
    mesh = _entry(source, "3D/3dmodel.model")
    copied, record = build_scheme_copy(
        source,
        [
            {"plate_index": 1, "slot": 1, "hex": "#aabbcc"},
            {"plate_index": 2, "slot": 1, "hex": "#AABBCC"},
        ],
    )
    settings = _settings(copied)
    assert settings["filament_colour"] == ["#AABBCC", "#222222"]
    assert settings["default_filament_colour"] == ["#AABBCC", "#222222"]
    assert settings["filament_multi_colour"] == ["#AABBCC", "#222222"]
    assert settings["extruder_colour"] == ["#018001"]
    assert settings["note"] == "synthetic keep #FFFFFF"
    assert _entry(copied, "3D/3dmodel.model") == mesh
    note = json.loads(_entry(copied, "Metadata/filament_picker_scheme.json"))
    assert note["caveat"] == CAVEAT
    assert record["sha256"] == hashlib.sha256(copied).hexdigest()
    assert record["source_sha256"] == hashlib.sha256(source).hexdigest()
    assert "需要重新切片" in record["caveat"]
    assert b"filament-picker-synthetic" in mesh


def test_refuses_conflict_unknown_slot_and_unsafe_archives(monkeypatch: pytest.MonkeyPatch) -> None:
    source = synthetic_3mf(["#111111", "#222222"])
    with pytest.raises(SchemeCopyError, match="不一致"):
        build_scheme_copy(
            source,
            [
                {"slot": 1, "hex": "#112233"},
                {"slot": 1, "hex": "#AABBCC"},
            ],
        )
    with pytest.raises(SchemeCopyError, match="不在 filament_colour"):
        build_scheme_copy(source, [{"slot": 3, "hex": "#112233"}])
    with pytest.raises(SchemeCopyError, match="没有可写入"):
        build_scheme_copy(source, [])
    slipped = io.BytesIO()
    with zipfile.ZipFile(slipped, "w") as archive:
        archive.writestr("../evil.txt", b"nope")
        archive.writestr(
            "Metadata/project_settings.config",
            json.dumps({"filament_colour": ["#111111"]}),
        )
    with pytest.raises(SchemeCopyError, match="路径不安全"):
        build_scheme_copy(slipped.getvalue(), [{"slot": 1, "hex": "#112233"}])
    with pytest.raises(SchemeCopyError, match="不是 3MF"):
        build_scheme_copy(b"solid ascii", [{"slot": 1, "hex": "#112233"}])
    bare = io.BytesIO()
    with zipfile.ZipFile(bare, "w") as archive:
        archive.writestr("3D/3dmodel.model", b"<model/>")
    with pytest.raises(SchemeCopyError, match="没有 project_settings"):
        build_scheme_copy(bare.getvalue(), [{"slot": 1, "hex": "#112233"}])
    short = json.loads(_entry(source, "Metadata/project_settings.config"))
    short["default_filament_colour"] = ["#111111"]
    uneven = io.BytesIO()
    with zipfile.ZipFile(uneven, "w") as archive:
        archive.writestr("3D/3dmodel.model", _entry(source, "3D/3dmodel.model"))
        archive.writestr("Metadata/project_settings.config", json.dumps(short))
    with pytest.raises(SchemeCopyError, match="长度"):
        build_scheme_copy(uneven.getvalue(), [{"slot": 1, "hex": "#112233"}])
    monkeypatch.setattr("filament_picker.scheme_copy._MAX_ENTRY", 8)
    with pytest.raises(SchemeCopyError, match="过大"):
        build_scheme_copy(source, [{"slot": 1, "hex": "#112233"}])
    monkeypatch.undo()
    blank = json.loads(_entry(source, "Metadata/project_settings.config"))
    blank["default_filament_colour"] = ["", ""]
    blank["filament_multi_colour"] = ["nope", "nope"]
    mixed = io.BytesIO()
    with zipfile.ZipFile(mixed, "w") as archive:
        archive.writestr("3D/3dmodel.model", _entry(source, "3D/3dmodel.model"))
        archive.writestr("Metadata/project_settings.config", json.dumps(blank))
    with pytest.raises(SchemeCopyError, match="不是可靠的颜色列表"):
        build_scheme_copy(mixed.getvalue(), [{"slot": 1, "hex": "#112233"}])
    blank["filament_multi_colour"] = ["#111111", "#222222"]
    placeholder = io.BytesIO()
    with zipfile.ZipFile(placeholder, "w") as archive:
        archive.writestr("3D/3dmodel.model", _entry(source, "3D/3dmodel.model"))
        archive.writestr("Metadata/project_settings.config", json.dumps(blank))
    copied, record = build_scheme_copy(placeholder.getvalue(), [{"slot": 2, "hex": "#ABCDEF"}])
    settings = _settings(copied)
    assert settings["filament_colour"] == ["#111111", "#ABCDEF"]
    assert settings["default_filament_colour"] == ["", ""]
    assert settings["filament_multi_colour"][1] == "#ABCDEF"
    assert "default_filament_colour" in record["unchanged"]
    assert settings["extruder_colour"] == ["#018001"]


def test_scheme_copy_download_keeps_original_and_is_private(preview: tuple) -> None:
    app, password, models = preview
    cookie = _cookie(app, password)
    original = models / "originals" / "sample-01.3mf"
    original.parent.mkdir()
    payload = synthetic_3mf(["#111111", "#222222"])
    original.write_bytes(payload)
    anonymous = _request(app, "POST", "/api/models/sample-01/scheme-copy")
    assert anonymous.status_code == 401
    assert anonymous.headers.get("location") is None
    missing = _request(app, "POST", "/api/models/sample-01/scheme-copy", cookie)
    assert missing.status_code == 409
    assert missing.json()["detail"] == "还没有可写入的槽位颜色"
    assert not (models.parent / "auth" / "scheme-copies").exists()
    saved = _request(
        app,
        "PUT",
        "/api/models/sample-01/scheme",
        cookie,
        json={"slots": [{"plate_index": 1, "slot": 1, "hex": "#ABCDEF"}]},
    )
    assert saved.status_code == 200
    original.unlink()
    stl = models / "originals" / "sample-01.stl"
    stl.write_bytes(b"solid stl")
    rejected = _request(app, "POST", "/api/models/sample-01/scheme-copy", cookie)
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "只有 3MF 能另存配色副本"
    assert not (models / "originals").joinpath("sample-01.3mf").exists()
    stl.unlink()
    original.write_bytes(payload)
    created = _request(app, "POST", "/api/models/sample-01/scheme-copy", cookie)
    assert created.status_code == 200
    body = created.json()
    assert body["caveat"] == CAVEAT
    assert body["source_sha256"] == hashlib.sha256(payload).hexdigest()
    assert original.read_bytes() == payload
    stored = models.parent / "auth" / "scheme-copies" / USER / "sample-01" / body["filename"]
    assert stored.is_file()
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert hashlib.sha256(stored.read_bytes()).hexdigest() == body["sha256"]
    assert not (models.parent / "auth" / "scheme-copies" / "other-user").exists()
    downloaded = _request(app, "GET", "/api/models/sample-01/scheme-copy", cookie)
    assert downloaded.status_code == 200
    assert downloaded.headers["x-content-sha256"] == body["sha256"]
    assert "location" not in {key.lower() for key in downloaded.headers}
    assert hashlib.sha256(downloaded.content).hexdigest() == body["sha256"]
    assert "attachment" in downloaded.headers["content-disposition"]
    stranger = _request(app, "GET", "/api/models/sample-01/scheme-copy")
    assert stranger.status_code == 401
