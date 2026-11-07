from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import shutil
import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

from .config import TZ

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_HEX_RE = re.compile(r"^#[0-9A-F]{6}$")
_THUMB_RE = re.compile(r"^thumb_([1-9][0-9]{0,3})\.jpe?g$", re.IGNORECASE)
_SHOT_RE = re.compile(r"^(plate|top)_([1-9][0-9]{0,3})\.png$")
_TAG_RE = re.compile(r"(?is)<[^>]+>")
_BLOCK_RE = re.compile(r"(?i)</(?:p|div|h[1-6]|li|tr|blockquote)\s*>")
_BREAK_RE = re.compile(r"(?i)<br\s*/?>")
_SCRIPT_RE = re.compile(r"(?is)<(script|style|iframe|object)\b[^>]*>.*?</\1>")

_CREATE_MODELS = """
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    series TEXT NOT NULL,
    author TEXT NOT NULL,
    source_relpath TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    plate_count INTEGER NOT NULL,
    colours TEXT NOT NULL,
    thumb_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    dedupe_key TEXT NOT NULL DEFAULT '',
    images TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT ''
)
"""
_EXTRA_COLUMNS = (
    ("description", "ALTER TABLE models ADD COLUMN description TEXT NOT NULL DEFAULT ''"),
    ("dedupe_key", "ALTER TABLE models ADD COLUMN dedupe_key TEXT NOT NULL DEFAULT ''"),
    ("images", "ALTER TABLE models ADD COLUMN images TEXT NOT NULL DEFAULT '[]'"),
    ("updated_at", "ALTER TABLE models ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"),
)
_CREATE_ALIASES = """
CREATE TABLE IF NOT EXISTS model_aliases (
    alias_id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    rel_path TEXT NOT NULL DEFAULT ''
)
"""


@dataclass(frozen=True, slots=True)
class ImportStats:
    lines: int
    groups: int
    canonical: int
    aliases: int
    duplicate_groups: int
    duplicate_rows: int
    skipped_missing: int
    skipped_failed: int
    skipped_invalid: int
    skipped_duplicate_id: int
    inserted: int
    updated: int
    unchanged: int
    images: int
    dry_run: bool

    def format(self) -> str:
        return (
            f"lines={self.lines} groups={self.groups} canonical={self.canonical} "
            f"aliases={self.aliases} duplicate_groups={self.duplicate_groups} "
            f"duplicate_rows={self.duplicate_rows} skipped_missing={self.skipped_missing} "
            f"skipped_failed={self.skipped_failed} skipped_invalid={self.skipped_invalid} "
            f"skipped_duplicate_id={self.skipped_duplicate_id} inserted={self.inserted} "
            f"updated={self.updated} unchanged={self.unchanged} images={self.images} "
            f"dry_run={int(self.dry_run)}"
        )


@dataclass(frozen=True, slots=True)
class _Preview:
    id: str
    rel_path: str
    title: str
    designer: str
    size_bytes: int
    plate_count: int
    colors: tuple[str, ...]
    dedupe_key: str
    description: str
    series: str
    created_at: str
    model_dir: Path
    has_meta: bool


@dataclass(frozen=True, slots=True)
class _Shot:
    kind: str
    plate: int
    name: str
    source: Path


