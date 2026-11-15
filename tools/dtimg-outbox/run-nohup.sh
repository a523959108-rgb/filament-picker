#!/usr/bin/env bash
# 不用 systemd 时，在后台跑 watcher。不发送钉钉消息。
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTBOX="${DTIMG_OUTBOX:-/home/box/agent-data/shared/dingtalk-outbox}"
PUT_SH="${DTIMG_PUT_SH:-/home/box/agent-data/shared/dingtalk-media/put.sh}"
OUTBOX="${OUTBOX%/}"
export DTIMG_OUTBOX="$OUTBOX"
export DTIMG_PUT_SH="$PUT_SH"

mkdir -p \
  "${OUTBOX}/inbox" \
  "${OUTBOX}/ready" \
  "${OUTBOX}/done" \
  "${OUTBOX}/failed" \
  "${OUTBOX}/sent" \
  "${OUTBOX}/state" \
  "${OUTBOX}/log"

PIDFILE="${OUTBOX}/state/dtimg-outbox.pid"
LOG="${OUTBOX}/log/nohup.out"

if [ -f "$PIDFILE" ]; then
  old="$(tr -cd '0-9' < "$PIDFILE" || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    echo "已在运行 pid=${old}"
    exit 0
  fi
fi

nohup "${TOOL_DIR}/dtimg-outbox" watch >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
echo "已启动 pid=$(tr -cd '0-9' < "$PIDFILE") 日志 ${LOG}"
