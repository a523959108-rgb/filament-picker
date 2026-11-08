import json
from pathlib import Path

import pytest

from filament_picker.ofd import (
    apply_matches,
    color_key,
    confidence_from_median,
    esun_store_swatch_confidence,
    filaments_from_payload,
    import_ofd,
    match_catalog,
    series_tokens,
    tokens_match,
)


def _entry(**extra: object) -> dict:
    entry = {
        "id": "esun/pla-basic/black",
        "status": "active",
        "brand_slug": "esun",
        "material": "PLA",
        "series_name": "PLA-Basic",
        "name_en": "Black",
        "name_raw": "Black",
        "hex": ["#272729"],
        "hex_source": "store_swatch",
        "hex_confidence": 0.3,
        "lab": [15.71, 0.49, -1.31],
        "effects": [],
    }
    entry.update(extra)
    return entry


def _payload() -> dict:
    return {
        "version": "test",
        "generated_at": "2026-11-08T00:00:00Z",
        "brands": [{"id": "b1", "slug": "esun_3d", "name": "eSUN"}],
        "filaments": [
            {
                "id": "f-basic",
                "name": "PLA-Basic",
                "material": "PLA",
                "brand_id": "b1",
                "density": 1.24,
                "min_print_temperature": 210,
                "max_print_temperature": 230,
                "min_bed_temperature": 45,
                "max_bed_temperature": 60,
            },
            {
                "id": "f-matte-a",
                "name": "PLA Matte",
                "material": "PLA",
                "brand_id": "b1",
                "density": 1.2,
                "min_print_temperature": 190,
                "max_print_temperature": 220,
                "min_bed_temperature": 45,
                "max_bed_temperature": 60,
            },
            {
                "id": "f-matte-b",
                "name": "Matte PLA",
                "material": "PLA",
                "brand_id": "b1",
                "density": 1.3,
                "min_print_temperature": 200,
                "max_print_temperature": 210,
                "min_bed_temperature": 50,
                "max_bed_temperature": 60,
            },
        ],
        "variants": [
            {
                "id": "v-black",
                "name": "Black",
                "slug": "black",
                "color_hex": "#010101",
                "filament_id": "f-basic",
                "discontinued": False,
            },
            {
                "id": "v-ivory",
                "name": "Ivory",
                "slug": "ivory",
                "color_hex": "#fffff0",
                "filament_id": "f-basic",
                "discontinued": False,
            },
            {
                "id": "v-orange",
                "name": "Orange",
                "slug": "orange",
                "color_hex": "#ff8800",
                "filament_id": "f-basic",
                "discontinued": False,
            },
            {
                "id": "v-old-black",
                "name": "Black",
                "slug": "black_old",
                "color_hex": "#111111",
                "filament_id": "f-basic",
                "discontinued": True,
            },
        ],
        "sizes": [
            {"variant_id": "v-black", "diameter": 1.75},
            {"variant_id": "v-ivory", "diameter": 1.75},
            {"variant_id": "v-orange", "diameter": 2.85},
        ],
    }


def test_series_tokens_ignore_material_order_and_a_single_plus() -> None:
    assert tokens_match(series_tokens("ePLA-HS"), series_tokens("ePLA+HS"))
    assert tokens_match(series_tokens("PLA Wood"), series_tokens("Wood PLA"))
    assert tokens_match(series_tokens("PETG（拼多多）"), series_tokens("PETG"))
    assert tokens_match(series_tokens("PLA"), series_tokens("PLA+")) is False
    assert tokens_match(series_tokens("PLA Silk"), series_tokens("PLA Silk Rainbow")) is False
    assert color_key("Concrete Grey") == "concrete gray"
    assert color_key("Bright Green 苹果绿 (30504)") == "bright green"


