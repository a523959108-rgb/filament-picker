from __future__ import annotations

import json
import os
import signal
import time
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import planner
from .catalog import Catalog, CatalogValidationError, load_catalog
from .config import CLEANUP_INTERVAL_S, RETENTION_DAYS, TZ, WORKER_POLL_S
from .validate import validate_json

SUBDIRS: tuple[str, ...] = (
    "inbox",
    "processing",
    "done",
    "failed",
    "outbox",
    "public/cards",
    "logs",
)
CLEAN_DIRS: tuple[str, ...] = ("inbox", "done", "failed", "outbox", "public/cards")
REQ_SUFFIX: str = ".request.json"


def ensure_dirs(root: Path) -> None:
    for subdir in SUBDIRS:
        (root / subdir).mkdir(parents=True, exist_ok=True)


def request_id_from_name(name: str) -> str:
    return name.removesuffix(REQ_SUFFIX)


def claim(req: Path, root: Path) -> Path | None:
    destination = root / "processing" / req.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(req, destination)
    except FileNotFoundError:
        return None
    return destination


def write_json_atomic(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _now() -> datetime:
    return datetime.now(ZoneInfo(TZ))


def _log(
    root: Path,
    event: str,
    request_id: str | None = None,
    status: str | None = None,
    code: str | None = None,
    elapsed_ms: int | None = None,
    detail: str | None = None,
) -> None:
    record = {
        "ts": _now().isoformat(timespec="seconds"),
        "event": event,
        "request_id": request_id,
        "status": status,
        "code": code,
        "elapsed_ms": elapsed_ms,
        "detail": detail,
    }
    try:
        log_path = root / "logs" / "worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _invalid_request_result(
    path: Path,
    request: dict[str, Any],
    catalog: Catalog,
    now: Callable[[], datetime],
) -> dict[str, Any]:
    finished = now()
    invalid = {
        "request_id": request_id_from_name(path.name),
        "created_at": request.get("created_at", finished.isoformat(timespec="seconds")),
        "context": request.get("context", {}),
    }
    if not isinstance(invalid["created_at"], str):
        invalid["created_at"] = finished.isoformat(timespec="seconds")
    if not isinstance(invalid["context"], dict):
        invalid["context"] = {}
    return planner.error_result(
        invalid,
        "INVALID_REQUEST",
        finished.isoformat(timespec="seconds"),
        0,
        {},
        catalog.generated_at,
        [],
    )


def process_request(
    path: Path,
    catalog: Catalog,
    root: Path,
    card_base_url: str | None,
    now: Callable[[], datetime],
) -> dict[str, Any]:
    request_id = request_id_from_name(path.name)
    try:
        request_obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        result = _invalid_request_result(path, {}, catalog, now)
        _log(root, "error", request_id, "error", "INVALID_REQUEST", 0, "invalid request")
        return result
    try:
        if not isinstance(request_obj, dict) or validate_json("request", request_obj):
            request = request_obj if isinstance(request_obj, dict) else {}
            result = _invalid_request_result(path, request, catalog, now)
            _log(root, "error", request_id, "error", "INVALID_REQUEST", 0, "invalid request")
            return result
        result = planner.run_plan(request_obj, catalog, root, now, card_base_url)
        return result
    except Exception as exc:
        finished = _now()
        result = planner.error_result(
            {
                "request_id": request_id,
                "created_at": finished.isoformat(timespec="seconds"),
                "context": {},
            },
            "INTERNAL",
            finished.isoformat(timespec="seconds"),
            0,
            {},
            catalog.generated_at,
            [],
        )
        _log(
            root,
            "error",
            request_id,
            "error",
            "INTERNAL",
            0,
            traceback.format_exc(),
        )
        del exc
        return result


def cleanup(root: Path, now: float) -> int:
    cutoff = now - RETENTION_DAYS * 86400
    removed = 0
    for directory in CLEAN_DIRS:
        path = root / directory
        if not path.is_dir():
            continue
        for child in path.iterdir():
            if not child.is_file():
                continue
            try:
                if child.stat().st_mtime < cutoff:
                    child.unlink()
                    removed += 1
            except FileNotFoundError:
                continue
    return removed


def _request_files(root: Path) -> list[Path]:
    entries: list[tuple[float, str, Path]] = []
    for path in (root / "inbox").glob(f"*{REQ_SUFFIX}"):
        try:
            entries.append((path.stat().st_mtime, path.name, path))
        except FileNotFoundError:
            continue
    return [path for _, _, path in sorted(entries)]


def run_worker(root: Path, catalog_path: Path, once: bool, card_base_url: str | None) -> int:
    ensure_dirs(root)
    _log(root, "start")
    try:
        catalog = load_catalog(catalog_path)
        catalog_mtime = catalog_path.stat().st_mtime_ns
    except (OSError, CatalogValidationError, ValueError) as exc:
        _log(root, "error", code="CATALOG_ERROR", detail=str(exc))
        return 2

    stopping = False

    def stop_handler(signum: int, frame: Any) -> None:
        del signum, frame
        nonlocal stopping
        stopping = True

    previous_int = signal.signal(signal.SIGINT, stop_handler)
    previous_term = signal.signal(signal.SIGTERM, stop_handler)
    last_cleanup = 0.0
    try:
        while True:
            try:
                current_mtime = catalog_path.stat().st_mtime_ns
                if current_mtime != catalog_mtime:
                    catalog = load_catalog(catalog_path)
                    catalog_mtime = current_mtime
                    _log(root, "catalog_reload")
            except (OSError, CatalogValidationError, ValueError) as exc:
                _log(root, "error", code="CATALOG_ERROR", detail=str(exc))

            for request in _request_files(root):
                claimed = claim(request, root)
                if claimed is None:
                    continue
                request_id = request_id_from_name(claimed.name)
                _log(root, "claimed", request_id)
                started = time.monotonic()
                try:
                    result = process_request(claimed, catalog, root, card_base_url, _now)
                    result_id = str(result.get("request_id", request_id))
                    write_json_atomic(root / "outbox" / f"{result_id}.json", result)
                    destination_dir = "done" if result.get("status") == "ok" else "failed"
                    os.replace(claimed, root / destination_dir / claimed.name)
                    _log(
                        root,
                        "done",
                        request_id,
                        result.get("status"),
                        (result.get("error") or {}).get("code")
                        if isinstance(result.get("error"), dict)
                        else None,
                        round((time.monotonic() - started) * 1000),
                    )
                except (OSError, ValueError, TypeError) as exc:
                    _log(
                        root,
                        "error",
                        request_id,
                        "error",
                        "INTERNAL",
                        round((time.monotonic() - started) * 1000),
                        str(exc),
                    )
                    try:
                        if claimed.exists():
                            os.replace(claimed, root / "failed" / claimed.name)
                    except OSError:
                        pass
                if stopping:
                    break

            current_time = time.time()
            if current_time - last_cleanup >= CLEANUP_INTERVAL_S:
                removed = cleanup(root, current_time)
                _log(root, "cleanup", detail=str(removed))
                last_cleanup = current_time
            if once or stopping:
                return 0
            time.sleep(WORKER_POLL_S)
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
