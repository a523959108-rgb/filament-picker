#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/filament-picker export-web
cd web && npm ci && npm run build
echo "built web/dist"
