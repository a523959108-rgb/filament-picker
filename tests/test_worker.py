from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from filament_picker.catalog import load_catalog
from filament_picker.validate import validate_json
from filament_picker.worker import (
    CLEAN_DIRS,
    REQ_SUFFIX,
    claim,
    cleanup,
    process_request,
    run_worker,
    write_json_atomic,
)


def _request(image: Path, request_id: str = "msgEXAMPLE0001", **extra: object) -> dict:
    request = {
        "schema_version": 1,
        "request_id": request_id,
        "created_at": "2026-11-05T14:03:12+09:00",
        "image_paths": [str(image)],
        "note": "",
        "constraints": {"materials": ["PETG"]},
        "context": {"conversationId": "cidEXAMPLE"},
    }
    request.update(extra)
    return request


@pytest.fixture
def example_catalog(repo_root: Path):
    return load_catalog(repo_root / "docs/schemas/examples/filament-catalog.example.json")


def _write_request(root: Path, request: dict, name: str | None = None) -> Path:
    request_id = name or request["request_id"]
    path = root / "inbox" / f"{request_id}{REQ_SUFFIX}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_worker_success(tmp_root: Path, repo_root: Path) -> None:
    image = tmp_root / "black.png"
    from helpers_images import square_on_white

    square_on_white(image, "#000000")
    _write_request(tmp_root, _request(image))
    catalog_path = repo_root / "docs/schemas/examples/filament-catalog.example.json"

    assert run_worker(tmp_root, catalog_path, True, None) == 0
    result_path = tmp_root / "outbox/msgEXAMPLE0001.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert validate_json("result", result) == []
    assert result["status"] == "ok"
    assert result["matches"][0]["picks"][0]["id"] == ("bambu-lab/petg-basic/black-30105")
    assert (tmp_root / "done/msgEXAMPLE0001.request.json").is_file()
    assert not list((tmp_root / "processing").iterdir())
    assert not list((tmp_root / "inbox").iterdir())


def test_worker_invalid_json_moves_to_failed(tmp_root: Path, repo_root: Path) -> None:
    path = tmp_root / "inbox/bad.request.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert (
        run_worker(
            tmp_root, repo_root / "docs/schemas/examples/filament-catalog.example.json", True, None
        )
        == 0
    )
    result = json.loads((tmp_root / "outbox/bad.json").read_text(encoding="utf-8"))
    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_REQUEST"
    assert (tmp_root / "failed/bad.request.json").is_file()


def test_worker_rejects_session_webhook(tmp_root: Path, repo_root: Path) -> None:
    image = tmp_root / "black.png"
    from helpers_images import square_on_white

    square_on_white(image, "#000000")
    _write_request(tmp_root, _request(image, context={"sessionWebhook": "secret"}), "badcontext")
    assert (
        run_worker(
            tmp_root, repo_root / "docs/schemas/examples/filament-catalog.example.json", True, None
        )
        == 0
    )
    result = json.loads((tmp_root / "outbox/badcontext.json").read_text(encoding="utf-8"))
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_worker_ignores_temporary_requests_and_images(tmp_root: Path, repo_root: Path) -> None:
    inbox = tmp_root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "pending.request.json.tmp").write_text("{}", encoding="utf-8")
    (inbox / "photo.png").write_bytes(b"not a request")
    assert (
        run_worker(
            tmp_root, repo_root / "docs/schemas/examples/filament-catalog.example.json", True, None
        )
        == 0
    )
    assert (inbox / "pending.request.json.tmp").exists()
    assert (inbox / "photo.png").exists()


def test_process_request_internal_error_is_logged(
    tmp_root: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import filament_picker.planner as planner

    image = tmp_root / "black.png"
    from helpers_images import square_on_white

    square_on_white(image, "#000000")
    path = _write_request(tmp_root, _request(image))
    catalog = load_catalog(repo_root / "docs/schemas/examples/filament-catalog.example.json")
    monkeypatch.setattr(
        planner,
        "run_plan",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    from datetime import datetime

    result = process_request(path, catalog, tmp_root, None, datetime.now)
    assert result["status"] == "error"
    assert result["error"]["code"] == "INTERNAL"
    assert "boom" not in json.dumps(result, ensure_ascii=False)
    log = (tmp_root / "logs/worker.log").read_text(encoding="utf-8")
    events = [json.loads(line) for line in log.splitlines()]
    assert any(event["event"] == "error" and "boom" in event["detail"] for event in events)


def test_claim_is_atomic(tmp_root: Path) -> None:
    path = tmp_root / "inbox/abc.request.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    (tmp_root / "processing").mkdir(exist_ok=True)
    assert claim(path, tmp_root) == tmp_root / "processing/abc.request.json"
    assert claim(path, tmp_root) is None


def test_two_workers_claim_each_request_once(tmp_root: Path, repo_root: Path) -> None:
    from helpers_images import square_on_white

    image = tmp_root / "black.png"
    square_on_white(image, "#000000")
    for index in range(10):
        _write_request(tmp_root, _request(image, f"msg{index:02d}"))
    catalog = str(repo_root / "docs/schemas/examples/filament-catalog.example.json")
    command = [
        str(repo_root / ".venv/bin/filament-picker"),
        "worker",
        "--root",
        str(tmp_root),
        "--once",
        "--catalog",
        catalog,
    ]
    first = subprocess.Popen(command)
    second = subprocess.Popen(command)
    assert first.wait(timeout=30) == 0
    assert second.wait(timeout=30) == 0
    assert len(list((tmp_root / "outbox").glob("*.json"))) == 10
    assert len(list((tmp_root / "done").glob("*.request.json"))) == 10
    events = [json.loads(line) for line in (tmp_root / "logs/worker.log").read_text().splitlines()]
    done = [event for event in events if event["event"] == "done"]
    assert len(done) == 10
    assert len({event["request_id"] for event in done}) == 10


def test_cleanup_only_old_regular_files(tmp_root: Path) -> None:
    old = time.time() - 8 * 86400
    for directory in CLEAN_DIRS:
        path = tmp_root / directory
        path.mkdir(parents=True, exist_ok=True)
        (path / "old").write_text("old", encoding="utf-8")
        os.utime(path / "old", (old, old))
        (path / "new").write_text("new", encoding="utf-8")
    keep = tmp_root / "inbox/keep"
    keep.mkdir(parents=True)
    os.utime(keep, (old, old))
    (tmp_root / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_root / "logs/old").write_text("old", encoding="utf-8")
    os.utime(tmp_root / "logs/old", (old, old))
    assert cleanup(tmp_root, time.time()) == 5
    assert all((tmp_root / directory / "new").exists() for directory in CLEAN_DIRS)
    assert keep.is_dir()
    assert (tmp_root / "logs/old").exists()


def test_run_worker_catalog_error(tmp_root: Path) -> None:
    assert run_worker(tmp_root, tmp_root / "missing.json", True, None) == 2
    events = [json.loads(line) for line in (tmp_root / "logs/worker.log").read_text().splitlines()]
    assert any(event["event"] == "error" and event["code"] == "CATALOG_ERROR" for event in events)


def test_write_json_atomic_leaves_no_tmp(tmp_root: Path) -> None:
    path = tmp_root / "outbox/result.json"
    write_json_atomic(path, {"ok": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
    assert not list(path.parent.glob("*.tmp"))
