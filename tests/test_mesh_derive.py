from __future__ import annotations

import io
import zipfile
from pathlib import Path

from filament_picker.mesh_derive import derive_bytes, derive_file
from filament_picker.scheme_copy import synthetic_3mf


def test_synthetic_mesh_becomes_an_overall_front_view(tmp_path: Path) -> None:
    source = synthetic_3mf(["#111111", "#222222"])
    original = tmp_path / "originals" / "sample-01.3mf"
    original.parent.mkdir()
    original.write_bytes(source)
    first = derive_file(tmp_path, "sample-01", original)
    second = derive_file(tmp_path, "sample-01", original)
    assert first["status"] == "ready"
    assert first["scope"] == "overall"
    assert first["triangles"] == 1
    assert first["plates"] == []
    assert "仅整体正视" in first["note"]
    assert first == second
    glb = (tmp_path / "derived" / "sample-01" / "model.glb").read_bytes()
    front = (tmp_path / "derived" / "sample-01" / "front.png").read_bytes()
    assert glb.startswith(b"glTF")
    assert front.startswith(b"\x89PNG")
    assert not (tmp_path / "derived" / "sample-01" / "front-1.png").exists()
    assert original.read_bytes() == source
    assert "originals" not in (tmp_path / "derived" / "sample-01").resolve().parts[-2:]


def test_unreadable_archive_records_failure_without_a_glb(tmp_path: Path) -> None:
    source = tmp_path / "originals" / "sample-01.3mf"
    source.parent.mkdir()
    source.write_bytes(b"not a zip")
    record = derive_file(tmp_path, "sample-01", source)
    assert record["status"] == "failed"
    assert record["error"]
    assert not (tmp_path / "derived" / "sample-01" / "model.glb").exists()
    assert source.read_bytes() == b"not a zip"


def test_partial_plate_map_stays_an_overall_view() -> None:
    mesh = synthetic_3mf(["#111111"])
    with zipfile.ZipFile(io.BytesIO(mesh)) as archive:
        model = archive.read("3D/3dmodel.model")
    settings = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<config><plate><metadata key="plater_id" value="1"/>'
        '<model_instance><metadata key="object_id" value="99"/></model_instance>'
        "</plate></config>"
    )
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("3D/3dmodel.model", model)
        archive.writestr("Metadata/model_settings.config", settings)
    _glb, images, record = derive_bytes(payload.getvalue())
    assert record["scope"] == "overall"
    assert record["plates"] == []
    assert set(images) == {"front.png"}


def test_external_component_and_dtd_are_refused_without_fetching(tmp_path: Path) -> None:
    remote_zip = io.BytesIO()
    with zipfile.ZipFile(remote_zip, "w") as archive:
        archive.writestr(
            "3D/3dmodel.model",
            '<?xml version="1.0"?><model unit="millimeter" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">'
            '<resources><object id="1" type="model"><components>'
            '<component p:path="https://example.invalid/evil.model" objectid="1"/>'
            '</components></object></resources><build><item objectid="1"/></build></model>',
        )
    remote_path = tmp_path / "originals" / "remote.3mf"
    remote_path.parent.mkdir()
    remote_path.write_bytes(remote_zip.getvalue())
    remote = derive_file(tmp_path, "remote", remote_path)
    assert remote["status"] == "failed"
    assert "不安全" in remote["error"]
    assert not (tmp_path / "derived" / "remote" / "model.glb").exists()
    bombed = io.BytesIO()
    with zipfile.ZipFile(bombed, "w") as archive:
        archive.writestr(
            "3D/3dmodel.model",
            '<!DOCTYPE model [<!ENTITY x "x">]>'
            '<model unit="millimeter"><resources></resources></model>',
        )
    entity_path = tmp_path / "originals" / "entity.3mf"
    entity_path.write_bytes(bombed.getvalue())
    entity = derive_file(tmp_path, "entity", entity_path)
    assert entity["status"] == "failed"
    assert "DTD" in entity["error"]
