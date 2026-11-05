import json
from pathlib import Path

import pytest

from filament_picker.calibrate import calibrate, qa_sample, run_extract, summarize
from filament_picker.catalog import Catalog, load_catalog
from helpers_images import blank_white, square_on_white


def _catalog(entries: list[dict]) -> Catalog:
    return Catalog("2026-11-05T12:00:00+09:00", tuple(entries), {e["id"]: e for e in entries})


def _entry(entry_id: str, image: Path | None, effects: list[str] | None = None) -> dict:
    return {
        "id": entry_id,
        "variant_image": str(image) if image is not None else None,
        "effects": effects or [],
        "hex": [],
        "hex_source": None,
        "hex_confidence": None,
        "brand_slug": "test",
    }


def test_run_extract_statuses_and_limit(tmp_path: Path) -> None:
    square = square_on_white(tmp_path / "square.png")
    blank = blank_white(tmp_path / "blank.png")
    catalog = _catalog(
        [
            _entry("a/series/ok", square),
            _entry("b/series/blank", blank),
            _entry("c/series/missing", tmp_path / "missing.png"),
        ]
    )

    result = run_extract(catalog, "2026-11-05T12:00:00+09:00")
    assert result["generated_at"] == "2026-11-05T12:00:00+09:00"
    assert list(result["results"]) == ["a/series/ok", "b/series/blank", "c/series/missing"]
    assert result["results"]["a/series/ok"]["status"] == "ok"
    assert result["results"]["b/series/blank"]["status"] == "no_foreground"
    missing = result["results"]["c/series/missing"]
    assert missing["status"] == "skipped"
    assert missing["error"] == "IMAGE_MISSING"
    assert missing["hexes"] == []
    assert missing["confidence"] == 0
    assert missing["share"] == 0
    assert missing["spread"] == 0
    assert missing["n_pixels"] == 0

    limited = run_extract(catalog, "now", limit=1)
    assert list(limited["results"]) == ["a/series/ok"]


def test_summarize() -> None:
    rows = [
        {"id": f"bambu-lab/x/{i}", "hex_source": "official", "delta_e": value}
        for i, value in enumerate([1, 2, 3, 4, 5])
    ]
    rows.extend(
        {"id": f"esun/x/{i}", "hex_source": "store_swatch", "delta_e": value}
        for i, value in enumerate([10, 20])
    )
    assert summarize(rows) == [
        "store_swatch esun n=2 median=15.0 p80=18.0",
        "bambu n=5 median=3.0 p80=4.2",
    ]


def _qa_catalog_and_extracted(count: int) -> tuple[Catalog, dict]:
    entries = [_entry(f"brand/series/{i:03d}", Path(f"/tmp/image-{i}.png")) for i in range(count)]
    extracted = {
        "generated_at": "now",
        "results": {
            entry["id"]: {
                "image": entry["variant_image"],
                "status": "ok",
                "hexes": ["#123456"],
                "confidence": 0.5,
                "share": 1.0,
                "spread": 0.0,
                "n_pixels": 1,
                "error": None,
            }
            for entry in entries
        },
    }
    return _catalog(entries), extracted


def test_qa_sample_is_deterministic_and_limits_n() -> None:
    catalog, extracted = _qa_catalog_and_extracted(60)
    first = qa_sample(catalog, extracted)
    assert first == qa_sample(catalog, extracted)
    assert first.count("<img") == 50

    catalog_ten, extracted_ten = _qa_catalog_and_extracted(10)
    assert qa_sample(catalog_ten, extracted_ten).count("<img") == 10


@pytest.mark.data
def test_run_extract_real_catalog_has_2457_images(repo_root: Path) -> None:
    catalog = load_catalog(repo_root / "data/build/filament-catalog.json")
    result = run_extract(catalog, "2026-11-05T12:00:00+09:00")
    assert len(result["results"]) == 2457


@pytest.mark.data
def test_calibrate_real_catalog_has_40_official_rows(repo_root: Path) -> None:
    catalog = load_catalog(repo_root / "data/build/filament-catalog.json")
    extracted_path = repo_root / "data/extracted/extracted.json"
    if not extracted_path.exists():
        pytest.skip("先运行 extract 生成 extracted.json")
    extracted = json.loads(extracted_path.read_text(encoding="utf-8"))
    rows = [row for row in calibrate(catalog, extracted) if row["hex_source"] == "official"]
    assert len(rows) == 40
