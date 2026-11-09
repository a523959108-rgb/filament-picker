#!/usr/bin/env python3
"""Local bridge: lumina-stack-job → Lumina HTTP API → lumina-stack-result.json.

Does NOT vendor or import Lumina / opencv / scipy (GPL). The engine must already
be running elsewhere, e.g.:

  cd "$LUMINA_ROOT"
  LUMINA_HOST=127.0.0.1 .venv-smoke/bin/python api_server.py

Usage:
  python scripts/run_lumina_stack_job.py --job /path/to/job.json --image photo.png -o out/
  python scripts/run_lumina_stack_job.py --job-zip lumina-stack-job-RYBW-....zip -o out/

Environment:
  LUMINA_BASE   default http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TOKYO = ZoneInfo("Asia/Tokyo")


def now_tokyo() -> str:
    return datetime.now(TOKYO).isoformat(timespec="seconds")


def http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=timeout) as resp:  # local engine only
        return json.loads(resp.read().decode("utf-8"))


def http_multipart(
    url: str,
    fields: dict[str, str],
    files: dict[str, Path],
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Minimal multipart uploader (stdlib only)."""
    boundary = "----LuminaStackBoundary7MA4YWxkTrZu0gW"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    for name, path in files.items():
        raw = path.read_bytes()
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'.encode()
        )
        chunks.append(b"Content-Type: application/octet-stream\r\n\r\n")
        chunks.append(raw)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Accept", "application/json")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_job(job_path: Path | None, job_zip: Path | None) -> tuple[dict[str, Any], Path | None]:
    image_from_zip: Path | None = None
    if job_zip is not None:
        extract_dir = job_zip.with_suffix("").parent / f".{job_zip.stem}-extract"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(job_zip) as zf:
            zf.extractall(extract_dir)
        job_file = extract_dir / "job.json"
        if not job_file.is_file():
            raise SystemExit(f"zip missing job.json: {job_zip}")
        job = json.loads(job_file.read_text(encoding="utf-8"))
        # Prefer image named in job, else first image-looking file.
        named = job.get("image_filename")
        if named and (extract_dir / named).is_file():
            image_from_zip = extract_dir / named
        else:
            for candidate in extract_dir.iterdir():
                if candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    image_from_zip = candidate
                    break
        return job, image_from_zip
    if job_path is None:
        raise SystemExit("need --job or --job-zip")
    return json.loads(job_path.read_text(encoding="utf-8")), None


def lut_name_for(job: dict[str, Any]) -> str:
    mode = job.get("lut_mode", "RYBW")
    hints = job.get("lut_hints") or []
    for hint in hints:
        if isinstance(hint, str) and "bambulab_pla_basic" in hint.lower():
            # Lumina API smoke used: "bambulab - bambulab_pla_basic_rybw"
            stem = Path(hint).stem if hint.endswith(".npy") else hint
            if "rybw" in stem.lower():
                return "bambulab - bambulab_pla_basic_rybw"
            if "cmyw" in stem.lower():
                return "bambulab - bambulab_pla_basic_cmyw"
    if mode == "RYBW":
        return "bambulab - bambulab_pla_basic_rybw"
    return "bambulab - bambulab_pla_basic_cmyw"


