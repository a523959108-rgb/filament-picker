#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir=/workspace/dev/filament-lumina
dist_dir=
while (($#)); do
    case $1 in
        --help|-h)
            echo '用法：smoke-box.sh [--source Lumina源码/解包目录] [--dist 已构建dist目录]'
            echo '运行数据放 /workspace/dev/lumina-run/A/，结束后停止后端并报告峰值 RSS。'; exit 0 ;;
        --source) source_dir=${2:?缺少源码目录}; shift 2 ;;
        --dist) dist_dir=${2:?缺少 dist}; shift 2 ;;
        *) echo "未知参数：$1" >&2; exit 2 ;;
    esac
done
source_dir=$(realpath "$source_dir")
dist_dir=${dist_dir:-$source_dir/frontend/dist}
[[ -f $source_dir/api_server.py && -f $dist_dir/index.html ]] || {
    echo '缺少入口或前端 dist；先 build.sh，再传 --source 解包目录，或显式 --dist。' >&2; exit 1;
}
run_root=/workspace/dev/lumina-run/A
mkdir -p "$run_root"
exec 9>"$run_root/smoke.lock"
flock -n 9 || { echo '已有 smoke-box 运行' >&2; exit 1; }
# 不复用其他服务端口、不杀已有服务；curl 只对本地执行。
if curl --noproxy '*' --silent --max-time 1 http://127.0.0.1:18101/api/health >/dev/null; then
    echo '18101 已有服务，拒绝启动或停止它。' >&2; exit 1
fi
instance=$(mktemp -d "$run_root/run-XXXXXXXX")
mkdir -p "$instance/source" "$instance/materials" "$instance/cache" "$instance/output" "$instance/shared" "$instance/logs"
# 源码始终只读，output 固定路径通过隔离副本解决。
tar -c -C "$source_dir" --exclude='./.git' --exclude='node_modules' --exclude='./output' \
    --exclude='./materials' --exclude='./logs' --exclude='./.env*' --exclude='./.venv' \
    --exclude='__pycache__' --exclude='./frontend/dist' . | tar -x -C "$instance/source"
mkdir -p "$instance/source/frontend"
cp -a "$dist_dir" "$instance/source/frontend/dist"
ln -s "$instance/output" "$instance/source/output"
export LUMINA_API_HOST=127.0.0.1 LUMINA_API_PORT=18101 LUMINA_MAX_WORKERS=1
export LUMINA_SERVE_FRONTEND_DIST=1 LUMINA_FRONTEND_DIST_DIR="$instance/source/frontend/dist"
export LUMINA_MATERIALS_DIR="$instance/materials" LUMINA_RUNTIME_CACHE_DIR="$instance/cache"
export LUMINA_PREVIEW_CACHE_MAX_BYTES=268435456 LUMINA_LOG_PATH="$instance/logs/lumina.jsonl"
export LUMINA_SETTINGS_PATH="$instance/shared/user_settings.json" LUMINA_WORKSHOP_DATA_DIR="$instance/shared/workshop"
export LUMINA_FEEDBACK_DUMP_DIR="$instance/output/feedback" NUMBA_CACHE_DIR="$instance/cache/numba"
export XDG_CACHE_HOME="$instance/cache/xdg" XDG_DATA_HOME="$instance/shared/xdg"
export PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES=-1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
# 清空继承的远端配置，本次只做本地 LUT 冒烟。
export LUMINA_MATERIAL_REGISTRY_URL= LUMINA_LUT_REGISTRY_URL= LUMINA_MATERIALS_SEED_URL= LUMINA_MATERIALS_SEED_PATH=
backend_pid= sampler_pid= scope= isolated=0
cleanup() {
    local code=$?
    trap - EXIT
    if [[ -n $backend_pid ]]; then
        if [[ -n $scope ]]; then systemctl --user stop "$scope.scope" || true; fi
        if ((isolated)); then kill -TERM -- "-$backend_pid" 2>/dev/null || true
        else kill -TERM "$backend_pid" 2>/dev/null || true; fi
        for _ in {1..20}; do
            kill -0 "$backend_pid" 2>/dev/null || break
            sleep 0.1
        done
        if ((isolated)); then kill -KILL -- "-$backend_pid" 2>/dev/null || true; fi
        wait "$backend_pid" 2>/dev/null || true
    fi
    touch "$instance/stop-sampling"
    [[ -z $sampler_pid ]] || wait "$sampler_pid"
    [[ ! -f $instance/memory.log ]] || cat "$instance/memory.log"
    echo "冒烟日志/峰值记录保留在：$instance"
    exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cd "$instance/source"
# 先实际试运行无副作用的 true，不能仅凭 systemd-run 命令存在就认为 cgroup 可用。
if command -v systemd-run >/dev/null && \
    systemd-run --user --scope -p MemoryMax=2.5G /usr/bin/true >/dev/null 2>&1; then
    scope="lumina-smoke-A-$$"
    echo '实际限制：systemd-run --user --scope MemoryMax=2.5G MemorySwapMax=512M'
    setsid systemd-run --user --scope --unit="$scope" -p MemoryMax=2.5G -p MemorySwapMax=512M \
        /workspace/lumina-venv/bin/python -B api_server.py >"$instance/backend.log" 2>&1 &
    backend_pid=$!; isolated=1
elif command -v prlimit >/dev/null; then
    echo '实际限制：prlimit --as=2684354560（虚拟地址空间 2.5 GiB，不等同 cgroup RSS 限额）'
    setsid prlimit --as=2684354560 -- /workspace/lumina-venv/bin/python -B api_server.py \
        >"$instance/backend.log" 2>&1 &
    backend_pid=$!; isolated=1
else
    echo '实际限制：ulimit -v 2621440（虚拟地址空间 2.5 GiB，不等同 cgroup RSS 限额）'
    setsid bash -c 'ulimit -v 2621440; exec /workspace/lumina-venv/bin/python -B api_server.py' \
        >"$instance/backend.log" 2>&1 &
    backend_pid=$!; isolated=1
fi
/workspace/lumina-venv/bin/python -B "$script_dir/deploy_support.py" sample "$backend_pid" \
    "$instance/stop-sampling" "$instance/peak-rss-kib" >"$instance/memory.log" &
sampler_pid=$!
ready=0
for _ in {1..60}; do
    kill -0 "$backend_pid" 2>/dev/null || { echo "后端退出，见 $instance/backend.log" >&2; break; }
    if curl --noproxy '*' --fail --silent --max-time 1 http://127.0.0.1:18101/api/health >/dev/null; then
        ready=1; break
    fi
    sleep 0.5
done
((ready)) || { echo '后端启动失败，未通过冒烟。' >&2; exit 1; }
"$script_dir/smoke.sh" http://127.0.0.1:18101
