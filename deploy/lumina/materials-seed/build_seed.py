"""Build and verify a deterministic Lumina material seed archive.

The seed is deliberately generated from the checked-in filament catalog.  It
contains display-color estimates only; the Stage-A vectors are conservative
placeholders until a printed gradient card has been measured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG = ROOT / "data" / "build" / "filament-catalog.json"
DEFAULT_LUMINA_ROOT = Path("/workspace/dev/filament-lumina")
if not DEFAULT_LUMINA_ROOT.is_dir():
    DEFAULT_LUMINA_ROOT = Path("/workspace/lumina-upstream")
OUTPUT_DATE_FALLBACK = "20261106"
BUILD_TIMESTAMP = "2026-11-06T19:07:41+09:00"
APPROXIMATION_NOTE = "近似（由官方 hex 估算，非实测光谱/透光数据）"
SOURCE_NOTE = "由 filament-picker 目录中的 Bambu Lab 官方 hex 估算；未进行实物光谱或透光率测量。"
DEFAULT_K = (2.0, 2.0, 2.0)
DEFAULT_E_SCALE = 0.35
WHITE_C0 = (1.0, 1.0, 1.0)
BLACK_C0 = (0.01, 0.01, 0.01)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode(
        "utf-8"
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex_to_srgb(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.strip().removeprefix("#")
    if len(value) != 6:
        raise ValueError(f"Expected a six-digit hex color, got {hex_value!r}")
    try:
        channels = tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as exc:
        raise ValueError(f"Invalid hex color: {hex_value!r}") from exc
    return channels  # type: ignore[return-value]


def _srgb_to_linear(channel: int) -> float:
    normalized = channel / 255.0
    if normalized <= 0.04045:
        return normalized / 12.92
    return ((normalized + 0.055) / 1.055) ** 2.4


def _estimated_e(rgb: tuple[int, int, int]) -> list[float]:
    return [round(DEFAULT_E_SCALE * _srgb_to_linear(channel), 6) for channel in rgb]


def _catalog_entries(catalog_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError("filament catalog must contain an entries list")
    selected: list[dict[str, Any]] = []
    for entry in payload["entries"]:
        if not isinstance(entry, dict):
            continue
        if entry.get("brand_slug") != "bambu-lab":
            continue
        if entry.get("material") != "PLA":
            continue
        if entry.get("series_name") not in {"PLA Basic", "PLA Matte"}:
            continue
        if entry.get("hex_source") != "official":
            continue
        hex_values = entry.get("hex")
        effects = entry.get("effects") or []
        if not isinstance(hex_values, list) or len(hex_values) != 1:
            continue
        if not isinstance(effects, list) or "gradient" in effects or "multicolor" in effects:
            continue
        required = ("id", "name_en", "name_zh", "code", "series_name", "hex")
        if any(not str(entry.get(key) or "").strip() for key in required):
            continue
        selected.append(entry)
    selected.sort(key=lambda item: str(item["id"]))
    if not selected:
        raise ValueError("No official Bambu Lab PLA Basic/PLA Matte hex entries found")
    return selected


def _output_date(catalog_path: Path) -> str:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    generated_at = str(payload.get("generated_at") or "")
    date_text = generated_at[:10].replace("-", "")
    return date_text if len(date_text) == 8 and date_text.isdigit() else OUTPUT_DATE_FALLBACK


def _material_directory(entry: dict[str, Any]) -> str:
    series = str(entry["series_name"])
    name = str(entry["name_en"])
    code = str(entry["code"])
    return f"Bambu Lab/{series} - {name} [{code}]"


def _material_payload(entry: dict[str, Any], material_name: str, profile_id: str) -> dict[str, Any]:
    catalog_id = str(entry["id"])
    return {
        "schema_version": "1.1",
        "kind": "lumina_stage_a_material",
        "material_name": material_name,
        "brand": "Bambu Lab",
        "material_type": "PLA",
        "material_product_id": catalog_id,
        "material_profile_id": profile_id,
        "contributor_name": "filament-picker",
        "catalog_id": catalog_id,
        "created_at": BUILD_TIMESTAMP,
        "updated_at": BUILD_TIMESTAMP,
        "stage_a_params_file": "stage_A_parameters.json",
        "fit_summary": {
            "method": "official_hex_estimate",
            "warnings": [APPROXIMATION_NOTE, "请在实际打印条件下重新拍摄梯度色卡并拟合。"],
            "overall_validation": {
                "mean_delta_e": None,
                "rmse_linear": None,
                "measured": False,
            },
        },
        "material_summary": {
            "estimated_rgb": list(_hex_to_srgb(str(entry["hex"][0]))),
            "estimated_k": list(DEFAULT_K),
            "layer_height_mm": 0.08,
            "white_zero_rgb": [255, 255, 255],
            "black_zero_rgb": [3, 3, 3],
            "measurement_status": "estimated_from_official_hex",
            "notes": SOURCE_NOTE,
        },
        "source": {
            "catalog_id": catalog_id,
            "catalog_path": "data/build/filament-catalog.json",
            "hex": str(entry["hex"][0]),
            "hex_source": "official",
            "catalog_brand": entry["brand_name"],
            "series_name": entry["series_name"],
            "code": entry["code"],
            "source_rows": entry.get("source_rows", []),
            "note": SOURCE_NOTE,
        },
        "verification_count": 0,
        "verification_runs": [],
        "aggregation": {
            "method": "official_hex_estimate",
            "aggregated_at": BUILD_TIMESTAMP,
            "image_source": None,
            "selection": None,
        },
    }


def _stage_a_payload(entry: dict[str, Any], material_name: str, catalog_id: str) -> dict[str, Any]:
    rgb = _hex_to_srgb(str(entry["hex"][0]))
    e_values = _estimated_e(rgb)
    return {
        "schema_version": "1.0",
        "kind": "lumina_stage_a_parameters",
        "meta": {
            "material_name": material_name,
            "material_type": "PLA",
            "source": "official_hex_estimate",
            "catalog_id": catalog_id,
            "approximation": APPROXIMATION_NOTE,
        },
        "parameters": {
            "channels": [
                {
                    "color_name": material_name,
                    "E": e_values,
                    "k": list(DEFAULT_K),
                }
            ],
            "substrates": [
                {"substrate_id": "white", "C0": list(WHITE_C0)},
                {"substrate_id": "black", "C0": list(BLACK_C0)},
            ],
        },
        "fitted_substrates": {
            "white": {"C0": list(WHITE_C0)},
            "black": {"C0": list(BLACK_C0)},
        },
        "validation": {
            "measured": False,
            "note": SOURCE_NOTE,
        },
    }


def _bundle_records(
    entries: Iterable[dict[str, Any]],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    files: dict[str, bytes] = {}
    packages: list[dict[str, Any]] = []
    for entry in entries:
        catalog_id = str(entry["id"])
        directory = _material_directory(entry)
        material_name = (
            f"{entry['series_name']} - {entry['name_en']} ({entry['code']})｜{APPROXIMATION_NOTE}"
        )
        profile_id = f"profile_{_sha256_bytes(catalog_id.encode('utf-8'))[:32]}"
        material_path = f"materials/{directory}/material.json"
        stage_path = f"materials/{directory}/stage_A_parameters.json"
        material_bytes = _json_bytes(_material_payload(entry, material_name, profile_id))
        stage_bytes = _json_bytes(_stage_a_payload(entry, material_name, catalog_id))
        files[material_path] = material_bytes
        files[stage_path] = stage_bytes
        material_hash = _sha256_bytes(material_bytes)
        stage_hash = _sha256_bytes(stage_bytes)
        records = [
            {
                "path": material_path,
                "role": "material_archive",
                "sha256": material_hash,
                "bytes": len(material_bytes),
                "required": True,
            },
            {
                "path": stage_path,
                "role": "stage_a_parameters",
                "sha256": stage_hash,
                "bytes": len(stage_bytes),
                "required": True,
            },
        ]
        content_lines = f"material.json:{material_hash}\nstage_A_parameters.json:{stage_hash}"
        content_hash = f"sha256:{_sha256_bytes(content_lines.encode('utf-8'))}"
        material_id = f"mat_{_sha256_bytes(catalog_id.encode('utf-8'))[:26]}"
        packages.append(
            {
                "material_id": material_id,
                "revision_id": f"rev_{content_hash.removeprefix('sha256:')[:26]}",
                "content_hash": content_hash,
                "channel": "manual",
                "visibility": "private",
                "local_directory": directory,
                "display": {
                    "brand": "Bambu Lab",
                    "material_name": material_name,
                    "material_type": "PLA",
                    "color_name": entry["name_en"],
                    "estimated_rgb": list(_hex_to_srgb(str(entry["hex"][0]))),
                },
                "files": records,
                "compatibility": {
                    "min_app_version": "0.0.0",
                    "material_schema_version": "1.1",
                },
            }
        )
    packages.sort(key=lambda package: str(package["local_directory"]))
    manifest = {
        "schema_version": "2.0",
        "kind": "lumina_material_bundle",
        "exported_at": BUILD_TIMESTAMP,
        "material_count": len(packages),
        "packages": packages,
    }
    return files, manifest


def _write_zip(output_path: Path, files: dict[str, bytes], manifest: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
        manifest_info = zipfile.ZipInfo(
            "lumina_material_bundle.json", date_time=(2020, 1, 1, 0, 0, 0)
        )
        manifest_info.compress_type = zipfile.ZIP_DEFLATED
        manifest_info.create_system = 3
        manifest_info.external_attr = 0o100644 << 16
        archive.writestr(manifest_info, _json_bytes(manifest))


def build_seed(catalog_path: Path, output_dir: Path) -> Path:
    entries = _catalog_entries(catalog_path)
    files, manifest = _bundle_records(entries)
    output_path = output_dir / f"lumina-materials-seed-{_output_date(catalog_path)}.zip"
    _write_zip(output_path, files, manifest)
    digest = _sha256_bytes(output_path.read_bytes())
    output_path.with_suffix(output_path.suffix + ".sha256").write_text(
        f"{digest}  {output_path.name}\n",
        encoding="utf-8",
    )
    return output_path


def verify_seed(seed_path: Path, lumina_root: Path) -> dict[str, Any]:
    digest = _sha256_bytes(seed_path.read_bytes())
    previous_materials_dir = os.environ.get("LUMINA_MATERIALS_DIR")
    previous_path = os.environ.get("LUMINA_MATERIALS_SEED_PATH")
    previous_sha = os.environ.get("LUMINA_MATERIALS_SEED_SHA256")
    with tempfile.TemporaryDirectory(prefix="lumina_seed_verify_") as temp_dir:
        materials_dir = Path(temp_dir) / "materials"
        source_root = Path(temp_dir) / "lumina"
        for source_file in lumina_root.rglob("*.py"):
            relative = source_file.relative_to(lumina_root)
            target_file = source_root / relative
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
        os.environ["LUMINA_MATERIALS_DIR"] = str(materials_dir)
        os.environ["LUMINA_MATERIALS_SEED_PATH"] = str(seed_path)
        os.environ["LUMINA_MATERIALS_SEED_SHA256"] = digest
        sys.path.insert(0, str(source_root))
        try:
            from api.material_seed import install_material_seed_if_needed

            result = install_material_seed_if_needed(materials_dir=str(materials_dir))
            if result is None:
                raise RuntimeError("Lumina did not install the material seed")
            return {
                "installed_count": int(result["installed_count"]),
                "installed_materials": result["installed_materials"],
                "materials_dir": str(materials_dir),
            }
        finally:
            sys.path.remove(str(source_root))
            if previous_materials_dir is None:
                os.environ.pop("LUMINA_MATERIALS_DIR", None)
            else:
                os.environ["LUMINA_MATERIALS_DIR"] = previous_materials_dir
            if previous_path is None:
                os.environ.pop("LUMINA_MATERIALS_SEED_PATH", None)
            else:
                os.environ["LUMINA_MATERIALS_SEED_PATH"] = previous_path
            if previous_sha is None:
                os.environ.pop("LUMINA_MATERIALS_SEED_SHA256", None)
            else:
                os.environ["LUMINA_MATERIALS_SEED_SHA256"] = previous_sha


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "dist")
    parser.add_argument("--lumina-root", type=Path, default=DEFAULT_LUMINA_ROOT)
    parser.add_argument(
        "--seed", type=Path, help="Existing ZIP to verify; otherwise build one first"
    )
    parser.add_argument(
        "--verify", action="store_true", help="Verify a seed using Lumina's importer"
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    seed_path = args.seed if args.seed is not None else build_seed(args.catalog, args.output_dir)
    if not seed_path.is_file():
        raise FileNotFoundError(f"Seed archive not found: {seed_path}")
    if args.verify:
        print(json.dumps(verify_seed(seed_path, args.lumina_root), ensure_ascii=False, indent=2))
    else:
        print(seed_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
