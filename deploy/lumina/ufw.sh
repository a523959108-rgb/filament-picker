#!/usr/bin/env bash
set -euo pipefail
apply=0 port=8790
while (($#)); do
    case $1 in
        --help|-h) echo '用法：ufw.sh [--port 8790] [--apply]；默认只打印，主备两台通用。'; exit 0 ;;
        --apply) apply=1; shift ;;
        --port) port=${2:?缺少端口}; shift 2 ;;
        *) echo "未知参数：$1" >&2; exit 2 ;;
    esac
done
[[ $port =~ ^[0-9]+$ ]] && ((port >= 1024 && port <= 65535)) || { echo '非法端口' >&2; exit 1; }
cat <<EOF
主备两台均执行以下策略；先确认 SSH 实际端口、现有规则和带外控制台，避免误封 ssh。
必须由运维先保留 SSH 管理入口，再设置默认拒绝入站；本脚本不启用 UFW。
建议：sudo ufw default deny incoming
建议：sudo ufw default allow outgoing
检查：sudo ufw status numbered（删除已有对公网或其他来源开放 $port 的规则）
规则：sudo ufw allow in on tailscale0 from 100.70.57.112 to any port $port proto tcp
只加这条 allow 不能覆盖已有宽泛放行规则；检查 tailscale0 存在及 Tailscale ACL。
EOF
if ((apply)); then
    ((EUID == 0)) || { echo '--apply 需要 root' >&2; exit 1; }
    command -v ufw >/dev/null || { echo '未安装 UFW，请运维准备。' >&2; exit 1; }
    ufw allow in on tailscale0 from 100.70.57.112 to any port "$port" proto tcp
    echo '只添加了 B 来源的规则；请运维按上述建议检查默认拒绝、SSH 和既有规则。'
fi
