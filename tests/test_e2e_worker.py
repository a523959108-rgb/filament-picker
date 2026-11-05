from __future__ import annotations

import json
import subprocess
from pathlib import Path

from filament_picker.validate import validate_json
from helpers_images import square_on_white


def _request(
    request_id: str,
    image_path: Path,
    context: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "request_id": request_id,
        "created_at": "2026-11-05T14:03:12+09:00",
        "image_paths": [str(image_path)],
        "note": "",
        "constraints": {"materials": ["PETG"]},
        "context": context or {},
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_worker_e2e_success_missing_and_invalid(tmp_path: Path, repo_root: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    image = inbox / "black.png"
    square_on_white(image, "#000000")
    _write_json(
        inbox / "ok.request.json",
        _request("ok", image, {"conversationId": "cidOK", "senderStaffId": "staffOK"}),
    )
    _write_json(
        inbox / "missing.request.json",
        _request(
            "missing",
            inbox / "missing.png",
            {"conversationId": "cidMISSING", "senderStaffId": "staffMISSING"},
        ),
    )
    (inbox / "invalid.request.json").write_text("{", encoding="utf-8")

    completed = subprocess.run(
        [
            str(repo_root / ".venv/bin/filament-picker"),
            "worker",
            "--root",
            str(tmp_path),
            "--once",
            "--catalog",
            str(repo_root / "docs/schemas/examples/filament-catalog.example.json"),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    outbox = sorted((tmp_path / "outbox").glob("*.json"))
    assert len(outbox) == 3
    results = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in outbox}
    assert all(validate_json("result", result) == [] for result in results.values())
    assert results["ok"]["status"] == "ok"
    assert results["missing"]["status"] == "error"
    assert results["missing"]["error"]["code"] == "IMAGE_MISSING"
    assert results["invalid"]["status"] == "error"
    assert results["invalid"]["error"]["code"] == "INVALID_REQUEST"
    assert results["ok"]["context"] == {
        "conversationId": "cidOK",
        "senderStaffId": "staffOK",
    }
    assert results["missing"]["context"] == {
        "conversationId": "cidMISSING",
        "senderStaffId": "staffMISSING",
    }
    assert results["ok"]["reply_markdown"].splitlines()[0] == "### 配色方案（1 色）"
    assert "Bambu Lab PETG Basic" in results["ok"]["reply_markdown"]
    assert len(list((tmp_path / "done").glob("*.request.json"))) == 1
    assert len(list((tmp_path / "failed").glob("*.request.json"))) == 2


def test_smoke_worker_script(repo_root: Path) -> None:
    completed = subprocess.run(
        ["scripts/smoke_worker.sh"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines()[-1] == "smoke ok"


def test_forbidden_terms_are_absent_from_source_and_scripts(repo_root: Path) -> None:
    schema = repo_root / "src/filament_picker/schemas/request.schema.json"
    assert schema.read_text(encoding="utf-8").count("sessionWebhook") == 2
    for path in sorted((repo_root / "src").rglob("*")) + sorted((repo_root / "scripts").rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path == schema:
            text = text.replace("sessionWebhook", "")
        lowered = text.lower()
        assert "dingtalk" not in lowered, path
        assert "sessionwebhook" not in lowered, path
        assert "bambu-print-agent" not in lowered, path
