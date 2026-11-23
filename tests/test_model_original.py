from __future__ import annotations

import asyncio
import hashlib
import io
import json
import secrets
import struct
import zipfile
from pathlib import Path

import httpx
import pytest
from PIL import Image

from filament_picker.auth import PREVIEW_USER_ENV, AuthStore
from filament_picker.cli import main
from filament_picker.model_import import import_previews
from filament_picker.server import build_server_app

GOOD = "c100000000000001"
BAD_SIZE = "c100000000000002"
ESCAPE = "c100000000000003"
LINKED = "c100000000000004"
MISSING = "c100000000000005"
INVALID = "c100000000000006"
SETTINGS = {
    "filament_colour": ["#FFFFFF", "#FFFFFF", "#F73CA0"],
    "filament_type": ["PLA", "PETG", "PLA"],
    "plate_names": ["眼白", "未命名"],
}


def _request(app, method: str, path: str, cookie: str = "", **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.request(method, path, headers={"cookie": cookie}, **kwargs)

    return asyncio.run(send())


def _3mf() -> bytes:
    model = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="1" type="model">
      <mesh><vertices><vertex x="0" y="0" z="0"/></vertices><triangles/></mesh>
    </object>
    <object id="2" type="model">
      <mesh><vertices><vertex x="1" y="0" z="0"/></vertices><triangles/></mesh>
    </object>
  </resources>
  <build><item objectid="1"/><item objectid="2"/></build>
</model>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("3D/3dmodel.model", model)
        archive.writestr("Metadata/project_settings.config", json.dumps(SETTINGS))
    return buffer.getvalue()


def _stl() -> bytes:
    header = b"\0" * 80
    triangle = struct.pack("<12fH", 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)
    return header + struct.pack("<I", 1) + triangle


def _image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 3), "#336699").save(path, format="JPEG")


def _row(model_id: str, rel_path: str, size: int, plates: list[dict]) -> dict:
    return {
        "id": model_id,
        "rel_path": rel_path,
        "file_name": Path(rel_path).name,
        "size_bytes": size,
        "mtime": 1_700_000_000,
        "title": "多盘彩色",
        "designer": "测试作者",
        "source": {
            "description": "原件说明",
            "design_model_id": model_id,
            "design_profile_id": "profile-1",
        },
        "colors": [],
        "plates": len(plates),
        "ok": True,
        "errors": [],
    }


def _stage(directory: Path, model_id: str, rel_path: str, size: int, plates: list[dict]) -> None:
    dest = directory / "models" / model_id
    dest.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": model_id,
        "title": "多盘彩色",
        "designer": "测试作者",
        "source": {
            "description": "原件说明",
            "design_model_id": model_id,
            "design_profile_id": "profile-1",
        },
        "plates": plates,
        "extracted_at": "2026-11-07T00:00:00+00:00",
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _image(dest / "thumb_1.jpg")
    (dest / "ignored.3mf").write_bytes(b"not-a-website-file")


def _plates() -> list[dict]:
    return [
        {
            "index": 1,
            "name": "眼白",
            "objects": ["body.stl", "eye.stl"],
            "filaments": [
                {
                    "slot": 3,
                    "hex": "#FFFFFF",
                    "type": "PLA",
                    "vendor": "Bambu Lab",
                    "settings_id": "PLA Basic",
                    "used_g": None,
                },
                {
                    "slot": 7,
                    "hex": "#ffffff",
                    "type": "PETG",
                    "vendor": "Bambu Lab",
                    "settings_id": "PETG Basic",
                    "used_g": 12.5,
                },
            ],
        },
        {
            "index": 2,
            "name": None,
            "objects": [],
            "filaments": [
                {"slot": 1, "hex": "not-a-color", "type": "PLA", "vendor": "", "settings_id": ""}
            ],
        },
    ]


