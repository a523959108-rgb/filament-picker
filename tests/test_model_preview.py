from __future__ import annotations

import asyncio
import secrets
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from filament_picker.auth import PREVIEW_USER_ENV, AuthStore
from filament_picker.cli import main
from filament_picker.mesh_glb import sample_glb_bytes
from filament_picker.model_samples import seed_samples
from filament_picker.server import build_server_app

PREVIEW_TEST_USER = "preview-tester"


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
        app, "POST", "/api/models/login", json={"username": PREVIEW_TEST_USER, "password": password}
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/models"),
        ("GET", "/api/models?page=bad"),
        ("GET", "/api/models/sample-01"),
        ("GET", "/api/models/missing"),
        ("GET", "/api/models/sample-01/thumb"),
        ("GET", "/api/models/sample-01/glb"),
        ("GET", "/api/models/me"),
        ("POST", "/api/models/logout"),
    ],
)
def test_models_require_auth_without_enumeration(preview: tuple, method: str, path: str) -> None:
    app, *_ = preview
    response = _request(app, method, path)
    assert response.status_code == 401
    assert response.json() == {"detail": "需要登录"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    for public_path in ("/", "/api/health", "/web-catalog.json"):
        assert _request(app, "GET", public_path).status_code == 200


def test_page_gates_robots_and_private_paths(preview: tuple) -> None:
    app, *_ = preview
    for path in ("/models", "/models/", "/models/sample-01", "/models/missing"):
        response = _request(app, "GET", path)
        assert response.status_code == 302
        assert response.headers["location"] == "/models/login"
        assert "sample-01" not in response.text
    assert _request(app, "GET", "/models/login").status_code == 200
    assert _request(app, "GET", "/internal-models/thumbs/sample-01.png").status_code == 404
    assert _request(app, "GET", "/data/models-private/manifest.sqlite").status_code == 404
    robots = _request(app, "GET", "/robots.txt")
    assert "Disallow: /models" in robots.text
    assert "Disallow: /api/models" in robots.text
    assert "Disallow: /internal-models" in robots.text


def test_login_throttle_and_recovery(preview: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    app, password, *_ = preview
    ticks = [100.0]
    monkeypatch.setattr("filament_picker.auth.monotonic", lambda: ticks[0])
    wrong = secrets.token_urlsafe(24)
    for _ in range(5):
        assert _login(app, wrong).status_code == 401
    locked = _login(app, password)
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0
    ticks[0] += 61
    assert _login(app, password).status_code == 200
    assert _login(app, wrong).status_code == 401
    assert _login(app, password).status_code == 200


def test_login_browse_filter_logout_and_cookie_replay(preview: tuple) -> None:
    app, password, *_ = preview
    login = _login(app, password)
    assert login.status_code == 200
    cookie = login.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert "Max-Age=604800" in cookie
    cookie = cookie.split(";", 1)[0]
    assert _request(app, "GET", "/api/models/me", cookie).json() == {"username": PREVIEW_TEST_USER}
    listing = _request(app, "GET", "/api/models?page_size=2", cookie)
    assert listing.status_code == 200
    result = listing.json()
    assert result["total"] == 8
    assert len(result["items"]) == 2
    assert result["page"] == 1 and result["page_size"] == 2
    first = result["items"][0]
    second = _request(app, "GET", "/api/models?page=2&page_size=2", cookie).json()
    assert second["items"][0]["id"] != first["id"]
    filtered = _request(
        app,
        "GET",
        "/api/models",
        cookie,
        params={"q": first["title"], "series": first["series"], "author": first["author"]},
    ).json()
    assert filtered["total"] == 1
    assert len(result["series"]) >= 2 and len(result["authors"]) >= 2
    assert _request(app, "GET", "/api/models?q=%25", cookie).json()["total"] == 0
    detail = _request(app, "GET", f"/api/models/{first['id']}", cookie)
    assert detail.status_code == 200
    assert detail.json()["colours"]
    assert "source_relpath" not in detail.json()
    assert _request(app, "GET", f"/models/{first['id']}", cookie).status_code == 200
    for query in ("page=0", "page_size=0", "page_size=101", "page=bad"):
        assert _request(app, "GET", f"/api/models?{query}", cookie).status_code == 422
    assert _request(app, "GET", "/api/models/missing", cookie).status_code == 404
    logout = _request(app, "POST", "/api/models/logout", cookie)
    assert logout.status_code == 200
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert _request(app, "GET", "/api/models", cookie).status_code == 401
    assert _request(app, "GET", first["thumb_url"], cookie).status_code == 401


@pytest.mark.parametrize("direct", [True, False])
def test_thumbnails_in_both_modes(
    preview: tuple, repo_root: Path, monkeypatch: pytest.MonkeyPatch, direct: bool
) -> None:
    _, password, models, _ = preview
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_DIRECT", "1" if direct else "0")
    app = build_server_app(
        models.parent / "dist",
        repo_root / "docs/schemas/examples/filament-catalog.example.json",
        models.parent,
        None,
    )
    assert app.state.model_preview.direct is direct
    cookie = _login(app, password).headers["set-cookie"].split(";", 1)[0]
    response = _request(app, "GET", "/api/models/sample-01/thumb", cookie)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    assert response.headers["cache-control"] == "no-store"
    if direct:
        assert response.content == (models / "thumbs/sample-01.png").read_bytes()
    else:
        assert response.headers["x-accel-redirect"] == "/internal-models/thumbs/sample-01.png"
        assert response.content == b""
        assert str(models) not in str(response.headers)


@pytest.mark.parametrize("thumb_path", ["../outside.png", "/outside.png", "manifest.sqlite"])
def test_manifest_cannot_escape_thumbnail_directory(preview: tuple, thumb_path: str) -> None:
    app, password, models, _ = preview
    with sqlite3.connect(models / "manifest.sqlite") as conn:
        conn.execute("UPDATE models SET thumb_path = ? WHERE id = 'sample-01'", (thumb_path,))
    cookie = _login(app, password).headers["set-cookie"].split(";", 1)[0]
    assert _request(app, "GET", "/api/models/sample-01/thumb", cookie).status_code == 404


@pytest.mark.parametrize("direct", [True, False])
def test_authenticated_glb_stays_inside_meshes(
    preview: tuple, repo_root: Path, monkeypatch: pytest.MonkeyPatch, direct: bool
) -> None:
    _, password, models, _ = preview
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_DIRECT", "1" if direct else "0")
    app = build_server_app(
        models.parent / "dist",
        repo_root / "docs/schemas/examples/filament-catalog.example.json",
        models.parent,
        None,
    )
    cookie = _login(app, password).headers["set-cookie"].split(";", 1)[0]
    anonymous = _request(app, "GET", "/api/models/sample-01/glb")
    assert anonymous.status_code == 401
    assert anonymous.json() == {"detail": "需要登录"}
    assert b"glTF" not in anonymous.content
    payload = sample_glb_bytes()
    assert (models / "meshes" / "sample-01.glb").read_bytes() == payload
    response = _request(app, "GET", "/api/models/sample-01/glb", cookie)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("model/gltf-binary")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert str(models) not in str(response.headers)
    assert str(models).encode() not in response.content
    detail = _request(app, "GET", "/api/models/sample-01", cookie)
    body = detail.json()
    assert body["mesh_url"] == "/api/models/sample-01/glb"
    assert "source_relpath" not in body and "thumb_path" not in body
    assert "synthetic/" not in detail.text
    assert str(models) not in detail.text
    plain = _request(app, "GET", "/api/models/sample-02", cookie).json()
    assert plain["mesh_url"] is None
    missing = _request(app, "GET", "/api/models/sample-02/glb", cookie)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "网格不存在"
    assert b"glTF" not in missing.content
    if direct:
        assert response.content == payload
        assert "x-accel-redirect" not in response.headers
    else:
        assert response.content == b""
        assert response.headers["x-accel-redirect"] == "/internal-models/meshes/sample-01.glb"


def test_mesh_rejects_symlink_directory_escape_and_unknown_ids(
    preview: tuple, tmp_path: Path
) -> None:
    app, password, models, _ = preview
    cookie = _login(app, password).headers["set-cookie"].split(";", 1)[0]
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "sample-01.glb"
    secret.write_bytes(b"glTFsecret-mesh")
    mesh = models / "meshes" / "sample-01.glb"
    mesh.unlink()
    mesh.symlink_to(secret)
    escaped = _request(app, "GET", "/api/models/sample-01/glb", cookie)
    assert escaped.status_code == 404
    assert b"secret-mesh" not in escaped.content
    mesh.unlink()
    mesh_dir = models / "meshes"
    mesh_dir.rmdir()
    mesh_dir.symlink_to(outside, target_is_directory=True)
    via_dir = _request(app, "GET", "/api/models/sample-01/glb", cookie)
    assert via_dir.status_code == 404
    assert b"secret-mesh" not in via_dir.content
    (models / "meshes").unlink()
    (models / "meshes").mkdir()
    (models / "meshes" / "missing.glb").write_bytes(sample_glb_bytes())
    unknown = _request(app, "GET", "/api/models/missing/glb", cookie)
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "模型不存在"
    assert unknown.headers["content-type"].startswith("application/json")
    assert b"glTF" not in unknown.content


def test_symlink_thumbnail_escape_is_blocked(preview: tuple, tmp_path: Path) -> None:
    app, password, models, _ = preview
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"private")
    thumb = models / "thumbs/sample-01.png"
    thumb.unlink()
    thumb.symlink_to(outside)
    cookie = _login(app, password).headers["set-cookie"].split(";", 1)[0]
    assert _request(app, "GET", "/api/models/sample-01/thumb", cookie).status_code == 404


def test_invalid_expired_sessions_and_unconfigured_secret(
    preview: tuple, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, password, models, db = preview
    cookie = _login(app, password).headers["set-cookie"].split(";", 1)[0]
    assert _request(app, "GET", "/api/models", cookie + "tampered").status_code == 401
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET expires_at = 0")
    assert _request(app, "GET", "/api/models", cookie).status_code == 401
    monkeypatch.delenv("FILAMENT_PICKER_SESSION_SECRET")
    app = build_server_app(
        models.parent / "dist",
        repo_root / "docs/schemas/examples/filament-catalog.example.json",
        models.parent,
        None,
    )
    assert _login(app, password).status_code == 503
    assert _request(app, "GET", "/api/health").status_code == 200


def test_secure_cookie_and_configurable_signed_session_expiry(
    preview: tuple, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    _, password, models, _ = preview
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECURE", "1")
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_TTL", "37")
    app = build_server_app(
        models.parent / "dist",
        repo_root / "docs/schemas/examples/filament-catalog.example.json",
        models.parent,
        None,
    )
    response = _login(app, password)
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie and "Max-Age=37" in cookie
    cookie = cookie.split(";", 1)[0]
    assert _request(app, "GET", "/api/models/me", cookie).status_code == 200
    future = int(time.time()) + 38
    monkeypatch.setattr("itsdangerous.TimestampSigner.get_timestamp", lambda _: future)
    assert _request(app, "GET", "/api/models/me", cookie).status_code == 401


def test_invalid_login_body_does_not_echo_credentials(preview: tuple) -> None:
    app, *_ = preview
    password = secrets.token_urlsafe(24)
    response = _request(app, "POST", "/api/models/login", json={"password": password})
    assert response.status_code == 400
    assert password not in response.text
    assert _request(app, "POST", "/api/models/login", content=b"not-json").status_code == 400


def test_missing_manifest_returns_empty_gallery(preview: tuple) -> None:
    app, password, models, _ = preview
    (models / "manifest.sqlite").unlink()
    cookie = _login(app, password).headers["set-cookie"].split(";", 1)[0]
    response = _request(app, "GET", "/api/models", cookie)
    assert response.status_code == 200
    assert response.json()["items"] == [] and response.json()["total"] == 0
    assert _request(app, "GET", "/api/models/sample-01/thumb", cookie).status_code == 404


def test_create_user_cli_hash_permissions_and_single_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "auth" / "users.sqlite"
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv(PREVIEW_USER_ENV, PREVIEW_TEST_USER)
    password = secrets.token_urlsafe(24)
    prompts = []

    def enter(prompt: str) -> str:
        prompts.append(prompt)
        return password

    monkeypatch.setattr("filament_picker.cli.getpass.getpass", enter)
    assert main(["auth", "create-user", "--username", PREVIEW_TEST_USER]) == 0
    assert len(prompts) == 2
    with sqlite3.connect(db) as conn:
        username, hashed = conn.execute("SELECT username, password_hash FROM users").fetchone()
    assert username == PREVIEW_TEST_USER and hashed.startswith("$argon2id$")
    assert password not in hashed
    assert db.stat().st_mode & 0o777 == 0o600
    assert main(["auth", "list-users"]) == 0
    assert main(["auth", "create-user", "--username", "other"]) == 1
    output = capsys.readouterr().out
    assert password not in output and "$argon2" not in output
    with pytest.raises(SystemExit):
        main(["auth", "create-user", "--username", PREVIEW_TEST_USER, "--password"])


def test_create_user_rejects_mismatch_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "users.sqlite"
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv(PREVIEW_USER_ENV, PREVIEW_TEST_USER)
    passwords = iter([secrets.token_urlsafe(24), secrets.token_urlsafe(24)])
    monkeypatch.setattr("filament_picker.cli.getpass.getpass", lambda _: next(passwords))
    assert main(["auth", "create-user", "--username", PREVIEW_TEST_USER]) == 1
    assert not db.exists()


def test_create_user_refuses_getpass_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import getpass
    import warnings

    db = tmp_path / "users.sqlite"
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv(PREVIEW_USER_ENV, PREVIEW_TEST_USER)

    def no_tty(prompt: str) -> str:
        warnings.warn("cannot hide input", getpass.GetPassWarning, stacklevel=2)
        raise AssertionError("getpass fallback must stop before reading")

    monkeypatch.setattr("filament_picker.cli.getpass.getpass", no_tty)
    assert main(["auth", "create-user", "--username", PREVIEW_TEST_USER]) == 1
    assert not db.exists()


def test_unconfigured_preview_user_rejects_login_and_logs(
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from fastapi.testclient import TestClient

    monkeypatch.delenv(PREVIEW_USER_ENV, raising=False)
    db = tmp_path / "auth" / "users.sqlite"
    with pytest.raises(ValueError, match=PREVIEW_USER_ENV):
        AuthStore(db).create_user(PREVIEW_TEST_USER, "not-used")
    monkeypatch.setenv(PREVIEW_USER_ENV, "change-me-preview-user")
    with pytest.raises(ValueError, match=PREVIEW_USER_ENV):
        AuthStore(db).create_user(PREVIEW_TEST_USER, "not-used")
    monkeypatch.delenv(PREVIEW_USER_ENV, raising=False)
    assert main(["auth", "create-user", "--username", PREVIEW_TEST_USER]) == 1
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>\n', encoding="utf-8")
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECRET", secrets.token_urlsafe(48))
    with (
        caplog.at_level(logging.WARNING, logger="filament_picker.auth"),
        TestClient(
            build_server_app(
                dist,
                repo_root / "docs/schemas/examples/filament-catalog.example.json",
                tmp_path,
                None,
            )
        ) as client,
    ):
        response = client.post(
            "/api/models/login",
            json={"username": PREVIEW_TEST_USER, "password": "nope"},
        )
    assert response.status_code == 503
    assert PREVIEW_USER_ENV in response.text
    assert PREVIEW_TEST_USER not in response.text
    assert "拒绝所有登录" in caplog.text


def test_seed_is_synthetic_repeatable_and_does_not_overwrite_real_manifest(tmp_path: Path) -> None:
    models = tmp_path / "models-private"
    assert seed_samples(models) == 8
    mesh = models / "meshes" / "sample-01.glb"
    assert mesh.read_bytes()[:4] == b"glTF"
    stamped = mesh.read_bytes()
    assert seed_samples(models) == 8
    assert mesh.read_bytes() == stamped
    with sqlite3.connect(models / "manifest.sqlite") as conn:
        rows = conn.execute("SELECT * FROM models").fetchall()
        assert len(rows) == 8
        conn.execute("UPDATE models SET title = 'private record' WHERE id = 'sample-01'")
    assert len(list((models / "thumbs").glob("*.png"))) == 8
    assert not list(models.rglob("*.3mf"))
    with pytest.raises(ValueError, match="sample"):
        seed_samples(models)


def test_seed_refuses_foreign_manifest_without_writing_a_mesh(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    with sqlite3.connect(root / "manifest.sqlite") as conn:
        conn.execute(
            "CREATE TABLE models (id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, "
            "title TEXT NOT NULL, series TEXT NOT NULL, author TEXT NOT NULL, "
            "source_relpath TEXT NOT NULL, size_bytes INTEGER NOT NULL, "
            "plate_count INTEGER NOT NULL, colours TEXT NOT NULL, thumb_path TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO models VALUES ("
            "'real', 'abc', '真实模型', '', '', 'secret/path.3mf', 1, 1, '[]', "
            "'thumbs/real.png', '2026-01-01T00:00:00+09:00')"
        )
    with pytest.raises(ValueError, match="sample"):
        seed_samples(root)
    assert not (root / "meshes").exists()
    assert list(root.rglob("*.glb")) == []
    assert list(root.rglob("*.3mf")) == []