def extract_engine_hexes(generate_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Best-effort slot colours from generate response; caller may override via --slots-json."""
    slots: list[dict[str, Any]] = []
    # Common shapes: filament_colours / filaments / metadata.slots
    colours = (
        generate_payload.get("filament_colours")
        or generate_payload.get("filament_colors")
        or generate_payload.get("colours")
        or []
    )
    names = generate_payload.get("filament_names") or []
    mode_slots = {
        "RYBW": [
            ("W", "白", "White"),
            ("R", "红", "Red"),
            ("Y", "黄", "Yellow"),
            ("B", "蓝", "Blue"),
        ],
        "CMYW": [
            ("C", "青", "Cyan"),
            ("M", "品红", "Magenta"),
            ("Y", "黄", "Yellow"),
            ("W", "白", "White"),
        ],
    }
    # Default order from smoke metadata: E1 W, E2 R, E3 Y, E4 B for RYBW
    letters = mode_slots.get(str(generate_payload.get("color_mode") or "RYBW"), mode_slots["RYBW"])
    if isinstance(colours, list) and colours:
        for i, colour in enumerate(colours[:4]):
            letter, zh, en = (
                letters[i] if i < len(letters) else (str(i + 1), str(i + 1), str(i + 1))
            )
            if isinstance(colour, str):
                hex_value = colour
            else:
                hex_value = str(colour.get("hex") or colour.get("colour") or "")
            if not hex_value.startswith("#"):
                hex_value = f"#{hex_value}"
            slots.append(
                {
                    "extruder": i + 1,
                    "slot": letter,
                    "name_zh": zh,
                    "name_en": names[i] if i < len(names) else en,
                    "engine_hex": hex_value.upper(),
                }
            )
    return slots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, help="path to job.json")
    parser.add_argument("--job-zip", type=Path, help="path to lumina-stack-job-*.zip")
    parser.add_argument("--image", type=Path, help="override image path")
    parser.add_argument("-o", "--out", type=Path, required=True, help="output directory")
    parser.add_argument("--base", default=None, help="Lumina API base (or LUMINA_BASE)")
    parser.add_argument(
        "--slots-json",
        type=Path,
        help="optional JSON array of {extruder,slot,name_zh,name_en,engine_hex} to force slots",
    )
    parser.add_argument(
        "--embed-base64",
        action="store_true",
        help="embed preview/3mf as base64 in result.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="print planned calls only")
    args = parser.parse_args()

    base = (
        args.base or __import__("os").environ.get("LUMINA_BASE") or "http://127.0.0.1:8000"
    ).rstrip("/")
    job, zip_image = load_job(args.job, args.job_zip)
    if job.get("kind") != "lumina-stack-job":
        print("warning: job.kind is not lumina-stack-job", file=sys.stderr)

    image = args.image or zip_image
    if image is None or not image.is_file():
        raise SystemExit("need an image via --image or inside the job zip")

    size = job.get("size_mm") or {}
    width_mm = float(size.get("width") or 100)
    lut_mode = job.get("lut_mode") or "RYBW"
    lut_name = lut_name_for(job)

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"[plan] base={base}")
    print(f"[plan] lut_name={lut_name} color_mode={lut_mode} width_mm={width_mm}")
    print(f"[plan] image={image}")

    if args.dry_run:
        print("[dry-run] skip HTTP")
        return 0

    try:
        health = http_json("GET", f"{base}/api/health", timeout=10)
        print(f"[health] {health.get('status')}")
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Lumina not reachable at {base}: {exc}", file=sys.stderr)
        print(
            "Start api_server.py first; this script does not embed the GPL engine.",
            file=sys.stderr,
        )
        return 2

    preview_fields = {
        "lut_name": lut_name,
        "target_width_mm": str(int(width_mm)),
        "color_mode": str(lut_mode),
        "modeling_mode": "high-fidelity",
        "quantize_colors": "32",
        "enable_cleanup": "true",
    }
    print("[1/2] POST /api/convert/preview …")
    preview = http_multipart(f"{base}/api/convert/preview", preview_fields, {"image": image})
    session_id = preview.get("session_id") or preview.get("session") or ""
    preview_png = args.out / "preview.png"
    # Response may include base64 preview or a path — handle common cases.
    if isinstance(preview.get("preview_base64"), str):
        preview_png.write_bytes(base64.b64decode(preview["preview_base64"]))
    elif isinstance(preview.get("preview_png_base64"), str):
        preview_png.write_bytes(base64.b64decode(preview["preview_png_base64"]))
    elif isinstance(preview.get("preview_path"), str) and Path(preview["preview_path"]).is_file():
        preview_png.write_bytes(Path(preview["preview_path"]).read_bytes())
    else:
        # Some servers return binary via separate download; keep raw JSON for debug.
        (args.out / "preview_response.json").write_text(
            json.dumps(preview, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "warning: could not extract preview image bytes; see preview_response.json",
            file=sys.stderr,
        )

    print("[2/2] POST /api/convert/generate …")
    generate_body = {
        "session_id": session_id,
        "params": {
            "lut_name": lut_name,
            "color_mode": lut_mode,
            "target_width_mm": int(width_mm),
            "modeling_mode": "high-fidelity",
            "quantize_colors": 32,
            "enable_cleanup": True,
        },
    }
    generate = http_json("POST", f"{base}/api/convert/generate", generate_body, timeout=300)
    (args.out / "generate_response.json").write_text(
        json.dumps(generate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    model_3mf = args.out / f"stack_{str(lut_mode).lower()}.3mf"
    if isinstance(generate.get("model_base64"), str):
        model_3mf.write_bytes(base64.b64decode(generate["model_base64"]))
    elif isinstance(generate.get("output_path"), str) and Path(generate["output_path"]).is_file():
        model_3mf.write_bytes(Path(generate["output_path"]).read_bytes())
    elif isinstance(generate.get("path"), str) and Path(generate["path"]).is_file():
        model_3mf.write_bytes(Path(generate["path"]).read_bytes())
    else:
        print("warning: 3mf path/base64 not found in generate response", file=sys.stderr)

    if args.slots_json and args.slots_json.is_file():
        slots = json.loads(args.slots_json.read_text(encoding="utf-8"))
    else:
        slots = extract_engine_hexes({**generate, "color_mode": lut_mode})
        if not slots:
            # Smoke fallback RYBW hexes so the picker can still recommend.
            smoke = {
                "RYBW": [
                    ("W", "白", "White", "#D7D2CF"),
                    ("R", "红", "Red", "#E94A39"),
                    ("Y", "黄", "Yellow", "#ECEF35"),
                    ("B", "蓝", "Blue", "#3451B1"),
                ],
                "CMYW": [
                    ("C", "青", "Cyan", "#0086D6"),
                    ("M", "品红", "Magenta", "#EC008C"),
                    ("Y", "黄", "Yellow", "#F4EE2A"),
                    ("W", "白", "White", "#FFFFFF"),
                ],
            }
            slots = [
                {
                    "extruder": i + 1,
                    "slot": letter,
                    "name_zh": zh,
                    "name_en": en,
                    "engine_hex": hex_value,
                }
                for i, (letter, zh, en, hex_value) in enumerate(
                    smoke.get(str(lut_mode), smoke["RYBW"])
                )
            ]
            print(
                "warning: using fallback engine hexes; pass --slots-json from 3MF metadata",
                file=sys.stderr,
            )

    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "lumina-stack-result",
        "created_at": now_tokyo(),
        "lut_mode": lut_mode,
        "source_job_kind": "lumina-stack-job",
        "preview_relpath": None,
        "model_3mf_relpath": None,
        "slots": [
            {
                **slot,
                "recommended_id": "",
                "recommended_hex": "",
                "recommended_name": "",
                "delta_e": 0,
                "purchase_url": None,
                "purchase_is_pdd": False,
            }
            for slot in slots
        ],
        "note": "generated by scripts/run_lumina_stack_job.py; picker re-recommends on import",
    }

    if args.embed_base64:
        if preview_png.is_file():
            result["preview_base64"] = base64.b64encode(preview_png.read_bytes()).decode("ascii")
        if model_3mf.is_file():
            result["model_3mf_base64"] = base64.b64encode(model_3mf.read_bytes()).decode("ascii")
    else:
        # Relative names for web/public/stack-smoke/ or for paths you host.
        if preview_png.is_file():
            result["preview_relpath"] = preview_png.name
        if model_3mf.is_file():
            result["model_3mf_relpath"] = model_3mf.name

    out_json = args.out / "lumina-stack-result.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] wrote {out_json}")
    print("Import that JSON on #/stack (paste/drag). Catalog ΔE runs in the picker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
