from __future__ import annotations

import re

from filament_picker.agent_color_map import (
    HIGH_FREQUENCY_MAPPINGS,
    as_inventory_seed,
    lookup_by_agent_filament_id,
    lookup_by_picker_color_id,
    missing_mapping_warning,
    warn_unmapped_ids,
)

_HEX = re.compile(r"^[0-9A-F]{6}$")
_ID = re.compile(r"^bambu-lab/pla-basic/[a-z0-9-]+$")


def test_high_frequency_map_has_twenty_unique_shared_ids() -> None:
    assert len(HIGH_FREQUENCY_MAPPINGS) == 20
    picker_ids = [item.picker_color_id for item in HIGH_FREQUENCY_MAPPINGS]
    agent_ids = [item.agent_filament_id for item in HIGH_FREQUENCY_MAPPINGS]
    assert len(set(picker_ids)) == 20
    assert picker_ids == agent_ids
    for item in HIGH_FREQUENCY_MAPPINGS:
        assert _ID.match(item.picker_color_id)
        assert item.vendor == "Bambu Lab"
        assert item.material == "PLA"
        assert _HEX.match(item.color_hex)
        assert item.bambu_code.isdigit()
        assert item.name_zh
        assert item.name_en


def test_lookup_round_trip_and_inventory_seed_shape() -> None:
    target = "bambu-lab/pla-basic/black-10101"
    found = lookup_by_picker_color_id(target)
    assert found is not None
    assert lookup_by_agent_filament_id(target) == found
    seed = as_inventory_seed(found)
    assert seed == {
        "filament_id": target,
        "vendor": "Bambu Lab",
        "material": "PLA",
        "color_hex": "000000",
        "diameter_mm": 1.75,
    }


def test_missing_mapping_is_not_silent() -> None:
    assert missing_mapping_warning(None) == "material_plan_filament_id_missing"
    assert missing_mapping_warning("") == "material_plan_filament_id_missing"
    assert (
        missing_mapping_warning("unknown/pla/red") == "unmapped_agent_filament_id:unknown/pla/red"
    )
    assert missing_mapping_warning("bambu-lab/pla-basic/black-10101") is None
    warnings = warn_unmapped_ids(
        ["bambu-lab/pla-basic/black-10101", "nope", None],
    )
    assert warnings == (
        "unmapped_agent_filament_id:nope",
        "material_plan_filament_id_missing",
    )
