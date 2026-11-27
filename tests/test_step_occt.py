"""STEP conversion through the distro OpenCASCADE draw executable.

tests/fixtures/synthetic-box.step is a 10x20x30 mm box written by occt-draw.
It is a synthetic test solid, not a user model and not the 22-plate original.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import shutil
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from filament_picker.auth import PREVIEW_USER_ENV, AuthStore
from filament_picker.model_samples import seed_samples
from filament_picker.server import build_server_app

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-box.step"
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


pytestmark = pytest.mark.skipif(
    shutil.which("occt-draw") is None,
    reason="本机没有 occt-draw。Ubuntu 24.04 的 freecad 包没有候选版本，snap 也不可用。",
)


def _open(preview: tuple, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FILAMENT_PICKER_SUBMISSIONS", "1")
    monkeypatch.setenv("FILAMENT_PICKER_STEP", "1")
    app, password, models = preview
    return app, _login(app, USER, password), models


def _upload(app, cookie: str, name: str, body: bytes):
    return _request(
        app,
        "POST",
        "/api/models/submissions",
        cookie,
        files={"file": (name, body, "application/step")},
    )


def test_synthetic_box_becomes_a_private_preview(
    preview: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, cookie, models = _open(preview, monkeypatch)
    response = _upload(app, cookie, "synthetic-box.step", FIXTURE.read_bytes())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready", body
    model_id = body["model_id"]
    stored = models / "accounts" / "preview-tester" / "originals" / f"{model_id}.step"
    assert stored.is_file()
    assert not (models / "originals" / f"{model_id}.step").exists()
    index = json.loads((models / "derived" / model_id / "index.json").read_text(encoding="utf-8"))
    assert index["triangles"] == 12
    assert (models / "derived" / model_id / "model.glb").is_file()
    detail = _request(app, "GET", f"/api/models/{model_id}", cookie)
    assert detail.status_code == 200
    assert detail.json()["mesh_derived"] is True
    registered = _request(
        app,
        "POST",
        "/api/models/register",
        json={"username": "step-member", "password": "long-enough-pw"},
    )
    assert registered.status_code == 200
    member = _login(app, "step-member", "long-enough-pw")
    assert _request(app, "GET", f"/api/models/{model_id}", member).status_code == 404


def test_corrupt_step_does_not_become_ready(
    preview: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, cookie, _models = _open(preview, monkeypatch)
    body = b"ISO-10303-21;\nDATA;\n#1=GARBAGE('not a solid');\nENDSEC;\nEND-ISO-10303-21;\n"
    response = _upload(app, cookie, "broken.step", body)
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "STL" in response.json()["error"]


def test_external_step_reference_is_not_fetched(
    preview: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, cookie, _models = _open(preview, monkeypatch)
    body = b"ISO-10303-21;\nHEADER;\nFILE_NAME('https://example.invalid/evil.step','');\nENDSEC;\n"
    response = _upload(app, cookie, "remote.step", body)
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "STEP 含有外部地址，不会自动抓取"


def test_step_converter_timeout_kills_the_process(
    preview: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, cookie, _models = _open(preview, monkeypatch)
    monkeypatch.setenv("FILAMENT_PICKER_STEP_TIMEOUT", "0.01")
    response = _upload(app, cookie, "synthetic-box.step", FIXTURE.read_bytes())
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "超时" in response.json()["error"]


def test_step_output_size_limit_rejects_the_mesh(
    preview: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, cookie, models = _open(preview, monkeypatch)
    monkeypatch.setenv("FILAMENT_PICKER_STEP_FSIZE", "80")
    response = _upload(app, cookie, "synthetic-box.step", FIXTURE.read_bytes())
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert not list((models / "accounts" / ".step-out").glob("*.stl"))
