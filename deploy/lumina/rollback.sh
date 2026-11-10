#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$script_dir/common.sh"
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo '用法：sudo bash rollback.sh [--dry-run]；切换 current 到 previous，失败恢复原版本。'
    exit 0
fi
[[ $# == 0 || ($# == 1 && $1 == --dry-run) ]] || fail '不支持的参数'
if [[ ${1:-} == --dry-run ]]; then
    echo '将校验 previous 指向 releases 内目录，原子切换 current，重启并 curl 健康检查；失败恢复原 current。'
    exit 0
fi
((EUID == 0)) || fail '必须以 root 执行'
exec 9>/run/lock/lumina-deploy.lock
flock -n 9 || fail '另一安装/回滚正在运行'
load_env /etc/lumina/lumina.env
[[ -L /opt/lumina/current && -L /opt/lumina/previous ]] || fail '缺少 current 或 previous 软链接'
old=$(readlink -f /opt/lumina/current)
previous=$(readlink -f /opt/lumina/previous)
for release in "$old" "$previous"; do
    [[ $release == /opt/lumina/releases/* && -x $release/.venv/bin/python ]] || fail 'release 路径越界或不完整'
done
[[ $old != "$previous" ]] || fail 'previous 与 current 相同'
success=0
restore() {
    local code=$?
    trap - EXIT
    if ((success == 0)); then
        echo '回滚目标健康失败，恢复原版本。' >&2
        atomic_link "$old" /opt/lumina/current
        systemctl restart lumina.service && health_check "$LUMINA_API_PORT" ||
            echo '恢复原版本失败，请运维排查。' >&2
    fi
    exit "$code"
}
trap restore EXIT
atomic_link "$previous" /opt/lumina/current
systemctl restart lumina.service
health_check "$LUMINA_API_PORT"
atomic_link "$old" /opt/lumina/previous
success=1
echo "回滚成功：$previous"
