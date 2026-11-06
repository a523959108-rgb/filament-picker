import json
from pathlib import Path

from filament_picker.cli import main
from filament_picker.web_export import export_entry, export_web


def _example_catalog() -> dict:
    return json.loads(
        Path("docs/schemas/examples/filament-catalog.example.json").read_text(encoding="utf-8")
    )


def test_export_web_matches_fixture() -> None:
    catalog = _example_catalog()
    expected = json.loads(Path("docs/fixtures/web-catalog.sample.json").read_text(encoding="utf-8"))
    actual = export_web(catalog)
    # Example fixture keeps img=null so it stays portable without web/public/sku/.
    for entry in actual["entries"]:
        entry["img"] = None
    assert actual == expected


def test_retired_entry_and_unused_brand_are_not_exported() -> None:
    catalog = _example_catalog()
    catalog["entries"][-1]["status"] = "retired"
    result = export_web(catalog)
    assert all(entry["id"] != "byehassle/pla-ya-guang/sakura-bloom" for entry in result["entries"])
    assert all(brand["slug"] != "byehassle" for brand in result["brands"])

    catalog = _example_catalog()
    catalog["entries"][0]["status"] = "retired"
    result = export_web(catalog)
    assert all(entry["id"] != "bambu-lab/petg-basic/black-30105" for entry in result["entries"])
    assert all(brand["slug"] != "bambu-lab" for brand in result["brands"])


def test_export_entry_has_required_key_order() -> None:
    catalog = _example_catalog()
    expected_keys = [
        "id",
        "b",
        "s",
        "m",
        "en",
        "zh",
        "code",
        "py",
        "pyi",
        "fam",
        "eff",
        "hex",
        "src",
        "conf",
        "url",
        "alt_url",
        "price",
        "img",
    ]
    for entry in catalog["entries"]:
        assert list(export_entry(entry)) == expected_keys


def test_export_web_cli_writes_output(tmp_path, capsys) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_example_catalog(), ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "w.json"

    assert main(["export-web", "--catalog", str(catalog_path), "--out", str(output_path)]) == 0
    assert output_path.exists()
    assert capsys.readouterr().out.rstrip().splitlines()[-1] == "entries=4"


def test_export_entry_img_when_cached(tmp_path, monkeypatch) -> None:
    from filament_picker import web_export

    sku = tmp_path / "sku"
    sku.mkdir()
    (sku / "bambu-lab__petg-basic__black-30105.jpg").write_bytes(b"fake")
    monkeypatch.setattr(web_export, "SKU_DIR", sku)
    entry = _example_catalog()["entries"][0]
    exported = web_export.export_entry(entry)
    assert exported["img"] == "/sku/bambu-lab__petg-basic__black-30105.jpg"
