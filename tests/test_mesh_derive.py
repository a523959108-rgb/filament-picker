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
