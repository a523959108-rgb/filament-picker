from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).with_name("build_seed.py")


def _run_builder(
    output_dir: Path,
    *extra: str,
    python: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [python or sys.executable, str(SCRIPT), "--output-dir", str(output_dir), *extra],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )


def test_build_is_byte_deterministic_and_writes_digest(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = _run_builder(first_dir)
    second = _run_builder(second_dir)
    first_zip = Path(first.stdout.strip().splitlines()[-1])
    second_zip = Path(second.stdout.strip().splitlines()[-1])
    assert first_zip.read_bytes() == second_zip.read_bytes()
    first_digest = first_zip.with_suffix(".zip.sha256")
    second_digest = second_zip.with_suffix(".zip.sha256")
    assert first_digest.read_text(encoding="utf-8") == second_digest.read_text(encoding="utf-8")
    assert first_digest.read_text(encoding="utf-8").startswith(
        hashlib.sha256(first_zip.read_bytes()).hexdigest()
    )


def test_bundle_manifest_and_catalog_provenance_are_present(tmp_path: Path) -> None:
    result = _run_builder(tmp_path)
    seed_zip = Path(result.stdout.strip().splitlines()[-1])
    with zipfile.ZipFile(seed_zip) as archive:
        names = archive.namelist()
        assert names[-1] == "lumina_material_bundle.json"
        manifest = json.loads(archive.read("lumina_material_bundle.json"))
        assert manifest["kind"] == "lumina_material_bundle"
        assert manifest["schema_version"] == "2.0"
        assert manifest["packages"]
        for package in manifest["packages"]:
            assert package["content_hash"].startswith("sha256:")
            assert package["channel"] == "manual"
            assert package["visibility"] == "private"
            material_path = f"materials/{package['local_directory']}/material.json"
            material = json.loads(archive.read(material_path))
            assert material["material_profile_id"].startswith("profile_")
            assert material["material_product_id"] == material["catalog_id"]
            assert "近似（由官方 hex 估算，非实测光谱/透光数据）" in material["material_name"]
            assert material["source"]["catalog_id"] == material["catalog_id"]


def test_verify_uses_lumina_importer_and_lists_materials(tmp_path: Path) -> None:
    result = _run_builder(tmp_path)
    seed_zip = Path(result.stdout.strip().splitlines()[-1])
    verify = _run_builder(
        tmp_path / "verify",
        "--verify",
        "--seed",
        str(seed_zip),
        python="/workspace/lumina-venv/bin/python",
    )
    assert "installed_count" in verify.stdout
    assert "bambu-lab" in verify.stdout
