#!/usr/bin/env bash
set -euo pipefail
usage() {
    echo '用法：cleanup-output.sh [--hours N] [--output-dir 绝对目录] [--cache-dir 预览缓存绝对目录]'
    echo '默认 24 小时，可用 LUMINA_CLEANUP_HOURS 配置；只删除普通文件，不跟随链接。'
}
hours=${LUMINA_CLEANUP_HOURS:-24}
output_dir=/var/lib/lumina/output
cache_dir=/var/lib/lumina/output/temp
while (($#)); do
    case $1 in
        --help|-h) usage; exit 0 ;;
        --hours) hours=${2:?缺少小时数}; shift 2 ;;
        --output-dir) output_dir=${2-}; shift 2 ;;
        --cache-dir) cache_dir=${2-}; shift 2 ;;
        *) usage >&2; exit 2 ;;
    esac
done
[[ $hours =~ ^[1-9][0-9]*$ && ${#hours} -le 6 ]] || { echo '小时数必须是正整数（最多六位）' >&2; exit 1; }
# 全部验证后才删除，防止第二个目录非法时第一个已经被清理。
roots=()
for directory in "$output_dir" "$cache_dir"; do
    [[ -n $directory && $directory == /* && -d $directory && ! -L $directory ]] || {
        echo '拒绝清理：目录为空、非绝对目录、不存在或是软链接。' >&2; exit 1;
    }
    directory=$(realpath -e -- "$directory")
    [[ $directory != / ]] || { echo '拒绝清理根目录 /' >&2; exit 1; }
    roots+=("$directory")
done
for directory in "${roots[@]}"; do
    echo "清理 $directory 中 mtime 超过 $hours 小时的普通文件"
    find -P "$directory" -xdev -type f ! -newermt "$hours hours ago" -delete
done