def _library(tmp_path: Path, data: bytes) -> tuple[Path, Path, Path]:
    directory = tmp_path / "incoming"
    library = tmp_path / "library"
    secret = tmp_path / "secret.3mf"
    secret.write_bytes(data)
    plates = _plates()
    rows = []
    specs = [
        (GOOD, "彩色/多盘示例.3mf", len(data), data),
        (BAD_SIZE, "彩色/尺寸不符.3mf", 1, data),
        (ESCAPE, "../secret.3mf", len(data), None),
        (LINKED, "彩色/链接.3mf", len(data), None),
        (MISSING, "彩色/缺失.3mf", len(data), None),
        (INVALID, "彩色/坏档.3mf", 11, b"not-a-3mf!!"),
    ]
    for model_id, rel_path, size, payload in specs:
        _stage(directory, model_id, rel_path, size, plates)
        rows.append(_row(model_id, rel_path, size, plates))
        if payload is None or rel_path.startswith(".."):
            continue
        target = library / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    link = library / "彩色" / "链接.3mf"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(library / "彩色" / "多盘示例.3mf")
    (directory / "index.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    return directory, library, secret


def _serve(
    tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch, root: Path, direct: str
):
    db = tmp_path / "auth" / "users.sqlite"
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_ROOT", str(root))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECURE", "0")
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_DIRECT", direct)
    password = secrets.token_urlsafe(24)
    monkeypatch.setenv(PREVIEW_USER_ENV, "preview-tester")
    AuthStore(db).create_user("preview-tester", password)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>\n', encoding="utf-8")
    app = build_server_app(
        dist, repo_root / "docs/schemas/examples/filament-catalog.example.json", tmp_path, None
    )
    login = _request(
        app, "POST", "/api/models/login", json={"username": "preview-tester", "password": password}
    )
    return app, login.headers["set-cookie"].split(";", 1)[0]


def _parse(text: str) -> dict[str, int]:
    return {key: int(value) for key, value in (part.split("=") for part in text.split())}


