#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
CAT=docs/schemas/examples/filament-catalog.example.json
mkdir -p "$ROOT/inbox"

.venv/bin/python -c "import sys; sys.path.insert(0, 'tests'); from helpers_images import square_on_white; from pathlib import Path; square_on_white(Path(sys.argv[1]), '#000000')" "$ROOT/inbox/smoke1.png"

.venv/bin/python - "$ROOT" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path(sys.argv[1])
created_at = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")
request = {
    "schema_version": 1,
    "request_id": "smoke1",
    "created_at": created_at,
    "image_paths": [str(root / "inbox/smoke1.png")],
    "note": "",
    "constraints": {"materials": ["PETG"]},
    "context": {"conversationId": "cidSMOKE"},
}
temporary = root / "inbox/smoke1.request.json.tmp"
temporary.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
missing = dict(request)
missing["request_id"] = "smoke2"
missing["image_paths"] = [str(root / "inbox/missing.png")]
(root / "inbox/smoke2.request.json").write_text(
    json.dumps(missing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PY
mv "$ROOT/inbox/smoke1.request.json.tmp" "$ROOT/inbox/smoke1.request.json"

.venv/bin/filament-picker worker --root "$ROOT" --once --catalog "$CAT"
.venv/bin/filament-picker validate result "$ROOT/outbox/smoke1.json"
.venv/bin/filament-picker validate result "$ROOT/outbox/smoke2.json"
.venv/bin/python - "$ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
smoke1 = json.loads((root / "outbox/smoke1.json").read_text(encoding="utf-8"))
smoke2 = json.loads((root / "outbox/smoke2.json").read_text(encoding="utf-8"))
assert smoke1["status"] == "ok"
assert smoke2["status"] == "error"
assert smoke2["error"]["code"] == "IMAGE_MISSING"
assert (root / "done/smoke1.request.json").is_file()
assert (root / "failed/smoke2.request.json").is_file()
PY
echo "smoke ok"
