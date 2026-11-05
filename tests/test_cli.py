import json
import sys
from pathlib import Path

import pytest

from filament_picker.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out == "filament-picker 0.3.0\n"


def test_version_from_process_argv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["filament-picker", "--version"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert capsys.readouterr().out == "filament-picker 0.3.0\n"


def test_validate_valid(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "request", "docs/schemas/examples/request.example.json"]) == 0
    assert capsys.readouterr().out == "OK\n"


def test_validate_invalid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    assert main(["validate", "request", str(path)]) == 1
    assert capsys.readouterr().out.splitlines()


def test_no_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert capsys.readouterr().out
