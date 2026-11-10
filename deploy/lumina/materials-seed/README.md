# Lumina materials seed

`build_seed.py` builds the deterministic Lumina v2 material bundle from the
checked-in filament catalog. It selects official Bambu Lab PLA Basic and PLA
Matte hex values, writes conservative Stage-A placeholders, and records each
catalog ID and source in `material.json`.

```bash
/workspace/lumina-venv/bin/python deploy/lumina/materials-seed/build_seed.py
```

The default output is `dist/lumina-materials-seed-20261106.zip` and its
`*.zip.sha256` sidecar. `dist/` is ignored by git. Use a different catalog or
output directory with `--catalog` and `--output-dir`.

Verify the generated archive with Lumina's own installer:

```bash
/workspace/lumina-venv/bin/python deploy/lumina/materials-seed/build_seed.py \
  --verify --seed deploy/lumina/materials-seed/dist/lumina-materials-seed-20261106.zip
```

Verification runs in a temporary copy of the Lumina Python source and a
temporary `LUMINA_MATERIALS_DIR`; it does not touch a real user library.

The ZIP root and manifest are the exact format consumed by
`core.single_stage.material_package` and
`core.single_stage.material_library.import_saved_stage_a_material_archives`:
`materials/<directory>/material.json`, the referenced
`stage_A_parameters.json`, and `lumina_material_bundle.json` schema `2.0`.
Every file has a SHA256 record and every package has the Lumina content hash.

For deployment, place the ZIP on the server and set:

```text
LUMINA_MATERIALS_SEED_PATH=/srv/lumina-seed/lumina-materials-seed-20261106.zip
LUMINA_MATERIALS_SEED_SHA256=<64-character SHA256 from the sidecar>
LUMINA_MATERIALS_DIR=/srv/lumina-data/materials
```

Lumina installs the seed only when the target library is empty. The same ZIP
can also be imported from the Lumina material-library UI; select the ZIP and
do not select the `.sha256` sidecar.

The material values are explicitly estimates from official hex colors, not
measured spectra or transmission data. See
[`docs/lumina-materials.md`](../../../docs/lumina-materials.md) for the
assumptions, LUT selection, update procedure, and calibration risks.
