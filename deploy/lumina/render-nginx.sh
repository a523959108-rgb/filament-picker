#!/usr/bin/env bash
# 把 nginx-b-stack.conf 里的上游占位符换成环境或 upstream.env 中的地址。
# 不修改仓库里的模板。未设置地址时失败，避免把占位符装进 nginx。
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$ROOT/common.sh"
out=
while (($#)); do
    case $1 in
        --help|-h)
            echo '用法：render-nginx.sh [--out 文件]'
            echo '从环境变量或 upstream.env 替换 nginx 模板中的上游地址，默认打印到标准输出。'
            exit 0 ;;
        --out) out=${2:?缺少路径}; shift 2 ;;
        *) echo "未知参数：$1" >&2; exit 2 ;;
    esac
done
load_upstream_env
missing=()
[[ -n ${LUMINA_UPSTREAM_HOST:-} ]] || missing+=(LUMINA_UPSTREAM_HOST)
[[ -n ${LUMINA_UPSTREAM_PORT:-} ]] || missing+=(LUMINA_UPSTREAM_PORT)
[[ -n ${LUMINA_UPSTREAM_BACKUP_HOST:-} ]] || missing+=(LUMINA_UPSTREAM_BACKUP_HOST)
[[ -n ${LUMINA_UPSTREAM_BACKUP_PORT:-} ]] || missing+=(LUMINA_UPSTREAM_BACKUP_PORT)
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "错误：缺少 ${missing[*]}。复制 upstream.env.example 后在服务器本地填写，不要提交。" >&2
    exit 1
fi
upstream_host_ok "$LUMINA_UPSTREAM_HOST" || fail 'LUMINA_UPSTREAM_HOST 不是可用的主机名或 IPv4'
upstream_port_ok "$LUMINA_UPSTREAM_PORT" || fail 'LUMINA_UPSTREAM_PORT 不是合法端口'
upstream_host_ok "$LUMINA_UPSTREAM_BACKUP_HOST" || fail 'LUMINA_UPSTREAM_BACKUP_HOST 不是可用的主机名或 IPv4'
upstream_port_ok "$LUMINA_UPSTREAM_BACKUP_PORT" || fail 'LUMINA_UPSTREAM_BACKUP_PORT 不是合法端口'
template=$(cat "$ROOT/nginx-b-stack.conf")
render=$template
render=${render//\$\{LUMINA_UPSTREAM_BACKUP_HOST\}/$LUMINA_UPSTREAM_BACKUP_HOST}
render=${render//\$\{LUMINA_UPSTREAM_BACKUP_PORT\}/$LUMINA_UPSTREAM_BACKUP_PORT}
render=${render//\$\{LUMINA_UPSTREAM_HOST\}/$LUMINA_UPSTREAM_HOST}
render=${render//\$\{LUMINA_UPSTREAM_PORT\}/$LUMINA_UPSTREAM_PORT}
[[ $render != *'${'* ]] || fail '模板仍有未替换的 ${} 占位符'
if [[ -n $out ]]; then
    [[ $out != "$ROOT/nginx-b-stack.conf" ]] || fail '不能覆盖仓库里的模板'
    printf '%s\n' "$render" > "$out"
else
    printf '%s\n' "$render"
fi
