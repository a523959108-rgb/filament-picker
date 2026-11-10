from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filament_picker.api import create_app
from filament_picker.lumina_bridge import match_request


@pytest.fixture
def catalog_path(repo_root: Path, tmp_path: Path) -> Path:
    path = tmp_path / "filament-catalog.json"
    shutil.copy(repo_root / "data/build/filament-catalog.json", path)
    return path


@pytest.fixture
def client(catalog_path: Path, tmp_path: Path) -> TestClient:
    return TestClient(create_app(catalog_path, tmp_path))


def test_rybw_tray_map_hit(client: TestClient) -> None:
    response = client.post(
        "/api/lumina/match",
        json={
            "channels": [
                {"label": "R", "hex": "#E94A39"},
                {"label": "Y", "hex": "#ECEF35"},
                {"label": "B", "hex": "#3451B1"},
                {"label": "W", "hex": "#D7D2CF"},
            ],
            "palette": "rybw",
            "material": "pla",
            "brand": "bambu-lab",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["palette"] == "RYBW"
    assert body["slots"][0]["best"]["catalog_id"] == ("bambu-lab/pla-matte/scarlet-red-11200")
    assert body["slots"][0]["best"]["source"] == "tray_map"
    assert body["slots"][0]["best"]["delta_e"] == 5.06


def test_hex_nearest_neighbors_are_sorted_and_rounded(client: TestClient) -> None:
    response = client.post(
        "/api/lumina/match",
        json={"channels": [{"hex": "000000"}], "material": "PLA", "max_alternatives": 3},
    )
    assert response.status_code == 200
    slot = response.json()["slots"][0]
    distances = [slot["best"]["delta_e"]] + [item["delta_e"] for item in slot["alternatives"]]
    assert distances == sorted(distances)
    assert len(slot["alternatives"]) == 3
    assert all(round(distance, 2) == distance for distance in distances)


def test_max_alternatives_accepts_zero_and_five(client: TestClient) -> None:
    for maximum in (0, 5):
        response = client.post(
            "/api/lumina/match",
            json={"channels": [{"hex": "#000000"}], "max_alternatives": maximum},
        )
        assert response.status_code == 200
        assert len(response.json()["slots"][0]["alternatives"]) == maximum


def test_brand_material_filter_falls_back_with_note(client: TestClient) -> None:
    response = client.post(
        "/api/lumina/match",
        json={
            "channels": [{"hex": "#E94A39"}],
            "brand": "brand-with-no-match",
            "material": "PLA",
        },
    )
    assert response.status_code == 200
    slot = response.json()["slots"][0]
    assert slot["best"] is not None
    assert "brand" in slot["note"]


def test_name_matching_uses_normalized_catalog_names(client: TestClient) -> None:
    response = client.post(
        "/api/lumina/match",
        json={"channels": [{"name": " Bambu PLA Basic 白 "}], "max_alternatives": 0},
    )
    assert response.status_code == 200
    slot = response.json()["slots"][0]
    assert slot["best"]["catalog_id"] == "bambu-lab/pla-basic/jade-white-10100"
    assert slot["best"]["source"] == "name"
    assert slot["best"]["delta_e"] is None
    assert slot["input_name"] == " Bambu PLA Basic 白 "


@pytest.mark.parametrize(
    "payload",
    [
        {"channels": []},
        {"channels": [{"hex": "#12345"}]},
        {"channels": [{"name": "x" * 81}]},
        {"channels": [{"label": "x" * 17, "hex": "#123456"}]},
        {"channels": [{}]},
        {"channels": [{"hex": "#123456"}], "palette": "RGB"},
        {"channels": [{"hex": "#123456"}], "max_alternatives": 6},
        {"channels": [{"hex": "#123456"}], "max_alternatives": -1},
    ],
)
def test_invalid_input_is_422(client: TestClient, payload: dict[str, object]) -> None:
    response = client.post("/api/lumina/match", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_buy_url_prefers_pdd_goods(client: TestClient) -> None:
    response = client.post(
        "/api/lumina/match",
        json={"channels": [{"hex": "#0056B8"}], "brand": "bambu-lab", "material": "PLA"},
    )
    assert response.status_code == 200
    best = response.json()["slots"][0]["best"]
    assert best["buy_url_kind"] == "pdd_goods"
    assert "goods_id=" in best["buy_url"]


def test_allowed_cors_preflight_and_actual_request_only_on_lumina(client: TestClient) -> None:
    origin = "https://stack.filament.ibaozi.com"
    preflight = client.options(
        "/api/lumina/match",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    actual = client.post(
        "/api/lumina/match",
        headers={"Origin": origin},
        json={"channels": [{"hex": "#000000"}]},
    )
    assert actual.headers["access-control-allow-origin"] == origin
    other = client.post(
        "/api/lumina/match",
        headers={"Origin": "https://evil.example"},
        json={"channels": [{"hex": "#000000"}]},
    )
    assert "access-control-allow-origin" not in other.headers
    health = client.get("/api/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in health.headers


def test_match_request_is_pure_and_accepts_catalog_json(repo_root: Path) -> None:
    catalog = json.loads((repo_root / "data/build/filament-catalog.json").read_text())
    result = match_request({"channels": [{"hex": "#000000"}]}, catalog)
    assert result["schema_version"] == 1
    assert result["slots"][0]["best"]


def test_white_nearest_prefers_buyable_ordinary_material_and_deduplicates(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/lumina/match",
        json={"channels": [{"hex": "#FFFFFF"}], "max_alternatives": 5},
    )
    assert response.status_code == 200
    slot = response.json()["slots"][0]
    assert slot["best"]["catalog_id"] == "bambu-lab/pla-basic/jade-white-10100"
    items = [slot["best"], *slot["alternatives"]]
    assert slot["best"]["catalog_id"] not in {item["catalog_id"] for item in slot["alternatives"]}
    assert len({item["hex"] for item in items}) == len(items)
    assert all("translucent" not in item["series"].casefold() for item in items)


def test_palette_alternatives_prefer_tray_brand(client: TestClient) -> None:
    response = client.post(
        "/api/lumina/match",
        json={
            "channels": [
                {"label": "C", "hex": "#0086D6"},
                {"label": "M", "hex": "#EC008C"},
                {"label": "Y", "hex": "#F4EE2A"},
                {"label": "W", "hex": "#FFFFFF"},
            ],
            "palette": "CMYW",
            "max_alternatives": 3,
        },
    )
    assert response.status_code == 200
    for slot in response.json()["slots"]:
        assert all(item["brand_slug"] == "bambu-lab" for item in slot["alternatives"])


def test_tray_map_statuses_are_explained_in_notes(client: TestClient) -> None:
    rybw = client.post(
        "/api/lumina/match",
        json={
            "channels": [
                {"label": "R", "hex": "#E94A39"},
                {"label": "Y", "hex": "#ECEF35"},
                {"label": "B", "hex": "#3451B1"},
                {"label": "W", "hex": "#D7D2CF"},
            ],
            "palette": "RYBW",
        },
    )
    assert rybw.status_code == 200
    assert "LUT 名义色 ΔE 超阈" in rybw.json()["slots"][0]["note"]
    assert "同品牌近色" in rybw.json()["slots"][0]["note"]

    cmyw = client.post(
        "/api/lumina/match",
        json={
            "channels": [
                {"label": "C", "hex": "#0086D6"},
                {"label": "M", "hex": "#EC008C"},
                {"label": "Y", "hex": "#F4EE2A"},
                {"label": "W", "hex": "#FFFFFF"},
            ],
            "palette": "CMYW",
        },
    )
    assert cmyw.status_code == 200
    assert all(slot["note"] == "该映射待人工确认" for slot in cmyw.json()["slots"])


def _best_ids(body: dict[str, object]) -> list[str]:
    return [slot["best"]["catalog_id"] for slot in body["slots"]]  # type: ignore[index]


def test_tray_map_assigns_lumina_channel_order_by_hex(repo_root: Path) -> None:
    catalog = json.loads((repo_root / "data/build/filament-catalog.json").read_text("utf-8"))
    body = match_request(
        {
            "channels": [
                {"hex": "#FFFFFF"},
                {"hex": "#E94A39"},
                {"hex": "#ECEF35"},
                {"hex": "#1F4EA3"},
            ],
            "palette": "RYBW",
        },
        catalog,
    )
    assert _best_ids(body) == [
        "bambu-lab/pla-basic/light-gray-10104",
        "bambu-lab/pla-matte/scarlet-red-11200",
        "bambu-lab/pla-basic/yellow-10400",
        "bambu-lab/pla-basic/cobalt-blue-10604",
    ]
    assert all(slot["best"]["source"] == "tray_map" for slot in body["slots"])


def test_tray_map_assigns_by_label_when_all_labelled(repo_root: Path) -> None:
    catalog = json.loads((repo_root / "data/build/filament-catalog.json").read_text("utf-8"))
    body = match_request(
        {
            "channels": [
                {"label": "W", "hex": "#FFFFFF"},
                {"label": "R", "hex": "#E94A39"},
                {"label": "Y", "hex": "#ECEF35"},
                {"label": "B", "hex": "#1F4EA3"},
            ],
            "palette": "RYBW",
        },
        catalog,
    )
    assert _best_ids(body)[0] == "bambu-lab/pla-basic/light-gray-10104"
    assert _best_ids(body)[1] == "bambu-lab/pla-matte/scarlet-red-11200"


def test_tray_map_rejected_when_colours_do_not_fit_palette(repo_root: Path) -> None:
    catalog = json.loads((repo_root / "data/build/filament-catalog.json").read_text("utf-8"))
    body = match_request(
        {
            "channels": [
                {"hex": "#00FF00"},
                {"hex": "#00FF00"},
                {"hex": "#00FF00"},
                {"hex": "#00FF00"},
            ],
            "palette": "RYBW",
        },
        catalog,
    )
    assert all(slot["best"]["source"] == "nearest" for slot in body["slots"])


def test_tray_map_accepts_lumina_colour_word_labels(repo_root: Path) -> None:
    catalog = json.loads((repo_root / "data/build/filament-catalog.json").read_text("utf-8"))
    body = match_request(
        {
            "channels": [
                {"label": "White", "hex": "#FFFFFF"},
                {"label": "Red", "hex": "#E94A39"},
                {"label": "Yellow", "hex": "#ECEF35"},
                {"label": "Blue", "hex": "#1F4EA3"},
            ],
            "palette": "RYBW",
        },
        catalog,
    )
    assert _best_ids(body)[1] == "bambu-lab/pla-matte/scarlet-red-11200"
    assert body["slots"][1]["label"] == "Red"
