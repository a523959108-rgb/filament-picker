#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$script_dir/common.sh"
usage() {
    echo '用法：sudo bash install.sh [--dry-run] --profile c|primary [--env-template 文件] 发布包.tar.gz'
    echo 'env 存在时保留；primary 首次安装必须先复制并填写 env.primary.example 的资源额度。'
}
profile= template= archive= dry_run=0
while (($#)); do
    case $1 in
        --help|-h) usage; exit 0 ;;
        --dry-run) dry_run=1; shift ;;
        --profile) profile=${2:?缺少 profile}; shift 2 ;;
        --env-template) template=${2:?缺少模板}; shift 2 ;;
        -*) fail "未知参数：$1" ;;
        *) [[ -z $archive ]] || fail '只能传一个发布包'; archive=$1; shift ;;
    esac
done
[[ $profile == primary || $profile == c ]] || { usage >&2; exit 2; }
[[ -f $archive ]] || fail '发布包不存在'
template=${template:-$script_dir/env.$profile.example}
[[ -f $template ]] || fail 'env 模板不存在'
cpu_count=$(nproc)
workers=$((cpu_count > 2 ? cpu_count - 2 : 1))
echo "主力建议 LUMINA_MAX_WORKERS=$workers（nproc=$cpu_count；仍需按内存实测调整）"
if ((dry_run)); then
    cat <<EOF
[只打印，不执行] profile=$profile
创建 lumina 系统用户、/opt/lumina/{releases,shared}、/var/lib/lumina/{materials,cache,output}、/var/log/lumina
apt-get install -y python3.12-venv python3-pip curl libgl1 libglib2.0-0
校验 SHA256、拒绝包内路径逃逸/链接；解包到 releases/<东京时间戳>
python3.12 -m venv；CPU torch 单独安装，绝不安装 CUDA 包
pip 首选 http://mirrors.tencentyun.com/pypi/simple --trusted-host mirrors.tencentyun.com
失败自动改用 https://mirrors.cloud.tencent.com/pypi/simple --trusted-host mirrors.cloud.tencent.com
原 opencv-python 保留，apt 提供 libGL；不改上游 requirements.txt
已有 /etc/lumina/lumina.env 不覆盖；新 primary env 并发填 $workers
根据 env 写 /etc/systemd/system/lumina.service.d/10-resources.conf（C 模板 MemoryMax=2.5G）
安装服务和每小时清理定时器，原子切换 current，daemon-reload、restart、curl 健康检查
失败自动回滚旧 current 和旧 systemd 文件，首次安装失败则停止服务
EOF
    exit 0
