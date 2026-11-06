import json
import shutil
from collections import Counter

import pytest

from filament_picker.cli import main
from filament_picker.ingest import (
    EXPECTED_SHA256,
    RAW_DIR,
    InventorySeries,
    RawRow,
    RowFormatError,
    SnapshotMismatchError,
    load_inventory,
    load_rows,
    sha256_file,
    verify_snapshots,
)


@pytest.mark.data
def test_verify_snapshots_and_hash() -> None:
    verify_snapshots()
    assert sha256_file(RAW_DIR / "page_rows.json") == EXPECTED_SHA256["page_rows.json"]


@pytest.mark.data
def test_load_rows_and_expected_sample() -> None:
    rows = load_rows(RAW_DIR / "page_rows.json")
    assert len(rows) == 3872
    assert rows[2808] == RawRow(
        row_index=2808,
        brand="Bambu Lab",
        series="PETG Basic",
        price_text="¥2,800 JPY",
        channel="Bambu Lab 日本官方商城",
        url="https://jp.store.bambulab.com/products/petg-basic",
        color_raw="Black 黑色 (30105)",
        family="黑白灰",
        hexes=("000000",),
    )


@pytest.mark.data
def test_row_hex_counts_and_brand_series_counts() -> None:
    rows = load_rows(RAW_DIR / "page_rows.json")
    assert Counter(len(row.hexes) for row in rows) == {0: 3272, 1: 582, 2: 17, 4: 1}
    assert len({row.brand for row in rows}) == 21
    assert len({(row.brand, row.series) for row in rows}) == 318


@pytest.mark.data
def test_load_inventory() -> None:
    inventory = load_inventory(RAW_DIR / "inventory.json")
    assert len(inventory) == 313
    assert isinstance(inventory[0], InventorySeries)


@pytest.mark.data
def test_verify_snapshots_detects_mismatch(tmp_path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy2(RAW_DIR / "page_rows.json", raw / "page_rows.json")
    shutil.copy2(RAW_DIR / "inventory.json", raw / "inventory.json")
    with (raw / "page_rows.json").open("a", encoding="utf-8") as file:
        file.write(" ")
    with pytest.raises(SnapshotMismatchError):
        verify_snapshots(raw)


def test_load_rows_rejects_missing_keys(tmp_path) -> None:
    path = tmp_path / "rows.json"
    path.write_text(json.dumps([{"b": "x"}]), encoding="utf-8")
    with pytest.raises(RowFormatError):
        load_rows(path)


def test_load_rows_rejects_string_hexes(tmp_path) -> None:
    path = tmp_path / "rows.json"
    path.write_text(
        json.dumps(
            [{"b": "x", "s": "", "p": "", "ch": "", "u": "", "c": "", "f": "", "h": "000000"}]
        ),
        encoding="utf-8",
    )
    with pytest.raises(RowFormatError):
        load_rows(path)


@pytest.mark.data
def test_ingest_command(capsys) -> None:
    assert main(["ingest"]) == 0
    assert capsys.readouterr().out == "rows=3872 brands=21 series=318\n"
