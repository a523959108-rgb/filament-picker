import json
from pathlib import Path

from filament_picker.catalog import build_catalog
from filament_picker.ingest import load_inventory, load_rows, sha256_file
from filament_picker.validate import validate_json


def _inputs(repo_root: Path):
    rows_path = repo_root / "data/raw/page_rows.json"
    inventory_path = repo_root / "data/raw/inventory.json"
    lock_path = repo_root / "data/ids.lock.json"
    return (
        load_rows(rows_path),
        json.loads(lock_path.read_text(encoding="utf-8")),
        load_inventory(inventory_path),
        {
            "page_rows_sha256": sha256_file(rows_path),
            "inventory_sha256": sha256_file(inventory_path),
            "ids_lock_sha256": sha256_file(lock_path),
        },
    )


def _result(confidence: float) -> dict:
    return {
        "image": "/workspace/filament-shots/example.jpg",
        "status": "ok",
        "hexes": ["#123456"],
        "confidence": confidence,
        "share": 1.0,
        "spread": 0.0,
        "n_pixels": 100,
        "error": None,
    }


def test_build_catalog_uses_extracted_hex_above_threshold(repo_root: Path) -> None:
    rows, lock, inventory, source = _inputs(repo_root)
    extracted = {
        "generated_at": "2026-11-05T12:00:00+09:00",
        "results": {
            "cailab/rainbow-shift-pla/bamboo-rb009": _result(0.40),
        },
    }
    catalog = build_catalog(
        rows, lock, inventory, {}, extracted, "2026-11-05T12:00:00+09:00", source
    )
    entry = next(
        item for item in catalog["entries"] if item["id"] == "cailab/rainbow-shift-pla/bamboo-rb009"
    )
    assert entry["hex_source"] == "image_extracted"
    assert entry["hex"] == ["#123456"]
    assert entry["hex_confidence"] == 0.4


def test_build_catalog_rejects_extracted_below_threshold_and_preserves_official(
    repo_root: Path,
) -> None:
    rows, lock, inventory, source = _inputs(repo_root)
    extracted = {
        "generated_at": "2026-11-05T12:00:00+09:00",
        "results": {
            "cailab/rainbow-shift-pla/bamboo-rb009": _result(0.39),
            "bambu-lab/petg-basic/black-30105": _result(0.99),
        },
    }
    catalog = build_catalog(
        rows, lock, inventory, {}, extracted, "2026-11-05T12:00:00+09:00", source
    )
    by_id = {item["id"]: item for item in catalog["entries"]}
    cailab = by_id["cailab/rainbow-shift-pla/bamboo-rb009"]
    assert cailab["hex"] == []
    assert cailab["hex_source"] is None
    assert cailab["hex_confidence"] is None
    assert cailab["lab"] is None
    bambu = by_id["bambu-lab/petg-basic/black-30105"]
    assert bambu["hex_source"] == "official"
    assert bambu["hex"] == ["#000000"]


def test_build_catalog_extracted_preserves_ids_and_validates(repo_root: Path) -> None:
    rows, lock, inventory, source = _inputs(repo_root)
    baseline = build_catalog(rows, lock, inventory, {}, None, "2026-11-05T12:00:00+09:00", source)
    extracted = {
        "generated_at": "2026-11-05T12:00:00+09:00",
        "results": {
            "cailab/rainbow-shift-pla/bamboo-rb009": _result(0.40),
        },
    }
    with_extracted = build_catalog(
        rows, lock, inventory, {}, extracted, "2026-11-05T12:00:00+09:00", source
    )
    assert [item["id"] for item in with_extracted["entries"]] == [
        item["id"] for item in baseline["entries"]
    ]
    assert with_extracted["counts"]["image_extracted"] == 1
    assert validate_json("catalog", with_extracted) == []
