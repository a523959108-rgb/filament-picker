import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filament_picker.cli import main


@pytest.fixture
def example_catalog(repo_root: Path, tmp_path: Path) -> Path:
    path = tmp_path / "filament-catalog.json"
    shutil.copy(repo_root / "docs/schemas/examples/filament-catalog.example.json", path)
    return path


@pytest.fixture
def dist(repo_root: Path, tmp_path: Path) -> Path:
    path = tmp_path / "dist"
    path.mkdir()
    (path / "index.html").write_text('<div id="root"></div>\n', encoding="utf-8")
    shutil.copy(repo_root / "docs/fixtures/web-catalog.sample.json", path / "web-catalog.json")
    return path


def test_static_files_and_api(dist: Path, example_catalog: Path, tmp_path: Path) -> None:
    from filament_picker.server import build_server_app

    with TestClient(build_server_app(dist, example_catalog, tmp_path, None)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert '<div id="root">' in page.text
        assert page.headers["content-type"].startswith("text/html")

        catalog = client.get("/web-catalog.json")
        assert catalog.status_code == 200
        assert len(catalog.json()["entries"]) == 4

        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True


def test_card_path_traversal(dist: Path, example_catalog: Path, tmp_path: Path) -> None:
    from filament_picker.server import build_server_app

    with TestClient(build_server_app(dist, example_catalog, tmp_path, None)) as client:
        assert client.get("/api/cards/../x").status_code == 404


@pytest.mark.parametrize("empty_dist", [False, True])
def test_missing_dist_or_index(example_catalog: Path, tmp_path: Path, empty_dist: bool) -> None:
    from filament_picker.server import build_server_app

    path = tmp_path / "missing-dist"
    if empty_dist:
        path.mkdir()
    with pytest.raises(RuntimeError, match=r"build_web\.sh"):
        build_server_app(path, example_catalog, tmp_path, None)


def test_serve_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["serve", "--help"])
    assert exc_info.value.code == 0
    assert "--port" in capsys.readouterr().out
