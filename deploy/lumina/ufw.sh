#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$ROOT/common.sh"
apply=0 port=8790
while (($#)); do
    case $1 in
        --help|-h)
            echo '用法：ufw.sh [--port 8790|7860] [--apply]；C 默认8790，主力用7860，默认只打印。'
            echo '来源地址读 LUMINA_EDGE_HOST，发布地址读 LUMINA_UPSTREAM_HOST；见 upstream.env.example。'
            exit 0 ;;
        --apply) apply=1; shift ;;
        --port) port=${2:?缺少端口}; shift 2 ;;
        *) echo "未知参数：$1" >&2; exit 2 ;;
    esac
done
[[ $port =~ ^[0-9]+$ ]] && ((port >= 1024 && port <= 65535)) || { echo '非法端口' >&2; exit 1; }
load_upstream_env
if [[ -n ${LUMINA_EDGE_HOST:-} ]] && ! upstream_host_ok "$LUMINA_EDGE_HOST"; then
    echo '错误：LUMINA_EDGE_HOST 不是可用的主机名或 IPv4' >&2
    exit 1
fi
if [[ -n ${LUMINA_UPSTREAM_HOST:-} ]] && ! upstream_host_ok "$LUMINA_UPSTREAM_HOST"; then
    echo '错误：LUMINA_UPSTREAM_HOST 不是可用的主机名或 IPv4' >&2
    exit 1
fi
if [[ -n ${LUMINA_EDGE_HOST:-} ]]; then
    edge_shown=$LUMINA_EDGE_HOST
else
    edge_shown='${LUMINA_EDGE_HOST}'
fi
if [[ -n ${LUMINA_UPSTREAM_HOST:-} ]]; then
    publish_shown=$LUMINA_UPSTREAM_HOST
else
    publish_shown='${LUMINA_UPSTREAM_HOST}'
fi
cat <<EOF
主备两台均执行以下策略；先确认 SSH 实际端口、现有规则和带外控制台，避免误封 ssh。
必须由运维先保留 SSH 管理入口，再设置默认拒绝入站；本脚本不启用 UFW。
建议：sudo ufw default deny incoming
建议：sudo ufw default allow outgoing
检查：sudo ufw status numbered（删除已有对公网或其他来源开放 $port 的规则）
规则：sudo ufw allow in on tailscale0 from $edge_shown to any port $port proto tcp
只加这条 allow 不能覆盖已有宽泛放行规则；检查 tailscale0 存在及 Tailscale ACL。
主力 Docker 发布端口会绕过 UFW INPUT：只绑定 $publish_shown 是主要隔离手段；
如需限制为 B 来源，按 README 核对 DOCKER-USER 链，不以本脚本代替转发链防护。
地址来自环境变量或未跟踪的 upstream.env，不要把 Tailscale 地址写进仓库。
EOF
if ((apply)); then
    [[ -n ${LUMINA_EDGE_HOST:-} ]] || {
        echo '错误：--apply 需要 LUMINA_EDGE_HOST（环境变量，或未跟踪的 upstream.env）' >&2
        exit 1
    }
    ((EUID == 0)) || { echo '--apply 需要 root' >&2; exit 1; }
    command -v ufw >/dev/null || { echo '未安装 UFW，请运维准备。' >&2; exit 1; }
    ufw allow in on tailscale0 from "$LUMINA_EDGE_HOST" to any port "$port" proto tcp
    echo '只添加了 B 来源的规则；请运维按上述建议检查默认拒绝、SSH 和既有规则。'
fi
