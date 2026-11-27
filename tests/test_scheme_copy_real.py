"""Read-only checks against the three real 3MF originals supplied for this round.

The files stay outside the repository. A missing directory skips the test.
The 22-plate model is not here as a 3MF, so this file does not claim it was copied.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from filament_picker.scheme_copy import SchemeCopyError, build_scheme_copy

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
_MANIFEST = {
    "9bb0daaf5dc37fed": "55d30f80808b4e8a7521cbfeae7c056e77cbb14d7974f7be69ab7b0ea71c09a4",
    "15522fe9a990b1d8": "7376058d5c7ad866663ccc1c23dda872b0b9a0eb012893ed25895de932d80b89",
    "66ec451c011a6daa": "790cc8320679992b582b4f20fbaf54355be2cc7cd9fffb65de400618619103b7",
}


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


def _settings(payload: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return json.loads(archive.read("Metadata/project_settings.config"))


def _names(payload: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


@pytest.mark.data
def test_real_originals_keep_unused_slots_and_hash_the_bytes() -> None:
    cases = {
        "9bb0daaf5dc37fed": (7, "#112233", 6),
        "15522fe9a990b1d8": (1, "#ABCDEF", 0),
        "66ec451c011a6daa": (1, "#445566", 0),
    }
    for model_id, (slot, colour, index) in cases.items():
        path = _original(model_id)
        before = path.read_bytes()
        assert hashlib.sha256(before).hexdigest() == _CONTENT[model_id]
        assert hashlib.sha256(model_id.encode()).hexdigest() == _MANIFEST[model_id]
        assert _CONTENT[model_id] != _MANIFEST[model_id]
        copied, record = build_scheme_copy(
            before,
            [
                {"plate_index": 1, "slot": slot, "hex": colour},
                {"plate_index": 2, "slot": slot, "hex": colour},
            ],
        )
        assert path.read_bytes() == before
        assert record["source_sha256"] == _CONTENT[model_id]
        assert record["source_sha256"] != _MANIFEST[model_id]
        assert record["sha256"] == hashlib.sha256(copied).hexdigest()
        settings = _settings(copied)
        original = _settings(before)
        assert settings["filament_colour"][index] == colour
        for position, item in enumerate(original["filament_colour"]):
            if position != index:
                assert settings["filament_colour"][position] == item
        assert settings["default_filament_colour"] == original["default_filament_colour"]
        assert settings["extruder_colour"] == original["extruder_colour"]
        assert settings.get("filament_ids") == original.get("filament_ids")
        if "filament_multi_colour" in original:
            assert settings["filament_multi_colour"][index] == colour
        source_entries = _names(before)
        copied_entries = _names(copied)
        for name, payload in source_entries.items():
            if name == "Metadata/project_settings.config":
                continue
            assert copied_entries[name] == payload
        assert "Metadata/filament_picker_scheme.json" in copied_entries
        note = json.loads(copied_entries["Metadata/filament_picker_scheme.json"])
        assert "需要重新切片" in note["caveat"]


@pytest.mark.data
def test_real_base_does_not_treat_an_unused_project_slot_as_damage() -> None:
    path = _original("15522fe9a990b1d8")
    before = path.read_bytes()
    copied, _record = build_scheme_copy(before, [{"plate_index": 1, "slot": 1, "hex": "#010203"}])
    settings = _settings(copied)
    assert settings["filament_colour"] == ["#010203", "#FF0000"]
    with pytest.raises(SchemeCopyError, match="不在 filament_colour"):
        build_scheme_copy(before, [{"slot": 3, "hex": "#010203"}])
    assert path.read_bytes() == before
