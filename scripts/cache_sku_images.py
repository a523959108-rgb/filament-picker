#!/usr/bin/env python3
"""Copy catalog variant_image files into web/public/sku/ as 240px JPEG thumbs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "build" / "filament-catalog.json"
OUT = ROOT / "web" / "public" / "sku"


def main() -> int:
    if not CATALOG.exists():
        print(f"missing {CATALOG}; run build-catalog first", file=sys.stderr)
        return 1
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    copied = 0
    for entry in catalog["entries"]:
        if entry.get("status") != "active":
            continue
        src = entry.get("variant_image")
        if not src:
            continue
        path = Path(src)
        if not path.is_file():
            continue
        dest = OUT / (entry["id"].replace("/", "__") + ".jpg")
        if dest.exists() and dest.stat().st_mtime >= path.stat().st_mtime:
            continue
        image = Image.open(path).convert("RGB")
        image.thumbnail((240, 240))
        image.save(dest, "JPEG", quality=82, optimize=True)
        copied += 1
    print(f"cached={copied} dir={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