def test_confidence_interpolates_between_the_historical_floor_and_the_default() -> None:
    assert confidence_from_median(8) == 0.8
    assert confidence_from_median(10) == 0.8
    assert confidence_from_median(21.2) == 0.55
    assert confidence_from_median(32.4) == 0.3
    assert confidence_from_median(40) == 0.3


def test_wide_p80_keeps_esun_swatches_out_of_recommendations() -> None:
    assert esun_store_swatch_confidence({"n": 121.0, "median": 11.21, "p80": 29.64}) == 0.4
    assert esun_store_swatch_confidence({"n": 5.0, "median": 8.0, "p80": 9.0}) == 0.8


def test_match_fills_missing_hex_replaces_esun_swatch_and_skips_the_rest() -> None:
    entries = [
        _entry(),
        _entry(
            id="esun/pla-basic/ivory",
            name_en="Ivory",
            name_raw="Ivory",
            hex=[],
            hex_source=None,
            hex_confidence=None,
            lab=None,
        ),
        _entry(
            id="esun/pla-basic/manual",
            name_en="Manual Red",
            name_raw="Manual Red",
            hex=["#AA0000"],
            hex_source="manual",
            hex_confidence=0.9,
        ),
        _entry(id="esun/pla-matte/black", series_name="PLA Matte", name_en="Black"),
        _entry(id="rmerme/pla/black", brand_slug="rmerme", series_name="PLA哑光"),
    ]
    filaments = filaments_from_payload(
        _payload(), {"f-basic": "https://api.openfilamentdatabase.org/orcaslicer/pla-basic.json"}
    )
    result = match_catalog(entries, filaments)
    catalog = {"entries": entries, "counts": {}}
    updated, params, comparisons = apply_matches(catalog, result)

    black = next(entry for entry in updated["entries"] if entry["id"] == "esun/pla-basic/black")
    ivory = next(entry for entry in updated["entries"] if entry["id"] == "esun/pla-basic/ivory")
    manual = next(entry for entry in updated["entries"] if entry["id"] == "esun/pla-basic/manual")
    matte = next(entry for entry in updated["entries"] if entry["id"] == "esun/pla-matte/black")

    assert black["hex"] == ["#010101"]
    assert black["hex_source"] == "ofd"
    assert black["hex_confidence"] == 1.0
    assert black["lab"] == [round(value, 2) for value in black["lab"]]
    assert ivory["hex"] == ["#FFFFF0"]
    assert ivory["hex_source"] == "ofd"
    assert manual["hex"] == ["#AA0000"]
    assert manual["hex_source"] == "manual"
    assert matte["hex_source"] == "store_swatch"
    assert {row["id"] for row in comparisons} == {"esun/pla-basic/black"}
    assert params["esun/pla-basic/black"] == {
        "nozzle_c": [210.0, 230.0],
        "bed_c": [45.0, 60.0],
        "density_g_cm3": 1.24,
        "diameter_mm": 1.75,
        "orca_url": "https://api.openfilamentdatabase.org/orcaslicer/pla-basic.json",
    }
    assert "esun/pla-matte/black" not in params
    assert result.stats["skipped_filaments"] == 2
    assert result.stats["skipped_variants"] >= 1
    assert result.stats["color_matches"] == 2
    assert updated["counts"]["ofd"] == 2
    assert updated["counts"]["with_hex"] == 5


