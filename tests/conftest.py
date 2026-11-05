import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def raw_rows(repo_root: Path) -> list[dict]:
    path = repo_root / "data/raw/page_rows.json"
    if not path.exists():
        pytest.skip("data/raw 未就绪（T02）")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def golden_ids(repo_root: Path) -> list[dict]:
    data = json.loads((repo_root / "docs/fixtures/ids_golden.json").read_text(encoding="utf-8"))
    return data["rows"]


@pytest.fixture(scope="session")
def golden_merges(repo_root: Path) -> list[dict]:
    data = json.loads((repo_root / "docs/fixtures/merges_golden.json").read_text(encoding="utf-8"))
    return data["merges"]


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    root = tmp_path / "filament-picker"
    for directory in (
        "inbox",
        "processing",
        "done",
        "failed",
        "outbox",
        "public/cards",
        "logs",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    return root
