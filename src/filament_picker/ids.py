from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .brands import brand_slug
from .config import REPO_ROOT
from .ingest import RawRow
from .names import ParsedName, parse_color_name
from .slug import row_id, series_slug, slug
from .validate import assert_valid


@dataclass(frozen=True, slots=True)
class RowInfo:
    row: RawRow
    parsed: ParsedName
    brand_slug: str
    series_slug: str
    row_id: str
    dedup_key: str


@dataclass(frozen=True, slots=True)
class AssignStats:
    keys: int
    new: int
    retired: int
    collisions: int


class IdCollisionError(RuntimeError):
    def __init__(self, key: str, new_id: str) -> None:
        self.key = key
        self.new_id = new_id
        super().__init__(f"ID collision for {key}: {new_id}")


LOCK_PATH: Path = REPO_ROOT / "data" / "ids.lock.json"
DOMESTIC_CHANNEL_WORDS: tuple[str, ...] = ("淘宝", "拼多多", "天猫")


def make_dedup_key(brand_slug: str, series_slug: str, parsed: ParsedName, raw: str) -> str:
    if parsed.code:
        return f"{brand_slug}|code|{parsed.code}"
    color = parsed.name_en or parsed.name_zh or raw
    return f"{brand_slug}|{series_slug}|{slug(color)}"


def build_row_infos(rows: list[RawRow]) -> list[RowInfo]:
    infos: list[RowInfo] = []
    for row in rows:
        parsed = parse_color_name(row.color_raw)
        brand = brand_slug(row.brand)
        series = series_slug(row.series)
        infos.append(
            RowInfo(
                row=row,
                parsed=parsed,
                brand_slug=brand,
                series_slug=series,
                row_id=row_id(brand, row.series, parsed, row.color_raw),
                dedup_key=make_dedup_key(brand, series, parsed, row.color_raw),
            )
        )
    return infos


def group_rows(infos: list[RowInfo]) -> dict[str, list[RowInfo]]:
    groups: dict[str, list[RowInfo]] = {}
    for info in infos:
        groups.setdefault(info.dedup_key, []).append(info)
    for group in groups.values():
        group.sort(key=lambda info: info.row.row_index)
    return groups


def canonical(group: list[RowInfo]) -> RowInfo:
    return sorted(
        group,
        key=lambda info: (
            0 if info.row.hexes else 1,
            1 if any(word in info.row.channel for word in DOMESTIC_CHANNEL_WORDS) else 0,
            info.row.row_index,
        ),
    )[0]


def empty_lock(today: str, source_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "rules_version": "slug-v1",
        "updated_at": today,
        "source_sha256": source_sha256,
        "entries": {},
    }


def load_lock(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    assert_valid("lock", lock)
    return lock


def assign_ids(
    groups: dict[str, list[RowInfo]],
    lock: dict[str, Any] | None,
    today: str,
    source_sha256: str,
) -> tuple[dict[str, Any], AssignStats]:
    result = copy.deepcopy(lock) if lock is not None else empty_lock(today, source_sha256)
    entries: dict[str, dict[str, Any]] = result["entries"]
    occupied = {entry["id"] for entry in entries.values()}
    new_count = 0
    retired_count = 0

    for key, group in groups.items():
        if key in entries:
            entry = entries[key]
            entry["status"] = "active"
            entry["last_seen"] = today
            continue
        new_id = canonical(group).row_id
        if new_id in occupied:
            raise IdCollisionError(key, new_id)
        entries[key] = {
            "id": new_id,
            "status": "active",
            "first_seen": today,
            "last_seen": today,
        }
        occupied.add(new_id)
        new_count += 1

    for key, entry in entries.items():
        if key not in groups and entry["status"] != "retired":
            entry["status"] = "retired"
            retired_count += 1

    result["updated_at"] = today
    result["source_sha256"] = source_sha256
    return result, AssignStats(len(groups), new_count, retired_count, 0)


def write_lock(path: Path, lock: dict[str, Any]) -> None:
    assert_valid("lock", lock)
    output = copy.deepcopy(lock)
    output["entries"] = dict(sorted(output["entries"].items()))
    text = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
