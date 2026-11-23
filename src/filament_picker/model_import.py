from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import shutil
import sqlite3
import struct
import zipfile
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

# Private originals only. Preview PNG/GLB files are not originals and are never copied here.
ORIGINAL_TYPES = {".3mf": "model/3mf", ".stl": "model/stl"}
ORIGINAL_MAX_BYTES = 512 * 1024 * 1024

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
    updated_at TEXT NOT NULL DEFAULT '',
    plate_layout TEXT NOT NULL DEFAULT '',
    original_name TEXT NOT NULL DEFAULT '',
    original_sha256 TEXT NOT NULL DEFAULT '',
    original_size INTEGER NOT NULL DEFAULT 0,
    original_relpath TEXT NOT NULL DEFAULT ''
)
"""
_EXTRA_COLUMNS = (
    ("description", "ALTER TABLE models ADD COLUMN description TEXT NOT NULL DEFAULT ''"),
    ("dedupe_key", "ALTER TABLE models ADD COLUMN dedupe_key TEXT NOT NULL DEFAULT ''"),
    ("images", "ALTER TABLE models ADD COLUMN images TEXT NOT NULL DEFAULT '[]'"),
    ("updated_at", "ALTER TABLE models ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"),
    ("plate_layout", "ALTER TABLE models ADD COLUMN plate_layout TEXT NOT NULL DEFAULT ''"),
    ("original_name", "ALTER TABLE models ADD COLUMN original_name TEXT NOT NULL DEFAULT ''"),
    ("original_sha256", "ALTER TABLE models ADD COLUMN original_sha256 TEXT NOT NULL DEFAULT ''"),
    ("original_size", "ALTER TABLE models ADD COLUMN original_size INTEGER NOT NULL DEFAULT 0"),
    ("original_relpath", "ALTER TABLE models ADD COLUMN original_relpath TEXT NOT NULL DEFAULT ''"),
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
    originals: int
    originals_skipped: int
    dry_run: bool

    def format(self) -> str:
        return (
            f"lines={self.lines} groups={self.groups} canonical={self.canonical} "
            f"aliases={self.aliases} duplicate_groups={self.duplicate_groups} "
            f"duplicate_rows={self.duplicate_rows} skipped_missing={self.skipped_missing} "
            f"skipped_failed={self.skipped_failed} skipped_invalid={self.skipped_invalid} "
            f"skipped_duplicate_id={self.skipped_duplicate_id} inserted={self.inserted} "
            f"updated={self.updated} unchanged={self.unchanged} images={self.images} "
            f"originals={self.originals} originals_skipped={self.originals_skipped} "
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
    plate_layout: str


@dataclass(frozen=True, slots=True)
class _OriginalDecision:
    status: str
    name: str = ""
    sha256: str = ""
    size: int = 0
    suffix: str = ""
    source: Path | None = None
    reason: str = ""


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


def import_previews(
    directory: Path, root: Path, dry_run: bool = False, library: Path | None = None
) -> ImportStats:
    """Copy preview images into ``root`` and upsert one manifest row per model.

    ``library`` is an optional read-only root of the operator's original files.
    A file is copied only when ``rel_path`` stays inside that root, the recorded
    size matches, and the bytes are a 3MF or STL that can be opened again.
    Preview images and GLB meshes are never treated as originals. The library
    itself is not modified or deleted.
    """
    directory = directory.resolve()
    root = root.resolve()
    if not directory.is_dir():
        raise ValueError(f"导入目录不存在：{directory}")
    if root == directory or root.is_relative_to(directory) or directory.is_relative_to(root):
        raise ValueError("导入目录与模型媒体目录不能相同或互相包含")
    if library is not None:
        library = library.resolve()
        if not library.is_dir():
            raise ValueError(f"原件库目录不存在：{library}")
        if library == root or library.is_relative_to(root) or root.is_relative_to(library):
            raise ValueError("原件库目录与模型媒体目录不能相同或互相包含")
        if (
            library == directory
            or library.is_relative_to(directory)
            or directory.is_relative_to(library)
        ):
            raise ValueError("原件库目录与导入目录不能相同或互相包含")
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

    canonical_rows: list[tuple[_Preview, list[_Preview], Path | None]] = []
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
        cover = _resolve_cover(canonical, aliases)
        alias_count += len(aliases)
        canonical_rows.append((canonical, aliases, cover))
        image_count += _count_images(canonical.model_dir, cover)

    existing = _load_existing(root / "manifest.sqlite")
    decisions = {
        canonical.id: _decide_original(library, canonical)
        for canonical, _aliases, _cover in canonical_rows
    }
    inserted = updated = unchanged = 0
    originals = originals_skipped = 0
    for canonical, _aliases, cover in canonical_rows:
        decision = decisions[canonical.id]
        if decision.status == "take":
            originals += 1
        elif decision.status == "skip":
            originals_skipped += 1
            logger.info("original skipped id=%s reason=%s", canonical.id, decision.reason)
        original = _resulting_original(canonical.id, existing.get(canonical.id), decision)
        payload = _payload(canonical, cover, original)
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
        originals=originals,
        originals_skipped=originals_skipped,
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
        for canonical, _aliases, cover in canonical_rows:
            decision = decisions[canonical.id]
            if decision.status == "take":
                _materialize_original(root, canonical.id, decision)
            original = _resulting_original(canonical.id, existing.get(canonical.id), decision)
            _write_images(root, canonical, cover)
            _upsert(conn, canonical, existing.get(canonical.id), cover, original)
        for canonical, aliases, _cover in canonical_rows:
            demoted.extend(_delete_demoted(conn, canonical, aliases))
        for canonical, aliases, _cover in canonical_rows:
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
        plate_layout=plate_layout_json(meta),
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


def _cover_file(model_dir: Path) -> Path | None:
    if model_dir.is_symlink() or not model_dir.is_dir():
        return None
    path = model_dir / "cover.png"
    if path.is_symlink() or not path.is_file():
        return None
    try:
        if not path.resolve().is_relative_to(model_dir.resolve()):
            return None
    except OSError:
        return None
    return path


def _resolve_cover(canonical: _Preview, aliases: list[_Preview]) -> Path | None:
    own = _cover_file(canonical.model_dir)
    if own is not None:
        return own
    for alias in sorted(aliases, key=lambda item: item.id):
        found = _cover_file(alias.model_dir)
        if found is not None:
            return found
    return None


def _count_images(model_dir: Path, cover: Path | None = None) -> int:
    thumb, shots = _iter_shots(model_dir)
    return (1 if thumb is not None else 0) + len(shots) + (0 if cover is None else 1)


def plate_layout_json(meta: dict[str, Any] | None) -> str:
    """Return canonical plate JSON, or ``""`` when the extract has no plate list.

    An empty list means the extract explicitly recorded no plates. Missing or
    invalid metadata stays ``""`` so the API can say the mapping is unknown
    instead of inventing one. Object names are not paired with filament slots;
    the source data only records filaments per print plate.
    """
    if meta is None or "plates" not in meta or not isinstance(meta.get("plates"), list):
        return ""
    plates: list[dict[str, Any]] = []
    for plate in meta["plates"]:
        if not isinstance(plate, dict):
            continue
        index = plate.get("index")
        index_value = index if isinstance(index, int) and not isinstance(index, bool) else None
        name = plain_text(plate.get("name")) or None
        objects: list[str] = []
        raw_objects = plate.get("objects")
        if isinstance(raw_objects, list):
            for item in raw_objects:
                text = plain_text(item)
                if text:
                    objects.append(text)
        filaments: list[dict[str, Any]] = []
        raw_filaments = plate.get("filaments")
        if isinstance(raw_filaments, list):
            for item in raw_filaments:
                if isinstance(item, dict):
                    filaments.append(_filament_record(item))
        plates.append(
            {"index": index_value, "name": name, "objects": objects, "filaments": filaments}
        )
    return json.dumps(plates, ensure_ascii=False, separators=(",", ":"))


def parse_plate_layout(raw: object) -> list[dict[str, Any]] | None:
    """Parse stored plate JSON. ``None`` means the mapping was never stored."""
    if not isinstance(raw, str) or raw == "":
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    plates: list[dict[str, Any]] = []
    for plate in parsed:
        if not isinstance(plate, dict):
            continue
        index = plate.get("index")
        index_value = index if isinstance(index, int) and not isinstance(index, bool) else None
        name = plate.get("name")
        name_value = name if isinstance(name, str) and name else None
        objects = [item for item in plate.get("objects", []) if isinstance(item, str) and item]
        filaments: list[dict[str, Any]] = []
        raw_filaments = plate.get("filaments")
        if isinstance(raw_filaments, list):
            for item in raw_filaments:
                if isinstance(item, dict):
                    filaments.append(_public_filament(item))
        plates.append(
            {
                "index": index_value,
                "name": name_value,
                "objects": objects,
                "filaments": filaments,
            }
        )
    return plates


def _filament_record(item: dict[str, Any]) -> dict[str, Any]:
    slot = item.get("slot")
    slot_value = slot if isinstance(slot, int) and not isinstance(slot, bool) else None
    colors = _normalize_colors([item.get("hex")] if isinstance(item.get("hex"), str) else [])
    used = item.get("used_g")
    used_value = None if isinstance(used, bool) or not isinstance(used, (int, float)) else used
    return {
        "slot": slot_value,
        "hex": colors[0] if colors else None,
        "type": plain_text(item.get("type")),
        "vendor": plain_text(item.get("vendor")),
        "settings_id": plain_text(item.get("settings_id")),
        "used_g": used_value,
    }


def _public_filament(item: dict[str, Any]) -> dict[str, Any]:
    slot = item.get("slot")
    hex_value = item.get("hex")
    used = item.get("used_g")
    return {
        "slot": slot if isinstance(slot, int) and not isinstance(slot, bool) else None,
        "hex": hex_value if isinstance(hex_value, str) and _HEX_RE.fullmatch(hex_value) else None,
        "type": item.get("type") if isinstance(item.get("type"), str) else "",
        "vendor": item.get("vendor") if isinstance(item.get("vendor"), str) else "",
        "settings_id": item.get("settings_id") if isinstance(item.get("settings_id"), str) else "",
        "used_g": used if not isinstance(used, bool) and isinstance(used, (int, float)) else None,
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    _ensure_schema(conn)


def original_suffix(filename: str) -> str | None:
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if suffix in ORIGINAL_TYPES:
        return suffix
    return None


def safe_original_name(filename: str, suffix: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name
    name = name.replace("\x00", "").replace("\r", "").replace("\n", "").replace('"', "")
    if not name or name in {".", ".."} or not name.lower().endswith(suffix):
        return f"model{suffix}"
    return name


def original_is_valid(path: Path, suffix: str) -> bool:
    try:
        if path.is_symlink() or not path.is_file():
            return False
        size = path.stat().st_size
    except OSError:
        return False
    if size <= 0 or size > ORIGINAL_MAX_BYTES or suffix not in ORIGINAL_TYPES:
        return False
    if suffix == ".3mf":
        return _zip_has_model(path)
    if suffix == ".stl":
        return _stl_ok(path, size)
    return False


def install_original(
    root: Path, model_id: str, filename: str, source: Path
) -> tuple[str, str, int, str]:
    """Copy a validated original into ``root/originals``. Never moves ``source``."""
    if _ID_RE.fullmatch(model_id) is None:
        raise ValueError("模型编号无效")
    suffix = original_suffix(filename)
    if suffix is None:
        raise ValueError("只接受 3MF 或 STL 原件")
    if not original_is_valid(source, suffix):
        raise ValueError("文件不是可重新打开的 3MF 或 STL")
    name = safe_original_name(filename, suffix)
    digest = _sha256(source).hex()
    size = source.stat().st_size
    destination = root / "originals" / f"{model_id}{suffix}"
    _copy_file(source, destination)
    _remove_other_originals(root, model_id, suffix)
    return name, digest, size, f"originals/{model_id}{suffix}"


def _decide_original(library: Path | None, preview: _Preview) -> _OriginalDecision:
    if library is None:
        return _OriginalDecision("absent")
    rel_text = preview.rel_path.replace("\\", "/").strip()
    rel = PurePosixPath(rel_text)
    suffix = rel.suffix.lower()
    if suffix not in ORIGINAL_TYPES:
        return _OriginalDecision("absent")
    if not rel_text or rel.is_absolute() or ".." in rel.parts or rel.name in {".", ".."}:
        return _OriginalDecision("skip", suffix=suffix, reason="path")
    root = library.resolve()
    candidate = root.joinpath(*rel.parts)
    try:
        if candidate.is_symlink():
            return _OriginalDecision("skip", suffix=suffix, reason="symlink")
        if not candidate.is_file():
            return _OriginalDecision("skip", suffix=suffix, reason="missing")
        resolved = candidate.resolve()
        size = candidate.stat().st_size
    except OSError:
        return _OriginalDecision("skip", suffix=suffix, reason="unreadable")
    if not resolved.is_relative_to(root) or resolved.parent != candidate.parent.resolve():
        return _OriginalDecision("skip", suffix=suffix, reason="escape")
    if size <= 0 or size > ORIGINAL_MAX_BYTES:
        return _OriginalDecision("skip", suffix=suffix, reason="size")
    if preview.size_bytes and preview.size_bytes != size:
        return _OriginalDecision("skip", suffix=suffix, reason="size-mismatch")
    if not original_is_valid(candidate, suffix):
        return _OriginalDecision("skip", suffix=suffix, reason="invalid")
    return _OriginalDecision(
        "take",
        name=safe_original_name(candidate.name, suffix),
        sha256=_sha256(candidate).hex(),
        size=size,
        suffix=suffix,
        source=candidate,
    )


def _resulting_original(
    model_id: str, current: tuple[Any, ...] | None, decision: _OriginalDecision
) -> tuple[str, str, int, str]:
    if decision.status == "take":
        return (
            decision.name,
            decision.sha256,
            decision.size,
            f"originals/{model_id}{decision.suffix}",
        )
    return _stored_original(current)


def _stored_original(current: tuple[Any, ...] | None) -> tuple[str, str, int, str]:
    if current is None or len(current) < 13:
        return ("", "", 0, "")
    value = current[12]
    if (
        isinstance(value, tuple)
        and len(value) == 4
        and isinstance(value[0], str)
        and isinstance(value[1], str)
        and isinstance(value[2], int)
        and not isinstance(value[2], bool)
        and isinstance(value[3], str)
    ):
        return value
    return ("", "", 0, "")


def _materialize_original(root: Path, model_id: str, decision: _OriginalDecision) -> None:
    if decision.source is None or decision.status != "take":
        return
    install_original(root, model_id, decision.name, decision.source)


def _remove_other_originals(root: Path, model_id: str, suffix: str) -> None:
    directory = root / "originals"
    if directory.is_symlink() or not directory.is_dir():
        return
    if directory.resolve() != root.resolve() / "originals":
        return
    for other in ORIGINAL_TYPES:
        if other == suffix:
            continue
        stale = directory / f"{model_id}{other}"
        if (
            stale.is_file()
            and not stale.is_symlink()
            and stale.parent.resolve() == directory.resolve()
        ):
            stale.unlink()


def _zip_has_model(path: Path) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = {name.replace("\\", "/") for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile):
        return False
    return "3D/3dmodel.model" in names


def _stl_ok(path: Path, size: int) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(84)
    except OSError:
        return False
    if len(header) >= 84:
        count = struct.unpack_from("<I", header, 80)[0]
        if count >= 0 and size == 84 + count * 50:
            return True
    if size > 5_000_000:
        return False
    try:
        text = path.read_bytes().lower()
    except OSError:
        return False
    return text.startswith(b"solid") and b"facet" in text and b"endsolid" in text


def _payload(
    preview: _Preview, cover: Path | None, original: tuple[str, str, int, str]
) -> tuple[Any, ...]:
    thumb, shots = _iter_shots(preview.model_dir)
    if cover is not None:
        shots = [_Shot("cover", 0, "cover.png", cover), *shots]
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
        preview.plate_layout,
        original,
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
        str(cell("plate_layout", "")),
        _original_cell(cell),
    )


def _original_cell(cell: Any) -> tuple[str, str, int, str]:
    size = cell("original_size", 0)
    if isinstance(size, bool) or not isinstance(size, int):
        size = 0
    return (
        str(cell("original_name", "") or ""),
        str(cell("original_sha256", "") or ""),
        size,
        str(cell("original_relpath", "") or ""),
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
        if not isinstance(name, str):
            continue
        if kind == "cover" and name == "cover.png":
            shots.append(("cover", 0, "cover.png"))
            continue
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


def _write_images(root: Path, preview: _Preview, cover: Path | None = None) -> None:
    thumb, shots = _iter_shots(preview.model_dir)
    if cover is not None:
        shots = [_Shot("cover", 0, "cover.png", cover), *shots]
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


def _upsert(
    conn: sqlite3.Connection,
    preview: _Preview,
    current: tuple[Any, ...] | None,
    cover: Path | None,
    original: tuple[str, str, int, str],
) -> None:
    payload = _payload(preview, cover, original)
    thumb_path = payload[7]
    shot_tuples = payload[10]
    images = [{"kind": kind, "plate": plate, "name": name} for kind, plate, name in shot_tuples]
    colours = json.dumps(list(preview.colors), ensure_ascii=False)
    image_json = json.dumps(images, ensure_ascii=False)
    digest = hashlib.sha256(preview.id.encode()).hexdigest()
    now = datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM model_aliases WHERE alias_id = ?", (preview.id,))
    original_name, original_sha256, original_size, original_relpath = original
    if current is None:
        conn.execute(
            "INSERT INTO models (id, sha256, title, series, author, source_relpath, "
            "size_bytes, plate_count, colours, thumb_path, created_at, description, "
            "dedupe_key, images, updated_at, plate_layout, original_name, "
            "original_sha256, original_size, original_relpath) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                preview.plate_layout,
                original_name,
                original_sha256,
                original_size,
                original_relpath,
            ),
        )
        return
    conn.execute(
        "UPDATE models SET sha256 = ?, title = ?, series = ?, author = ?, source_relpath = ?, "
        "size_bytes = ?, plate_count = ?, colours = ?, thumb_path = ?, description = ?, "
        "dedupe_key = ?, images = ?, updated_at = ?, plate_layout = ?, original_name = ?, "
        "original_sha256 = ?, original_size = ?, original_relpath = ? WHERE id = ?",
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
            preview.plate_layout,
            original_name,
            original_sha256,
            original_size,
            original_relpath,
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
