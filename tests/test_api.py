from __future__ import annotations

import shutil
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filament_picker.api import MAX_UPLOAD_BYTES, create_app
from filament_picker.validate import validate_json


@pytest.fixture
def example_catalog(repo_root: Path, tmp_path: Path) -> Path:
    path = tmp_path / "filament-catalog.json"
    shutil.copy(repo_root / "docs/schemas/examples/filament-catalog.example.json", path)
    return path


def _png_bytes(color: str = "#000000") -> bytes:
    from PIL import Image

    image = Image.new("RGB", (200, 200), "#FFFFFF")
    image.paste(color, (40, 40, 160, 160))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_health(example_catalog: Path, tmp_path: Path) -> None:
    client = TestClient(create_app(example_catalog, tmp_path))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "catalog_generated_at": "2026-11-05T12:00:00+09:00",
    }


def test_plan_upload_and_card_download(example_catalog: Path, tmp_path: Path) -> None:
    client = TestClient(create_app(example_catalog, tmp_path))
    response = client.post(
        "/api/plan",
        files={"file": ("black.png", _png_bytes(), "image/png")},
        data={"constraints": '{"materials":["PETG"]}'},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ok"
    assert validate_json("result", result) == []
    assert result["matches"][0]["picks"][0]["id"] == "bambu-lab/petg-basic/black-30105"
    assert Path(result["card_path"]).is_file()
    inbox = list((tmp_path / "inbox").glob("web-*.png"))
    assert len(inbox) == 1

    card_path = Path(result["card_path"])
    downloaded = client.get(f"/api/cards/{card_path.name}")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "image/png"
    assert downloaded.content == card_path.read_bytes()


def test_upload_size_limits(example_catalog: Path, tmp_path: Path) -> None:
    client = TestClient(create_app(example_catalog, tmp_path))
    too_large = client.post(
        "/api/plan",
        files={"file": ("large.bin", b"x" * (MAX_UPLOAD_BYTES + 1), "application/octet-stream")},
    )
    assert too_large.status_code == 413
    assert too_large.json() == {"detail": "图片超过 10MB"}

    exact = client.post(
        "/api/plan",
        files={"file": ("exact.bin", b"x" * MAX_UPLOAD_BYTES, "application/octet-stream")},
    )
    assert exact.status_code == 200
    assert exact.json()["status"] == "error"
    assert exact.json()["error"]["code"] == "IMAGE_UNREADABLE"
    assert validate_json("result", exact.json()) == []


def test_invalid_constraints(example_catalog: Path, tmp_path: Path) -> None:
    client = TestClient(create_app(example_catalog, tmp_path))
    response = client.post(
        "/api/plan",
        files={"file": ("black.png", _png_bytes(), "image/png")},
        data={"constraints": "not json"},
    )
    assert response.status_code == 200
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_card_name_validation(example_catalog: Path, tmp_path: Path) -> None:
    client = TestClient(create_app(example_catalog, tmp_path))
    for name in ("../x", "EXAMPLE_TOKEN.png", "a" * 32 + ".png"):
        assert client.get(f"/api/cards/{name}").status_code == 404


@pytest.mark.data
def test_green_upload_real_catalog(repo_root: Path, tmp_path: Path) -> None:
    catalog_path = repo_root / "data/build/filament-catalog.json"
    if not catalog_path.exists():
        pytest.skip("T08 真实目录未就绪")
    from helpers_images import square_on_white

    image = square_on_white(tmp_path / "green.png")
    client = TestClient(create_app(catalog_path, tmp_path))
    response = client.post(
        "/api/plan",
        files={"file": ("green.png", image.read_bytes(), "image/png")},
        data={"note": "1色 只要拓竹 PLA"},
    )
    assert response.status_code == 200
    assert response.json()["matches"][0]["picks"][0]["id"] == (
        "bambu-lab/pla-basic/bambu-green-10501"
    )
