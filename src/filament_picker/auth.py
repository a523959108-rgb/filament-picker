from __future__ import annotations

import hashlib
import logging
import math
import os
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from time import monotonic

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import REPO_ROOT

COOKIE_NAME = "fp_session"
SESSION_TTL = 7 * 24 * 60 * 60
LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_SECONDS = 60
PREVIEW_USER_ENV = "FILAMENT_PICKER_PREVIEW_USER"
PREVIEW_USER_PLACEHOLDER = "change-me-preview-user"

logger = logging.getLogger(__name__)


def configured_preview_user() -> str | None:
    """Return the single preview account name, or None when login must be refused.

    Unset, blank, and the example placeholder are all unconfigured. There is
    no built-in default name.
    """
    raw = os.environ.get(PREVIEW_USER_ENV)
    if raw is None:
        return None
    value = raw.strip()
    if not value or value == PREVIEW_USER_PLACEHOLDER:
        return None
    return value


def warn_if_preview_user_unconfigured() -> None:
    if configured_preview_user() is not None:
        return
    logger.warning("%s 未配置，模型预览拒绝所有登录", PREVIEW_USER_ENV)


def auth_db_path() -> Path:
    return Path(os.environ.get("FILAMENT_PICKER_AUTH_DB", REPO_ROOT / "data/auth/users.sqlite"))


class AuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.hasher = PasswordHasher(type=Type.ID)

    def create_user(self, username: str, password: str) -> None:
        expected = configured_preview_user()
        if expected is None:
            raise ValueError(f"未配置 {PREVIEW_USER_ENV}，拒绝创建账号")
        if username != expected or not password:
            raise ValueError(f"仅支持 {PREVIEW_USER_ENV} 指定的单账号，密码不能为空")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, "
                "password_hash TEXT NOT NULL, singleton INTEGER NOT NULL DEFAULT 1 "
                "UNIQUE CHECK (singleton = 1))"
            )
            if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                raise ValueError("账号已存在；本命令不重置密码或追加账号")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sessions (token_digest TEXT PRIMARY KEY, "
                "username TEXT NOT NULL, expires_at INTEGER NOT NULL)"
            )
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, self.hasher.hash(password)),
            )

    def verify(self, username: str, password: str) -> bool:
        if not self.path.is_file():
            return False
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE username = ?", (username,)
            ).fetchone()
        if row is None:
            return False
        try:
            return self.hasher.verify(row[0], password)
        except (VerificationError, InvalidHashError):
            return False

    def list_users(self) -> list[str]:
        if not self.path.is_file():
            return []
        with closing(sqlite3.connect(self.path)) as conn:
            return [row[0] for row in conn.execute("SELECT username FROM users ORDER BY username")]

    def add_session(self, token: str, username: str, ttl: int) -> None:
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (self._digest(token), username, int(time.time()) + ttl),
            )

    def session_active(self, token: str, username: str) -> bool:
        if not self.path.is_file():
            return False
        with closing(sqlite3.connect(self.path)) as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM sessions JOIN users USING (username) "
                    "WHERE token_digest = ? AND username = ? AND expires_at > ?",
                    (self._digest(token), username, int(time.time())),
                ).fetchone()
                is not None
            )

    def revoke_session(self, token: str) -> None:
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("DELETE FROM sessions WHERE token_digest = ?", (self._digest(token),))

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


class ModelAuth:
    def __init__(self) -> None:
        self.store = AuthStore(auth_db_path())
        self.secret = os.environ.get("FILAMENT_PICKER_SESSION_SECRET") or None
        if self.secret == "change-me":
            self.secret = None
        self.ttl = int(os.environ.get("FILAMENT_PICKER_SESSION_TTL", SESSION_TTL))
        if self.ttl <= 0:
            raise ValueError("FILAMENT_PICKER_SESSION_TTL must be positive")
        self.secure = os.environ.get("FILAMENT_PICKER_SESSION_SECURE", "1") != "0"
        self._failures: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def _serializer(self) -> URLSafeTimedSerializer:
        if self.secret is None:
            raise HTTPException(status_code=503, detail="模型登录尚未配置")
        return URLSafeTimedSerializer(self.secret, salt="filament-picker-models")

    def login(self, ip: str, username: str, password: str) -> str:
        expected = configured_preview_user()
        if expected is None:
            raise HTTPException(status_code=503, detail=f"未配置 {PREVIEW_USER_ENV}")
        serializer = self._serializer()
        with self._lock:
            now = monotonic()
            self._failures = {key: value for key, value in self._failures.items() if value[1] > now}
            failures, until = self._failures.get(ip, (0, 0.0))
            if failures >= LOGIN_FAILURE_LIMIT:
                raise HTTPException(
                    status_code=429,
                    detail="登录尝试过多，请稍后重试",
                    headers={"Retry-After": str(max(1, math.ceil(until - now)))},
                )
            if username != expected or not self.store.verify(username, password):
                self._failures[ip] = (failures + 1, now + LOGIN_LOCK_SECONDS)
                raise HTTPException(status_code=401, detail="用户名或密码错误")
            self._failures.pop(ip, None)
        token = serializer.dumps({"username": username, "nonce": secrets.token_urlsafe(24)})
        self.store.add_session(token, username, self.ttl)
        return token

    def username(self, token: str | None) -> str | None:
        expected = configured_preview_user()
        if expected is None or not token or self.secret is None:
            return None
        try:
            payload = self._serializer().loads(token, max_age=self.ttl)
        except BadSignature:
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("username"), str):
            return None
        username = payload["username"]
        if username != expected or not self.store.session_active(token, username):
            return None
        return username
