#!/usr/bin/env bash
# 仅构建新镜像，不查询/删除/停止/启动任何容器。
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo '用法：build-image.sh 预期完整40位SHA 发布包.tar.gz；主力需要docker和python3.12。'
    exit 0
fi
[[ $# == 2 ]] || { echo '请传预期SHA和发布包，见 --help' >&2; exit 2; }
commit=$1 archive=$(realpath "$2")
bash "$script_dir/../check-commit.sh" "$commit" --archive "$archive"
read -r expected_hash _ < "$archive.sha256"
actual_hash=$(sha256sum "$archive")
[[ $expected_hash =~ ^[0-9a-fA-F]{64}$ && ${actual_hash%% *} == "${expected_hash,,}" ]] || {
    echo '发布包 SHA256 不匹配' >&2; exit 1;
}
python3.12 "$script_dir/../deploy_support.py" validate "$archive"
context=$(mktemp -d)
trap 'rm -rf -- "$context"' EXIT
tar --no-same-owner --no-same-permissions -xzf "$archive" -C "$context"
mkdir -p "$context/_deploy"
cp "$script_dir/Dockerfile" "$script_dir/.dockerignore" "$context/"
cp "$script_dir/../check-commit.sh" "$script_dir/../deploy_support.py" \
    "$script_dir/../cleanup-output.sh" "$context/_deploy/"
docker build --build-arg "LUMINA_COMMIT=$commit" --tag "filament-lumina:$commit" "$context"
