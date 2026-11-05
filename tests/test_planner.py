from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from filament_picker.catalog import Catalog, build_catalog
from filament_picker.cli import main
from filament_picker.ingest import load_inventory, load_rows, sha256_file
from filament_picker.planner import run_plan
from filament_picker.validate import validate_json


@pytest.fixture(scope="session")
def catalog(repo_root: Path) -> Catalog:
    rows_path = repo_root / "data/raw/page_rows.json"
    inventory_path = repo_root / "data/raw/inventory.json"
    lock_path = repo_root / "data/ids.lock.json"
    rows = load_rows(rows_path)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    inventory = load_inventory(inventory_path)
    source = {
        "page_rows_sha256": sha256_file(rows_path),
        "inventory_sha256": sha256_file(inventory_path),
        "ids_lock_sha256": sha256_file(lock_path),
    }
    data = build_catalog(rows, lock, inventory, {}, None, "2026-11-05T12:00:00+09:00", source)
    return Catalog(
        data["generated_at"], tuple(data["entries"]), {e["id"]: e for e in data["entries"]}
    )


def _request(image: Path, **extra: object) -> dict:
    request = {
        "schema_version": 1,
        "request_id": "msgT17",
        "created_at": "2026-11-05T14:03:12+09:00",
        "image_paths": [str(image)],
        "note": "1色 只要拓竹 PLA",
        "constraints": {},
        "context": {"conversationId": "cid"},
    }
    request.update(extra)
    return request


def _clock() -> object:
    t0 = datetime(2026, 11, 5, 14, 3, 12, tzinfo=ZoneInfo("Asia/Tokyo"))
    return iter([t0, t0 + timedelta(milliseconds=1840)]).__next__


@pytest.mark.data
def test_run_plan_end_to_end(catalog: Catalog, tmp_root: Path, repo_root: Path) -> None:
    from helpers_images import square_on_white

    image = square_on_white(tmp_root / "green.png")
    result = run_plan(_request(image), catalog, tmp_root, _clock(), None)
    assert result["status"] == "ok"
    assert result["created_at"] == "2026-11-05T14:03:12+09:00"
    assert result["finished_at"] == "2026-11-05T14:03:13+09:00"
    assert result["elapsed_ms"] == 1840
    assert result["palette"][0]["hex"] == "#00AE42"
    assert result["palette"][0]["share"] == 1.0
    assert result["matches"][0]["picks"][0]["id"] == "bambu-lab/pla-basic/bambu-green-10501"
    assert result["matches"][0]["picks"][0]["delta_e"] == 0.0
    assert result["matches"][0]["picks"][1]["id"] == "bambu-lab/pla-lite/green-16501"
    assert result["matches"][0]["picks"][1]["delta_e"] == 4.70
    assert result["card_path"] is not None
    card_path = Path(result["card_path"])
    assert card_path.is_file()
    assert tmp_root / "public/cards" in card_path.parents
    assert result["card_url"] is None
    assert validate_json("result", result) == []
    assert result["context"] == {"conversationId": "cid"}


@pytest.mark.data
def test_run_plan_card_url(catalog: Catalog, tmp_root: Path) -> None:
    from helpers_images import square_on_white

    image = square_on_white(tmp_root / "green.png")
    result = run_plan(_request(image), catalog, tmp_root, _clock(), "https://cards.example.invalid")
    assert result["card_url"].startswith("https://cards.example.invalid/")
    assert result["reply_markdown"].splitlines()[1] == f"![配色卡]({result['card_url']})"


@pytest.mark.data
@pytest.mark.parametrize(
    ("image_name", "expected_code"),
    (
        ("missing.png", "IMAGE_MISSING"),
        ("tiny.png", "IMAGE_TOO_SMALL"),
        ("blank.png", "NO_FOREGROUND"),
    ),
)
def test_run_plan_image_errors(
    catalog: Catalog, tmp_root: Path, image_name: str, expected_code: str
) -> None:
    from helpers_images import blank_white, tiny

    image = tmp_root / image_name
    if expected_code == "IMAGE_TOO_SMALL":
        tiny(image)
    elif expected_code == "NO_FOREGROUND":
        blank_white(image)
    result = run_plan(_request(image), catalog, tmp_root, _clock(), None)
    assert result["status"] == "error"
    assert result["error"]["code"] == expected_code
    assert result["card_path"] is None
    assert validate_json("result", result) == []
    if expected_code == "IMAGE_MISSING":
        assert result["reply_markdown"] == "没找到这张图片，可能已过期，请重新发送。"


@pytest.mark.data
def test_run_plan_no_match(catalog: Catalog, tmp_root: Path) -> None:
    from helpers_images import square_on_white

    image = square_on_white(tmp_root / "magenta.png", "#FF00FF")
    result = run_plan(_request(image), catalog, tmp_root, _clock(), None)
    assert result["status"] == "error"
    assert result["error"]["code"] == "NO_MATCH"
    assert result["card_path"] is None
    assert validate_json("result", result) == []


@pytest.mark.data
def test_run_plan_extra_images_warning(catalog: Catalog, tmp_root: Path) -> None:
    from helpers_images import square_on_white

    first = square_on_white(tmp_root / "first.png")
    second = square_on_white(tmp_root / "second.png")
    result = run_plan(
        _request(first, image_paths=[str(first), str(second)]),
        catalog,
        tmp_root,
        _clock(),
        None,
    )
    assert "EXTRA_IMAGES_IGNORED:1" in result["warnings"]


@pytest.mark.data
def test_plan_cli(catalog: Catalog, tmp_root: Path, repo_root: Path, monkeypatch, capsys) -> None:
    from helpers_images import square_on_white

    del catalog
    image = square_on_white(tmp_root / "green.png")
    monkeypatch.setenv("FP_CATALOG", str(repo_root / "data/build/filament-catalog.json"))
    assert main(["plan", str(image), "--note", "1色 只要拓竹 PLA", "--out", str(tmp_root)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert re.fullmatch(r"cli-\d{14}", result["request_id"])
