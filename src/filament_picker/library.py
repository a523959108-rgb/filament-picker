"""Private favorites and display-only slot colors for the single preview account.

Tables live in the auth database and are created on demand. They do not alter
the model manifest. A saved color is a screen swatch, not a change to the
original file or to the physical filament.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from .auth import auth_db_path
from .config import TZ
from .shares import ensure_tables as ensure_share_tables

_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_MAX_FAVORITES = 500
_MAX_SLOTS = 64
_NOTE = "仅展示色，不修改原件，也不表示零件已换料"


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS favorites ("
        "username TEXT NOT NULL, model_id TEXT NOT NULL, created_at TEXT NOT NULL, "
        "PRIMARY KEY (username, model_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS display_schemes ("
        "username TEXT NOT NULL, model_id TEXT NOT NULL, slots_json TEXT NOT NULL, "
        "updated_at TEXT NOT NULL, PRIMARY KEY (username, model_id))"
    )
    ensure_share_tables(conn)


def _connect() -> sqlite3.Connection:
    path = auth_db_path()
    if not path.is_file():
        raise HTTPException(status_code=503, detail="登录库尚未就绪")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_tables(conn)
    return conn


def _now() -> str:
    return datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")


def _check_id(model_id: str) -> str:
    if _MODEL_ID.fullmatch(model_id) is None:
        raise HTTPException(status_code=400, detail="模型编号无效")
    return model_id


def list_favorites(username: str) -> list[dict[str, str]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT model_id, created_at FROM favorites WHERE username = ? "
            "ORDER BY created_at, model_id",
            (username,),
        ).fetchall()
    return [{"model_id": row["model_id"], "created_at": row["created_at"]} for row in rows]


def put_favorite(username: str, model_id: str) -> None:
    model_id = _check_id(model_id)
    with closing(_connect()) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM favorites WHERE username = ?", (username,)
        ).fetchone()[0]
        exists = conn.execute(
            "SELECT 1 FROM favorites WHERE username = ? AND model_id = ?",
            (username, model_id),
        ).fetchone()
        if exists is None and count >= _MAX_FAVORITES:
            raise HTTPException(status_code=400, detail="收藏已满")
        conn.execute(
            "INSERT INTO favorites (username, model_id, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(username, model_id) DO NOTHING",
            (username, model_id, _now()),
        )


def delete_favorite(username: str, model_id: str) -> None:
    model_id = _check_id(model_id)
    with closing(_connect()) as conn, conn:
        conn.execute(
            "DELETE FROM favorites WHERE username = ? AND model_id = ?",
            (username, model_id),
        )


def get_scheme(username: str, model_id: str) -> dict[str, Any]:
    model_id = _check_id(model_id)
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT slots_json FROM display_schemes WHERE username = ? AND model_id = ?",
            (username, model_id),
        ).fetchone()
    slots: list[dict[str, Any]] = []
    if row is not None:
        try:
            parsed = json.loads(row["slots_json"])
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            slots = [item for item in parsed if isinstance(item, dict)]
    return {"model_id": model_id, "note": _NOTE, "slots": slots}


def put_scheme(
    username: str,
    model_id: str,
    slots: object,
    plates: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    model_id = _check_id(model_id)
    cleaned = _validate_slots(slots, plates)
    payload = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
    with closing(_connect()) as conn, conn:
        if cleaned:
            conn.execute(
                "INSERT INTO display_schemes (username, model_id, slots_json, updated_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(username, model_id) DO UPDATE SET "
                "slots_json = excluded.slots_json, updated_at = excluded.updated_at",
                (username, model_id, payload, _now()),
            )
        else:
            conn.execute(
                "DELETE FROM display_schemes WHERE username = ? AND model_id = ?",
                (username, model_id),
            )
    return {"model_id": model_id, "note": _NOTE, "slots": cleaned}


def _validate_slots(slots: object, plates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(slots, list):
        raise HTTPException(status_code=400, detail="展示色格式无效")
    if len(slots) > _MAX_SLOTS:
        raise HTTPException(status_code=400, detail="展示色过多")
    if slots and not plates:
        raise HTTPException(status_code=409, detail="没有盘映射，不能保存展示色")
    known = {
        (plate.get("index"), filament.get("slot"))
        for plate in plates or []
        for filament in plate.get("filaments", [])
        if isinstance(filament, dict)
    }
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[object, object]] = set()
    for item in slots:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="展示色格式无效")
        plate_index = item.get("plate_index")
        slot = item.get("slot")
        color = item.get("hex")
        if isinstance(plate_index, bool) or not isinstance(plate_index, int):
            raise HTTPException(status_code=400, detail="盘号无效")
        if isinstance(slot, bool) or not isinstance(slot, int):
            raise HTTPException(status_code=400, detail="槽位无效")
        if not isinstance(color, str) or _HEX.fullmatch(color) is None:
            raise HTTPException(status_code=400, detail="展示色无效")
        key = (plate_index, slot)
        if key in seen:
            raise HTTPException(status_code=400, detail="同一槽位重复")
        if key not in known or slot is None:
            raise HTTPException(status_code=400, detail="没有这个槽位")
        seen.add(key)
        cleaned.append({"plate_index": plate_index, "slot": slot, "hex": color.upper()})
    return cleaned
