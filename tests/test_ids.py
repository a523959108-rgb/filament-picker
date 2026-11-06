import copy
import json

import pytest

from filament_picker.ids import (
    AssignStats,
    IdCollisionError,
    RowInfo,
    assign_ids,
    build_row_infos,
    canonical,
    empty_lock,
    group_rows,
    load_lock,
    make_dedup_key,
    write_lock,
)
from filament_picker.ingest import RawRow
from filament_picker.names import ParsedName, parse_color_name


def _infos(raw_rows: list[dict]) -> list[RowInfo]:
    rows = [
        RawRow(
            row_index=i,
            brand=item["b"],
            series=item["s"],
            price_text=item["p"],
            channel=item["ch"],
            url=item["u"],
            color_raw=item["c"],
            family=item["f"],
            hexes=tuple(item["h"]),
        )
        for i, item in enumerate(raw_rows)
    ]
    return build_row_infos(rows)


def test_make_dedup_key_examples() -> None:
    assert (
        make_dedup_key(
            "cailab", "rainbow-shift-pla", ParsedName("Bamboo", None, "RB009"), "Bamboo RB009"
        )
        == "cailab|code|RB009"
    )
    parsed = parse_color_name("Red&Blue-3KG")
    assert (
        make_dedup_key("eryone", "pla-silk-dual-color", parsed, "Red&Blue-3KG")
        == "eryone|pla-silk-dual-color|red-blue"
    )


def test_golden_ids(golden_ids: list[dict], raw_rows: list[dict]) -> None:
    infos = _infos(raw_rows)
    by_index = {info.row.row_index: info for info in infos}
    for expected in golden_ids:
        info = by_index[expected["row_index"]]
        assert info.dedup_key == expected["dedup_key"]
        assert info.row_id == expected["row_id"]


@pytest.mark.data
def test_groups_match_golden(raw_rows: list[dict], golden_merges: list[dict]) -> None:
    groups = group_rows(_infos(raw_rows))
    assert len(groups) == 3848
    assert sum(len(group) > 1 for group in groups.values()) == 24
    expected = {merge["dedup_key"]: merge for merge in golden_merges}
    actual = {key: group for key, group in groups.items() if len(group) > 1}
    assert set(actual) == set(expected)
    for key, merge in expected.items():
        group = actual[key]
        assert canonical(group).row_id == merge["canonical_id"]
        assert [info.row.row_index for info in group] == [row["row_index"] for row in merge["rows"]]


@pytest.mark.data
def test_canonical_ids_are_unique(raw_rows: list[dict]) -> None:
    groups = group_rows(_infos(raw_rows))
    ids = [canonical(group).row_id for group in groups.values()]
    assert len(ids) == 3848
    assert len(set(ids)) == 3848


@pytest.mark.data
def test_assign_ids_lifecycle(raw_rows: list[dict]) -> None:
    groups = group_rows(_infos(raw_rows))
    lock1, stats1 = assign_ids(groups, None, "2026-11-05", "0" * 64)
    assert stats1 == AssignStats(3848, 3848, 0, 0)
    lock1_copy = copy.deepcopy(lock1)
    lock2, stats2 = assign_ids(groups, lock1, "2026-11-06", "1" * 64)
    assert lock1 == lock1_copy
    assert stats2.new == 0
    assert stats2.retired == 0
    for key, entry in lock1["entries"].items():
        assert lock2["entries"][key]["id"] == entry["id"]
        assert lock2["entries"][key]["first_seen"] == entry["first_seen"]
        assert lock2["entries"][key]["last_seen"] == "2026-11-06"

    removed_key = next(iter(groups))
    reduced = {key: group for key, group in groups.items() if key != removed_key}
    retired_lock, retired_stats = assign_ids(reduced, lock2, "2026-11-07", "2" * 64)
    assert retired_stats.retired == 1
    assert retired_lock["entries"][removed_key]["status"] == "retired"
    restored, restored_stats = assign_ids(groups, retired_lock, "2026-11-08", "3" * 64)
    assert restored_stats.new == 0
    assert restored["entries"][removed_key]["status"] == "active"
    assert restored["entries"][removed_key]["id"] == lock1["entries"][removed_key]["id"]


def test_collision() -> None:
    row = RawRow(0, "Bambu Lab", "PETG Basic", "", "", "", "Black (30105)", "", ())
    group = build_row_infos([row])
    groups = group_rows(group)
    lock = empty_lock("2026-11-05", "0" * 64)
    lock["entries"]["zzz|x|y"] = {
        "id": "bambu-lab/petg-basic/black-30105",
        "status": "active",
        "first_seen": "2026-11-05",
        "last_seen": "2026-11-05",
    }
    with pytest.raises(IdCollisionError):
        assign_ids(groups, lock, "2026-11-05", "0" * 64)


def test_write_lock_is_valid_and_deterministic(tmp_path) -> None:
    lock = empty_lock("2026-11-05", "0" * 64)
    lock["entries"] = {
        "b|x|z": {
            "id": "b/s/z",
            "status": "active",
            "first_seen": "2026-11-05",
            "last_seen": "2026-11-05",
        },
        "a|x|z": {
            "id": "a/s/z",
            "status": "retired",
            "first_seen": "2026-11-04",
            "last_seen": "2026-11-05",
        },
    }
    path = tmp_path / "ids.lock.json"
    write_lock(path, lock)
    first = path.read_bytes()
    write_lock(path, lock)
    assert path.read_bytes() == first
    assert first.endswith(b"\n")
    data = json.loads(first)
    assert list(data["entries"]) == ["a|x|z", "b|x|z"]
    assert load_lock(path) == data


def test_load_lock_missing(tmp_path) -> None:
    assert load_lock(tmp_path / "missing.json") is None
