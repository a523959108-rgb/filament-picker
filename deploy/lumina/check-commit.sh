#!/usr/bin/env bash
# Docker 构建和 venv 安装共用；必须显式传入预期完整 SHA。
set -euo pipefail
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo '用法：check-commit.sh 预期40位SHA [--archive] LUMINA_COMMIT文件或发布包'
    exit 0
fi
expected=${1:-}
[[ $expected =~ ^[0-9a-f]{40}$ ]] || { echo 'LUMINA_COMMIT：预期值必须为完整40位小写SHA' >&2; exit 1; }
if [[ ${2:-} == --archive ]]; then
    actual=$(tar -xOzf "${3:?缺少发布包}" ./LUMINA_COMMIT 2>/dev/null ||
        tar -xOzf "$3" LUMINA_COMMIT 2>/dev/null) || {
        echo 'LUMINA_COMMIT：发布包缺少版本文件' >&2; exit 1;
    }
else
    [[ -f ${2:-} ]] || { echo 'LUMINA_COMMIT：缺少版本文件' >&2; exit 1; }
    actual=$(cat "$2")
fi
[[ $actual =~ ^[0-9a-f]{40}$ && $actual == "$expected" ]] || {
    echo 'LUMINA_COMMIT：版本格式非法或与预期不一致，拒绝部署' >&2; exit 1;
}
