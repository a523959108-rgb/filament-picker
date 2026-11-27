from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from argon2 import PasswordHasher, Type
from fastapi import HTTPException

from filament_picker.auth import PREVIEW_USER_ENV, AuthStore, ModelAuth

OWNER = "synthetic-owner"
MEMBER = "synthetic-member"
OWNER_PASSWORD = "synthetic-owner-password"
MEMBER_PASSWORD = "synthetic-member-password"
OTHER_PASSWORD = "synthetic-other-password"


def _hash(password: str) -> str:
    return PasswordHasher(type=Type.ID).hash(password)


def _old_db(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, "
            "singleton INTEGER NOT NULL DEFAULT 1 UNIQUE CHECK (singleton = 1))"
        )
        conn.executemany("INSERT INTO users (username, password_hash) VALUES (?, ?)", rows)


def _partial_db(path: Path, rows: list[tuple[str, str]]) -> None:
    """旧表已改名为 users_legacy，新 users 还是空的。这是连接回滚后留下的状态。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE users_legacy (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL)"
        )
        conn.executemany("INSERT INTO users_legacy (username, password_hash) VALUES (?, ?)", rows)
        conn.execute(
            "CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, "
            "email TEXT, role TEXT NOT NULL DEFAULT 'member', created_at TEXT NOT NULL)"
        )


def _hashes(path: Path) -> dict[str, str]:
    with sqlite3.connect(path) as conn:
        return dict(conn.execute("SELECT username, password_hash FROM users"))


def _legacy_exists(path: Path) -> bool:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users_legacy'"
        ).fetchone()
    return row is not None


def test_old_schema_keeps_the_original_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "auth.sqlite"
    original = _hash(OWNER_PASSWORD)
    _old_db(db, [(OWNER, original)])
    monkeypatch.setenv(PREVIEW_USER_ENV, OWNER)
    store = AuthStore(db)
    assert store.verify(OWNER, OWNER_PASSWORD) is True
    assert store.verify(OWNER, OTHER_PASSWORD) is False
    assert _hashes(db)[OWNER] == original
    assert _legacy_exists(db) is False
    with sqlite3.connect(db) as conn:
        role = conn.execute("SELECT role FROM users WHERE username = ?", (OWNER,)).fetchone()[0]
    assert role == "owner"


def test_partial_migration_restores_login_without_rewriting_the_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "auth.sqlite"
    original = _hash(OWNER_PASSWORD)
    _partial_db(db, [(OWNER, original)])
    monkeypatch.setenv(PREVIEW_USER_ENV, OWNER)
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECRET", "synthetic-session-secret")
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECURE", "0")
    store = AuthStore(db)
    assert store.verify(OWNER, OWNER_PASSWORD) is True
    assert store.verify(OWNER, OTHER_PASSWORD) is False
    assert _hashes(db) == {OWNER: original}
    assert _legacy_exists(db) is False
    again = AuthStore(db)
    assert again.verify(OWNER, OWNER_PASSWORD) is True
    assert _hashes(db) == {OWNER: original}
    with pytest.raises(ValueError, match="不重置密码"):
        AuthStore(db).create_user(OWNER, OTHER_PASSWORD)
    assert _hashes(db) == {OWNER: original}
    auth = ModelAuth()
    assert auth.login("127.0.0.1", OWNER, OWNER_PASSWORD)
    with pytest.raises(HTTPException) as refused:
        auth.login("127.0.0.2", OWNER, OTHER_PASSWORD)
    assert refused.value.status_code == 401


def test_legacy_hash_wins_over_a_password_created_in_the_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "auth.sqlite"
    original = _hash(OWNER_PASSWORD)
    replacement = _hash(OTHER_PASSWORD)
    _partial_db(db, [(OWNER, original)])
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, email, role, created_at) "
            "VALUES (?, ?, NULL, 'owner', '2026-11-25T09:57:38+09:00')",
            (OWNER, replacement),
        )
    monkeypatch.setenv(PREVIEW_USER_ENV, OWNER)
    assert AuthStore(db).verify(OWNER, OWNER_PASSWORD) is True
    assert AuthStore(db).verify(OWNER, OTHER_PASSWORD) is False
    assert _hashes(db)[OWNER] == original


def test_legacy_accounts_stay_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "auth.sqlite"
    owner_hash = _hash(OWNER_PASSWORD)
    member_hash = _hash(MEMBER_PASSWORD)
    _partial_db(db, [(OWNER, owner_hash), (MEMBER, member_hash)])
    monkeypatch.setenv(PREVIEW_USER_ENV, OWNER)
    store = AuthStore(db)
    assert store.verify(OWNER, OWNER_PASSWORD) is True
    assert store.verify(MEMBER, MEMBER_PASSWORD) is True
    assert store.verify(OWNER, MEMBER_PASSWORD) is False
    assert store.verify(MEMBER, OWNER_PASSWORD) is False
    assert _hashes(db) == {OWNER: owner_hash, MEMBER: member_hash}
    with sqlite3.connect(db) as conn:
        roles = dict(conn.execute("SELECT username, role FROM users"))
    assert roles == {OWNER: "owner", MEMBER: "member"}
    again = AuthStore(db)
    assert again.verify(MEMBER, MEMBER_PASSWORD) is True
    assert _hashes(db)[MEMBER] == member_hash
