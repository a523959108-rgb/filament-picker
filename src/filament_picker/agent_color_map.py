"""Read-only color-card ↔ external print inventory id map (P1 slice).

Convention (shared id, no auto stock deduction, no printer I/O):
- ``picker_color_id``: filament-picker catalog ``entries[].id``
  (e.g. ``bambu-lab/pla-basic/black-10101``).
- ``agent_filament_id``: same string, meant for ``InventoryStore`` /
  ``MaterialPlanItem.filament_id`` so both products share one key.
- ``color_hex``: six hex digits without ``#``, matching agent ``Filament.color_hex``.
- ``bambu_code``: Bambu SKU code when the picker entry has ``code``.

This module is intentionally one-way documentation + lookup helpers. It does
not import or call any external print agent, does not reserve/release spools,
and does not open network sockets.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentColorMapping:
    picker_color_id: str
    agent_filament_id: str
    vendor: str
    material: str
    color_hex: str
    bambu_code: str
    name_zh: str
    name_en: str


# First-wave high-frequency Bambu PLA Basic colors (20). Expand per brand later.
HIGH_FREQUENCY_MAPPINGS: tuple[AgentColorMapping, ...] = (
    AgentColorMapping(
        "bambu-lab/pla-basic/black-10101",
        "bambu-lab/pla-basic/black-10101",
        "Bambu Lab",
        "PLA",
        "000000",
        "10101",
        "黑色",
        "Black",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/jade-white-10100",
        "bambu-lab/pla-basic/jade-white-10100",
        "Bambu Lab",
        "PLA",
        "FFFFFF",
        "10100",
        "玉石白",
        "Jade White",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/red-10200",
        "bambu-lab/pla-basic/red-10200",
        "Bambu Lab",
        "PLA",
        "C12E1F",
        "10200",
        "红色",
        "Red",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/blue-10601",
        "bambu-lab/pla-basic/blue-10601",
        "Bambu Lab",
        "PLA",
        "0A2989",
        "10601",
        "蓝色",
        "Blue",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/bambu-green-10501",
        "bambu-lab/pla-basic/bambu-green-10501",
        "Bambu Lab",
        "PLA",
        "00AE42",
        "10501",
        "拓竹绿",
        "Bambu Green",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/gray-10103",
        "bambu-lab/pla-basic/gray-10103",
        "Bambu Lab",
        "PLA",
        "8E9089",
        "10103",
        "灰色",
        "Gray",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/yellow-10400",
        "bambu-lab/pla-basic/yellow-10400",
        "Bambu Lab",
        "PLA",
        "F4EE2A",
        "10400",
        "黄色",
        "Yellow",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/orange-10300",
        "bambu-lab/pla-basic/orange-10300",
        "Bambu Lab",
        "PLA",
        "FF6A13",
        "10300",
        "橙色",
        "Orange",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/pink-10203",
        "bambu-lab/pla-basic/pink-10203",
        "Bambu Lab",
        "PLA",
        "F55A74",
        "10203",
        "粉色",
        "Pink",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/purple-10700",
        "bambu-lab/pla-basic/purple-10700",
        "Bambu Lab",
        "PLA",
        "5E43B7",
        "10700",
        "紫色",
        "Purple",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/beige-10201",
        "bambu-lab/pla-basic/beige-10201",
        "Bambu Lab",
        "PLA",
        "F7E6DE",
        "10201",
        "杏色",
        "Beige",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/dark-gray-10105",
        "bambu-lab/pla-basic/dark-gray-10105",
        "Bambu Lab",
        "PLA",
        "545454",
        "10105",
        "深灰",
        "Dark Gray",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/light-gray-10104",
        "bambu-lab/pla-basic/light-gray-10104",
        "Bambu Lab",
        "PLA",
        "D1D3D5",
        "10104",
        "浅灰",
        "Light Gray",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/cyan-10603",
        "bambu-lab/pla-basic/cyan-10603",
        "Bambu Lab",
        "PLA",
        "0086D6",
        "10603",
        "青色",
        "Cyan",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/brown-10800",
        "bambu-lab/pla-basic/brown-10800",
        "Bambu Lab",
        "PLA",
        "9D432C",
        "10800",
        "棕色",
        "Brown",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/silver-10102",
        "bambu-lab/pla-basic/silver-10102",
        "Bambu Lab",
        "PLA",
        "A6A9AA",
        "10102",
        "银色",
        "Silver",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/gold-10401",
        "bambu-lab/pla-basic/gold-10401",
        "Bambu Lab",
        "PLA",
        "E4BD68",
        "10401",
        "金色",
        "Gold",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/hot-pink-10204",
        "bambu-lab/pla-basic/hot-pink-10204",
        "Bambu Lab",
        "PLA",
        "F5547C",
        "10204",
        "桃红色",
        "Hot Pink",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/cobalt-blue-10604",
        "bambu-lab/pla-basic/cobalt-blue-10604",
        "Bambu Lab",
        "PLA",
        "0056B8",
        "10604",
        "钴蓝色",
        "Cobalt Blue",
    ),
    AgentColorMapping(
        "bambu-lab/pla-basic/turquoise-10605",
        "bambu-lab/pla-basic/turquoise-10605",
        "Bambu Lab",
        "PLA",
        "00B1B7",
        "10605",
        "松石绿",
        "Turquoise",
    ),
)

_BY_PICKER: dict[str, AgentColorMapping] = {
    item.picker_color_id: item for item in HIGH_FREQUENCY_MAPPINGS
}
_BY_AGENT: dict[str, AgentColorMapping] = {
    item.agent_filament_id: item for item in HIGH_FREQUENCY_MAPPINGS
}


def lookup_by_picker_color_id(picker_color_id: str) -> AgentColorMapping | None:
    return _BY_PICKER.get(picker_color_id)


def lookup_by_agent_filament_id(agent_filament_id: str) -> AgentColorMapping | None:
    return _BY_AGENT.get(agent_filament_id)


def missing_mapping_warning(agent_filament_id: str | None) -> str | None:
    """Return a non-silent warning when a material-plan id is absent from the map."""
    if agent_filament_id is None or agent_filament_id.strip() == "":
        return "material_plan_filament_id_missing"
    if lookup_by_agent_filament_id(agent_filament_id) is None:
        return f"unmapped_agent_filament_id:{agent_filament_id}"
    return None


def warn_unmapped_ids(agent_filament_ids: Iterable[str | None]) -> tuple[str, ...]:
    warnings: list[str] = []
    for filament_id in agent_filament_ids:
        warning = missing_mapping_warning(filament_id)
        if warning is not None:
            warnings.append(warning)
    return tuple(warnings)


def as_inventory_seed(mapping: AgentColorMapping) -> dict[str, str | float]:
    """Shape compatible with agent ``Filament`` fields (read-only seed helper)."""
    return {
        "filament_id": mapping.agent_filament_id,
        "vendor": mapping.vendor,
        "material": mapping.material,
        "color_hex": mapping.color_hex,
        "diameter_mm": 1.75,
    }
