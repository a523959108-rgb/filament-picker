#!/usr/bin/env bash
set -euo pipefail
usage() {
    echo '用法：build.sh [--frontend-deps 已安装的node_modules目录] [源码目录] 输出目录'
    echo '默认源码 /workspace/dev/filament-lumina；只在临时副本构建，不安装依赖。'
}
source_dir=/workspace/dev/filament-lumina
frontend_deps=
positional=()
while (($#)); do
    case $1 in
        --help|-h) usage; exit 0 ;;
        --frontend-deps) frontend_deps=${2:?缺少依赖目录}; shift 2 ;;
        -*) echo "未知参数：$1" >&2; exit 2 ;;
        *) positional+=("$1"); shift ;;
    esac
done
case ${#positional[@]} in
    1) output_dir=${positional[0]} ;;
    2) source_dir=${positional[0]}; output_dir=${positional[1]} ;;
    *) usage >&2; exit 2 ;;
esac
source_dir=$(realpath "$source_dir")
frontend_deps=${frontend_deps:-$source_dir/frontend/node_modules}
[[ -x $frontend_deps/.bin/tsc && -x $frontend_deps/.bin/vite ]] || {
    echo '缺少已装的前端依赖；可传 --frontend-deps，不会自动安装。' >&2; exit 1;
}
[[ -z $(git -C "$source_dir" status --porcelain --untracked-files=no) ]] || {
    echo '源码含未提交修改，拒绝生成与 commit 不一致的发布包。' >&2; exit 1;
}
mkdir -p "$output_dir"
output_dir=$(realpath "$output_dir")
[[ $output_dir != "$source_dir" && $output_dir != "$source_dir/"* ]] || {
    echo '输出目录必须在只读源码目录之外。' >&2; exit 1;
}
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
commit=$(git -C "$source_dir" rev-parse HEAD)
# 只读 Git 快照，避免夹带 .env.local、日志、个人数据及工作树未跟踪文件。
git -C "$source_dir" archive "$commit" | tar -x -C "$work"
cp -a --reflink=auto "$frontend_deps" "$work/frontend/node_modules"
(
    cd "$work/frontend"
    node_modules/.bin/tsc -b
    node_modules/.bin/vite build
)
[[ -f $work/frontend/dist/index.html && -f $work/LICENSE ]]
build_stamp=$(TZ=Asia/Tokyo date +%Y%m%dT%H%M%S)
archive="lumina-${build_stamp}-${commit:0:12}.tar.gz"
{
    echo "commit=$commit"
    echo "built_at=$(TZ=Asia/Tokyo date --iso-8601=seconds)"
    echo 'source=https://github.com/a523959108-rgb/filament-lumina'
    echo 'frontend_build=tsc -b && vite build (existing dependencies, temporary copy)'
} > "$work/BUILD-INFO"
# 运行所需 api/core/utils/assets/lut-preset 及全部后端模块保留。
tar -czf "$output_dir/$archive" -C "$work" \
    --exclude='./.git*' --exclude='./.env*' --exclude='node_modules' \
    --exclude='./frontend/src' --exclude='./frontend/public' --exclude='./tests' \
    --exclude='./test_images' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='./logs' --exclude='./output' --exclude='./materials' \
    --exclude='./feedback' --exclude='./electron' --exclude='./.venv' \
    --exclude='./venv' --exclude='./user_settings.json' --exclude='./.github' .
cp "$work/BUILD-INFO" "$output_dir/BUILD-INFO"
(cd "$output_dir" && sha256sum "$archive" > "$archive.sha256")
echo "发布包：$output_dir/$archive"
echo "SHA256：$output_dir/$archive.sha256"
echo "commit：$commit"
