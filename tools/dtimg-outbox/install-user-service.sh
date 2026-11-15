#!/usr/bin/env bash
# 安装 systemd --user 服务。不上传图片，不发送钉钉消息。
set -euo pipefail

require_safe_path() {
  local value="$1"
  local label="$2"
  if [ -z "$value" ]; then
    echo "${label} 为空" >&2
    exit 2
  fi
  case "$value" in
    *[!A-Za-z0-9_./:-]*)
      echo "${label} 含有空格或特殊字符，请换一个路径：${value}" >&2
      exit 2
      ;;
  esac
}

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="${TOOL_DIR}/dtimg-outbox"
OUTBOX="${DTIMG_OUTBOX:-/home/box/agent-data/shared/dingtalk-outbox}"
PUT_SH="${DTIMG_PUT_SH:-/home/box/agent-data/shared/dingtalk-media/put.sh}"
OUTBOX="${OUTBOX%/}"
PUT_SH="${PUT_SH%/}"
UNIT_DIR="${DTIMG_SYSTEMD_USER_DIR:-${HOME}/.config/systemd/user}"
UNIT="${UNIT_DIR}/dtimg-outbox.service"

require_safe_path "$OUTBOX" "DTIMG_OUTBOX"
require_safe_path "$PUT_SH" "DTIMG_PUT_SH"
require_safe_path "$WRAPPER" "启动脚本"

mkdir -p \
  "${OUTBOX}/inbox" \
  "${OUTBOX}/ready" \
  "${OUTBOX}/done" \
  "${OUTBOX}/failed" \
  "${OUTBOX}/sent" \
  "${OUTBOX}/state" \
  "${OUTBOX}/log" \
  "${UNIT_DIR}"

cat > "${UNIT}" <<EOF
[Unit]
Description=钉钉图片发件箱上传（不发送消息）
After=default.target

[Service]
Type=simple
WorkingDirectory=${OUTBOX}
Environment=PYTHONUNBUFFERED=1
Environment=DTIMG_OUTBOX=${OUTBOX}
Environment=DTIMG_PUT_SH=${PUT_SH}
ExecStart=${WRAPPER} watch
Restart=on-failure
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=15

[Install]
WantedBy=default.target
EOF

echo "已写入 ${UNIT}"
echo "发件箱：${OUTBOX}"
echo "put.sh：${PUT_SH}"

if [ "${DTIMG_INSTALL_NO_START:-}" = "1" ]; then
  echo "DTIMG_INSTALL_NO_START=1，未执行 systemctl。"
  exit 0
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "未找到 systemctl。可改用：${TOOL_DIR}/run-nohup.sh"
  exit 0
fi

if ! systemctl --user show-environment >/dev/null 2>&1; then
  echo "当前没有可用的 systemd --user。可改用：${TOOL_DIR}/run-nohup.sh"
  echo "若希望开机或登出后仍运行，先执行：loginctl enable-linger \"\$USER\""
  exit 0
fi

systemctl --user daemon-reload
systemctl --user enable --now dtimg-outbox.service
systemctl --user --no-pager --full status dtimg-outbox.service || true
