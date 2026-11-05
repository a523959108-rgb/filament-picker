#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/filament-picker worker --root "${FP_ROOT:-/home/box/agent-data/shared/filament-picker}"
