"""Write a separate 3MF whose filament colour list follows a saved display scheme.

The original archive is only read. The copy changes ``filament_colour`` and the
parallel colour lists of the same length in ``Metadata/project_settings.config``.
Mesh bytes, extruder colours, and slice paths stay as they were. The copy is
not a resliced file and must not be treated as ready to print.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

from .auth import auth_db_path
from .config import TZ

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_USER = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MAX_ENTRIES = 4000
_MAX_UNCOMPRESSED = 256 * 1024 * 1024
_MAX_ENTRY = 64 * 1024 * 1024
_COLOUR_KEYS = ("filament_colour", "default_filament_colour", "filament_multi_colour")
_CAVEAT = "只改了耗材颜色记录，没有改切片路径。不能直接打印，需要重新切片。"
_FIXED_DATE = (2026, 1, 1, 0, 0, 0)


class SchemeCopyError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(detail)


def synthetic_3mf(colours: list[str]) -> bytes:
    """Build a tiny valid mesh archive. It is synthetic, not a shop sample."""
    if not colours or any(_HEX.fullmatch(item) is None for item in colours):
        raise ValueError("synthetic colours must be #RRGGBB")
    settings = {
        "filament_colour": colours,
        "default_filament_colour": list(colours),
        "filament_multi_colour": list(colours),
        "extruder_colour": ["#018001"],
        "note": "synthetic keep #FFFFFF",
    }
    mesh = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <metadata name="Application">filament-picker-synthetic</metadata>
 <resources>
  <object id="1" type="model">
   <mesh>
    <vertices>
     <vertex x="0" y="0" z="0"/>
     <vertex x="1" y="0" z="0"/>
     <vertex x="0" y="1" z="0"/>
    </vertices>
    <triangles><triangle v1="0" v2="1" v3="2"/></triangles>
   </mesh>
  </object>
 </resources>
 <build><item objectid="1"/></build>
</model>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        _write(archive, "3D/3dmodel.model", mesh.encode())
        _write(archive, "Metadata/project_settings.config", json.dumps(settings).encode())
    return buffer.getvalue()


def build_scheme_copy(source: bytes, slots: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    """Return the new archive and a record of what was written."""
    if not slots:
        raise SchemeCopyError(409, "还没有可写入的槽位颜色")
    wanted = _slot_colours(slots)
    archive = _open_zip(source)
    try:
        names = archive.namelist()
        _reject_unsafe(names)
        if "Metadata/project_settings.config" not in names:
            raise SchemeCopyError(422, "没有 project_settings.config，不能另存配色副本")
        if sum(archive.getinfo(name).file_size for name in names) > _MAX_UNCOMPRESSED:
            raise SchemeCopyError(413, "3MF 解压后过大")
        settings = _read_settings(archive)
        colours = _colour_list(settings, "filament_colour", required=True)
        assert isinstance(colours, list)
        for slot in wanted:
            if slot < 1 or slot > len(colours):
                raise SchemeCopyError(422, f"槽位 {slot} 不在 filament_colour 里，没有生成副本")
        rewrite = ["filament_colour"]
        blank: list[str] = []
        for key in _COLOUR_KEYS[1:]:
            action = _parallel_action(settings, key, len(colours))
            if action == "rewrite":
                rewrite.append(key)
            elif action == "blank":
                blank.append(key)
        for slot, hex_color in wanted.items():
            index = slot - 1
            colours[index] = hex_color
            for key in rewrite[1:]:
                parallel = settings[key]
                parallel[index] = hex_color
        settings["filament_colour"] = colours
        replacement = json.dumps(settings, ensure_ascii=False, indent=2).encode() + b"\n"
        if len(replacement) > _MAX_ENTRY:
            raise SchemeCopyError(413, "配色记录过大")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as target:
            for name in names:
                payload = archive.read(name)
                if name == "Metadata/project_settings.config":
                    payload = replacement
                _write(target, name, payload)
            note = {
                "caveat": _CAVEAT,
                "slots": [
                    {"slot": slot, "hex": hex_color} for slot, hex_color in sorted(wanted.items())
                ],
                "rewritten": rewrite,
                "untouched": [*blank, "extruder_colour", "3D/3dmodel.model"],
            }
            sidecar = json.dumps(note, ensure_ascii=False).encode()
            _write(target, "Metadata/filament_picker_scheme.json", sidecar)
    finally:
        archive.close()
    data = output.getvalue()
    return data, {
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "slots": [{"slot": slot, "hex": hex_color} for slot, hex_color in sorted(wanted.items())],
        "rewritten": rewrite,
        "unchanged": [*blank, "extruder_colour"],
        "caveat": _CAVEAT,
    }


def store_scheme_copy(
    username: str,
    model_id: str,
    source: Path,
    slots: list[dict[str, Any]],
) -> dict[str, Any]:
    before = source.read_bytes()
    data, record = build_scheme_copy(before, slots)
    if source.read_bytes() != before:
        raise SchemeCopyError(500, "原件被改动，已中止")
    directory = _copy_dir(username, model_id)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    filename = f"{model_id}-scheme-{record['sha256'][:12]}.3mf"
    target = directory / filename
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.chmod(0o600)
    temporary.replace(target)
    for stale in directory.glob("*.3mf"):
        if stale != target:
            stale.unlink()
    record["filename"] = filename
    record["model_id"] = model_id
    _remember(username, model_id, record)
    return record


def scheme_copy_path(username: str, model_id: str) -> tuple[Path, dict[str, Any]] | None:
    with closing(_connect()) as conn:
        _ensure(conn)
        row = conn.execute(
            "SELECT sha256, filename, source_sha256, slots_json, caveat FROM scheme_copies "
            "WHERE username = ? AND model_id = ?",
            (username, model_id),
        ).fetchone()
    if row is None:
        return None
    path = _copy_dir(username, model_id) / str(row["filename"])
    if not path.is_file() or path.is_symlink():
        return None
    record = {
        "sha256": row["sha256"],
        "filename": row["filename"],
        "source_sha256": row["source_sha256"],
        "slots": json.loads(row["slots_json"]),
        "caveat": row["caveat"],
        "bytes": path.stat().st_size,
        "model_id": model_id,
    }
    return path, record


def _slot_colours(slots: list[dict[str, Any]]) -> dict[int, str]:
    wanted: dict[int, str] = {}
    for item in slots:
        slot = item.get("slot")
        color = item.get("hex")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 1:
            raise SchemeCopyError(422, "槽位不是可映射的正整数")
        if not isinstance(color, str) or _HEX.fullmatch(color) is None:
            raise SchemeCopyError(422, "展示色不是 #RRGGBB")
        normalized = color.upper()
        previous = wanted.get(slot)
        if previous is not None and previous != normalized:
            raise SchemeCopyError(422, f"槽位 {slot} 在不同盘上的颜色不一致，没有生成副本")
        wanted[slot] = normalized
    return wanted


def _open_zip(source: bytes) -> zipfile.ZipFile:
    if len(source) > _MAX_UNCOMPRESSED:
        raise SchemeCopyError(413, "原件过大")
    try:
        archive = zipfile.ZipFile(io.BytesIO(source))
        bad = archive.testzip()
    except zipfile.BadZipFile as exc:
        raise SchemeCopyError(422, "不是 3MF 压缩包，没有生成副本") from exc
    if bad is not None:
        archive.close()
        raise SchemeCopyError(422, "3MF 压缩包已损坏")
    if len(archive.namelist()) > _MAX_ENTRIES:
        archive.close()
        raise SchemeCopyError(413, "3MF 条目过多")
    for info in archive.infolist():
        if info.file_size > _MAX_ENTRY:
            archive.close()
            raise SchemeCopyError(413, "3MF 里有过大的文件")
    return archive


def _reject_unsafe(names: list[str]) -> None:
    for name in names:
        pure = PurePosixPath(name)
        if name.startswith("/") or "\\" in name or ".." in pure.parts or pure.is_absolute():
            raise SchemeCopyError(422, "3MF 路径不安全，没有生成副本")


def _read_settings(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        parsed = json.loads(archive.read("Metadata/project_settings.config"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise SchemeCopyError(422, "project_settings.config 不是可解析的配色记录") from exc
    if not isinstance(parsed, dict):
        raise SchemeCopyError(422, "project_settings.config 不是对象")
    return parsed


def _parallel_action(settings: dict[str, Any], key: str, expect: int) -> str:
    """Decide whether a sibling colour list can be updated with filament_colour.

    A same-length list of #RRGGBB is rewritten. A same-length list of empty
    strings is a blank placeholder, not a colour, so it is left as it is.
    Any other shape is not a reliable mapping and aborts before a file is written.
    """
    if key not in settings:
        return "absent"
    value = settings[key]
    if not isinstance(value, list) or len(value) != expect:
        raise SchemeCopyError(422, f"{key} 的长度和 filament_colour 不一致，没有生成副本")
    if all(isinstance(item, str) and _HEX.fullmatch(item) for item in value):
        return "rewrite"
    if all(item == "" for item in value):
        return "blank"
    raise SchemeCopyError(422, f"{key} 不是可靠的颜色列表，没有生成副本")


def _colour_list(
    settings: dict[str, Any], key: str, *, required: bool, expect: int | None = None
) -> list[str] | None:
    value = settings.get(key)
    if value is None and not required:
        return None
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or _HEX.fullmatch(item) is None for item in value)
    ):
        raise SchemeCopyError(422, f"{key} 不是可靠的颜色列表，没有生成副本")
    if expect is not None and len(value) != expect:
        raise SchemeCopyError(422, f"{key} 的长度和 filament_colour 不一致，没有生成副本")
    return value


def _write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, payload)


def _copy_dir(username: str, model_id: str) -> Path:
    if _USER.fullmatch(username) is None:
        raise SchemeCopyError(400, "账号名不能作为副本目录")
    root = auth_db_path().resolve().parent / "scheme-copies"
    return root / username / model_id


def _connect() -> sqlite3.Connection:
    path = auth_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS scheme_copies ("
        "username TEXT NOT NULL, model_id TEXT NOT NULL, sha256 TEXT NOT NULL, "
        "filename TEXT NOT NULL, source_sha256 TEXT NOT NULL, slots_json TEXT NOT NULL, "
        "caveat TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (username, model_id))"
    )


def _remember(username: str, model_id: str, record: dict[str, Any]) -> None:
    with closing(_connect()) as conn, conn:
        _ensure(conn)
        conn.execute(
            "INSERT INTO scheme_copies (username, model_id, sha256, filename, source_sha256, "
            "slots_json, caveat, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(username, model_id) DO UPDATE SET sha256 = excluded.sha256, "
            "filename = excluded.filename, source_sha256 = excluded.source_sha256, "
            "slots_json = excluded.slots_json, caveat = excluded.caveat, "
            "created_at = excluded.created_at",
            (
                username,
                model_id,
                record["sha256"],
                record["filename"],
                record["source_sha256"],
                json.dumps(record["slots"], ensure_ascii=False),
                record["caveat"],
                datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds"),
            ),
        )