fi
((EUID == 0)) || fail '必须以 root 运行；可用 --dry-run 预览'
command -v flock >/dev/null || fail '缺少 flock（Ubuntu 的 util-linux）'
exec 9>/run/lock/lumina-deploy.lock
flock -n 9 || fail '另一安装/回滚正在运行'
[[ -f $archive.sha256 ]] || fail '缺少发布包旁的 .sha256 文件'
archive=$(realpath "$archive")
# 不让 checksum 文件决定待读取路径，只取并校验唯一的哈希值。
read -r expected_hash _ < "$archive.sha256"
[[ $expected_hash =~ ^[0-9a-fA-F]{64}$ && $(wc -l < "$archive.sha256") == 1 ]] || fail '非法 SHA256 文件'
actual_hash=$(sha256sum "$archive")
[[ ${actual_hash%% *} == "${expected_hash,,}" ]] || fail 'SHA256 不匹配'
work=$(mktemp -d)
release= old_release= switched=0 units_touched=0
unit_files=(/etc/systemd/system/lumina.service /etc/systemd/system/lumina.service.d/10-resources.conf)
finish() {
    local code=$? index path
    trap - EXIT
    if ((code != 0 && units_touched)); then
        echo '安装失败，自动回滚。' >&2
        for index in "${!unit_files[@]}"; do
            path=${unit_files[$index]}
            if [[ -f $work/unit-$index ]]; then
                cp -p -- "$work/unit-$index" "$path"
            else
                rm -f -- "$path"
            fi
        done
        if ((switched)); then
            if [[ -n $old_release ]]; then atomic_link "$old_release" /opt/lumina/current
            else rm -f /opt/lumina/current; fi
        fi
        systemctl daemon-reload || echo '恢复 daemon-reload 失败' >&2
        if [[ -n $old_release ]]; then
            systemctl restart lumina.service && health_check "$LUMINA_API_PORT" ||
                echo '旧版本恢复失败，需运维检查服务日志。' >&2
        else
            systemctl stop lumina.service || echo '停止首次安装服务失败' >&2
        fi
    fi
    rm -rf -- "$work"
    exit "$code"
}
trap finish EXIT
old_release=$(current_release /opt/lumina)
if [[ -n $old_release ]]; then
    [[ $old_release == /opt/lumina/releases/* && -d $old_release ]] || fail '旧 current 越界或已损坏'
fi
# 所有模板预检先于 apt/用户/发布目录变更；不回显 env 内容。
if [[ -f /etc/lumina/lumina.env ]]; then
    load_env /etc/lumina/lumina.env
else
    cp "$template" "$work/lumina.env"
    if [[ $profile == primary ]]; then
        sed -i "s/^LUMINA_MAX_WORKERS=.*/LUMINA_MAX_WORKERS=$workers/" "$work/lumina.env"
    fi
    load_env "$work/lumina.env"
fi
[[ ${LUMINA_MEMORY_MAX:-} =~ ^[1-9][0-9]*(\.[0-9]+)?[MG]$ ]] || fail '请填写 LUMINA_MEMORY_MAX（如 2.5G）'
[[ ${LUMINA_MEMORY_SWAP_MAX:-} =~ ^(0|[1-9][0-9]*(\.[0-9]+)?[MG])$ ]] || fail '请填写 LUMINA_MEMORY_SWAP_MAX'
[[ ${LUMINA_CPU_QUOTA:-} =~ ^[1-9][0-9]*%$ ]] || fail '请填写 LUMINA_CPU_QUOTA（如 150%）'
if [[ $profile == c ]]; then
    ((LUMINA_MAX_WORKERS <= 2)) || fail 'C 的 worker 最多 2，建议 1'
fi
# 加固单元只开放这些根目录；不接受落到 release 或系统其他位置的路径。
for key in LUMINA_MATERIALS_DIR LUMINA_RUNTIME_CACHE_DIR LUMINA_LOG_PATH LUMINA_SETTINGS_PATH \
    LUMINA_WORKSHOP_DATA_DIR LUMINA_FEEDBACK_DUMP_DIR NUMBA_CACHE_DIR XDG_CACHE_HOME XDG_DATA_HOME; do
    value=${!key:-}
    case $value in /var/lib/lumina/*|/var/log/lumina/*|/opt/lumina/shared/*) ;;
        *) fail "$key 必须位于持久可写根目录下" ;;
    esac
    [[ $value != *'/../'* && $value != */.. ]] || fail "$key 路径不能含 .."
done
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3.12-venv python3-pip curl libgl1 libglib2.0-0
python3.12 "$script_dir/deploy_support.py" validate "$archive"
getent group lumina >/dev/null || groupadd --system lumina
id lumina >/dev/null 2>&1 || useradd --system --gid lumina --home-dir /var/lib/lumina --shell /usr/sbin/nologin lumina
install -d -m 0755 /opt/lumina /opt/lumina/releases
install -d -o lumina -g lumina -m 0750 /opt/lumina/shared /var/lib/lumina \
    /var/lib/lumina/materials /var/lib/lumina/cache /var/lib/lumina/output /var/log/lumina
install -d -m 0750 -o root -g lumina /etc/lumina
if [[ ! -f /etc/lumina/lumina.env ]]; then
    install -o root -g lumina -m 0640 "$work/lumina.env" /etc/lumina/lumina.env
fi
# 包含日志文件、设置文件的父目录；共享目录只创建不清空。
install -d -o lumina -g lumina -m 0750 "$LUMINA_MATERIALS_DIR" "$LUMINA_RUNTIME_CACHE_DIR" \
    "$(dirname "$LUMINA_LOG_PATH")" "$(dirname "$LUMINA_SETTINGS_PATH")" \
    "$LUMINA_WORKSHOP_DATA_DIR" "$LUMINA_FEEDBACK_DUMP_DIR" "$NUMBA_CACHE_DIR" \
    "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
release="/opt/lumina/releases/$(TZ=Asia/Tokyo date +%Y%m%dT%H%M%S)"
[[ ! -e $release ]] || fail '同一秒的 release 已存在，请稍后重试'
mkdir -m 0755 "$release"
tar --no-same-owner --no-same-permissions -xzf "$archive" -C "$release"
python3.12 "$script_dir/deploy_support.py" requirements "$release/requirements.txt" "$work"
python3.12 -m venv "$release/.venv"
pip_cmd=("$release/.venv/bin/python" -m pip --isolated --disable-pip-version-check)
if [[ -s $work/torch.txt && $(tr -d '[:space:]' < "$work/torch.txt") != '' ]]; then
    echo '检测到 torch：只从官方 CPU wheel 索引安装（此步骤不使用腾讯镜像）。'
    "${pip_cmd[@]}" install --dry-run --report "$work/cpu-report.json" --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu --trusted-host download.pytorch.org \
        -r "$work/torch.txt"
    python3.12 "$script_dir/deploy_support.py" report "$work/cpu-report.json"
    "${pip_cmd[@]}" install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        --trusted-host download.pytorch.org -r "$work/torch.txt"
    "${pip_cmd[@]}" freeze | sed -n -E '/^(torch|torchvision|torchaudio)==/p' > "$work/cpu-constraints.txt"
