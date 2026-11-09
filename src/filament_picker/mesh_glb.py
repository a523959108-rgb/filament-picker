"""Minimal glTF binary cube for the private sample preview.

The bytes are a deterministic glTF 2.0 GLB (one mesh, one PBR material, no
textures). They are not a converted 3MF and do not embed source paths.
"""

from __future__ import annotations

import json
import struct

_GLB_MAGIC = b"glTF"
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942
# #E76F51, the first synthetic swatch, as linear-ish display RGBA.
_SAMPLE_ORANGE = (231 / 255, 111 / 255, 81 / 255, 1.0)


def sample_glb_bytes(
    base_color: tuple[float, float, float, float] = _SAMPLE_ORANGE,
) -> bytes:
    """Return a 1×1×1 cube centered at the origin."""
    color = _rgba(base_color)
    positions, normals, indices = _cube_buffers()
    blob = positions + normals + indices
    document = {
        "asset": {"version": "2.0", "generator": "filament-picker"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "materials": [
            {
                "name": "sample",
                "pbrMetallicRoughness": {
                    "baseColorFactor": list(color),
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.55,
                },
            }
        ],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1},
                        "indices": 2,
                        "material": 0,
                    }
                ]
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 24,
                "type": "VEC3",
                "min": [-0.5, -0.5, -0.5],
                "max": [0.5, 0.5, 0.5],
            },
            {"bufferView": 1, "componentType": 5126, "count": 24, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5123, "count": 36, "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {
                "buffer": 0,
                "byteOffset": len(positions),
                "byteLength": len(normals),
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": len(positions) + len(normals),
                "byteLength": len(indices),
                "target": 34963,
            },
        ],
        "buffers": [{"byteLength": len(blob)}],
    }
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = _chunk(_CHUNK_JSON, payload, b" ") + _chunk(_CHUNK_BIN, blob, b"\x00")
    return struct.pack("<4sII", _GLB_MAGIC, 2, 12 + len(body)) + body


def _rgba(color: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if len(color) != 4:
        raise ValueError("base_color must be four channels in 0..1")
    channels: list[float] = []
    for channel in color:
        if isinstance(channel, bool) or not isinstance(channel, (int, float)):
            raise ValueError("base_color must be four channels in 0..1")
        value = float(channel)
        if value < 0.0 or value > 1.0:
            raise ValueError("base_color must be four channels in 0..1")
        channels.append(value)
    return (channels[0], channels[1], channels[2], channels[3])


def _chunk(kind: int, data: bytes, pad: bytes) -> bytes:
    padded = data + pad * ((4 - len(data) % 4) % 4)
    return struct.pack("<II", len(padded), kind) + padded


def _cube_buffers() -> tuple[bytes, bytes, bytes]:
    # Outward CCW faces, matching a unit box from -0.5 to 0.5.
    faces = (
        (
            (0.0, 0.0, 1.0),
            ((-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)),
        ),
        (
            (0.0, 0.0, -1.0),
            ((0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5)),
        ),
        (
            (0.0, 1.0, 0.0),
            ((-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5)),
        ),
        (
            (0.0, -1.0, 0.0),
            ((-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5)),
        ),
        (
            (1.0, 0.0, 0.0),
            ((0.5, -0.5, 0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5)),
        ),
        (
            (-1.0, 0.0, 0.0),
            ((-0.5, -0.5, -0.5), (-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (-0.5, 0.5, -0.5)),
        ),
    )
    positions: list[float] = []
    normals: list[float] = []
    indices: list[int] = []
    for normal, corners in faces:
        base = len(positions) // 3
        for corner in corners:
            positions.extend(corner)
            normals.extend(normal)
        indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
    return (
        struct.pack(f"<{len(positions)}f", *positions),
        struct.pack(f"<{len(normals)}f", *normals),
        struct.pack(f"<{len(indices)}H", *indices),
    )
