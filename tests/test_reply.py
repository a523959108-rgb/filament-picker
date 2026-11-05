from __future__ import annotations

import json
from pathlib import Path

from filament_picker.reply import APPROX_NOTE, build_reply_markdown


def _example(repo_root: Path) -> dict:
    return json.loads(
        (repo_root / "docs/schemas/examples/result.example.json").read_text(encoding="utf-8")
    )


def test_reply_matches_golden(repo_root: Path) -> None:
    result = _example(repo_root)
    assert build_reply_markdown(result) == result["reply_markdown"]


def test_reply_without_card_url(repo_root: Path) -> None:
    result = _example(repo_root)
    expected = result["reply_markdown"].splitlines()
    expected.pop(1)
    result["card_url"] = None
    assert build_reply_markdown(result) == "\n".join(expected)
    assert "![配色卡]" not in build_reply_markdown(result)


def test_reply_approx_note_and_line(repo_root: Path) -> None:
    result = _example(repo_root)
    result["matches"][0]["picks"][0]["is_approx"] = True
    result["matches"][0]["picks"][0]["hex_source"] = "store_swatch"
    lines = build_reply_markdown(result).splitlines()
    assert any("（ΔE 4.4，接近，近似色）" in line for line in lines)
    assert lines[-2] == APPROX_NOTE


def test_reply_without_single_series(repo_root: Path) -> None:
    result = _example(repo_root)
    result["single_series_option"] = None
    assert "**同系列方案**" not in build_reply_markdown(result)


def test_reply_without_picks(repo_root: Path) -> None:
    result = _example(repo_root)
    result["matches"][0]["picks"] = []
    assert "   - 暂无 ΔE ≤ 10 的耗材" in build_reply_markdown(result).splitlines()


def test_reply_has_no_trailing_whitespace(repo_root: Path) -> None:
    result = _example(repo_root)
    reply = build_reply_markdown(result)
    assert all(line == line.rstrip() for line in reply.splitlines())
    assert not reply.endswith("\n")


def test_reply_error() -> None:
    result = {"status": "error", "error": {"message_zh": "出错了"}}
    assert build_reply_markdown(result) == "出错了"
