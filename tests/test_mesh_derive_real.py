"""Parse the three supplied 3MF originals. Skip when the pack is absent."""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from pathlib import Path

import pytest

from filament_picker.mesh_derive import derive_bytes

_ROOT = Path(
    os.environ.get(
        "FILAMENT_PICKER_REAL_SAMPLES",
        "/tmp/fp-real-accept/filament-real-acceptance",
    )
)
_CONTENT = {
    "9bb0daaf5dc37fed": "c72363560a7e0d761034a982f7534d92b0b82a026b7074b886f0e982a7a6b57a",
    "15522fe9a990b1d8": "975fc1d6213565435af14d97845db964f0d3d28b5d33b5b9fd65c93ad9d774af",
    "66ec451c011a6daa": "19b3beb6139e429a54ae904d12635687db1233d7469b6772a9f3d080fbe6b15b",
}
_PLATES = {"9bb0daaf5dc37fed": [1], "15522fe9a990b1d8": [1, 2], "66ec451c011a6daa": [1]}


def _original(model_id: str) -> Path:
    directory = _ROOT / "samples" / model_id / "original"
    if not directory.is_dir():
        pytest.skip("真实原件目录不在这台机器上")
    files = [
        path for path in directory.iterdir() if path.suffix.lower() == ".3mf" and path.is_file()
    ]
    if len(files) != 1:
        pytest.skip("真实原件不在这台机器上")
    return files[0]


@pytest.mark.data
def test_real_meshes_export_glb_and_front_views_without_touching_originals() -> None:
    for model_id, digest in _CONTENT.items():
        path = _original(model_id)
        before = path.read_bytes()
        assert hashlib.sha256(before).hexdigest() == digest
        glb, images, record = derive_bytes(before)
        assert path.read_bytes() == before
        assert record["status"] == "ready"
        assert record["scope"] == "plate"
        assert record["source_sha256"] == digest
        assert record["triangles"] > 0
        assert [plate["index"] for plate in record["plates"]] == _PLATES[model_id]
        assert glb.startswith(b"glTF") and len(glb) > 100
        assert images["front.png"].startswith(b"\x89PNG") and len(images["front.png"]) > 32
        with zipfile.ZipFile(io.BytesIO(before)) as archive:
            for name in archive.namelist():
                if name.startswith("Metadata/") and name.endswith(".png"):
                    assert images["front.png"] != archive.read(name)
        if len(record["plates"]) > 1:
            assert images["front-1.png"] != images["front-2.png"]
        for plate in record["plates"]:
            assert images[plate["front"]].startswith(b"\x89PNG")
