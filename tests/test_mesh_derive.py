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


def test_high_poly_mesh_with_component_path_simplifies(monkeypatch) -> None:
    from filament_picker import mesh_derive, originals

    assert originals._FETCH_LIMIT >= 512 * 1024 * 1024
    monkeypatch.setattr(mesh_derive, "_TARGET_OBJECT_TRIANGLES", 300)
    monkeypatch.setattr(mesh_derive, "_TARGET_SCENE_TRIANGLES", 300)

    n = 28
    verts = []
    for y in range(n + 1):
        for x in range(n + 1):
            z = float((x - n / 2) ** 2 + (y - n / 2) ** 2) * 0.05
            verts.append(f'<vertex x="{x * 2.0}" y="{y * 2.0}" z="{z:.2f}"/>')
    tris = []
    stride = n + 1
    for y in range(n):
        for x in range(n):
            v0 = y * stride + x
            v1 = v0 + 1
            v2 = v0 + stride
            v3 = v2 + 1
            tris.append(f'<triangle v1="{v0}" v2="{v1}" v3="{v3}"/>')
            tris.append(f'<triangle v1="{v0}" v2="{v3}" v3="{v2}"/>')

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(
            "3D/3dmodel.model",
            '<model unit="millimeter" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">'
            '<resources><object id="2" type="model"><components>'
            '<component p:path="/3D/Objects/part.model" objectid="1"/>'
            "</components></object></resources>"
            '<build><item objectid="2"/></build></model>',
        )
        archive.writestr(
            "3D/Objects/part.model",
            '<model unit="millimeter"><resources><object id="1" type="model"><mesh>'
            f"<vertices>{''.join(verts)}</vertices>"
            f"<triangles>{''.join(tris)}</triangles>"
            "</mesh></object></resources></model>",
        )

    glb, images, record = derive_bytes(payload.getvalue())
    assert glb.startswith(b"glTF")
    assert images["front.png"].startswith(b"\x89PNG\r\n\x1a\n")
    assert record["status"] == "ready"
    assert 0 < record["triangles"] < len(tris)
