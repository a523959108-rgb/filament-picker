"""Spoolman stock on plan results, using a fake HTTP response.

The public payload only carries booleans. Location, remaining grams, spool ids,
and the Spoolman address stay off the response.
"""

from __future__ import annotations

import json
import logging
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from filament_picker.api import create_app
from filament_picker.catalog import load_catalog
from filament_picker.models import ModelPreview
from filament_picker.spoolman import COLOR_ID_EXTRA_KEY
from filament_picker.validate import validate_json

BAMBU = "bambu-lab/petg-basic/black-30105"
ESUN = "esun/petg-basic/black"
NEAR = "bambu-lab/petg-hf/black-00000"
_Handler = Callable[[urllib.request.Request, float], object]


@pytest.fixture
def example_catalog(repo_root: Path, tmp_path: Path) -> Path:
    path = tmp_path / "filament-catalog.json"
    shutil.copy(repo_root / "docs/schemas/examples/filament-catalog.example.json", path)
    return path


def _png_bytes() -> bytes:
    image = Image.new("RGB", (200, 200), "#FFFFFF")
    image.paste("#000000", (40, 40, 160, 160))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _Body:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


def _filament(color_id: str, **overrides: object) -> dict[str, object]:
    filament: dict[str, object] = {
        "id": 10,
        "vendor": {"name": "eSUN"},
        "material": "PETG",
        "color_hex": "272729",
        "extra": {COLOR_ID_EXTRA_KEY: color_id},
    }
    filament.update(overrides)
    return filament


def _spool(
    spool_id: int,
    filament: dict[str, object],
    remaining: object = 640,
) -> dict[str, object]:
    return {
        "id": spool_id,
        "archived": False,
        "remaining_weight": remaining,
        "location": "柜A",
        "filament": filament,
    }


def _install_http(monkeypatch: pytest.MonkeyPatch, handler: _Handler) -> list[str]:
    seen: list[str] = []

    def urlopen(request: urllib.request.Request, timeout: float = 0) -> object:
        assert request.get_method() == "GET"
        seen.append(request.full_url)
        return handler(request, timeout)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return seen


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_SPOOLMAN_ENABLED", "1")
    monkeypatch.setenv("FP_SPOOLMAN_BASE_URL", "http://spoolman.local:7912")


