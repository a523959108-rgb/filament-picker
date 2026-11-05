from pathlib import Path

import pytest

from filament_picker.ids import build_row_infos
from filament_picker.ingest import load_inventory, load_rows
from filament_picker.variants import VARIANT_RE, build_variant_index, find_variant_image, norm_key


def test_norm_key_removes_separators_and_normalizes() -> None:
    assert norm_key("Black 黑色 (30105)") == "black黑色30105"
    assert norm_key("Red&Blue") == "redblue"


def test_variant_re_captures_name() -> None:
    assert VARIANT_RE.match("variant_00_Black.jpg")[2] == "Black"
    assert VARIANT_RE.match("cover.jpg") is None


@pytest.mark.data
def test_find_variant_image_counts_and_bambu(raw_rows, repo_root: Path) -> None:
    rows = load_rows(repo_root / "data/raw/page_rows.json")
    inventory = load_inventory(repo_root / "data/raw/inventory.json")
    infos = build_row_infos(rows)
    index = build_variant_index(inventory)
    paths = [find_variant_image(index, info) for info in infos]
    assert find_variant_image(index, infos[2808]) == (
        "/workspace/filament-shots/Bambu Lab/PETG_Basic/variant_00_Black.jpg"
    )
    assert sum(path is not None for path in paths) == 2457
    assert (
        sum(
            path is not None
            for path, info in zip(paths, infos, strict=True)
            if info.brand_slug == "bambu-lab"
        )
        == 43
    )
    assert (
        sum(path is not None for path, info in zip(paths, infos, strict=True) if not info.row.hexes)
        == 2101
    )