def plain_text(value: object) -> str:
    """Decode HTML entities and drop tags. External 3MF text is not trusted as HTML."""
    if not isinstance(value, str) or not value:
        return ""
    text = value.replace("\x00", "")
    for _ in range(5):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text = _SCRIPT_RE.sub(" ", text)
    text = _BREAK_RE.sub("\n", text)
    text = _BLOCK_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ").replace("<", "").replace(">", "")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def import_previews(directory: Path, root: Path, dry_run: bool = False) -> ImportStats:
    """Copy preview images into ``root`` and upsert one manifest row per model."""
    directory = directory.resolve()
    root = root.resolve()
    if not directory.is_dir():
        raise ValueError(f"导入目录不存在：{directory}")
    if root == directory or root.is_relative_to(directory) or directory.is_relative_to(root):
        raise ValueError("导入目录与模型媒体目录不能相同或互相包含")
    index_path = directory / "index.jsonl"
    if index_path.is_symlink() or not index_path.is_file():
        raise ValueError("导入目录缺少 index.jsonl")

    previews, skipped_invalid, skipped_failed, skipped_duplicate_id, lines = _read_index(
        directory, index_path
    )
    grouped: dict[str, list[_Preview]] = defaultdict(list)
    for preview in previews:
        grouped[preview.dedupe_key].append(preview)
    duplicate_groups = sum(1 for group in grouped.values() if len(group) > 1)
    duplicate_rows = sum(len(group) - 1 for group in grouped.values() if len(group) > 1)

    canonical_rows: list[tuple[_Preview, list[_Preview]]] = []
    skipped_missing = 0
    alias_count = 0
    image_count = 0
    for group in grouped.values():
        present = [item for item in group if item.has_meta]
        if not present:
            skipped_missing += len(group)
            continue
        canonical = min(present, key=lambda item: item.id)
        aliases = [item for item in group if item.id != canonical.id]
        alias_count += len(aliases)
        canonical_rows.append((canonical, aliases))
        image_count += _count_images(canonical.model_dir)

    existing = _load_existing(root / "manifest.sqlite")
    inserted = updated = unchanged = 0
    for canonical, _aliases in canonical_rows:
        payload = _payload(canonical)
        current = existing.get(canonical.id)
        if current is None:
            inserted += 1
        elif current == payload:
            unchanged += 1
        else:
            updated += 1

    stats = ImportStats(
        lines=lines,
        groups=len(grouped),
        canonical=len(canonical_rows),
        aliases=alias_count,
        duplicate_groups=duplicate_groups,
        duplicate_rows=duplicate_rows,
        skipped_missing=skipped_missing,
        skipped_failed=skipped_failed,
        skipped_invalid=skipped_invalid,
        skipped_duplicate_id=skipped_duplicate_id,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        images=image_count,
        dry_run=dry_run,
    )
    if dry_run:
        logger.info("%s", stats.format())
        return stats

    root.mkdir(parents=True, exist_ok=True)
    (root / "thumbs").mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(parents=True, exist_ok=True)
    demoted: list[str] = []
    with closing(sqlite3.connect(root / "manifest.sqlite")) as conn, conn:
        _ensure_schema(conn)
        for canonical, _aliases in canonical_rows:
            _write_images(root, canonical)
            _upsert(conn, canonical, existing.get(canonical.id))
        for canonical, aliases in canonical_rows:
            demoted.extend(_delete_demoted(conn, canonical, aliases))
        for canonical, aliases in canonical_rows:
            _insert_aliases(conn, canonical, aliases)
    for model_id in demoted:
        _remove_media(root, model_id)
    logger.info("%s", stats.format())
    return stats


def _read_index(directory: Path, index_path: Path) -> tuple[list[_Preview], int, int, int, int]:
    previews: list[_Preview] = []
    seen: set[str] = set()
    invalid = failed = duplicate_id = lines = 0
    with index_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            lines += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if not isinstance(obj, dict):
                invalid += 1
                continue
            if obj.get("ok") is False:
                failed += 1
                continue
            model_id = obj.get("id")
            if not isinstance(model_id, str) or _ID_RE.fullmatch(model_id) is None:
                invalid += 1
                continue
            if model_id in seen:
                duplicate_id += 1
                continue
            seen.add(model_id)
            previews.append(_preview_from(directory, model_id, obj))
    return previews, invalid, failed, duplicate_id, lines


def _preview_from(directory: Path, model_id: str, obj: dict[str, Any]) -> _Preview:
    model_dir = directory / "models" / model_id
    meta = _load_meta(model_dir)
    source = obj.get("source") if isinstance(obj.get("source"), dict) else {}
    title = plain_text(obj.get("title"))
    designer = plain_text(obj.get("designer"))
    if meta is not None:
        title = title or plain_text(meta.get("title"))
        designer = designer or plain_text(meta.get("designer"))
    file_name = obj.get("file_name") if isinstance(obj.get("file_name"), str) else ""
    title = title or plain_text(Path(file_name).stem)
    colors = _normalize_colors(obj.get("colors")) or _colors_from_meta(meta)
    plate_count = _plate_count(obj.get("plates"), meta)
    rel_path = plain_text(obj.get("rel_path"))
    return _Preview(
        id=model_id,
        rel_path=rel_path,
        title=title,
        designer=designer,
        size_bytes=_nonneg_int(obj.get("size_bytes")),
        plate_count=plate_count,
        colors=tuple(colors),
        dedupe_key=_dedupe_key(source, meta, title, designer, plate_count, colors),
        description=_description(source, meta),
        series=_series(rel_path),
        created_at=_created_at(meta, obj.get("mtime")),
        model_dir=model_dir,
        has_meta=meta is not None,
    )


