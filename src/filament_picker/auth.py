from __future__ import annotations

import hashlib
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


def auth_db_path() -> Path:
    return Path(os.environ.get("FILAMENT_PICKER_AUTH_DB", REPO_ROOT / "data/auth/users.sqlite"))


class AuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.hasher = PasswordHasher(type=Type.ID)

    def create_user(self, username: str, password: str) -> None:
        if username != "yulanmoxing" or not password:
            raise ValueError("仅支持单账号 yulanmoxing，密码不能为空")
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
            if not self.store.verify(username, password):
                self._failures[ip] = (failures + 1, now + LOGIN_LOCK_SECONDS)
                raise HTTPException(status_code=401, detail="用户名或密码错误")
            self._failures.pop(ip, None)
        token = serializer.dumps({"username": username, "nonce": secrets.token_urlsafe(24)})
        self.store.add_session(token, username, self.ttl)
        return token

    def username(self, token: str | None) -> str | None:
        if not token or self.secret is None:
            return None
        try:
            payload = self._serializer().loads(token, max_age=self.ttl)
        except BadSignature:
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("username"), str):
            return None
        username = payload["username"]
        return username if self.store.session_active(token, username) else None