def _plan(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/plan",
        files={"file": ("black.png", _png_bytes(), "image/png")},
        data={"constraints": '{"materials":["PETG"]}'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert validate_json("result", body) == []
    return body


def _ids(body: dict[str, object]) -> list[str]:
    matches = body["matches"]
    assert isinstance(matches, list)
    picks = matches[0]["picks"]
    return [pick["id"] for pick in picks]


def _picks(body: dict[str, object]) -> list[dict[str, object]]:
    matches = body["matches"]
    assert isinstance(matches, list)
    return matches[0]["picks"]


def test_disabled_plan_does_not_call_spoolman(
    example_catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: urllib.request.Request, timeout: float) -> object:
        raise AssertionError((request.full_url, timeout))

    seen = _install_http(monkeypatch, handler)
    monkeypatch.setenv("FP_SPOOLMAN_ENABLED", "0")
    monkeypatch.setenv("FP_SPOOLMAN_BASE_URL", "http://spoolman.local:7912")
    client = TestClient(create_app(example_catalog, tmp_path))
    body = _plan(client)
    assert seen == []
    assert _ids(body) == [BAMBU, ESUN]
    assert all("stock" not in pick for pick in _picks(body))
    assert "库存有" not in str(body["reply_markdown"])
    stock = client.get("/api/stock", params={"ids": f"{BAMBU},{ESUN}"})
    assert stock.status_code == 200
    assert stock.json() == {"ok": True, "hints": {}}
    assert seen == []
    preview = ModelPreview(load_catalog(example_catalog))
    model_picks = preview.match_colours(["#000000"])[0]["picks"]
    assert [pick["id"] for pick in model_picks] == [BAMBU, ESUN]
    assert all("stock" not in pick for pick in model_picks)


def test_enabled_in_stock_sorts_ahead_and_keeps_buy_links(
    example_catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = [_spool(3, _filament(ESUN))]

    def handler(request: urllib.request.Request, timeout: float) -> _Body:
        assert request.full_url == "http://spoolman.local:7912/api/v1/spool"
        assert timeout == 3.0
        return _Body(json.dumps(payload).encode())

    seen = _install_http(monkeypatch, handler)
    _enable(monkeypatch)
    client = TestClient(create_app(example_catalog, tmp_path))
    body = _plan(client)
    assert seen == ["http://spoolman.local:7912/api/v1/spool"]
    assert _ids(body) == [ESUN, BAMBU]
    esun, bambu = _picks(body)
    assert esun["stock"] == {"in_stock": True, "nearby_in_stock": False}
    assert bambu["stock"] == {"in_stock": False, "nearby_in_stock": False}
    assert str(esun["url"]).startswith("http")
    assert str(bambu["url"]).startswith("http")
    encoded = json.dumps(body, ensure_ascii=False)
    assert "柜A" not in encoded
    assert "remaining_weight" not in encoded
    assert "spool_id" not in encoded
    assert "spoolman" not in encoded.casefold()
    lines = str(body["reply_markdown"]).splitlines()
    assert any("eSUN" in line and "库存有" in line for line in lines)
    assert all("库存有" not in line for line in lines if "Bambu Lab" in line)
    stock = client.get("/api/stock", params={"ids": f"{ESUN},{BAMBU}"})
    assert stock.status_code == 200
    assert stock.json() == {
        "ok": True,
        "hints": {ESUN: {"in_stock": True, "nearby_in_stock": False}},
    }
    preview = ModelPreview(load_catalog(example_catalog))
    model_picks = preview.match_colours(["#000000"])[0]["picks"]
    assert [pick["id"] for pick in model_picks] == [ESUN, BAMBU]
    assert model_picks[0]["stock"]["in_stock"] is True
    assert "柜A" not in json.dumps(model_picks, ensure_ascii=False)


def test_spoolman_down_returns_todays_plan(
    example_catalog: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: urllib.request.Request, timeout: float) -> object:
        raise urllib.error.URLError("timed out")

    seen = _install_http(monkeypatch, handler)
    _enable(monkeypatch)
    client = TestClient(create_app(example_catalog, tmp_path))
    with caplog.at_level(logging.WARNING):
        body = _plan(client)
        stock = client.get("/api/stock", params={"ids": BAMBU})
    assert seen
    assert all(url.endswith("/api/v1/spool") for url in seen)
    assert _ids(body) == [BAMBU, ESUN]
    assert all("stock" not in pick for pick in _picks(body))
    assert "库存有" not in str(body["reply_markdown"])
    assert stock.status_code == 200
    assert stock.json() == {"ok": True, "hints": {}}
    assert any("Spoolman" in record.message for record in caplog.records)


def test_missing_remaining_weight_is_not_in_stock(
    example_catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = [_spool(4, _filament(ESUN), remaining=None)]

    def handler(request: urllib.request.Request, timeout: float) -> _Body:
        del request, timeout
        return _Body(json.dumps(payload).encode())

    _install_http(monkeypatch, handler)
    _enable(monkeypatch)
    client = TestClient(create_app(example_catalog, tmp_path))
    body = _plan(client)
    assert _ids(body) == [BAMBU, ESUN]
    esun = _picks(body)[1]
    assert esun["id"] == ESUN
    assert esun["stock"] == {"in_stock": False, "nearby_in_stock": False}
    stock = client.get("/api/stock", params={"ids": ESUN})
    assert stock.json() == {"ok": True, "hints": {}}


def test_near_color_is_not_the_same_color_id(
    example_catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = [
        _spool(
            5,
            _filament(
                NEAR,
                vendor={"name": "Bambu Lab"},
                material="PETG",
                color_hex="000000",
            ),
            remaining=900,
        )
    ]

    def handler(request: urllib.request.Request, timeout: float) -> _Body:
        del request, timeout
        return _Body(json.dumps(payload).encode())

    _install_http(monkeypatch, handler)
    _enable(monkeypatch)
    client = TestClient(create_app(example_catalog, tmp_path))
    body = _plan(client)
    assert _ids(body) == [BAMBU, ESUN]
    assert NEAR not in _ids(body)
    bambu, esun = _picks(body)
    assert bambu["id"] == BAMBU
    assert bambu["stock"] == {"in_stock": False, "nearby_in_stock": True}
    assert esun["stock"]["in_stock"] is False
    assert "库存有" not in str(body["reply_markdown"])
    stock = client.get("/api/stock", params={"ids": f"{BAMBU},{ESUN},{NEAR}"})
    assert stock.json() == {"ok": True, "hints": {}}


def test_credentials_in_base_url_do_not_leak_into_the_plan(
    example_catalog: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: urllib.request.Request, timeout: float) -> object:
        raise AssertionError((request.full_url, timeout))

    seen = _install_http(monkeypatch, handler)
    monkeypatch.setenv("FP_SPOOLMAN_ENABLED", "1")
    monkeypatch.setenv("FP_SPOOLMAN_BASE_URL", "http://admin:secret@spoolman.local:7912")
    client = TestClient(create_app(example_catalog, tmp_path))
    with caplog.at_level(logging.WARNING):
        body = _plan(client)
    assert seen == []
    assert _ids(body) == [BAMBU, ESUN]
    assert all("stock" not in pick for pick in _picks(body))
    assert "secret" not in json.dumps(body, ensure_ascii=False)
    assert "secret" not in caplog.text
