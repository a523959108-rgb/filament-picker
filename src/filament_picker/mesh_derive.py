"""Derive a private GLB and orthographic front views from a 3MF mesh.

Build-item transforms and model units are applied. Plate images are emitted
only when every printable build item is listed on a plate. Otherwise the
result is one overall front view, not a guessed per-plate crop. Slice
thumbnails are never copied or renamed into these files.
"""

from __future__ import annotations

import array
import hashlib
import io
import json
import logging
import math
import os
import re
import threading
import xml.parsers.expat as expat
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageDraw

from .config import TZ
from .mesh_glb import _chunk
from .originals import content_sha256

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 10_000
_MAX_ENTRY = 512 * 1024 * 1024
_MAX_TOTAL_UNCOMPRESSED = 4 * 1024 * 1024 * 1024
_MAX_TRIANGLES = 30_000_000
_TARGET_OBJECT_TRIANGLES = 120_000
_TARGET_SCENE_TRIANGLES = 450_000
_RENDER_MAX_TRIANGLES = 150_000
_UNITS = {
    "micron": 0.001,
    "millimeter": 1.0,
    "centimeter": 10.0,
    "meter": 1000.0,
    "inch": 25.4,
    "foot": 304.8,
}
_OVERALL_NOTE = "仅整体正视，没有可靠的盘面定位。这是网格正交投影，不是切片斜视图。"
_PLATE_NOTE = "网格正交正视，不是切片斜视图。"
_LOCKS: dict[str, threading.Lock] = {}
_LOCK_GUARD = threading.Lock()


class DeriveError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def model_lock(model_id: str) -> threading.Lock:
    with _LOCK_GUARD:
        lock = _LOCKS.get(model_id)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[model_id] = lock
        return lock


def parse_scene(source: bytes | Path | os.PathLike[str]) -> dict[str, Any]:
    """Return world-space triangles in millimeters and a plate assignment."""
    archive = _open_zip(source)
    try:
        if "3D/3dmodel.model" not in archive.namelist():
            raise DeriveError("没有 3D/3dmodel.model，不能派生网格")
        cache: dict[str, tuple[dict[int, dict[str, Any]], float, list[dict[str, Any]]]] = {}
        root_objects, root_unit, items = _load_objects(archive, "3D/3dmodel.model", cache)
        plates = _plate_map(archive)
    finally:
        archive.close()
    if not items:
        raise DeriveError("没有可打印的构建项，不能派生网格")
    parts: list[dict[str, Any]] = []
    for item in items:
        obj = root_objects.get(item["object_id"])
        if obj is None:
            raise DeriveError(f"构建项 {item['object_id']} 没有网格，不能派生")
        positions, indices = _flatten(obj, item["transform"], root_unit, ())
        if len(indices) == 0:
            continue
        parts.append(
            {
                "object_id": item["object_id"],
                "plate": plates.get(item["object_id"]),
                "positions": positions,
                "indices": indices,
            }
        )
    if not parts:
        raise DeriveError("网格里没有三角面，不能派生")
    total = sum(len(part["indices"]) for part in parts)
    if total > _MAX_TRIANGLES:
        raise DeriveError("三角面过多，没有生成派生文件")
    if total > _TARGET_SCENE_TRIANGLES:
        for part in parts:
            count = len(part["indices"])
            if count <= 10_000:
                continue
            budget = max(10_000, int(_TARGET_SCENE_TRIANGLES * (count / total)))
            if count > budget:
                part["positions"], part["indices"] = _decimate_mesh(
                    part["positions"], part["indices"], budget
                )
    assigned = all(part["plate"] is not None for part in parts)
    return {"unit": "millimeter", "parts": parts, "scope": "plate" if assigned else "overall"}


