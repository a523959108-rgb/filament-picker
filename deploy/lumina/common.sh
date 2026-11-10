#!/usr/bin/env bash
# 安装/回滚共用函数；被 source 时不执行系统操作。
set -euo pipefail
if [[ ${1:-} == --help && ${BASH_SOURCE[0]} == "$0" ]]; then
    echo '安装和回滚共用库，不单独执行。'
    exit 0
fi
fail() { echo "错误：$*" >&2; exit 1; }
current_release() {
    local root=$1
    if [[ -L $root/current ]]; then
        readlink -e -- "$root/current"
    elif [[ -e $root/current ]]; then
        fail 'current 必须是软链接'
    fi
}
atomic_link() {
    local target=$1 link=$2
    [[ ! -e $link || -L $link ]] || fail "$link 不是软链接"
    # ln -sfn 后同文件系统 rename，读者不会看见 current 短暂消失。
    ln -sfn -- "$target" "${link}.next"
    mv -Tf -- "${link}.next" "$link"
}
load_env() {
    local file=$1 line key value
    [[ -f $file ]] || fail "缺少 env：$file"
    # 只接受 KEY=简单值；绝不 source root 配置，也不打印配置内容。
    while IFS= read -r line || [[ -n $line ]]; do
        [[ -z $line || $line == \#* ]] && continue
        [[ $line =~ ^([A-Z][A-Z0-9_]*)=([a-zA-Z0-9_./:@,+%-]*)$ ]] ||
            fail 'env 格式不支持：请用不带引号、空格或 shell 展开的 KEY=VALUE'
        key=${BASH_REMATCH[1]} value=${BASH_REMATCH[2]}
        case $key in LUMINA_*|CUDA_VISIBLE_DEVICES|NUMBA_CACHE_DIR|PYTHONDONTWRITEBYTECODE|XDG_CACHE_HOME|XDG_DATA_HOME|OMP_NUM_THREADS|OPENBLAS_NUM_THREADS|MKL_NUM_THREADS)
            export "$key=$value" ;;
            *) fail 'env 含不支持的变量名' ;;
        esac
    done < "$file"
    [[ ${LUMINA_API_PORT:-} =~ ^[0-9]+$ ]] || fail 'LUMINA_API_PORT 必须是整数'
    (( LUMINA_API_PORT >= 1024 && LUMINA_API_PORT <= 65535 )) || fail '端口范围 1024..65535'
    [[ ${LUMINA_MAX_WORKERS:-} =~ ^[1-9][0-9]*$ ]] || fail '并发数必须是正整数'
    [[ ${LUMINA_API_HOST:-} == 0.0.0.0 || ${LUMINA_API_HOST:-} == 127.0.0.1 ]] || fail '不支持的绑定地址'
}
health_check() {
    local port=$1 attempt
    for attempt in {1..30}; do
        if curl --noproxy '*' --fail --silent --show-error --max-time 2 \
            "http://127.0.0.1:$port/api/health" 2>/dev/null |
            python3.12 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(not (d.get("status")=="ok" and d.get("worker_pool",{}).get("healthy") is True))' \
            2>/dev/null; then
            echo "健康检查通过：127.0.0.1:$port/api/health"
            return 0
        fi
        sleep 1
    done
    echo '健康检查失败；请查 journalctl -u lumina 和 /var/log/lumina。' >&2
    return 1
}
