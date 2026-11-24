"""Expiring, revocable grants for one private model.

The raw token is returned once and only its SHA-256 is stored. Anonymous
callers present that token to open a short session cookie. Every later image
or mesh request checks the cookie again. Nothing is public unless a logged-in
user creates a grant, and downloads stay off unless that user turns them on.
"""

from __future__ import annotations

import hashlib
import math
import re
import secrets
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from .auth import auth_db_path
from .config import TZ

_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_GRANT_ID = re.compile(r"^[A-Za-z0-9_-]{16,32}$")
_DAYS = {1, 7, 30}
_FAIL_LIMIT = 8
_FAIL_WINDOW = 60.0
_MAX_GRANTS = 100
COOKIE_NAME = "fp_share"
_FAILURES: dict[str, tuple[int, float]] = {}
_LOCK = threading.Lock()


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS share_grants ("
        "grant_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, "
        "username TEXT NOT NULL, model_id TEXT NOT NULL, expires_at TEXT NOT NULL, "
        "revoked_at TEXT, allow_original INTEGER NOT NULL DEFAULT 0, "
        "allow_scheme_copy INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS share_sessions ("
        "session_hash TEXT PRIMARY KEY, grant_id TEXT NOT NULL, expires_at INTEGER NOT NULL)"
    )


def may_share_model(username: str, model_id: str, owner: str) -> bool:
    """Only the current owner of this model may create or list its grants.

    Being logged in is not enough. A member cannot share the library owner's files.
    """
    return bool(username) and username == owner and _MODEL_ID.fullmatch(model_id) is not None


def create_grant(
    username: str,
    model_id: str,
    owner: str,
    *,
    days: int,
    allow_original: bool,
    allow_scheme_copy: bool,
) -> dict[str, Any]:
    if not may_share_model(username, model_id, owner):
        raise HTTPException(status_code=403, detail="不能分享这个模型")
    if days not in _DAYS:
        raise HTTPException(status_code=400, detail="有效期只能是 1、7 或 30 天")
    if not isinstance(allow_original, bool) or not isinstance(allow_scheme_copy, bool):
        raise HTTPException(status_code=400, detail="下载授权必须明确打开或关闭")
    token = secrets.token_urlsafe(32)
    grant_id = secrets.token_urlsafe(12)
    now = datetime.now(ZoneInfo(TZ))
    expires = (now + timedelta(days=days)).isoformat(timespec="seconds")
    created = now.isoformat(timespec="seconds")
    with closing(_connect()) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM share_grants WHERE username = ? AND revoked_at IS NULL",
            (username,),
        ).fetchone()[0]
        if count >= _MAX_GRANTS:
            raise HTTPException(status_code=409, detail="未撤销的分享过多")
        conn.execute(
            "INSERT INTO share_grants (grant_id, token_hash, username, model_id, expires_at, "
            "revoked_at, allow_original, allow_scheme_copy, created_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)",
            (
                grant_id,
                _digest(token),
                username,
                model_id,
                expires,
                1 if allow_original else 0,
                1 if allow_scheme_copy else 0,
                created,
            ),
        )
    return {
        "grant_id": grant_id,
        "token": token,
        "expires_at": expires,
        "allow_original": allow_original,
        "allow_scheme_copy": allow_scheme_copy,
        "model_id": model_id,
    }


def list_grants(username: str, model_id: str) -> list[dict[str, Any]]:
    if _MODEL_ID.fullmatch(model_id) is None:
        raise HTTPException(status_code=400, detail="模型编号无效")
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT grant_id, expires_at, revoked_at, allow_original, "
            "allow_scheme_copy, created_at "
            "FROM share_grants WHERE username = ? AND model_id = ? ORDER BY created_at, grant_id",
            (username, model_id),
        ).fetchall()
    return [_public_grant(row) for row in rows]


