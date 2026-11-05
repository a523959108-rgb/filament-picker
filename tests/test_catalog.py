import json
from pathlib import Path

import pytest

from filament_picker.brands import BRAND_ORDER
from filament_picker.catalog import (
    CatalogValidationError,
    build_catalog,
    load_catalog,
    write_catalog,
)
from filament_picker.ingest import load_inventory, load_rows, sha256_file
from filament_picker.validate import validate_json


def _inputs(repo_root: Path):
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
    return rows, lock, inventory, source


@pytest.mark.data
def test_build_catalog_matches_counts_examples_and_order(repo_root: Path) -> None:
    rows, lock, inventory, source = _inputs(repo_root)
    cat = build_catalog(rows, lock, inventory, {}, None, "2026-11-05T12:00:00+09:00", source)
    assert validate_json("catalog", cat) == []
    assert cat["counts"] == {
        "entries": 3821,
        "with_hex": 600,
        "official": 246,
        "store_swatch": 354,
        "image_extracted": 0,
        "manual": 0,
    }
    assert [entry["id"] for entry in cat["entries"]] == sorted(
        entry["id"] for entry in cat["entries"]
    )
    assert [brand["slug"] for brand in cat["brands"]] == list(BRAND_ORDER)
    expected = json.loads(
        (repo_root / "docs/schemas/examples/filament-catalog.example.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {entry["id"]: entry for entry in cat["entries"]}
    for entry in expected["entries"]:
        assert by_id[entry["id"]] == entry
    assert sum(entry["material"] == "PLA" for entry in cat["entries"]) == 3059
    assert sum(entry["material"] == "PETG" for entry in cat["entries"]) == 762
    merged = by_id["cailab/rainbow-shift-pla/bamboo-rb009"]
    assert len(merged["source_rows"]) == 2
    assert merged["aliases"] == ["竹 RB009"]
    assert len(merged["offers"]) == 2


@pytest.mark.data
def test_manual_overrides_and_missing_lock(repo_root: Path) -> None:
    rows, lock, inventory, source = _inputs(repo_root)
    overrides = {
        "schema_version": 1,
        "hex": {"esun/petg-basic/black": {"hex": ["#111111"], "note": "test"}},
        "store_swatch_confidence": {"esun": 0.3},
    }
    cat = build_catalog(rows, lock, inventory, overrides, None, "2026-11-05T12:00:00+09:00", source)
    by_id = {entry["id"]: entry for entry in cat["entries"]}
    assert by_id["esun/petg-basic/black"]["hex_source"] == "manual"
    assert by_id["esun/petg-basic/black"]["hex_confidence"] == 0.9
    assert all(
        entry["hex_confidence"] == 0.3
        for entry in cat["entries"]
        if entry["brand_slug"] == "esun" and entry["hex_source"] == "store_swatch"
    )
    missing = dict(lock)
    missing["entries"] = dict(lock["entries"])
    missing["entries"].pop(next(iter(missing["entries"])))
    with pytest.raises(CatalogValidationError):
        build_catalog(rows, missing, inventory, {}, None, "2026-11-05T12:00:00+09:00", source)


@pytest.mark.data
def test_catalog_write_and_load(repo_root: Path, tmp_path: Path) -> None:
    rows, lock, inventory, source = _inputs(repo_root)
    catalog = build_catalog(rows, lock, inventory, {}, None, "2026-11-05T12:00:00+09:00", source)
    path = tmp_path / "nested" / "catalog.json"
    write_catalog(path, catalog)
    loaded = load_catalog(path)
    assert len(loaded.entries) == 3821
    assert loaded.by_id["bambu-lab/petg-basic/black-30105"]["hex"] == ["#000000"]
    with pytest.raises(CatalogValidationError):
        load_catalog(tmp_path / "missing.json")