def test_plus_suffix_does_not_steal_an_exact_series_match() -> None:
    payload = {
        "version": "test",
        "generated_at": "2026-11-08T00:00:00Z",
        "brands": [{"id": "b", "slug": "bambu_lab", "name": "Bambu Lab"}],
        "filaments": [
            {
                "id": "tough",
                "name": "PLA Tough",
                "material": "PLA",
                "brand_id": "b",
                "density": 1.26,
                "min_print_temperature": 190,
                "max_print_temperature": 230,
                "min_bed_temperature": 35,
                "max_bed_temperature": 45,
            },
            {
                "id": "tough-plus",
                "name": "PLA Tough+",
                "material": "PLA",
                "brand_id": "b",
                "density": 1.21,
                "min_print_temperature": 220,
                "max_print_temperature": 250,
                "min_bed_temperature": 35,
                "max_bed_temperature": 65,
            },
            {
                "id": "hs",
                "name": "PLA-HS",
                "material": "PLA",
                "brand_id": "b",
                "density": 1.1,
                "min_print_temperature": 190,
                "max_print_temperature": 210,
                "min_bed_temperature": 40,
                "max_bed_temperature": 50,
            },
            {
                "id": "ehs",
                "name": "ePLA+HS",
                "material": "PLA",
                "brand_id": "b",
                "density": 1.24,
                "min_print_temperature": 210,
                "max_print_temperature": 230,
                "min_bed_temperature": 45,
                "max_bed_temperature": 60,
            },
        ],
        "variants": [],
        "sizes": [],
    }
    entries = [
        _entry(
            id="bambu-lab/pla-tough/black",
            brand_slug="bambu-lab",
            series_name="PLA Tough",
            hex_source="official",
            hex_confidence=1.0,
        ),
        _entry(
            id="bambu-lab/pla-tough-plus/black",
            brand_slug="bambu-lab",
            series_name="PLA Tough+",
            hex_source="official",
            hex_confidence=1.0,
        ),
        _entry(id="esun/epla-hs/black", series_name="ePLA-HS", brand_slug="esun"),
    ]
    # eSUN brand is not bambu_lab; give the HS filaments an esun brand too.
    payload["brands"].append({"id": "e", "slug": "esun_3d", "name": "eSUN"})
    for filament in payload["filaments"]:
        if filament["id"] in {"hs", "ehs"}:
            filament["brand_id"] = "e"
    result = match_catalog(entries, filaments_from_payload(payload))
    by_id = {match.entry_id: match.print_params for match in result.matches}
    assert by_id["bambu-lab/pla-tough/black"]["nozzle_c"] == [190.0, 230.0]
    assert by_id["bambu-lab/pla-tough-plus/black"]["nozzle_c"] == [220.0, 250.0]
    assert by_id["esun/epla-hs/black"]["density_g_cm3"] == 1.24


def test_ambiguous_color_hex_is_not_applied() -> None:
    payload = _payload()
    payload["variants"].append(
        {
            "id": "v-black-2",
            "name": "Black",
            "slug": "black_2",
            "color_hex": "#222222",
            "filament_id": "f-basic",
            "discontinued": False,
        }
    )
    result = match_catalog([_entry()], filaments_from_payload(payload))
    catalog = {"entries": [_entry()], "counts": {}}
    updated, params, comparisons = apply_matches(catalog, result)
    assert updated["entries"][0]["hex"] == ["#272729"]
    assert updated["entries"][0]["hex_source"] == "store_swatch"
    assert comparisons == []
    assert params["esun/pla-basic/black"]["nozzle_c"] == [210.0, 230.0]


