from __future__ import annotations

import hashlib
import logging
import math
import os
import re
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
_REGISTER_USER = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
_REGISTER_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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


def registration_enabled() -> bool:
    return os.environ.get("FILAMENT_PICKER_REGISTRATION", "0") == "1"


def _timestamp() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from .config import TZ

    return datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")


_NEW_USERS = (
    "CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, "
    "email TEXT, role TEXT NOT NULL DEFAULT 'member', created_at TEXT NOT NULL)"
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _migrate_users(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sessions (token_digest TEXT PRIMARY KEY, "
        "username TEXT NOT NULL, expires_at INTEGER NOT NULL)"
    )
    # 改名和建表会单独提交。复制哈希必须在同一事务里提交，否则连接关闭时回滚，
    # 新 users 留下 0 行，users_legacy 里的原哈希再也不会被读到。
    conn.execute("BEGIN IMMEDIATE")
    try:
        _copy_legacy_users(conn)
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def _copy_legacy_users(conn: sqlite3.Connection) -> None:
    legacy = _table_exists(conn, "users_legacy")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "singleton" in columns:
        if legacy:
            raise sqlite3.DatabaseError("users 与 users_legacy 不能同时是旧结构")
        conn.execute("ALTER TABLE users RENAME TO users_legacy")
        legacy = True
        columns = set()
    if not columns:
        conn.execute(_NEW_USERS)
    elif "role" not in columns:
        raise sqlite3.DatabaseError("users 表结构无法迁移")
    if not legacy:
        return
    owner = configured_preview_user()
    now = _timestamp()
    rows = list(conn.execute("SELECT username, password_hash FROM users_legacy"))
    for username, password_hash in rows:
        if not isinstance(username, str) or not username:
            raise sqlite3.DatabaseError("users_legacy 缺少用户名")
        if not isinstance(password_hash, str) or not password_hash.startswith("$argon2id$"):
            raise sqlite3.DatabaseError("users_legacy 密码哈希不是 Argon2id")
        existing = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if existing is None:
            role = "owner" if owner and username == owner else "member"
            conn.execute(
                "INSERT INTO users (username, password_hash, email, role, created_at) "
                "VALUES (?, ?, NULL, ?, ?)",
                (username, password_hash, role, now),
            )
            continue
        if existing[0] != password_hash:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (password_hash, username),
            )
    conn.execute("DROP TABLE users_legacy")


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
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                raise ValueError("账号已存在；本命令不重置密码或追加账号")
            conn.execute(
                "INSERT INTO users (username, password_hash, email, role, created_at) "
                "VALUES (?, ?, NULL, 'owner', ?)",
                (username, self.hasher.hash(password), _timestamp()),
            )

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
            self.path.chmod(0o600)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        _migrate_users(conn)
        return conn

    def register_account(
        self, username: str, password: str, email: str | None
    ) -> dict[str, object]:
        if not registration_enabled():
            raise HTTPException(status_code=403, detail="注册未开放")
        owner = configured_preview_user()
        if owner is None:
            raise HTTPException(status_code=503, detail=f"未配置 {PREVIEW_USER_ENV}")
        if _REGISTER_USER.fullmatch(username) is None or username == owner:
            raise HTTPException(status_code=400, detail="用户名不可用")
        if not isinstance(password, str) or len(password) < 10 or len(password) > 200:
            raise HTTPException(status_code=400, detail="密码至少 10 位")
        stored_email = None
        if email:
            if (
                not isinstance(email, str)
                or _REGISTER_EMAIL.fullmatch(email) is None
                or len(email) > 200
            ):
                raise HTTPException(status_code=400, detail="邮箱格式无效")
            stored_email = email
        with closing(self.connect()) as conn, conn:
            if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                raise HTTPException(status_code=409, detail="账号已存在")
            conn.execute(
                "INSERT INTO users (username, password_hash, email, role, created_at) "
                "VALUES (?, ?, ?, 'member', ?)",
                (username, self.hasher.hash(password), stored_email, _timestamp()),
            )
        return {"username": username, "email_sent": False, "email_verification": False}

    def user_exists(self, username: str) -> bool:
        if not self.path.is_file():
            return False
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        return row is not None

    def verify(self, username: str, password: str) -> bool:
        if not self.path.is_file():
            return False
        with closing(self.connect()) as conn:
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
        with closing(self.connect()) as conn:
            return [row[0] for row in conn.execute("SELECT username FROM users ORDER BY username")]

    def add_session(self, token: str, username: str, ttl: int) -> None:
        with closing(self.connect()) as conn, conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (self._digest(token), username, int(time.time()) + ttl),
            )

    def session_active(self, token: str, username: str) -> bool:
        if not self.path.is_file():
            return False
        with closing(self.connect()) as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM sessions JOIN users USING (username) "
                    "WHERE token_digest = ? AND username = ? AND expires_at > ?",
                    (self._digest(token), username, int(time.time())),
                ).fetchone()
                is not None
            )

    def revoke_session(self, token: str) -> None:
        with closing(self.connect()) as conn, conn:
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
        self._registrations: dict[str, tuple[int, float]] = {}
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
            if not self.store.verify(username, password):
                self._failures[ip] = (failures + 1, now + LOGIN_LOCK_SECONDS)
                raise HTTPException(status_code=401, detail="用户名或密码错误")
            self._failures.pop(ip, None)
        token = serializer.dumps({"username": username, "nonce": secrets.token_urlsafe(24)})
        self.store.add_session(token, username, self.ttl)
        return token

    def register(
        self, ip: str, username: str, password: str, email: str | None
    ) -> dict[str, object]:
        with self._lock:
            now = monotonic()
            self._registrations = {
                key: value for key, value in self._registrations.items() if value[1] > now
            }
            count, until = self._registrations.get(ip, (0, 0.0))
            if count >= LOGIN_FAILURE_LIMIT:
                raise HTTPException(
                    status_code=429,
                    detail="注册尝试过多，请稍后重试",
                    headers={"Retry-After": str(max(1, math.ceil(until - now)))},
                )
            self._registrations[ip] = (count + 1, now + LOGIN_LOCK_SECONDS)
        return self.store.register_account(username, password, email)

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
        if not self.store.session_active(token, username):
            return None
        return username
