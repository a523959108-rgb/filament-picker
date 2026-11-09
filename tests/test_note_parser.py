from __future__ import annotations

import json
from pathlib import Path

import pytest

from filament_picker.note_parser import Params, SampleRegion, parse_note, resolve_params
from filament_picker.validate import validate_json


@pytest.mark.parametrize(
    ("text", "values", "warnings"),
    (
        (
            "帮我配 4 色，AMS 一台，只要拓竹 PLA",
            {
                "max_colors": 4,
                "ams_slots": 4,
                "materials": ["PLA"],
                "brands": ["bambu-lab"],
            },
            (),
        ),
        ("黑白两色就行", {"max_colors": 2}, ()),
        (
            "8个槽 PETG 保留细节",
            {"ams_slots": 8, "materials": ["PETG"], "keep_small": True},
            (),
        ),
        ("两台AMS，只要官方色", {"ams_slots": 8, "allow_approx": False}, ()),
        ("display 用的", {}, ()),
        ("20色", {}, ("NOTE_VALUE_OUT_OF_RANGE:max_colors=20",)),
        ("", {}, ()),
    ),
)
def test_parse_note_spec_examples(
    text: str, values: dict[str, object], warnings: tuple[str, ...]
) -> None:
    parsed = parse_note(text)
    assert parsed.values == values
    assert parsed.warnings == warnings


@pytest.mark.parametrize(
    ("text", "values"),
    (
        ("3 colors", {"max_colors": 3}),
        ("色差小一点", {}),
        ("AMS lite 两台", {"ams_slots": 8}),
        ("有 AMS", {"ams_slots": 4}),
        ("pla 和 petg 都行", {"materials": ["PLA", "PETG"]}),
        ("易生或三绿", {"brands": ["sunlu", "esun"]}),
    ),
)
def test_parse_note_extra_examples(text: str, values: dict[str, object]) -> None:
    assert parse_note(text).values == values


def test_parse_note_zero_colors_warns() -> None:
    parsed = parse_note("0色")
    assert parsed.values == {}
    assert parsed.warnings == ("NOTE_VALUE_OUT_OF_RANGE:max_colors=0",)


def test_resolve_params_matches_result_example(repo_root: Path) -> None:
    params = resolve_params({}, parse_note("帮我配 4 色，AMS 一台，只要拓竹 PLA"))
    expected = json.loads(
        (repo_root / "docs/schemas/examples/result.example.json").read_text(encoding="utf-8")
    )["params"]
    assert params.to_dict() == expected


def test_resolve_constraints_override_note() -> None:
    params = resolve_params({"max_colors": 2}, parse_note("4色"))
    assert params.max_colors == 2
    assert params.n_colors == 2
    assert params.note_parsed == {"max_colors": 4}


def test_resolve_ams_constraints_affect_n_colors() -> None:
    assert resolve_params({"ams_slots": 3}, parse_note("4色")).n_colors == 3


def test_resolve_defaults() -> None:
    assert resolve_params(None, parse_note("")) == Params(4, 4, 4, ("PLA",), (), True, False, 2, {})


def test_resolve_regions_round_trip() -> None:
    params = resolve_params(
        {
            "regions": [
                {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
                {"space": "px", "x": 10, "y": 20, "r": 8},
            ]
        },
        parse_note(""),
    )
    assert params.regions == (
        SampleRegion(0.1, 0.2, "norm", 0.3, 0.4, None),
        SampleRegion(10, 20, "px", None, None, 8),
    )
    assert params.to_dict()["regions"] == [
        {"space": "norm", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
        {"space": "px", "x": 10.0, "y": 20.0, "r": 8.0},
    ]


def test_request_regions_validate(repo_root: Path) -> None:
    request = json.loads(
        (repo_root / "docs/schemas/examples/request.example.json").read_text(encoding="utf-8")
    )
    request["regions"] = [{"space": "norm", "x": 0.2, "y": 0.3, "w": 0.1, "h": 0.2}]
    request["constraints"] = {"regions": [{"x": 12, "y": 8, "space": "px", "r": 6}]}
    assert validate_json("request", request) == []
    request["regions"] = [{"x": 0.1, "y": 0.2, "w": 0.3}]
    assert validate_json("request", request)


def test_to_dict_validates_result_params(repo_root: Path) -> None:
    result = json.loads(
        (repo_root / "docs/schemas/examples/result.example.json").read_text(encoding="utf-8")
    )
    result["params"] = resolve_params(
        {}, parse_note("帮我配 4 色，AMS 一台，只要拓竹 PLA")
    ).to_dict()
    assert validate_json("result", result) == []
