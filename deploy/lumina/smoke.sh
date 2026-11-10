#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo '用法：smoke.sh [base URL]；默认 http://127.0.0.1:18101，30 秒总超时。'
    echo '或 smoke.sh --in-process --source 可写隔离副本（先设置所有运行时目录 env）。'
    exit 0
fi
# 外层硬截止防止 TestClient 退出时等待 worker 使 Python 的计时异常无法及时退出。
code=0
timeout --foreground --signal=TERM --kill-after=2s 30s \
    /workspace/lumina-venv/bin/python -B "$script_dir/smoke.py" "$@" || code=$?
if ((code == 124 || code == 137)); then
    echo '冒烟失败：触发 30 秒总时限。' >&2
fi
exit "$code"
