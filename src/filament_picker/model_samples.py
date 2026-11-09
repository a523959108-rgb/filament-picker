from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from .config import TZ
from .mesh_glb import sample_glb_bytes


def seed_samples(root: Path) -> int:
    """Write eight synthetic records; refuse to overwrite a non-sample manifest."""
    colours = ("#E76F51", "#2A9D8F", "#E9C46A", "#457B9D")
    records = [
        (
            f"sample-{index:02d}",
            hashlib.sha256(f"synthetic-model-{index}".encode()).hexdigest(),
            f"纯色样例 {index:02d}",
            ("几何样例", "色彩样例")[index % 2],
            ("样例作者甲", "样例作者乙", "样例作者丙")[index % 3],
            f"synthetic/sample-{index:02d}",
            index * 1024 * 1024,
            index % 3 + 1,
            json.dumps([colours[(index - 1) % 4], "#FFFFFF"], ensure_ascii=False, indent=2),
            f"thumbs/sample-{index:02d}.png",
        )
        for index in range(1, 9)
    ]
    manifest = root / "manifest.sqlite"
    if manifest.exists():
        with closing(sqlite3.connect(manifest.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            existing = conn.execute(
                "SELECT id, sha256, title, series, author, source_relpath, size_bytes, "
                "plate_count, colours, thumb_path FROM models ORDER BY id"
            ).fetchall()
        if existing != records:
            raise ValueError("refusing to overwrite a non-sample manifest")
        _ensure_sample_mesh(root)
        return len(records)
    (root / "thumbs").mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
    with closing(sqlite3.connect(manifest)) as conn, conn:
        conn.execute(
            "CREATE TABLE models (id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, "
            "title TEXT NOT NULL, series TEXT NOT NULL, author TEXT NOT NULL, "
            "source_relpath TEXT NOT NULL, size_bytes INTEGER NOT NULL, "
            "plate_count INTEGER NOT NULL, colours TEXT NOT NULL, thumb_path TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        for index, record in enumerate(records):
            Image.new("RGB", (320, 240), colours[index % 4]).save(root / record[9], format="PNG")
            conn.execute(
                "INSERT INTO models VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*record, created_at),
            )
    _ensure_sample_mesh(root)
    return len(records)


def _ensure_sample_mesh(root: Path) -> None:
    """Add the synthetic cube for sample-01 when that file is absent.

    A file that is already there is left untouched, including a replacement an
    operator dropped in for the sample id. Non-sample manifests never reach
    this helper. A ``meshes`` directory that resolves outside ``root`` is refused.
    """
    directory = root / "meshes"
    destination = directory / "sample-01.glb"
    if destination.exists():
        return
    resolved_root = root.resolve()
    if directory.exists() and directory.resolve() != resolved_root / "meshes":
        raise ValueError("sample mesh directory escapes the models root")
    directory.mkdir(parents=True, exist_ok=True)
    if destination.resolve().parent != directory.resolve():
        raise ValueError("sample mesh directory escapes the models root")
    destination.write_bytes(sample_glb_bytes())