else
    : > "$work/cpu-constraints.txt"
fi
pip_install() {
    "${pip_cmd[@]}" install --dry-run --report "$work/pip-report.json" \
        --no-cache-dir --timeout 20 --retries 1 --index-url "$1" --trusted-host "$2" \
        -c "$work/cpu-constraints.txt" -r "$work/requirements.txt" || return "$?"
    python3.12 "$script_dir/deploy_support.py" report "$work/pip-report.json" || return "$?"
    "${pip_cmd[@]}" install --no-cache-dir --timeout 20 --retries 1 \
        --index-url "$1" --trusted-host "$2" -c "$work/cpu-constraints.txt" -r "$work/requirements.txt"
}
if ! pip_install http://mirrors.tencentyun.com/pypi/simple mirrors.tencentyun.com; then
    echo '内网镜像失败，自动改用腾讯公网镜像。' >&2
    pip_install https://mirrors.cloud.tencent.com/pypi/simple mirrors.cloud.tencent.com
fi
"${pip_cmd[@]}" check
"$release/.venv/bin/python" - <<'PY'
from importlib.metadata import distributions
for package in distributions():
    name = package.metadata['Name'].lower()
    if any(word in name for word in ('cuda', 'nvidia', 'triton', 'cupy')):
        raise SystemExit('拒绝 CUDA 相关安装结果')
    if name in {'torch', 'torchvision', 'torchaudio'} and '+cpu' not in package.version:
        raise SystemExit('torch 家族必须是 +cpu wheel')
PY
ln -s /var/lib/lumina/output "$release/output"
ln -s "$LUMINA_MATERIALS_DIR" "$release/materials"
ln -s /var/log/lumina "$release/logs"
# Custom/Cloud 可写；其余 LUT 和代码保持只读，且升级保留用户 LUT。
for name in Custom Cloud _sync; do
    install -d -o lumina -g lumina -m 0750 "/opt/lumina/shared/lut-preset/$name"
    if [[ -d $release/lut-preset/$name ]]; then
        cp -an "$release/lut-preset/$name/." "/opt/lumina/shared/lut-preset/$name/"
        rm -rf -- "$release/lut-preset/$name"
    fi
    ln -s "/opt/lumina/shared/lut-preset/$name" "$release/lut-preset/$name"
done
chown -R lumina:lumina /opt/lumina/shared/lut-preset
chown -hR root:root "$release"
chmod -R go-w "$release"
# 只开放 assets 顶层以创建旧版提色临时页，现有静态文件仍由 root 持有。
chown lumina:lumina "$release/assets"
chmod 0755 "$release/assets"
install -d -m 0755 /etc/systemd/system/lumina.service.d
for index in "${!unit_files[@]}"; do
    [[ ! -f ${unit_files[$index]} ]] || cp -p -- "${unit_files[$index]}" "$work/unit-$index"
done
units_touched=1
install -m 0644 "$script_dir/lumina.service" /etc/systemd/system/lumina.service
cat > /etc/systemd/system/lumina.service.d/10-resources.conf <<EOF
[Service]
MemoryMax=$LUMINA_MEMORY_MAX
MemorySwapMax=$LUMINA_MEMORY_SWAP_MAX
CPUQuota=$LUMINA_CPU_QUOTA
EOF
switched=1
atomic_link "$release" /opt/lumina/current
systemctl daemon-reload
systemctl restart lumina.service
health_check "$LUMINA_API_PORT"
# 定时器最后安装；健康失败不会给旧服务增加清理动作。
install -d -m 0755 /opt/lumina/shared/deploy
install -m 0755 "$script_dir/cleanup-output.sh" /opt/lumina/shared/deploy/cleanup-output.sh
install -m 0644 "$script_dir/lumina-cleanup.service" "$script_dir/lumina-cleanup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable lumina.service
systemctl enable --now lumina-cleanup.timer
# 全部成功才更新 previous，失败时保留原来的上一成功版本指针。
if [[ -n $old_release ]]; then atomic_link "$old_release" /opt/lumina/previous; fi
units_touched=0
echo "安装成功：$release；旧版本保留，手工回滚用 rollback.sh。"