def build_glb(scene: dict[str, Any]) -> bytes:
    primitives: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    views: list[dict[str, Any]] = []
    blob = bytearray()
    for part in scene["parts"]:
        positions = np.asarray(part["positions"], dtype=np.float32)
        indices = np.asarray(part["indices"], dtype=np.uint32).reshape(-1)
        normals = _vertex_normals(positions, indices.reshape(-1, 3))
        pos_bytes = positions.tobytes()
        nrm_bytes = normals.tobytes()
        idx_bytes = indices.tobytes()
        pos_off = _align(blob)
        blob.extend(pos_bytes)
        nrm_off = _align(blob)
        blob.extend(nrm_bytes)
        idx_off = _align(blob)
        blob.extend(idx_bytes)
        base = len(accessors)
        views.extend(
            [
                {"buffer": 0, "byteOffset": pos_off, "byteLength": len(pos_bytes), "target": 34962},
                {"buffer": 0, "byteOffset": nrm_off, "byteLength": len(nrm_bytes), "target": 34962},
                {"buffer": 0, "byteOffset": idx_off, "byteLength": len(idx_bytes), "target": 34963},
            ]
        )
        low = positions.min(axis=0)
        high = positions.max(axis=0)
        accessors.extend(
            [
                {
                    "bufferView": base,
                    "componentType": 5126,
                    "count": int(positions.shape[0]),
                    "type": "VEC3",
                    "min": [float(low[0]), float(low[1]), float(low[2])],
                    "max": [float(high[0]), float(high[1]), float(high[2])],
                },
                {
                    "bufferView": base + 1,
                    "componentType": 5126,
                    "count": int(positions.shape[0]),
                    "type": "VEC3",
                },
                {
                    "bufferView": base + 2,
                    "componentType": 5125,
                    "count": int(indices.shape[0]),
                    "type": "SCALAR",
                },
            ]
        )
        primitives.append(
            {
                "attributes": {"POSITION": base, "NORMAL": base + 1},
                "indices": base + 2,
                "material": 0,
            }
        )
    document = {
        "asset": {"version": "2.0", "generator": "filament-picker-derive"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "materials": [
            {
                "name": "derived",
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.78, 0.8, 0.82, 1.0],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.62,
                },
            }
        ],
        "meshes": [{"primitives": primitives}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = _chunk(0x4E4F534A, payload, b" ") + _chunk(0x004E4942, bytes(blob), b"\x00")
    import struct

    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def render_front(scene: dict[str, Any], parts: list[dict[str, Any]] | None = None) -> bytes:
    """Orthographic view from the front of the bed: X to the right, Z up."""
    chosen = scene["parts"] if parts is None else parts
    positions = np.concatenate([part["positions"] for part in chosen])
    indices = _offset_indices(chosen)
    if len(indices) == 0:
        raise DeriveError("没有三角面，不能生成正视")
    width, height = 720, 540
    xs = positions[:, 0]
    zs = positions[:, 2]
    depth = positions[:, 1]
    span_x = float(xs.max() - xs.min())
    span_z = float(zs.max() - zs.min())
    span = max(span_x, span_z, 1e-3)
    pad = span * 0.08
    min_x, max_x = float(xs.min()) - pad, float(xs.max()) + pad
    min_z, max_z = float(zs.min()) - pad, float(zs.max()) + pad
    scale = min((width - 1) / (max_x - min_x), (height - 1) / (max_z - min_z))
    used_w = (max_x - min_x) * scale
    used_h = (max_z - min_z) * scale
    origin_x = (width - used_w) / 2
    origin_y = (height - used_h) / 2

    px = origin_x + (xs - min_x) * scale
    py = origin_y + (max_z - zs) * scale

    v0 = positions[indices[:, 0]]
    v1 = positions[indices[:, 1]]
    v2 = positions[indices[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    norms = np.linalg.norm(cross, axis=1)
    valid = norms >= 1e-8
    if len(indices) > 50_000:
        tri_px = px[indices]
        tri_py = py[indices]
        span_px = tri_px.max(axis=1) - tri_px.min(axis=1)
        span_py = tri_py.max(axis=1) - tri_py.min(axis=1)
        valid &= (span_px >= 0.4) | (span_py >= 0.4)

    image = Image.new("RGB", (width, height), "#0d1c2d")
    if np.any(valid):
        valid_indices = indices[valid]
        means = depth[valid_indices].mean(axis=1)
        order = np.argsort(-means)
        if len(order) > _RENDER_MAX_TRIANGLES:
            order = order[-_RENDER_MAX_TRIANGLES:]
        ordered = valid_indices[order]
        facing = np.minimum(1.0, np.abs(cross[valid, 1]) / norms[valid])[order]
        shades = (150 + 90 * facing).astype(np.int64).tolist()
        px_list = px.tolist()
        py_list = py.tolist()
        draw = ImageDraw.Draw(image)
        for (i0, i1, i2), shade in zip(ordered.tolist(), shades, strict=True):
            draw.polygon(
                [
                    (px_list[i0], py_list[i0]),
                    (px_list[i1], py_list[i1]),
                    (px_list[i2], py_list[i2]),
                ],
                fill=(shade, shade, shade + 4),
            )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _derive_source(
    source: bytes | Path | os.PathLike[str],
    source_digest: str | None = None,
) -> tuple[bytes, dict[str, bytes], dict[str, Any]]:
    scene = parse_scene(source)
    glb = build_glb(scene)
    if not glb.startswith(b"glTF") or len(glb) < 20:
        raise DeriveError("GLB 没有生成")
    images = {"front.png": render_front(scene)}
    record_plates: list[dict[str, Any]] = []
    if scene["scope"] == "plate":
        grouped: dict[int, list[dict[str, Any]]] = {}
        for part in scene["parts"]:
            grouped.setdefault(int(part["plate"]), []).append(part)
        for plate in sorted(grouped):
            name = f"front-{plate}.png"
            images[name] = render_front(scene, grouped[plate])
            record_plates.append(
                {
                    "index": plate,
                    "front": name,
                    "triangles": int(sum(len(part["indices"]) for part in grouped[plate])),
                }
            )
    note = _PLATE_NOTE if scene["scope"] == "plate" else _OVERALL_NOTE
    digest = (
        source_digest
        if source_digest is not None
        else (
            hashlib.sha256(source).hexdigest()
            if isinstance(source, bytes)
            else content_sha256(Path(source))
        )
    )
    record = {
        "source_sha256": digest,
        "status": "ready",
        "scope": scene["scope"],
        "note": note,
        "error": None,
        "triangles": int(sum(len(part["indices"]) for part in scene["parts"])),
        "unit": scene["unit"],
        "glb": "model.glb",
        "front": "front.png",
        "plates": record_plates,
    }
    if len(images["front.png"]) < 32:
        raise DeriveError("正视图片是空的")
    return glb, images, record


def derive_bytes(source: bytes) -> tuple[bytes, dict[str, bytes], dict[str, Any]]:
    return _derive_source(source)


def save_derived_scene(
    root: Path, model_id: str, source_sha: str, scene: dict[str, Any]
) -> dict[str, Any]:
    """Write a GLB and front view for an already parsed scene. Does not touch originals."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", model_id):
        raise DeriveError("模型编号无效")
    glb = build_glb(scene)
    images = {"front.png": render_front(scene)}
    record = {
        "model_id": model_id,
        "source_sha256": source_sha,
        "status": "ready",
        "scope": scene.get("scope") or "overall",
        "note": _OVERALL_NOTE,
        "error": None,
        "triangles": int(sum(len(part["indices"]) for part in scene["parts"])),
        "unit": scene.get("unit") or "millimeter",
        "glb": "model.glb",
        "front": "front.png",
        "plates": [],
        "updated_at": datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds"),
    }
    directory = _derived_dir(root, model_id)
    if _inside_originals(root, directory):
        raise DeriveError("派生目录不能放在原件目录里")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = directory / ".model.glb.tmp"
    temporary.write_bytes(glb)
    temporary.chmod(0o600)
    temporary.replace(directory / "model.glb")
    image_tmp = directory / ".front.png.tmp"
    image_tmp.write_bytes(images["front.png"])
    image_tmp.chmod(0o600)
    image_tmp.replace(directory / "front.png")
    _write_index(directory, record)
    return record


def derive_file(root: Path, model_id: str, source: Path, *, force: bool = False) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", model_id):
        raise DeriveError("模型编号无效")
    digest = content_sha256(source)
    directory = _derived_dir(root, model_id)
    current = _read_index(directory)
    if (
        not force
        and current is not None
        and current.get("status") == "ready"
        and current.get("source_sha256") == digest
        and _outputs_present(directory, current)
    ):
        return current
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        glb, images, record = _derive_source(source, source_digest=digest)
    except DeriveError as exc:
        _clear_outputs(directory)
        failed = _failed_record(model_id, digest, exc.detail)
        _write_index(directory, failed)
        if content_sha256(source) != digest:
            raise DeriveError("原件被改动，已中止") from exc
        return failed
    if content_sha256(source) != digest:
        raise DeriveError("原件被改动，已中止")
    if _inside_originals(root, directory):
        raise DeriveError("派生目录不能放在原件目录里")
    temporary_glb = directory / ".model.glb.tmp"
    temporary_glb.write_bytes(glb)
    temporary_glb.chmod(0o600)
    temporary_glb.replace(directory / "model.glb")
    for name, payload in images.items():
        target = directory / name
        temporary = directory / f".{name}.tmp"
        temporary.write_bytes(payload)
        temporary.chmod(0o600)
        temporary.replace(target)
    record["model_id"] = model_id
    record["updated_at"] = datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
    _write_index(directory, record)
    return record


def derived_index(root: Path, model_id: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", model_id):
        return None
    return _read_index(_derived_dir(root, model_id))


def derived_file(root: Path, model_id: str, name: str) -> Path | None:
    if not re.fullmatch(r"model\.glb|front\.png|front-[1-9][0-9]{0,2}\.png", name):
        return None
    directory = _derived_dir(root, model_id).resolve()
    candidate = directory / name
    try:
        path = candidate.resolve()
    except OSError:
        return None
    if path.parent != directory or candidate.is_symlink() or not path.is_file():
        return None
    index = _read_index(directory)
    if index is None or index.get("status") != "ready":
        return None
    return path


def _open_zip(source: bytes | Path | os.PathLike[str]) -> zipfile.ZipFile:
    stream: io.BytesIO | Path | os.PathLike[str] = (
        io.BytesIO(source) if isinstance(source, bytes) else source
    )
    try:
        archive = zipfile.ZipFile(stream)
    except zipfile.BadZipFile as exc:
        raise DeriveError("不是 3MF 压缩包，没有派生") from exc
    infos = archive.infolist()
    if len(infos) > _MAX_ENTRIES:
        archive.close()
        raise DeriveError("3MF 条目过多，没有派生")
    total_size = 0
    for info in infos:
        name = info.filename
        pure = PurePosixPath(name)
        if name.startswith("/") or "\\" in name or ".." in pure.parts or pure.is_absolute():
            archive.close()
            raise DeriveError("3MF 路径不安全，没有派生")
        if info.file_size > _MAX_ENTRY:
            archive.close()
            raise DeriveError("3MF 里有过大的文件，没有派生")
        total_size += info.file_size
    if total_size > _MAX_TOTAL_UNCOMPRESSED:
        archive.close()
        raise DeriveError("3MF 解压后过大，没有派生")
    return archive


def _attr_ci(attrs: dict[str, str], target: str) -> str | None:
    direct = attrs.get(target)
    if direct is not None:
        return direct
    for key, value in attrs.items():
        if key.rsplit(" ", 1)[-1].rsplit(":", 1)[-1] == target:
            return value
    return None


def _cluster_once(
    positions: np.ndarray,
    indices: np.ndarray,
    grid_k: int,
) -> tuple[np.ndarray, np.ndarray]:
    bmin = positions.min(axis=0)
    span = float((positions.max(axis=0) - bmin).max())
    if span <= 1e-9:
        return positions, indices
    voxel = span / float(grid_k)
    coords = np.floor((positions - bmin) / voxel).astype(np.int64)
    coords = np.clip(coords, 0, grid_k)
    stride = int(grid_k) + 1
    keys = coords[:, 0] * (stride * stride) + coords[:, 1] * stride + coords[:, 2]
    _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    new_pos = np.zeros((len(counts), 3), dtype=np.float64)
    np.add.at(new_pos, inverse, positions)
    new_pos /= counts[:, None]
    remapped = inverse[indices]
    keep = (
        (remapped[:, 0] != remapped[:, 1])
        & (remapped[:, 1] != remapped[:, 2])
        & (remapped[:, 2] != remapped[:, 0])
    )
    remapped = remapped[keep]
    if len(remapped) == 0:
        return positions, indices
    canonical = np.ascontiguousarray(np.sort(remapped, axis=1), dtype=np.int64)
    row_view = canonical.view(np.dtype((np.void, canonical.dtype.itemsize * 3))).ravel()
    _, unique_idx = np.unique(row_view, return_index=True)
    remapped = remapped[np.sort(unique_idx)]
    return new_pos, remapped


def _decimate_mesh(
    positions: np.ndarray,
    indices: np.ndarray,
    target_triangles: int,
) -> tuple[np.ndarray, np.ndarray]:
    if len(indices) <= target_triangles or target_triangles <= 0:
        return positions, indices
    grid_k = max(24, min(512, round(math.sqrt(target_triangles / 4.0))))
    dec_pos, dec_idx = _cluster_once(positions, indices, grid_k)
    if len(dec_idx) > int(target_triangles * 1.5):
        next_k = max(16, round(grid_k * math.sqrt(target_triangles / max(len(dec_idx), 1))))
        if next_k < grid_k:
            dec_pos, dec_idx = _cluster_once(positions, indices, next_k)
    return dec_pos, dec_idx


def _load_objects(
    archive: zipfile.ZipFile,
    name: str,
    cache: dict[str, tuple[dict[int, dict[str, Any]], float, list[dict[str, Any]]]],
) -> tuple[dict[int, dict[str, Any]], float, list[dict[str, Any]]]:
    key = name.lstrip("/")
    cached = cache.get(key)
    if cached is not None:
        return cached
    if key not in archive.namelist():
        raise DeriveError(f"缺少网格 {key}，没有派生")

    objects: dict[int, dict[str, Any]] = {}
    build_items: list[dict[str, Any]] = []
    unit_holder: list[float] = [1.0]
    pending: list[tuple[int, list[tuple[str, str, str | None]]]] = []
    cache[key] = (objects, 1.0, build_items)

    in_build = False
    current_object_id: int | None = None
    in_mesh = False
    vertices = array.array("d")
    triangles = array.array("q")
    comp_refs: list[tuple[str, str, str | None]] = []

    parser = expat.ParserCreate(namespace_separator=" ")

    def _reject_dtd(*_args: object) -> None:
        raise DeriveError(f"{key} 含有 DTD，没有派生")

    def _start(raw_name: str, attrs: dict[str, str]) -> None:
        nonlocal in_build, current_object_id, in_mesh
        local = raw_name.rsplit(" ", 1)[-1]
        if local == "model":
            unit_name = _attr_ci(attrs, "unit") or "millimeter"
            unit = _UNITS.get(unit_name)
            if unit is None:
                raise DeriveError(f"不认识的长度单位 {unit_name}")
            unit_holder[0] = unit
            return
        if local == "build":
            in_build = True
            return
        if in_build and local == "item":
            if (_attr_ci(attrs, "printable") or "1") == "0":
                return
            raw_id = _attr_ci(attrs, "objectid")
            if raw_id is None or not raw_id.isdigit():
                raise DeriveError("构建项编号无效，没有派生")
            build_items.append(
                {
                    "object_id": int(raw_id),
                    "transform": _transform(_attr_ci(attrs, "transform")),
                }
            )
            return
        if local == "object":
            raw_id = _attr_ci(attrs, "id")
            if raw_id is not None and raw_id.isdigit():
                current_object_id = int(raw_id)
                in_mesh = False
                del vertices[:]
                del triangles[:]
                comp_refs.clear()
            else:
                current_object_id = None
            return
        if current_object_id is None:
            return
        if local == "mesh":
            in_mesh = True
            return
        if in_mesh and local == "vertex":
            vertices.extend(
                (
                    float(_attr_ci(attrs, "x") or "0"),
                    float(_attr_ci(attrs, "y") or "0"),
                    float(_attr_ci(attrs, "z") or "0"),
                )
            )
            return
        if in_mesh and local == "triangle":
            triangles.extend(
                (
                    int(_attr_ci(attrs, "v1") or "-1"),
                    int(_attr_ci(attrs, "v2") or "-1"),
                    int(_attr_ci(attrs, "v3") or "-1"),
                )
            )
            return
        if local == "component":
            child_id = _attr_ci(attrs, "objectid")
            if child_id is None or not child_id.isdigit():
                raise DeriveError("组件编号无效，没有派生")
            child_path = (_attr_ci(attrs, "path") or key).lstrip("/")
            if (
                ".." in PurePosixPath(child_path).parts
                or "://" in child_path
                or child_path.startswith("//")
                or child_path.startswith("\\\\")
            ):
                raise DeriveError("组件路径不安全，没有派生")
            comp_refs.append((child_id, child_path, _attr_ci(attrs, "transform")))

    def _end(raw_name: str) -> None:
        nonlocal in_build, current_object_id, in_mesh
        local = raw_name.rsplit(" ", 1)[-1]
        if local == "build":
            in_build = False
            return
        if local == "mesh":
            in_mesh = False
            return
        if local == "object" and current_object_id is not None:
            if vertices:
                positions = np.array(vertices, dtype=np.float64).reshape(-1, 3)
            else:
                positions = np.zeros((0, 3), dtype=np.float64)
            if triangles:
                indices = np.array(triangles, dtype=np.int64).reshape(-1, 3)
                if np.any(indices < 0) or np.any(indices >= len(positions)):
                    raise DeriveError("三角面引用了不存在的顶点，没有派生")
                if len(indices) > _TARGET_OBJECT_TRIANGLES:
                    positions, indices = _decimate_mesh(
                        positions, indices, _TARGET_OBJECT_TRIANGLES
                    )
            else:
                indices = np.zeros((0, 3), dtype=np.int64)
            del vertices[:]
            del triangles[:]
            objects[current_object_id] = {
                "positions": positions,
                "indices": indices,
                "unit": unit_holder[0],
                "components": [],
            }
            if comp_refs:
                pending.append((current_object_id, list(comp_refs)))
                comp_refs.clear()
            current_object_id = None

    parser.StartDoctypeDeclHandler = _reject_dtd
    parser.EntityDeclHandler = _reject_dtd
    parser.UnparsedEntityDeclHandler = _reject_dtd
    parser.StartElementHandler = _start
    parser.EndElementHandler = _end

    tail = b""
    try:
        with archive.open(key) as stream:
            while chunk := stream.read(1 << 20):
                probe = tail + chunk
                if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
                    raise DeriveError(f"{key} 含有 DTD，没有派生")
                tail = probe[-16:]
                parser.Parse(chunk, False)
            parser.Parse(b"", True)
    except expat.ExpatError as exc:
        raise DeriveError(f"{key} 不是可解析的网格") from exc

    cache[key] = (objects, unit_holder[0], build_items)
    for object_id, refs in pending:
        parts: list[dict[str, Any]] = []
        for child_id, child_path, transform_raw in refs:
            child_objects, _child_unit, _child_build = _load_objects(archive, child_path, cache)
            child = child_objects.get(int(child_id))
            if child is None:
                raise DeriveError(f"组件 {child_id} 不存在，没有派生")
            parts.append({"object": child, "transform": _transform(transform_raw)})
        objects[object_id]["components"] = parts
    return objects, unit_holder[0], build_items


def _plate_map(archive: zipfile.ZipFile) -> dict[int, int]:
    if "Metadata/model_settings.config" not in archive.namelist():
        return {}
    try:
        root = ElementTree.fromstring(archive.read("Metadata/model_settings.config"))
    except ElementTree.ParseError as exc:
        raise DeriveError("model_settings.config 无法解析，没有按盘派生") from exc
    found: dict[int, int] = {}
    for plate in _children(root, "plate"):
        raw_index = None
        for meta in _children(plate, "metadata"):
            if _attr(meta, "key") == "plater_id":
                raw_index = _attr(meta, "value")
        if raw_index is None or not raw_index.isdigit():
            continue
        index = int(raw_index)
        for instance in _children(plate, "model_instance"):
            raw_object = None
            for meta in _children(instance, "metadata"):
                if _attr(meta, "key") == "object_id":
                    raw_object = _attr(meta, "value")
            if raw_object is None or not raw_object.isdigit():
                continue
            object_id = int(raw_object)
            previous = found.get(object_id)
            if previous is not None and previous != index:
                raise DeriveError(f"对象 {object_id} 同时出现在多张盘上，没有按盘派生")
            found[object_id] = index
    return found


def _flatten(
    obj: dict[str, Any],
    transform: np.ndarray,
    parent_unit: float,
    stack: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray]:
    marker = id(obj)
    if marker in stack:
        raise DeriveError("组件循环引用，没有派生")
    scale = float(obj["unit"])
    local = _scale_translation(transform, parent_unit)
    chunks_p: list[np.ndarray] = []
    chunks_i: list[np.ndarray] = []
    positions = obj["positions"]
    if len(positions):
        world = _apply(local, positions * scale)
        chunks_p.append(world)
        chunks_i.append(obj["indices"])
    for component in obj["components"]:
        child_p, child_i = _flatten(
            component["object"], component["transform"], scale, (*stack, marker)
        )
        if len(child_i) == 0:
            continue
        chunks_p.append(_apply(local, child_p))
        chunks_i.append(child_i)
    if not chunks_p:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int64)
    return _merge(chunks_p, chunks_i)


def _merge(parts: list[np.ndarray], faces: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    positions: list[np.ndarray] = []
    indices: list[np.ndarray] = []
    cursor = 0
    for points, tris in zip(parts, faces, strict=True):
        positions.append(points)
        indices.append(tris + cursor)
        cursor += len(points)
    return np.concatenate(positions), np.concatenate(indices)


def _offset_indices(parts: list[dict[str, Any]]) -> np.ndarray:
    chunks: list[np.ndarray] = []
    cursor = 0
    for part in parts:
        chunks.append(part["indices"] + cursor)
        cursor += len(part["positions"])
    return np.concatenate(chunks) if chunks else np.zeros((0, 3), dtype=np.int64)


def _apply(transform: np.ndarray, points: np.ndarray) -> np.ndarray:
    rotation = transform[:3, :3]
    translation = transform[:3, 3]
    return points @ rotation.T + translation


def _scale_translation(transform: np.ndarray, unit: float) -> np.ndarray:
    scaled = transform.copy()
    scaled[:3, 3] *= unit
    return scaled


def _transform(raw: str | None) -> np.ndarray:
    matrix = np.eye(4, dtype=np.float64)
    if not raw:
        return matrix
    parts = raw.split()
    if len(parts) != 12:
        raise DeriveError("变换矩阵不是 12 个数，没有派生")
    try:
        values = [float(part) for part in parts]
    except ValueError as exc:
        raise DeriveError("变换矩阵含有非数字，没有派生") from exc
    matrix[0, :3] = values[0:3]
    matrix[1, :3] = values[3:6]
    matrix[2, :3] = values[6:9]
    matrix[:3, 3] = values[9:12]
    return matrix


def _vertex_normals(positions: np.ndarray, faces: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(positions)
    corners = positions[faces]
    face_normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    for corner in range(3):
        np.add.at(normals, faces[:, corner], face_normals)
    lengths = np.linalg.norm(normals, axis=1)
    lengths[lengths == 0] = 1
    return (normals / lengths[:, None]).astype(np.float32)


def _align(blob: bytearray) -> int:
    while len(blob) % 4:
        blob.append(0)
    return len(blob)


def _derived_dir(root: Path, model_id: str) -> Path:
    return root.resolve() / "derived" / model_id


def _inside_originals(root: Path, directory: Path) -> bool:
    try:
        directory.resolve().relative_to(root.resolve() / "originals")
    except ValueError:
        return False
    return True


def _outputs_present(directory: Path, record: dict[str, Any]) -> bool:
    names = ["model.glb", "front.png"]
    names.extend(str(plate["front"]) for plate in record.get("plates") or [])
    return all(
        (directory / name).is_file() and not (directory / name).is_symlink() for name in names
    )


def _clear_outputs(directory: Path) -> None:
    if not directory.is_dir():
        return
    for name in os.listdir(directory):
        if name == "index.json":
            continue
        path = directory / name
        if path.is_file() and not path.is_symlink():
            path.unlink()


def _failed_record(model_id: str, digest: str, detail: str) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "source_sha256": digest,
        "status": "failed",
        "scope": "overall",
        "note": detail,
        "error": detail,
        "triangles": 0,
        "unit": None,
        "glb": None,
        "front": None,
        "plates": [],
        "updated_at": datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds"),
    }


def _read_index(directory: Path) -> dict[str, Any] | None:
    path = directory / "index.json"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _write_index(directory: Path, record: dict[str, Any]) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    target = directory / "index.json"
    temporary = directory / ".index.json.tmp"
    temporary.write_text(payload, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(target)


def _children(node: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in list(node) if _local(child.tag) == name]


def _child(node: ElementTree.Element, name: str) -> ElementTree.Element | None:
    found = _children(node, name)
    return found[0] if found else None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(node: ElementTree.Element, name: str) -> str | None:
    for key, value in node.attrib.items():
        if _local(key) == name:
            return value
    return None
