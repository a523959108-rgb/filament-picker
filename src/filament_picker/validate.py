import json
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_FILES: dict[str, str] = {
    "catalog": "filament-catalog.schema.json",
    "lock": "ids.lock.schema.json",
    "request": "request.schema.json",
    "result": "result.schema.json",
}


class SchemaValidationError(ValueError):
    def __init__(self, name: str, errors: list[str]) -> None:
        self.name = name
        self.errors = errors
        super().__init__(f"{name}: " + "; ".join(errors))


@cache
def load_schema(name: str) -> dict[str, Any]:
    filename = SCHEMA_FILES[name]
    path = resources.files("filament_picker").joinpath("schemas", filename)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_json(name: str, obj: Any) -> list[str]:
    validator = Draft202012Validator(load_schema(name))
    messages: list[str] = []
    for error in validator.iter_errors(obj):
        path = "/".join(str(part) for part in error.absolute_path) or "<root>"
        messages.append(f"{path}: {error.message}")
    return sorted(messages)


def assert_valid(name: str, obj: Any) -> None:
    errors = validate_json(name, obj)
    if errors:
        raise SchemaValidationError(name, errors)
