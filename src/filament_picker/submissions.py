"""Private uploads. Files stay under the uploader's directory until validated.

A ready submission is visible only to that account. It is not added to anyone
else's library. STEP is refused unless FreeCAD's freecadcmd is installed.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import signal
import sqlite3
import struct
import subprocess
import sys
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image

from .config import TZ
from .mesh_derive import DeriveError

_USER = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
_ID = re.compile(r"^m-[0-9a-f]{16}$")
_SUB = re.compile(r"^sub-[0-9a-f]{16}$")
_MAX_BYTES = 32 * 1024 * 1024
_MAX_TRIANGLES = 1_500_000
_MAX_ATTEMPTS = 3
_CHECK_TIMEOUT = 25
_SLOTS = threading.BoundedSemaphore(2)


def submissions_enabled() -> bool:
    return os.environ.get("FILAMENT_PICKER_SUBMISSIONS", "0") == "1"


class SubmissionError(Exception):
    def __init__(self, detail: str, *, status: int = 400) -> None:
        self.detail = detail
        self.status = status
        super().__init__(detail)


def step_dependency() -> str | None:
    if shutil.which("freecadcmd"):
        return None
    return "freecadcmd"


def accept_upload(
    root: Path, manifest: Path, username: str, filename: str, data: bytes
) -> dict[str, Any]:
    if not submissions_enabled():
        raise SubmissionError("投稿未开放", status=403)
    if _USER.fullmatch(username) is None:
        raise SubmissionError("账号名无效", status=403)
    suffix = PurePosixPath(filename or "").suffix.lower()
    if suffix not in {".3mf", ".stl", ".step", ".stp"}:
        raise SubmissionError("只接受 .3mf、.stl，以及显式开启后的 .step/.stp")
    if suffix in {".step", ".stp"} and os.environ.get("FILAMENT_PICKER_STEP", "0") != "1":
        raise SubmissionError(
            "STEP 转换默认关闭，尚未实现。需要 FILAMENT_PICKER_STEP=1 和本机 freecadcmd。"
            "缺命令时的拒绝不是已经实现的转换。"
        )
    if len(data) > _MAX_BYTES:
        raise SubmissionError("文件超过 32MB", status=413)
    if len(data) < 16:
        raise SubmissionError("文件太小")
    content_sha = hashlib.sha256(data).hexdigest()
    submission_id = "sub-" + secrets.token_hex(8)
    _ensure_submissions(manifest)
    _keep_upload(root, username, submission_id, suffix, data)
    _insert_submission(
        manifest, submission_id, username, filename, suffix, len(data), content_sha, "queued"
    )
    return _process(root, manifest, username, submission_id, suffix, data, content_sha)


def list_submissions(manifest: Path, username: str) -> list[dict[str, Any]]:
    _ensure_submissions(manifest)
    with closing(_conn(manifest)) as conn:
        rows = conn.execute(
            "SELECT id, status, filename, suffix, size_bytes, sha256, error, model_id, attempts, "
            "created_at, updated_at FROM submissions WHERE username = ? ORDER BY created_at, id",
            (username,),
        ).fetchall()
    return [_public(row) for row in rows]


def retry_submission(
    root: Path, manifest: Path, username: str, submission_id: str
) -> dict[str, Any]:
    if _SUB.fullmatch(submission_id) is None:
        raise SubmissionError("没有这份投稿", status=404)
    row = _get(manifest, submission_id, username)
    if row is None:
        raise SubmissionError("没有这份投稿", status=404)
    if row["status"] != "failed":
        raise SubmissionError("只有失败的投稿可以重试", status=409)
    if int(row["attempts"]) >= _MAX_ATTEMPTS:
        raise SubmissionError("已达到重试次数", status=409)
    path = _inbox_file(root, username, submission_id, row["suffix"])
    if path is None:
        raise SubmissionError("原上传已清理，不能重试", status=409)
    data = path.read_bytes()
    return _process(root, manifest, username, submission_id, row["suffix"], data, row["sha256"])


def _process(
    root: Path,
    manifest: Path,
    username: str,
    submission_id: str,
    suffix: str,
    data: bytes,
    content_sha: str,
) -> dict[str, Any]:
    _mark(manifest, submission_id, "processing", None)
    try:
        if hashlib.sha256(data).hexdigest() != content_sha:
            raise SubmissionError("内容和记录的校验不一致")
        if suffix not in {".3mf", ".stl", ".step", ".stp"}:
            raise SubmissionError("只接受 .3mf、.stl，以及显式开启后的 STEP")
        if suffix in {".step", ".stp"} and os.environ.get("FILAMENT_PICKER_STEP", "0") != "1":
            raise SubmissionError(
                "STEP 转换默认关闭。设置 FILAMENT_PICKER_STEP=1 且安装 freecadcmd 后才会尝试。"
                "缺命令时的拒绝不是已经实现的 STEP 转换。"
            )
    except (SubmissionError, DeriveError, OSError, ValueError) as exc:
        detail = exc.detail if isinstance(exc, (SubmissionError, DeriveError)) else "处理失败"
        _mark(manifest, submission_id, "failed", detail)
        failed = _get(manifest, submission_id, username)
        if failed is None:
            raise SubmissionError(detail) from exc
        return failed
    model_id = "m-" + secrets.token_hex(8)
    stored = _account_file(root, username, "originals", f"{model_id}{suffix}")
    stored.write_bytes(data)
    stored.chmod(0o600)
    title = f"投稿 {submission_id[-6:]}"
    _insert_model(manifest, model_id, username, title, suffix, len(data), stored)
    _write_thumb(root, model_id, content_sha)
    try:
        _run_isolated(root, model_id, stored, suffix, content_sha)
    except SubmissionError as exc:
        _mark(manifest, submission_id, "failed", exc.detail)
        failed = _get(manifest, submission_id, username)
        if failed is None:
            raise
        return failed
    _mark(manifest, submission_id, "ready", None, model_id=model_id)
    ready = _get(manifest, submission_id, username)
    if ready is None:
        raise SubmissionError("投稿记录丢失", status=500)
    return ready


def _run_isolated(root: Path, model_id: str, stored: Path, suffix: str, content_sha: str) -> None:
    free = shutil.disk_usage(root).free
    if free < stored.stat().st_size + 64 * 1024 * 1024:
        raise SubmissionError("磁盘空间不足", status=507)
    if not _SLOTS.acquire(timeout=1):
        raise SubmissionError("同时处理的投稿过多", status=429)
    command = [
        sys.executable,
        "-m",
        "filament_picker.upload_check",
        suffix,
        str(stored),
        str(root),
        model_id,
        content_sha,
    ]
    proc = subprocess.Popen(
        command,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _stdout, stderr = proc.communicate(timeout=_CHECK_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise SubmissionError("处理超时，已停止该进程") from None
    finally:
        _SLOTS.release()
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip().splitlines()
        raise SubmissionError(detail[-1] if detail else "校验失败")


def _parse_stl(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    if data[:5].lower() == b"solid" and b"\x00" not in data[:80]:
        vertices: list[tuple[float, float, float]] = []
        for line in data.decode("utf-8", "replace").splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].lower() == "vertex":
                try:
                    vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError as exc:
                    raise SubmissionError("STL 顶点不是数字") from exc
        if len(vertices) < 3 or len(vertices) % 3:
            raise SubmissionError("STL 三角面不完整")
        if len(vertices) // 3 > _MAX_TRIANGLES:
            raise SubmissionError("STL 三角面过多")
        points = np.asarray(vertices, dtype=np.float64)
        faces = np.arange(len(points), dtype=np.int64).reshape(-1, 3)
        return points, faces
    if len(data) < 84:
        raise SubmissionError("STL 太短")
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + count * 50
    if count < 1 or count > _MAX_TRIANGLES or expected != len(data):
        raise SubmissionError("STL 三角面数量和文件长度不一致")
    points = np.empty((count * 3, 3), dtype=np.float64)
    for index in range(count):
        start = 84 + index * 50 + 12
        raw = struct.unpack_from("<9f", data, start)
        points[index * 3] = raw[0:3]
        points[index * 3 + 1] = raw[3:6]
        points[index * 3 + 2] = raw[6:9]
    faces = np.arange(count * 3, dtype=np.int64).reshape(-1, 3)
    return points, faces


def _reject_zip_bomb(data: bytes) -> None:
    import zipfile

    try:
        archive = zipfile.ZipFile(__import__("io").BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SubmissionError("不是有效的 3MF 压缩包") from exc
    total = 0
    try:
        for info in archive.infolist():
            name = info.filename
            pure = PurePosixPath(name)
            if name.startswith("/") or "\\" in name or ".." in pure.parts:
                raise SubmissionError("3MF 路径不安全")
            total += info.file_size
            if info.file_size > _MAX_BYTES:
                raise SubmissionError("3MF 里有过大的文件")
        if total > max(len(data) * 80, 8 * 1024 * 1024) and total > len(data) * 50:
            raise SubmissionError("3MF 压缩比异常")
    finally:
        archive.close()


def _insert_model(
    manifest: Path, model_id: str, username: str, title: str, suffix: str, size: int, stored: Path
) -> None:
    now = datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
    rel = stored.resolve().relative_to(manifest.parent.resolve()).as_posix()
    with closing(_conn(manifest)) as conn, conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(models)")]
        if "owner" not in columns:
            conn.execute("ALTER TABLE models ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
            columns.append("owner")
        values = {
            "id": model_id,
            "sha256": hashlib.sha256(model_id.encode()).hexdigest(),
            "title": title,
            "series": "投稿",
            "author": username,
            "source_relpath": rel,
            "size_bytes": size,
            "plate_count": 1,
            "colours": "[]",
            "thumb_path": f"thumbs/{model_id}.png",
            "created_at": now,
            "description": "仅投稿者可见，未进入他人的模型库。",
            "owner": username,
            "plate_layout": "[]",
            "images": "[]",
            "dedupe_key": content_key(model_id),
            "updated_at": now,
        }
        present = [name for name in values if name in columns]
        sql = (
            f"INSERT INTO models ({', '.join(present)}) VALUES ({', '.join('?' for _ in present)})"
        )
        conn.execute(sql, [values[name] for name in present])


def content_key(model_id: str) -> str:
    return "submission:" + model_id


def _write_thumb(root: Path, model_id: str, digest: str) -> None:
    colour = "#" + digest[:6]
    image = Image.new("RGB", (640, 400), "#0d1c2d")
    swatch = Image.new("RGB", (180, 180), colour)
    image.paste(swatch, (230, 110))
    path = root / "thumbs" / f"{model_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _account_file(root: Path, username: str, kind: str, name: str) -> Path:
    directory = root.resolve() / "accounts" / username / kind
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / name
    if path.parent != directory:
        raise SubmissionError("存储路径无效")
    return path


def _inbox_file(root: Path, username: str, submission_id: str, suffix: str) -> Path | None:
    path = root / "accounts" / username / "inbox" / submission_id / f"upload{suffix}"
    if path.is_file() and not path.is_symlink():
        return path
    return None


def _keep_upload(root: Path, username: str, submission_id: str, suffix: str, data: bytes) -> None:
    directory = root.resolve() / "accounts" / username / "inbox" / submission_id
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = directory / f"upload{suffix}"
    target.write_bytes(data)
    target.chmod(0o600)


def _ensure_submissions(manifest: Path) -> None:
    with closing(_conn(manifest)) as conn, conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS submissions ("
            "id TEXT PRIMARY KEY, username TEXT NOT NULL, status TEXT NOT NULL, "
            "filename TEXT NOT NULL, suffix TEXT NOT NULL, size_bytes INTEGER NOT NULL, "
            "sha256 TEXT NOT NULL, error TEXT, model_id TEXT, attempts INTEGER NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )


def _insert_submission(
    manifest: Path,
    submission_id: str,
    username: str,
    filename: str,
    suffix: str,
    size: int,
    digest: str,
    status: str,
) -> None:
    now = datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
    safe_name = Path(filename).name[:120] or f"upload{suffix}"
    with closing(_conn(manifest)) as conn, conn:
        conn.execute(
            "INSERT INTO submissions (id, username, status, filename, suffix, size_bytes, sha256, "
            "error, model_id, attempts, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?, ?)",
            (submission_id, username, status, safe_name, suffix, size, digest, now, now),
        )


def _mark(
    manifest: Path,
    submission_id: str,
    status: str,
    error: str | None,
    *,
    model_id: str | None = None,
) -> None:
    now = datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
    with closing(_conn(manifest)) as conn, conn:
        if status == "failed":
            conn.execute(
                "UPDATE submissions SET status = ?, error = ?, attempts = attempts + 1, "
                "updated_at = ? "
                "WHERE id = ?",
                (status, error, now, submission_id),
            )
            return
        if model_id is None:
            conn.execute(
                "UPDATE submissions SET status = ?, error = NULL, updated_at = ? WHERE id = ?",
                (status, now, submission_id),
            )
        else:
            conn.execute(
                "UPDATE submissions SET status = ?, error = NULL, model_id = ?, "
                "updated_at = ? WHERE id = ?",
                (status, model_id, now, submission_id),
            )


def _get(manifest: Path, submission_id: str, username: str) -> dict[str, Any] | None:
    _ensure_submissions(manifest)
    with closing(_conn(manifest)) as conn:
        row = conn.execute(
            "SELECT * FROM submissions WHERE id = ? AND username = ?",
            (submission_id, username),
        ).fetchone()
    if row is None:
        return None
    return _public(row)


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "status": row["status"],
        "filename": row["filename"],
        "suffix": row["suffix"],
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "error": row["error"],
        "model_id": row["model_id"],
        "attempts": row["attempts"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "retryable": row["status"] == "failed" and int(row["attempts"]) < _MAX_ATTEMPTS,
    }


def _conn(manifest: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(manifest)
    conn.row_factory = sqlite3.Row
    return conn
