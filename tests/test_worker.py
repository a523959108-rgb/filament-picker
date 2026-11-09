from __future__ import annotations

import json
import os
import shutil
import signal
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


def _log_events(root: Path) -> list[dict[str, object]]:
    path = root / "logs/worker.log"
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _wait_for_events(root: Path, proc: subprocess.Popen[bytes], pred, timeout: float = 15) -> list:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"worker exited early: {proc.returncode}")
        events = _log_events(root)
        if pred(events):
            return events
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for log: {_log_events(root)}")


def _worker_command(tmp_root: Path, repo_root: Path, catalog: Path) -> list[str]:
    return [
        str(repo_root / ".venv/bin/filament-picker"),
        "worker",
        "--root",
        str(tmp_root),
        "--catalog",
        str(catalog),
    ]


def _stop_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)


def test_requeues_orphaned_processing_request(tmp_root: Path, repo_root: Path) -> None:
    image = tmp_root / "black.png"
    from helpers_images import square_on_white

    square_on_white(image, "#000000")
    path = _write_request(tmp_root, _request(image, "orphan"))
    path.rename(tmp_root / "processing" / path.name)
    catalog = repo_root / "docs/schemas/examples/filament-catalog.example.json"

    assert run_worker(tmp_root, catalog, True, None) == 0
    result = json.loads((tmp_root / "outbox/orphan.json").read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert (tmp_root / "done/orphan.request.json").is_file()
    assert not list((tmp_root / "processing").iterdir())
    assert any(
        event["event"] == "claimed"
        and event["detail"] == "requeued"
        and event["request_id"] == "orphan"
        for event in _log_events(tmp_root)
    )


def test_requeue_does_not_overwrite_inbox_request(tmp_root: Path, repo_root: Path) -> None:
    image = tmp_root / "black.png"
    from helpers_images import square_on_white

    square_on_white(image, "#000000")
    path = _write_request(tmp_root, _request(image, "same"))
    (tmp_root / "processing" / path.name).write_text("{not json", encoding="utf-8")
    catalog = repo_root / "docs/schemas/examples/filament-catalog.example.json"

    assert run_worker(tmp_root, catalog, True, None) == 0
    result = json.loads((tmp_root / "outbox/same.json").read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert (tmp_root / "done/same.request.json").is_file()
    assert (tmp_root / "failed/same.request.json").read_text(encoding="utf-8") == "{not json"


def test_cleanup_skips_file_that_cannot_be_unlinked(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_root / "inbox/old"
    path.write_text("old", encoding="utf-8")
    old = time.time() - 8 * 86400
    os.utime(path, (old, old))
    real_unlink = Path.unlink

    def flaky_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == "old":
            raise OSError("busy")
        real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    assert cleanup(tmp_root, time.time()) == 0
    assert path.exists()
    assert any(
        event["event"] == "error" and "busy" in str(event["detail"])
        for event in _log_events(tmp_root)
    )


def test_claim_oserror_does_not_stop_the_worker(
    tmp_root: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from filament_picker import worker as worker_module
    from helpers_images import square_on_white

    image = tmp_root / "black.png"
    square_on_white(image, "#000000")
    _write_request(tmp_root, _request(image, "a"))
    _write_request(tmp_root, _request(image, "b"))
    original = worker_module.claim

    def wrapped(req: Path, root: Path) -> Path | None:
        if req.name.startswith("a."):
            raise PermissionError("nope")
        return original(req, root)

    monkeypatch.setattr(worker_module, "claim", wrapped)
    catalog = repo_root / "docs/schemas/examples/filament-catalog.example.json"
    assert run_worker(tmp_root, catalog, True, None) == 0
    assert (tmp_root / "inbox/a.request.json").is_file()
    assert (tmp_root / "done/b.request.json").is_file()
    result = json.loads((tmp_root / "outbox/b.json").read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert any(event["detail"] == "nope" for event in _log_events(tmp_root))


def test_sigterm_exits_zero_and_second_worker_does_not_steal_processing(
    tmp_root: Path, repo_root: Path
) -> None:
    from helpers_images import square_on_white

    catalog = repo_root / "docs/schemas/examples/filament-catalog.example.json"
    command = _worker_command(tmp_root, repo_root, catalog)
    proc = subprocess.Popen(command, cwd=repo_root)
    try:
        _wait_for_events(
            tmp_root,
            proc,
            lambda events: any(event["event"] == "start" for event in events),
        )
        image = tmp_root / "black.png"
        square_on_white(image, "#000000")
        processing = tmp_root / "processing/inflight.request.json"
        processing.write_text(
            json.dumps(_request(image, "inflight"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        second = subprocess.run([*command, "--once"], cwd=repo_root, timeout=60, check=False)
        assert second.returncode == 0
        assert processing.is_file()
        assert not (tmp_root / "outbox/inflight.json").exists()
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=15) == 0
        third = subprocess.run([*command, "--once"], cwd=repo_root, timeout=60, check=False)
        assert third.returncode == 0
        assert (tmp_root / "done/inflight.request.json").is_file()
        assert not processing.exists()
        result = json.loads((tmp_root / "outbox/inflight.json").read_text(encoding="utf-8"))
        assert result["status"] == "ok"
    finally:
        _stop_process(proc)


def test_catalog_reload_and_failed_reload_keeps_running(tmp_root: Path, repo_root: Path) -> None:
    from helpers_images import square_on_white

    catalog = tmp_root.parent / "catalog.json"
    shutil.copy(repo_root / "docs/schemas/examples/filament-catalog.example.json", catalog)
    command = _worker_command(tmp_root, repo_root, catalog)
    proc = subprocess.Popen(command, cwd=repo_root)
    try:
        _wait_for_events(
            tmp_root,
            proc,
            lambda events: any(event["event"] == "start" for event in events),
        )
        replacement = catalog.with_name(f".{catalog.name}.tmp")
        replacement.write_text(catalog.read_text(encoding="utf-8"), encoding="utf-8")
        os.replace(replacement, catalog)
        _wait_for_events(
            tmp_root,
            proc,
            lambda events: any(event["event"] == "catalog_reload" for event in events),
        )
        replacement.write_text("{", encoding="utf-8")
        os.replace(replacement, catalog)
        _wait_for_events(
            tmp_root,
            proc,
            lambda events: (
                sum(
                    1
                    for event in events
                    if event["event"] == "error" and event["code"] == "CATALOG_ERROR"
                )
                >= 1
            ),
        )
        time.sleep(2.5)
        assert proc.poll() is None
        catalog_errors = [
            event
            for event in _log_events(tmp_root)
            if event["event"] == "error" and event["code"] == "CATALOG_ERROR"
        ]
        assert len(catalog_errors) == 1
        image = tmp_root / "black.png"
        square_on_white(image, "#000000")
        _write_request(tmp_root, _request(image, "still"))
        _wait_for_events(
            tmp_root,
            proc,
            lambda events: any(
                event["event"] == "done" and event["request_id"] == "still" for event in events
            ),
            timeout=20,
        )
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=15) == 0
    finally:
        _stop_process(proc)
