#!/usr/bin/env bash
# 只跑本工具的测试，不碰网站测试。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

if [ -x "$REPO/.venv/bin/pytest" ]; then
  exec "$REPO/.venv/bin/pytest" tools/dtimg-outbox/tests -q
fi

exec python3 -m pytest tools/dtimg-outbox/tests -q
