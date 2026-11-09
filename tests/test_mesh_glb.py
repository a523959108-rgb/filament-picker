from __future__ import annotations

import json
import struct

import pytest

from filament_picker.mesh_glb import sample_glb_bytes


def _chunks(blob: bytes) -> list[tuple[int, bytes]]:
    magic, version, length = struct.unpack_from("<4sII", blob)
    assert magic == b"glTF"
    assert version == 2
    assert length == len(blob)
    offset = 12
    chunks: list[tuple[int, bytes]] = []
    while offset < len(blob):
        size, kind = struct.unpack_from("<II", blob, offset)
        offset += 8
        chunks.append((kind, blob[offset : offset + size]))
        offset += size
    return chunks


def test_sample_glb_is_a_deterministic_unit_cube() -> None:
    first = sample_glb_bytes()
    assert first == sample_glb_bytes()
    chunks = _chunks(first)
    assert [kind for kind, _ in chunks] == [0x4E4F534A, 0x004E4942]
    document = json.loads(chunks[0][1])
    binary = chunks[1][1]
    assert document["asset"]["version"] == "2.0"
    assert document["buffers"][0]["byteLength"] == len(binary)
    assert document["accessors"][0]["count"] == 24
    assert document["accessors"][2]["count"] == 36
    assert document["accessors"][0]["min"] == [-0.5, -0.5, -0.5]
    assert document["accessors"][0]["max"] == [0.5, 0.5, 0.5]
    color = document["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"]
    assert color[0] == pytest.approx(231 / 255)
    assert color[3] == 1
    views = document["bufferViews"]
    assert views[-1]["byteOffset"] + views[-1]["byteLength"] == len(binary)
    assert b"source_relpath" not in first
    assert b"/home/" not in first


def test_sample_glb_rejects_colors_outside_unit_range() -> None:
    with pytest.raises(ValueError, match="base_color"):
        sample_glb_bytes((1.2, 0.0, 0.0, 1.0))
    with pytest.raises(ValueError, match="base_color"):
        sample_glb_bytes((True, 0.0, 0.0, 1.0))  # type: ignore[arg-type]
