import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import REPO_ROOT


@dataclass(frozen=True, slots=True)
class RawRow:
    row_index: int
    brand: str
    series: str
    price_text: str
    channel: str
    url: str
    color_raw: str
    family: str
    hexes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InventorySeries:
    brand: str
    series: str
    variant_image_paths: tuple[str, ...]


class SnapshotMismatchError(RuntimeError):
    pass


class RowFormatError(ValueError):
    pass


RAW_DIR: Path = REPO_ROOT / "data" / "raw"
EXPECTED_SHA256: dict[str, str] = {
    "page_rows.json": "510566fc490559f6ccd4eaf347f05f61b41ea557fc7c99a4d8ba55f6fed63c61",
    "inventory.json": "b6a775ea341a7a5acfda4a918dd2737281fffe4b56bebb6c86ee6c26aec481cd",
}

_ROW_KEYS = {"b", "s", "p", "ch", "u", "c", "f", "h"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_snapshots(raw_dir: Path = RAW_DIR) -> None:
    for name, expected in EXPECTED_SHA256.items():
        path = raw_dir / name
        try:
            actual = sha256_file(path)
        except OSError as exc:
            raise SnapshotMismatchError(name) from exc
        if actual != expected:
            raise SnapshotMismatchError(name)


def _load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RowFormatError(f"unable to read {path}") from exc


def load_rows(path: Path) -> list[RawRow]:
    data = _load_json(path)
    if not isinstance(data, list):
        raise RowFormatError("rows: expected a list")

    rows: list[RawRow] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise RowFormatError(f"row {index}: expected an object")
        if set(item) != _ROW_KEYS:
            raise RowFormatError(f"row {index}: keys must be {_ROW_KEYS!r}")
        if any(not isinstance(item[key], str) for key in _ROW_KEYS - {"h"}):
            raise RowFormatError(f"row {index}: fields other than h must be strings")
        hexes = item["h"]
        if not isinstance(hexes, list) or any(not isinstance(value, str) for value in hexes):
            raise RowFormatError(f"row {index}: h must be a list[str]")
        rows.append(
            RawRow(
                row_index=index,
                brand=item["b"],
                series=item["s"],
                price_text=item["p"],
                channel=item["ch"],
                url=item["u"],
                color_raw=item["c"],
                family=item["f"],
                hexes=tuple(hexes),
            )
        )
    return rows


def load_inventory(path: Path) -> list[InventorySeries]:
    data = _load_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("series"), list):
        raise RowFormatError("inventory: series must be a list")

    inventory: list[InventorySeries] = []
    for index, item in enumerate(data["series"]):
        if not isinstance(item, dict):
            raise RowFormatError(f"series {index}: expected an object")
        brand = item.get("brand")
        series = item.get("series")
        paths = item.get("variant_image_paths", [])
        if not isinstance(brand, str) or not isinstance(series, str):
            raise RowFormatError(f"series {index}: brand and series must be strings")
        if not isinstance(paths, list) or any(not isinstance(value, str) for value in paths):
            raise RowFormatError(f"series {index}: variant_image_paths must be a list[str]")
        inventory.append(
            InventorySeries(brand=brand, series=series, variant_image_paths=tuple(paths))
        )
    return inventory
