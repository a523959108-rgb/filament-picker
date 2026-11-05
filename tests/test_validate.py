import json
from pathlib import Path

import pytest

from filament_picker.validate import SchemaValidationError, assert_valid, load_schema, validate_json


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("schema", "filename"),
    (
        ("catalog", "filament-catalog.example.json"),
        ("lock", "ids.lock.example.json"),
        ("request", "request.example.json"),
        ("result", "result.example.json"),
        ("result", "result.error.example.json"),
    ),
)
def test_examples_are_valid(repo_root: Path, schema: str, filename: str) -> None:
    obj = read_json(repo_root / "docs/schemas/examples" / filename)
    assert validate_json(schema, obj) == []


@pytest.mark.parametrize(
    "filename",
    (
        "filament-catalog.schema.json",
        "ids.lock.schema.json",
        "request.schema.json",
        "result.schema.json",
    ),
)
def test_packaged_schemas_match_docs(repo_root: Path, filename: str) -> None:
    assert (repo_root / "src/filament_picker/schemas" / filename).read_bytes() == (
        repo_root / "docs/schemas" / filename
    ).read_bytes()


def test_catalog_hex_must_be_uppercase(repo_root: Path) -> None:
    obj = read_json(repo_root / "docs/schemas/examples/filament-catalog.example.json")
    obj["entries"][0]["hex"] = ["#00ae42"]
    errors = validate_json("catalog", obj)
    assert any(error.startswith("entries/0/hex/0") for error in errors)


def test_request_context_rejects_session_webhook(repo_root: Path) -> None:
    obj = read_json(repo_root / "docs/schemas/examples/request.example.json")
    obj.setdefault("context", {})["sessionWebhook"] = "x"
    assert validate_json("request", obj)


def test_assert_valid_raises() -> None:
    with pytest.raises(SchemaValidationError):
        assert_valid("request", {})


def test_unknown_schema() -> None:
    with pytest.raises(KeyError):
        load_schema("nope")