def test_library_copy_is_byte_identical_and_reopens_multicolor_3mf(
    tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _3mf()
    directory, library, secret = _library(tmp_path, data)
    root = tmp_path / "models-private"
    source = library / "彩色" / "多盘示例.3mf"
    dry = import_previews(directory, root, dry_run=True, library=library)
    assert _parse(dry.format())["originals"] == 1
    assert _parse(dry.format())["originals_skipped"] == 5
    assert _parse(dry.format())["dry_run"] == 1
    assert not root.exists()
    assert source.read_bytes() == data
    imported = import_previews(directory, root, library=library)
    parsed = _parse(imported.format())
    assert parsed["originals"] == 1
    assert parsed["originals_skipped"] == 5
    assert source.read_bytes() == data
    assert secret.read_bytes() == data
    assert (library / "彩色" / "尺寸不符.3mf").read_bytes() == data
    assert list(root.rglob("ignored.3mf")) == []
    stored = root / "originals" / f"{GOOD}.3mf"
    assert stored.read_bytes() == data
    assert not (root / "originals" / f"{BAD_SIZE}.3mf").exists()
    assert not (root / "originals" / f"{ESCAPE}.3mf").exists()
    assert not (root / "originals" / f"{LINKED}.3mf").exists()
    assert not (root / "originals" / f"{INVALID}.3mf").exists()
    app, cookie = _serve(tmp_path, repo_root, monkeypatch, root, "1")
    detail = _request(app, "GET", f"/api/models/{GOOD}", cookie).json()
    filaments = detail["plates"][0]["filaments"]
    assert [item["slot"] for item in filaments] == [3, 7]
    assert [item["hex"] for item in filaments] == ["#FFFFFF", "#FFFFFF"]
    assert filaments[0]["type"] == "PLA"
    assert filaments[1]["type"] == "PETG"
    assert filaments[1]["used_g"] == 12.5
    assert detail["plates"][0]["objects"] == ["body.stl", "eye.stl"]
    assert detail["plates"][1]["name"] is None
    assert detail["plates"][1]["objects"] == []
    assert detail["plates"][1]["filaments"][0]["hex"] is None
    assert detail["plates"][1]["filaments"][0]["slot"] == 1
    assert detail["colours"] == ["#FFFFFF"]
    original = detail["original"]
    assert original["available"] is True
    assert original["filename"] == "多盘示例.3mf"
    assert original["size_bytes"] == len(data)
    assert original["sha256"] == hashlib.sha256(data).hexdigest()
    assert original["media_type"] == "model/3mf"
    assert original["url"] == f"/api/models/{GOOD}/original"
    assert "彩色/" not in json.dumps(detail, ensure_ascii=False)
    assert _request(app, "GET", original["url"]).status_code == 401
    downloaded = _request(app, "GET", original["url"], cookie)
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("model/3mf")
    disposition = downloaded.headers["content-disposition"]
    assert disposition == "attachment; filename*=utf-8''" + quote_name("多盘示例.3mf")
    assert downloaded.headers["x-content-sha256"] == original["sha256"]
    assert downloaded.content == data
    assert hashlib.sha256(downloaded.content).hexdigest() == original["sha256"]
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        opened = json.loads(archive.read("Metadata/project_settings.config"))
        mesh = archive.read("3D/3dmodel.model")
    assert opened["filament_colour"] == ["#FFFFFF", "#FFFFFF", "#F73CA0"]
    assert b'object id="1"' in mesh
    assert b'object id="2"' in mesh
    assert b"glTF" not in downloaded.content


def test_upload_preserves_bytes_and_reimport_does_not_drop_them(
    tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _3mf()
    stl = _stl()
    directory, library, _secret = _library(tmp_path, data)
    root = tmp_path / "models-private"
    import_previews(directory, root, library=library)
    app, cookie = _serve(tmp_path, repo_root, monkeypatch, root, "1")
    rejected = _request(
        app,
        "POST",
        f"/api/models/{MISSING}/original",
        cookie,
        files={"file": ("preview.png", b"\x89PNG\r\n", "image/png")},
    )
    assert rejected.status_code == 415
    assert rejected.json()["detail"] == "只接受 3MF 或 STL 原件"
    bogus = _request(
        app,
        "POST",
        f"/api/models/{MISSING}/original",
        cookie,
        files={"file": ("broken.3mf", b"not-a-zip", "application/octet-stream")},
    )
    assert bogus.status_code == 400
    assert "可重新打开" in bogus.json()["detail"]
    assert not (root / "originals" / f"{MISSING}.3mf").exists()
    uploaded = _request(
        app,
        "POST",
        f"/api/models/{MISSING}/original",
        cookie,
        files={"file": ("../../evil.3mf", data, "application/octet-stream")},
    )
    assert uploaded.status_code == 200
    info = uploaded.json()
    assert info["filename"] == "evil.3mf"
    assert info["sha256"] == hashlib.sha256(data).hexdigest()
    assert "../" not in json.dumps(info)
    saved = _request(app, "GET", info["url"], cookie)
    assert saved.content == data
    assert 'filename="evil.3mf"' in saved.headers["content-disposition"]
    again = _parse(import_previews(directory, root).format())
    assert again["unchanged"] == 6
    assert _request(app, "GET", info["url"], cookie).content == data
    replaced = _request(
        app,
        "POST",
        f"/api/models/{MISSING}/original",
        cookie,
        files={"file": ("零件.stl", stl, "model/stl")},
    )
    assert replaced.status_code == 200
    assert replaced.json()["media_type"] == "model/stl"
    assert not (root / "originals" / f"{MISSING}.3mf").exists()
    stl_response = _request(app, "GET", replaced.json()["url"], cookie)
    assert stl_response.content == stl
    assert stl_response.headers["content-type"].startswith("model/stl")
    assert "filename*=utf-8''" in stl_response.headers["content-disposition"]
    assert quote_name("零件.stl") in stl_response.headers["content-disposition"]
    count = struct.unpack_from("<I", stl_response.content, 80)[0]
    assert count == 1
    assert len(stl_response.content) == 84 + 50
    monkeypatch.setattr("filament_picker.models.ORIGINAL_MAX_BYTES", 8)
    huge = _request(
        app,
        "POST",
        f"/api/models/{BAD_SIZE}/original",
        cookie,
        files={"file": ("too-big.3mf", data, "application/octet-stream")},
    )
    assert huge.status_code == 413
    assert not (root / "originals" / f"{BAD_SIZE}.3mf").exists()


def test_original_accel_redirect_stays_private(
    tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _3mf()
    directory, library, _secret = _library(tmp_path, data)
    root = tmp_path / "models-private"
    import_previews(directory, root, library=library)
    app, cookie = _serve(tmp_path, repo_root, monkeypatch, root, "0")
    response = _request(app, "GET", f"/api/models/{GOOD}/original", cookie)
    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["x-accel-redirect"] == f"/internal-models/originals/{GOOD}.3mf"
    assert response.headers["content-type"].startswith("model/3mf")
    assert response.headers["x-content-sha256"] == hashlib.sha256(data).hexdigest()
    assert str(root) not in str(response.headers)
    assert _request(app, "GET", "/internal-models/originals/" + f"{GOOD}.3mf").status_code == 404


def test_cli_library_import_does_not_modify_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _3mf()
    directory, library, _secret = _library(tmp_path, data)
    root = tmp_path / "models-private"
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_ROOT", str(root))
    source = library / "彩色" / "多盘示例.3mf"
    assert (
        main(
            [
                "models",
                "import-previews",
                str(directory),
                "--library",
                str(library),
            ]
        )
        == 0
    )
    parsed = _parse(capsys.readouterr().out.strip())
    assert parsed["originals"] == 1
    assert source.read_bytes() == data
    assert (root / "originals" / f"{GOOD}.3mf").read_bytes() == data


def quote_name(name: str) -> str:
    from urllib.parse import quote

    return quote(name)