def _load_meta(model_dir: Path) -> dict[str, Any] | None:
    if model_dir.is_symlink() or not model_dir.is_dir():
        return None
    meta_path = model_dir / "meta.json"
    if meta_path.is_symlink() or not meta_path.is_file():
        return None
    try:
        resolved = meta_path.resolve()
        if not resolved.is_relative_to(model_dir.resolve()):
            return None
        obj = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _normalize_colors(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    colors: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip().upper()
        if not text.startswith("#"):
            text = f"#{text}"
        if _HEX_RE.fullmatch(text) is None or text in seen:
            continue
        seen.add(text)
        colors.append(text)
    return colors


def _colors_from_meta(meta: dict[str, Any] | None) -> list[str]:
    if meta is None or not isinstance(meta.get("plates"), list):
        return []
    raw: list[object] = []
    for plate in meta["plates"]:
        if not isinstance(plate, dict) or not isinstance(plate.get("filaments"), list):
            continue
        for filament in plate["filaments"]:
            if isinstance(filament, dict):
                raw.append(filament.get("hex"))
    return _normalize_colors(raw)


def _plate_count(value: object, meta: dict[str, Any] | None) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if meta is not None and isinstance(meta.get("plates"), list):
        return len(meta["plates"])
    return 0


def _nonneg_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _clean_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _design_ids(source: dict[str, Any], meta: dict[str, Any] | None) -> tuple[str, str]:
    model_id = _clean_id(source.get("design_model_id"))
    profile_id = _clean_id(source.get("design_profile_id"))
    if meta is None or (model_id and profile_id):
        return model_id, profile_id
    meta_source = meta.get("source") if isinstance(meta.get("source"), dict) else {}
    metadata = meta.get("model_metadata") if isinstance(meta.get("model_metadata"), dict) else {}
    model_id = model_id or _clean_id(meta_source.get("design_model_id"))
    model_id = model_id or _clean_id(metadata.get("DesignModelId"))
    profile_id = profile_id or _clean_id(meta_source.get("design_profile_id"))
    profile_id = profile_id or _clean_id(metadata.get("DesignProfileId"))
    return model_id, profile_id


def _dedupe_key(
    source: dict[str, Any],
    meta: dict[str, Any] | None,
    title: str,
    designer: str,
    plate_count: int,
    colors: list[str],
) -> str:
    model_id, profile_id = _design_ids(source, meta)
    if model_id and profile_id:
        return f"design\0{model_id}\0{profile_id}"
    signature = f"{plate_count}:{','.join(colors)}"
    return f"fallback\0{title.casefold()}\0{designer.casefold()}\0{signature}"


def _description(source: dict[str, Any], meta: dict[str, Any] | None) -> str:
    text = plain_text(source.get("description"))
    if not text and meta is not None and isinstance(meta.get("source"), dict):
        text = plain_text(meta["source"].get("description"))
    profile = ""
    if meta is not None and isinstance(meta.get("model_metadata"), dict):
        profile = plain_text(meta["model_metadata"].get("ProfileDescription"))
    if profile and profile not in text:
        text = f"{text}\n{profile}" if text else profile
    return text


def _series(rel_path: str) -> str:
    parts = PurePosixPath(rel_path.replace("\\", "/")).parts
    if len(parts) >= 2:
        return plain_text(parts[-2])
    return ""


def _created_at(meta: dict[str, Any] | None, mtime: object) -> str:
    if meta is not None:
        stamp = _parse_iso(meta.get("extracted_at"))
        if stamp is not None:
            return stamp
    if isinstance(mtime, int) and not isinstance(mtime, bool) and mtime > 0:
        return datetime.fromtimestamp(mtime, ZoneInfo(TZ)).isoformat(timespec="seconds")
    return datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")


def _parse_iso(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(TZ))
    return parsed.astimezone(ZoneInfo(TZ)).isoformat(timespec="seconds")


def _iter_shots(model_dir: Path) -> tuple[Path | None, list[_Shot]]:
    if model_dir.is_symlink() or not model_dir.is_dir():
        return None, []
    root = model_dir.resolve()
    thumbs: list[tuple[int, Path]] = []
    shots: list[_Shot] = []
    for path in model_dir.iterdir():
        if path.name.startswith(".") or path.is_symlink() or not path.is_file():
            continue
        try:
            if not path.resolve().is_relative_to(root):
                continue
        except OSError:
            continue
        thumb_match = _THUMB_RE.fullmatch(path.name)
        if thumb_match:
            thumbs.append((int(thumb_match.group(1)), path))
            continue
        shot_match = _SHOT_RE.fullmatch(path.name)
        if shot_match:
            shots.append(_Shot(shot_match.group(1), int(shot_match.group(2)), path.name, path))
    thumbs.sort()
    shots.sort(key=lambda shot: (0 if shot.kind == "plate" else 1, shot.plate, shot.name))
    return (thumbs[0][1] if thumbs else None), shots


def _count_images(model_dir: Path) -> int:
    thumb, shots = _iter_shots(model_dir)
    return (1 if thumb is not None else 0) + len(shots)


def _payload(preview: _Preview) -> tuple[Any, ...]:
    thumb, shots = _iter_shots(preview.model_dir)
    suffix = thumb.suffix.lower() if thumb is not None else ""
    thumb_path = f"thumbs/{preview.id}{suffix}" if thumb is not None else ""
    return (
        preview.title,
        preview.series,
        preview.designer,
        preview.rel_path,
        preview.size_bytes,
        preview.plate_count,
        tuple(preview.colors),
        thumb_path,
        preview.description,
        preview.dedupe_key,
        tuple((shot.kind, shot.plate, shot.name) for shot in shots),
    )


def _load_existing(database: Path) -> dict[str, tuple[Any, ...]]:
    if not database.is_file():
        return {}
    found: dict[str, tuple[Any, ...]] = {}
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
        if "id" not in columns:
            return {}
        for row in conn.execute("SELECT * FROM models"):
            found[row["id"]] = _stored_payload(row, columns)
    return found


def _stored_payload(row: sqlite3.Row, columns: set[str]) -> tuple[Any, ...]:
    def cell(name: str, default: object) -> object:
        return row[name] if name in columns else default

    try:
        colours = tuple(_normalize_colors(json.loads(str(cell("colours", "[]")))))
    except (TypeError, json.JSONDecodeError):
        colours = ()
    return (
        cell("title", ""),
        cell("series", ""),
        cell("author", ""),
        cell("source_relpath", ""),
        cell("size_bytes", 0),
        cell("plate_count", 0),
        colours,
        cell("thumb_path", ""),
        cell("description", ""),
        cell("dedupe_key", ""),
        _stored_shots(cell("images", "[]")),
    )


def _stored_shots(value: object) -> tuple[tuple[str, int, str], ...]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    shots: list[tuple[str, int, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        plate = item.get("plate")
        name = item.get("name")
        if kind in ("plate", "top") and isinstance(plate, int) and isinstance(name, str):
            shots.append((kind, plate, name))
    return tuple(shots)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_MODELS)
    present = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
    for name, statement in _EXTRA_COLUMNS:
        if name not in present:
            conn.execute(statement)
    conn.execute(_CREATE_ALIASES)


def _write_images(root: Path, preview: _Preview) -> None:
    thumb, shots = _iter_shots(preview.model_dir)
    thumb_dir = root / "thumbs"
    if thumb is not None:
        destination = thumb_dir / f"{preview.id}{thumb.suffix.lower()}"
        _copy_file(thumb, destination)
        for path in thumb_dir.glob(f"{preview.id}.*"):
            if path.name != destination.name and path.is_file() and not path.is_symlink():
                path.unlink()
    else:
        for path in thumb_dir.glob(f"{preview.id}.*"):
            if path.is_file() and not path.is_symlink():
                path.unlink()
    image_dir = root / "images" / preview.id
    keep = {shot.name for shot in shots}
    if shots:
        image_dir.mkdir(parents=True, exist_ok=True)
        for shot in shots:
            _copy_file(shot.source, image_dir / shot.name)
    if image_dir.is_dir() and not image_dir.is_symlink():
        for path in image_dir.iterdir():
            if path.name not in keep and path.is_file() and not path.is_symlink():
                path.unlink()


def _copy_file(source: Path, destination: Path) -> None:
    if _same_bytes(source, destination):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def _same_bytes(source: Path, destination: Path) -> bool:
    if destination.is_symlink() or not destination.is_file():
        return False
    if source.stat().st_size != destination.stat().st_size:
        return False
    return _sha256(source) == _sha256(destination)


def _sha256(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def _upsert(conn: sqlite3.Connection, preview: _Preview, current: tuple[Any, ...] | None) -> None:
    payload = _payload(preview)
    thumb_path = payload[7]
    shot_tuples = payload[10]
    images = [{"kind": kind, "plate": plate, "name": name} for kind, plate, name in shot_tuples]
    colours = json.dumps(list(preview.colors), ensure_ascii=False)
    image_json = json.dumps(images, ensure_ascii=False)
    digest = hashlib.sha256(preview.id.encode()).hexdigest()
    now = datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM model_aliases WHERE alias_id = ?", (preview.id,))
    if current is None:
        conn.execute(
            "INSERT INTO models (id, sha256, title, series, author, source_relpath, "
            "size_bytes, plate_count, colours, thumb_path, created_at, description, "
            "dedupe_key, images, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                preview.id,
                digest,
                preview.title,
                preview.series,
                preview.designer,
                preview.rel_path,
                preview.size_bytes,
                preview.plate_count,
                colours,
                thumb_path,
                preview.created_at,
                preview.description,
                preview.dedupe_key,
                image_json,
                now,
            ),
        )
        return
    conn.execute(
        "UPDATE models SET sha256 = ?, title = ?, series = ?, author = ?, source_relpath = ?, "
        "size_bytes = ?, plate_count = ?, colours = ?, thumb_path = ?, description = ?, "
        "dedupe_key = ?, images = ?, updated_at = ? WHERE id = ?",
        (
            digest,
            preview.title,
            preview.series,
            preview.designer,
            preview.rel_path,
            preview.size_bytes,
            preview.plate_count,
            colours,
            thumb_path,
            preview.description,
            preview.dedupe_key,
            image_json,
            now,
            preview.id,
        ),
    )


def _delete_demoted(
    conn: sqlite3.Connection, canonical: _Preview, aliases: list[_Preview]
) -> list[str]:
    keep = [alias.id for alias in aliases]
    if keep:
        placeholders = ", ".join("?" for _ in keep)
        conn.execute(
            f"DELETE FROM model_aliases WHERE model_id = ? AND alias_id NOT IN ({placeholders})",
            (canonical.id, *keep),
        )
    else:
        conn.execute("DELETE FROM model_aliases WHERE model_id = ?", (canonical.id,))
    demoted: list[str] = []
    for alias in aliases:
        removed = conn.execute("DELETE FROM models WHERE id = ?", (alias.id,))
        if removed.rowcount:
            demoted.append(alias.id)
    return demoted


def _insert_aliases(conn: sqlite3.Connection, canonical: _Preview, aliases: list[_Preview]) -> None:
    for alias in aliases:
        conn.execute(
            "INSERT INTO model_aliases (alias_id, model_id, rel_path) VALUES (?, ?, ?) "
            "ON CONFLICT(alias_id) DO UPDATE SET model_id = excluded.model_id, "
            "rel_path = excluded.rel_path",
            (alias.id, canonical.id, alias.rel_path),
        )


def _remove_media(root: Path, model_id: str) -> None:
    if _ID_RE.fullmatch(model_id) is None:
        return
    thumb_dir = root / "thumbs"
    if thumb_dir.is_dir() and not thumb_dir.is_symlink():
        for path in thumb_dir.glob(f"{model_id}.*"):
            inside = path.is_file() and not path.is_symlink()
            if inside and path.parent.resolve() == thumb_dir.resolve():
                path.unlink()
    images_root = root / "images"
    image_dir = images_root / model_id
    if image_dir.is_symlink() or not image_dir.is_dir():
        return
    if image_dir.resolve().parent != images_root.resolve():
        return
    shutil.rmtree(image_dir)