def test_import_ofd_records_coverage_and_esun_confidence(tmp_path: Path) -> None:
    snapshot = tmp_path / "all.json"
    snapshot.write_text(json.dumps(_payload()), encoding="utf-8")
    orca = tmp_path / "orca.json"
    orca.write_text(
        json.dumps({"profiles": [{"id": "f-basic", "path": "brands/esun/pla.json"}]}),
        encoding="utf-8",
    )
    catalog = {
        "schema_version": 1,
        "generated_at": "2026-11-05T12:00:00+09:00",
        "source": {
            "page_rows_sha256": "a" * 64,
            "inventory_sha256": "b" * 64,
            "ids_lock_sha256": "c" * 64,
        },
        "counts": {},
        "brands": [],
        "entries": [_entry(), _entry(id="esun/pla-basic/other", name_en="Nope", name_raw="Nope")],
    }
    updated, enrichment, confidence = import_ofd(
        snapshot,
        catalog,
        orca_index=orca,
        now="2026-11-08T12:00:00+09:00",
    )
    assert updated["entries"][0]["hex_source"] == "ofd"
    assert enrichment["source"]["license"] == "MIT"
    assert enrichment["source"]["dataset_version"] == "test"
    assert enrichment["coverage_before"]["with_hex"] == 2
    assert enrichment["coverage_after"]["with_hex"] == 2
    assert enrichment["stats"]["hex_filled"] == 0
    assert enrichment["stats"]["esun_replaced"] == 1
    assert enrichment["esun_calibration"]["method"] == "store_swatch_vs_official"
    compared = enrichment["esun_calibration"]["compared"]
    assert compared["n"] == 1.0
    assert confidence == esun_store_swatch_confidence(compared)
    assert enrichment["entries"]["esun/pla-basic/black"]["orca_url"].endswith(
        "/orcaslicer/brands/esun/pla.json"
    )
    assert "esun/pla-basic/other" in enrichment["entries"]


@pytest.mark.data
def test_committed_ofd_import_matches_catalog(repo_root: Path) -> None:
    catalog = json.loads(
        (repo_root / "data/build/filament-catalog.json").read_text(encoding="utf-8")
    )
    enrichment = json.loads((repo_root / "data/ofd/enrichment.json").read_text(encoding="utf-8"))
    overrides = json.loads((repo_root / "data/manual_overrides.json").read_text(encoding="utf-8"))
    web = json.loads((repo_root / "web/public/web-catalog.json").read_text(encoding="utf-8"))
    assert enrichment["source"]["license"] == "MIT"
    assert enrichment["coverage_before"] == {"entries": 3848, "with_hex": 2362}
    assert enrichment["coverage_after"] == {"entries": 3848, "with_hex": 2664}
    assert enrichment["stats"]["hex_filled"] == 302
    assert enrichment["stats"]["esun_replaced"] == 132
    assert enrichment["stats"]["skipped_entries"] == 1587
    assert enrichment["stats"]["skipped_variants"] == 2657
    assert enrichment["esun_calibration"]["method"] == "sku_extract_vs_official"
    assert enrichment["esun_calibration"]["compared"]["median"] == 11.21
    assert enrichment["esun_calibration"]["compared"]["p80"] == 29.64
    assert enrichment["esun_calibration"]["confidence_after"] == 0.4
    assert overrides["store_swatch_confidence"]["esun"] == 0.4
    esun_swatches = [
        entry
        for entry in catalog["entries"]
        if entry["brand_slug"] == "esun" and entry["hex_source"] == "store_swatch"
    ]
    assert len(esun_swatches) == 74
    assert {entry["hex_confidence"] for entry in esun_swatches} == {0.4}
    assert all(
        entry["hex_confidence"] == 1.0
        for entry in catalog["entries"]
        if entry["hex_source"] == "ofd"
    )
    assert catalog["counts"]["with_hex"] == 2664
    assert catalog["counts"]["ofd"] == 434
    black = next(entry for entry in catalog["entries"] if entry["id"] == "esun/pla-basic/black")
    assert black["hex_source"] == "ofd"
    assert black["hex"] == ["#393D47"]
    web_black = next(entry for entry in web["entries"] if entry["id"] == "esun/pla-basic/black")
    assert web_black["src"] == "ofd"
    assert web_black["print"]["nozzle_c"] == [210.0, 230.0]
    tough = next(
        entry for entry in web["entries"] if entry["id"] == "bambu-lab/pla-tough/black-12101"
    )
    assert tough["url"].startswith("https://mobile.pinduoduo.com/search_result.html?search_key=")
    assert "filaments_color_codes" not in tough["url"]
    assert all("filaments_color_codes" not in (entry["url"] or "") for entry in web["entries"])
    assert all(
        "filaments_color_codes" not in (entry.get("alt_url") or "") for entry in web["entries"]
    )
