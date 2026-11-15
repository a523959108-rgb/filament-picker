from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

from dtimg_outbox.outbox import (  # noqa: E402
    DEFAULT_MAX_BYTES,
    OutboxError,
    Settings,
    ack,
    enqueue_image,
    list_ready,
    open_inotify,
    process_once,
    watch,
)

TOKYO = ZoneInfo("Asia/Tokyo")
URL = "https://dtimg.ibaozi.com/20261115/abc.png"
FAKE_PUT = """#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
printf '%s\\n' "$1" >> "${DIR}/calls.log"
MODE="ok"
if [ -f "${DIR}/mode" ]; then
  MODE="$(tr -d '[:space:]' < "${DIR}/mode")"
fi
if [ "$MODE" = "fail" ]; then
  echo "temporary network error" >&2
  exit 1
fi
if [ "$MODE" = "bad" ]; then
  echo "unsupported extension" >&2
  exit 2
fi
printf '%s\\n' "https://dtimg.ibaozi.com/20261115/abc.png"
"""


def write_fake_put(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "put.sh"
    script.write_text(FAKE_PUT, encoding="utf-8")
    script.chmod(0o755)
    return script


def set_mode(put: Path, mode: str) -> None:
    (put.parent / "mode").write_text(mode + "\n", encoding="utf-8")


def calls(put: Path) -> list[str]:
    log = put.parent / "calls.log"
    if not log.exists():
        return []
    return [line for line in log.read_text(encoding="utf-8").splitlines() if line]


def make_settings(root: Path, put_sh: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "root": root,
        "put_sh": put_sh,
        "max_bytes": 10_485_760,
        "max_attempts": 3,
        "retry_base_sec": 0.0,
        "retry_cap_sec": 60.0,
        "stable_sec": 0.0,
        "poll_interval": 0.1,
        "put_timeout": 5.0,
        "log_path": root / "log" / "dtimg-outbox.log",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def write_image(inbox: Path, name: str, payload: bytes) -> Path:
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / name
    path.write_bytes(payload)
    return path


def ready_record(root: Path, stem: str) -> dict[str, object]:
    return json.loads((root / "ready" / f"{stem}.json").read_text(encoding="utf-8"))


def test_default_limit_matches_put_sh() -> None:
    assert DEFAULT_MAX_BYTES == 10_485_760


def test_pickup_writes_ready_and_replays_without_upload(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    root = tmp_path / "outbox"
    settings = make_settings(root, put)
    inbox = root / "inbox"
    payload = b"\x89PNG\r\n\x1a\ncat"
    meta = {
        "to": "耗材群",
        "text": "今日配色",
        "requested_by": "image-assistant",
        "created_at": "2026-11-15T10:00:00+09:00",
        "ticket": "T-1",
    }
    inbox.mkdir(parents=True)
    (inbox / "cat.json").write_text(
        json.dumps(meta, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_image(inbox, "cat.png", payload)

    report = process_once(settings)

    assert report.ready == ("cat",)
    assert calls(put) == [str(inbox / "cat.png")]
    raw = (root / "ready" / "cat.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert "耗材群" in raw
    record = json.loads(raw)
    assert record["photoURL"] == URL
    assert record["to"] == "耗材群"
    assert record["text"] == "今日配色"
    assert record["requested_by"] == "image-assistant"
    assert record["created_at"] == "2026-11-15T10:00:00+09:00"
    assert record["ticket"] == "T-1"
    assert record["sha256"] == hashlib.sha256(payload).hexdigest()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00", str(record["uploaded_at"]))
    assert record["deduped"] is False
    assert (root / "done" / "cat.png").is_file()
    assert (root / "done" / "cat.json").is_file()
    assert not (inbox / "cat.png").exists()
    log = (root / "log" / "dtimg-outbox.log").read_text(encoding="utf-8")
    assert re.search(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00 INFO uploaded ",
        log,
        re.M,
    )

    shutil.move(root / "done" / "cat.png", inbox / "cat.png")
    shutil.move(root / "done" / "cat.json", inbox / "cat.json")
    process_once(settings)
    assert calls(put) == [str(inbox / "cat.png")]
    assert not (inbox / "cat.png").exists()
    assert len(list(root.joinpath("ready").glob("*.json"))) == 1


def test_partial_and_fresh_files_wait(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    root = tmp_path / "outbox"
    settings = make_settings(root, put, stable_sec=5)
    inbox = root / "inbox"
    write_image(inbox, "foo.png.partial", b"partial")
    write_image(inbox, ".hidden.png", b"hidden")
    write_image(inbox, "bar.png.tmp", b"tmp")
    write_image(inbox, "empty.png", b"")
    fresh = write_image(inbox, "fresh.png", b"fresh")
    old = write_image(inbox, "old.png", b"old-enough")
    past = time.time() - 30
    os.utime(old, (past, past))

    report = process_once(settings, now=datetime.now(TOKYO))

    assert [Path(line).name for line in calls(put)] == ["old.png"]
    assert report.ready == ("old",)
    assert (inbox / "foo.png.partial").is_file()
    assert (inbox / ".hidden.png").is_file()
    assert (inbox / "bar.png.tmp").is_file()
    assert (inbox / "empty.png").is_file()
    assert fresh.is_file()
    assert not list((root / "failed").glob("*.error.json"))

    os.utime(fresh, (past, past))
    process_once(settings, now=datetime.now(TOKYO))
    assert (root / "ready" / "fresh.json").is_file()
    assert not fresh.exists()
    assert (inbox / "empty.png").is_file()
    assert [Path(line).name for line in calls(put)] == ["old.png", "fresh.png"]

    os.utime(inbox / "empty.png", (past, past))
    emptied = process_once(settings, now=datetime.now(TOKYO))
    assert "empty" in emptied.failed
    assert not (inbox / "empty.png").exists()
    empty_error = json.loads((root / "failed" / "empty.error.json").read_text(encoding="utf-8"))
    assert "空文件" in str(empty_error["error"])


def test_dedupe_reuses_url(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    root = tmp_path / "outbox"
    settings = make_settings(root, put)
    payload = b"same-bytes"
    write_image(root / "inbox", "one.png", payload)
    write_image(root / "inbox", "two.png", payload)

    process_once(settings)

    assert len(calls(put)) == 1
    first = ready_record(root, "one")
    second = ready_record(root, "two")
    assert first["photoURL"] == URL
    assert second["photoURL"] == URL
    assert first["sha256"] == second["sha256"] == hashlib.sha256(payload).hexdigest()
    assert first["deduped"] is False
    assert second["deduped"] is True
    assert (root / "done" / "one.png").is_file()
    assert (root / "done" / "two.png").is_file()


def test_retry_then_failed(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    set_mode(put, "fail")
    root = tmp_path / "outbox"
    settings = make_settings(root, put, max_attempts=2, retry_base_sec=0)
    image = write_image(root / "inbox", "x.png", b"retry-me")

    first = process_once(settings)
    assert first.failed == ()
    assert image.is_file()
    assert len(calls(put)) == 1
    assert not list((root / "failed").glob("*.error.json"))

    second = process_once(settings)
    assert second.failed == ("x",)
    assert not image.exists()
    assert len(calls(put)) == 2
    error = json.loads((root / "failed" / "x.error.json").read_text(encoding="utf-8"))
    assert error["attempts"] == 2
    assert "temporary network error" in error["error"]
    assert not list((root / "ready").glob("*.json"))
    assert (root / "failed" / "x.png").is_file()


def test_put_exit_2_does_not_retry(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    set_mode(put, "bad")
    root = tmp_path / "outbox"
    settings = make_settings(root, put, max_attempts=3, retry_base_sec=0)
    write_image(root / "inbox", "bad.png", b"nope")

    report = process_once(settings)

    assert report.failed == ("bad",)
    assert len(calls(put)) == 1
    error = json.loads((root / "failed" / "bad.error.json").read_text(encoding="utf-8"))
    assert "退出码 2" in error["error"]
    process_once(settings)
    assert len(calls(put)) == 1


def test_retry_waits_for_backoff(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    set_mode(put, "fail")
    root = tmp_path / "outbox"
    settings = make_settings(root, put, max_attempts=3, retry_base_sec=30)
    write_image(root / "inbox", "wait.png", b"wait")
    start = datetime(2026, 11, 15, 11, 0, 0, tzinfo=TOKYO)

    process_once(settings, now=start)
    process_once(settings, now=start + timedelta(seconds=10))
    assert len(calls(put)) == 1
    assert (root / "inbox" / "wait.png").is_file()

    process_once(settings, now=start + timedelta(seconds=30))
    assert len(calls(put)) == 2


def test_ack_moves_record_to_sent(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    root = tmp_path / "outbox"
    settings = make_settings(root, put)
    write_image(root / "inbox", "pic.png", b"pic")
    process_once(settings)
    record = ready_record(root, "pic")
    assert record["photoURL"] == URL

    dest = ack(settings, "pic")

    assert dest == root / "sent" / "pic.json"
    assert not (root / "ready" / "pic.json").exists()
    sent = json.loads(dest.read_text(encoding="utf-8"))
    assert sent["photoURL"] == URL
    assert str(sent["acked_at"]).endswith("+09:00")
    assert list_ready(settings) == []
    with pytest.raises(OutboxError, match="已经确认过"):
        ack(settings, "pic")
    with pytest.raises(OutboxError, match="id 不合法"):
        ack(settings, "../secret")


def test_symlink_is_not_uploaded(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    root = tmp_path / "outbox"
    settings = make_settings(root, put)
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    target = tmp_path / "secret.png"
    target.write_bytes(b"secret")
    link = inbox / "link.png"
    link.symlink_to(target)

    with pytest.raises(OutboxError, match="符号链接"):
        enqueue_image(settings, link, to=None, text=None, requested_by=None)
    assert link.is_symlink()
    assert calls(put) == []

    report = process_once(settings)
    assert report.failed == ("link",)
    assert calls(put) == []
    assert target.is_file()
    assert target.read_bytes() == b"secret"
    assert not link.exists()
    assert (root / "failed" / "link.png").is_symlink()
    error = json.loads((root / "failed" / "link.error.json").read_text(encoding="utf-8"))
    assert "符号链接" in str(error["error"])


def test_reject_bad_extension_and_oversize(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    root = tmp_path / "outbox"
    settings = make_settings(root, put, max_bytes=8)
    inbox = root / "inbox"
    write_image(inbox, "diagram.svg", b"<svg></svg>")
    write_image(inbox, "big.png", b"123456789")
    write_image(inbox, "bad.png", b"img")
    (inbox / "bad.json").write_text("{", encoding="utf-8")

    report = process_once(settings)

    assert calls(put) == []
    assert set(report.failed) == {"diagram", "big", "bad"}
    errors = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in (root / "failed").glob("*.error.json")
    }
    assert "不支持的扩展名" in errors["diagram.error.json"]["error"]
    assert "文件过大" in errors["big.error.json"]["error"]
    assert "上限 8" in errors["big.error.json"]["error"]
    assert "sidecar" in errors["bad.error.json"]["error"]
    assert not (inbox / "diagram.svg").exists()
    assert (root / "failed" / "big.png").is_file()


def test_allowed_extensions(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    root = tmp_path / "outbox"
    settings = make_settings(root, put)
    names = ["a.jpg", "b.jpeg", "c.png", "d.GIF", "e.webp", "f.bmp"]
    for name in names:
        write_image(root / "inbox", name, f"img-{name}".encode())

    process_once(settings)

    assert len(calls(put)) == len(names)
    for name in names:
        stem = Path(name).stem
        assert ready_record(root, stem)["photoURL"] == URL


def test_cli_put_watch_list_ack(tmp_path: Path) -> None:
    put = write_fake_put(tmp_path / "bin")
    root = tmp_path / "outbox"
    source = tmp_path / "配色.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\ncolor")
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("DTIMG_"):
            del env[key]
    env.update(
        {
            "PYTHONPATH": str(TOOL_ROOT),
            "DTIMG_OUTBOX": str(root),
            "DTIMG_PUT_SH": str(put),
            "DTIMG_STABLE_SEC": "0",
            "DTIMG_RETRY_BASE_SEC": "0",
            "DTIMG_MAX_ATTEMPTS": "2",
        }
    )

    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "dtimg_outbox", *args],
            cwd=TOOL_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    queued = run(
        [
            "put",
            str(source),
            "--to",
            "耗材群",
            "--text",
            "今日配色",
            "--requested-by",
            "image-assistant",
        ]
    )
    assert queued.returncode == 0, queued.stderr
    assert "已放入发件箱" in queued.stdout
    assert "id=配色" in queued.stdout
    assert (root / "inbox" / "配色.png").is_file()
    sidecar = json.loads((root / "inbox" / "配色.json").read_text(encoding="utf-8"))
    assert sidecar["to"] == "耗材群"
    assert sidecar["text"] == "今日配色"

    scanned = run(["watch", "--once"])
    assert scanned.returncode == 0, scanned.stderr
    assert "ready=1" in scanned.stdout
    listed = run(["list-ready", "--json"])
    assert listed.returncode == 0, listed.stderr
    records = json.loads(listed.stdout)
    assert records[0]["id"] == "配色"
    assert records[0]["to"] == "耗材群"
    assert records[0]["text"] == "今日配色"
    assert records[0]["photoURL"] == URL
    assert records[0]["requested_by"] == "image-assistant"

    acked = run(["ack", "配色"])
    assert acked.returncode == 0, acked.stderr
    assert "已确认" in acked.stdout
    empty = run(["list-ready"])
    assert empty.returncode == 0
    assert "没有待发送的图片" in empty.stdout
    assert (root / "sent" / "配色.json").is_file()

    (tmp_path / "note.svg").write_bytes(b"<svg/>")
    rejected = run(["put", str(tmp_path / "note.svg")])
    assert rejected.returncode == 2
    assert "不支持的扩展名" in rejected.stderr
    assert calls(put) == [str(root / "inbox" / "配色.png")]


def test_install_script_writes_unit_without_network(tmp_path: Path) -> None:
    home = tmp_path / "home"
    unit_dir = home / ".config" / "systemd" / "user"
    outbox = tmp_path / "outbox"
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["DTIMG_OUTBOX"] = str(outbox)
    env["DTIMG_PUT_SH"] = str(tmp_path / "put.sh")
    env["DTIMG_SYSTEMD_USER_DIR"] = str(unit_dir)
    env["DTIMG_INSTALL_NO_START"] = "1"
    proc = subprocess.run(
        ["bash", str(TOOL_ROOT / "install-user-service.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    unit = (unit_dir / "dtimg-outbox.service").read_text(encoding="utf-8")
    assert f"ExecStart={TOOL_ROOT / 'dtimg-outbox'} watch" in unit
    assert f"DTIMG_OUTBOX={outbox}" in unit
    assert "sampleImageMsg" not in unit
    assert re.search(r"\d+\.\d+\.\d+\.\d+", unit) is None
    assert (outbox / "inbox").is_dir()
    assert (outbox / "ready").is_dir()
    assert (outbox / "sent").is_dir()
    for name in ("install-user-service.sh", "run-nohup.sh", "run-tests.sh", "dtimg-outbox"):
        syntax = subprocess.run(
            ["bash", "-n", str(TOOL_ROOT / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert syntax.returncode == 0, syntax.stderr


def test_package_does_not_send_dingtalk() -> None:
    banned = (
        "oapi.dingtalk.com",
        "sampleImageMsg",
        "sessionWebhook",
        "urllib.request",
        "http.client",
    )
    for path in (TOOL_ROOT / "dtimg_outbox").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text
        assert re.search(r"\d+\.\d+\.\d+\.\d+", text) is None


def test_inotify_opens_on_linux(tmp_path: Path) -> None:
    fd = open_inotify(tmp_path)
    if fd is None:
        pytest.skip("内核不提供 inotify")
    os.close(fd)


def test_watch_one_iteration_uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    put = write_fake_put(tmp_path / "bin")
    root = tmp_path / "outbox"
    settings = make_settings(root, put, poll_interval=30)
    write_image(root / "inbox", "once.png", b"once")
    seen = {"n": 0}

    def stop() -> bool:
        seen["n"] += 1
        return seen["n"] > 1

    monkeypatch.setattr("dtimg_outbox.outbox._install_stop", lambda: stop)
    assert watch(settings, once=False, force_poll=True) is None
    assert seen["n"] == 2
    assert [Path(line).name for line in calls(put)] == ["once.png"]
    assert ready_record(root, "once")["photoURL"] == URL