def revoke_grant(username: str, grant_id: str) -> None:
    if _GRANT_ID.fullmatch(grant_id) is None:
        raise HTTPException(status_code=404, detail="没有这份分享")
    now = datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT username FROM share_grants WHERE grant_id = ?", (grant_id,)
        ).fetchone()
        if row is None or row["username"] != username:
            raise HTTPException(status_code=404, detail="没有这份分享")
        conn.execute(
            "UPDATE share_grants SET revoked_at = ? WHERE grant_id = ? AND revoked_at IS NULL",
            (now, grant_id),
        )


def open_token(ip: str, token: str) -> tuple[dict[str, Any], str]:
    _refuse_if_limited(ip)
    if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
        _note_failure(ip)
        raise HTTPException(status_code=404, detail="链接无效")
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM share_grants WHERE token_hash = ?", (_digest(token),)
        ).fetchone()
    try:
        grant = _live(row)
    except HTTPException:
        _note_failure(ip)
        raise
    session = secrets.token_urlsafe(32)
    expires = int(datetime.fromisoformat(grant["expires_at"]).timestamp())
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO share_sessions (session_hash, grant_id, expires_at) VALUES (?, ?, ?)",
            (_digest(session), grant["grant_id"], expires),
        )
    _clear_failures(ip)
    return grant, session


def grant_from_cookie(cookie: str | None) -> dict[str, Any]:
    if not cookie or _TOKEN.fullmatch(cookie) is None:
        raise HTTPException(status_code=401, detail="分享未打开")
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT g.* FROM share_sessions AS s JOIN share_grants AS g ON g.grant_id = s.grant_id "
            "WHERE s.session_hash = ? AND s.expires_at > ?",
            (_digest(cookie), int(datetime.now(ZoneInfo(TZ)).timestamp())),
        ).fetchone()
    return _live(row, missing_status=401, missing_detail="分享未打开")


def _live(
    row: sqlite3.Row | None, *, missing_status: int = 404, missing_detail: str = "链接无效"
) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=missing_status, detail=missing_detail)
    if row["revoked_at"]:
        raise HTTPException(status_code=410, detail="链接已撤销")
    expires = datetime.fromisoformat(row["expires_at"])
    if expires <= datetime.now(ZoneInfo(TZ)):
        raise HTTPException(status_code=410, detail="链接已过期")
    return {
        "grant_id": row["grant_id"],
        "username": row["username"],
        "model_id": row["model_id"],
        "expires_at": row["expires_at"],
        "allow_original": bool(row["allow_original"]),
        "allow_scheme_copy": bool(row["allow_scheme_copy"]),
    }


def _public_grant(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "grant_id": row["grant_id"],
        "expires_at": row["expires_at"],
        "revoked": row["revoked_at"] is not None,
        "allow_original": bool(row["allow_original"]),
        "allow_scheme_copy": bool(row["allow_scheme_copy"]),
        "created_at": row["created_at"],
    }


def _refuse_if_limited(ip: str) -> None:
    now = datetime.now(ZoneInfo(TZ)).timestamp()
    with _LOCK:
        count, until = _FAILURES.get(ip, (0, 0.0))
        if until <= now or count < _FAIL_LIMIT:
            return
        raise HTTPException(
            status_code=429,
            detail="尝试过多，请稍后重试",
            headers={"Retry-After": str(max(1, math.ceil(until - now)))},
        )


def _note_failure(ip: str) -> None:
    now = datetime.now(ZoneInfo(TZ)).timestamp()
    with _LOCK:
        count, until = _FAILURES.get(ip, (0, 0.0))
        if until <= now:
            count = 0
        _FAILURES[ip] = (count + 1, now + _FAIL_WINDOW)


def _clear_failures(ip: str) -> None:
    with _LOCK:
        _FAILURES.pop(ip, None)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _connect() -> sqlite3.Connection:
    path = auth_db_path()
    if not path.is_file():
        raise HTTPException(status_code=503, detail="登录库尚未就绪")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_tables(conn)
    return conn
