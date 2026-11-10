"""部署包的离线行为测试；不调用 apt、pip、systemctl 或网络。"""

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b89af08226a88c9c9b3e2934ea1838c449923858"


def release_archive(path: Path, commit: str = COMMIT) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name in (
            "api_server.py",
            "config.py",
            "requirements.txt",
            "LICENSE",
            "frontend/dist/index.html",
            "BUILD-INFO",
            "LUMINA_COMMIT",
        ):
            content = (commit + "\n" if name == "LUMINA_COMMIT" else "fixture\n").encode()
            item = tarfile.TarInfo("./" + name)
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
    return path


def run_script(name: str, *args: str, **kwargs: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(ROOT / name), *args], capture_output=True, text=True, **kwargs
    )


def test_deliverables_and_shell_syntax() -> None:
    names = [
        "README.md",
        "build.sh",
        "install.sh",
        "rollback.sh",
        "common.sh",
        "lumina.service",
        "env.primary.example",
        "env.c.example",
        "nginx-b-stack.conf",
        "nginx-b-limit-req-zone.conf",
        "cleanup-output.sh",
        "lumina-cleanup.service",
        "lumina-cleanup.timer",
        "ufw.sh",
        "smoke.sh",
        "smoke.py",
        "smoke-box.sh",
        "deploy_support.py",
        "check-commit.sh",
        "docker/Dockerfile",
        "docker/compose.yaml",
        "docker/.dockerignore",
        "docker/build-image.sh",
    ]
    for name in names:
        assert (ROOT / name).is_file(), name
        if name.endswith(".sh"):
            assert run_script(name, "--help").returncode == 0, name
            subprocess.run(["bash", "-n", str(ROOT / name)], check=True)


def test_install_dry_run_has_no_mutation(tmp_path: Path) -> None:
    archive = release_archive(tmp_path / "lumina.tar.gz")
    result = run_script(
        "install.sh", "--dry-run", "--profile", "c", "--expected-commit", COMMIT, str(archive)
    )
    assert result.returncode == 0, result.stderr
    for expected in (
        "python3.12-venv",
        "mirrors.tencentyun.com",
        "mirrors.cloud.tencent.com",
        "10-resources.conf",
        "2.5G",
        "回滚",
    ):
        assert expected in result.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == [archive.name]


def test_cleanup_refuses_unsafe_roots_and_preserves_links(tmp_path: Path) -> None:
    assert run_script(
        "cleanup-output.sh", "--output-dir", "/", "--cache-dir", str(tmp_path)
    ).returncode
    assert run_script(
        "cleanup-output.sh", "--output-dir", "", "--cache-dir", str(tmp_path)
    ).returncode
    output, cache = tmp_path / "output", tmp_path / "cache"
    output.mkdir()
    cache.mkdir()
    old, recent, outside = output / "old", output / "recent", tmp_path / "outside"
    old.write_text("old")
    recent.write_text("recent")
    outside.write_text("outside")
    os.utime(old, (1, 1))
    os.utime(outside, (1, 1))
    (output / "link").symlink_to(outside)
    result = run_script("cleanup-output.sh", "--output-dir", str(output), "--cache-dir", str(cache))
    assert result.returncode == 0, result.stderr
    assert not old.exists()
    assert recent.exists() and outside.exists() and (output / "link").is_symlink()


def test_ufw_default_only_prints() -> None:
    result = run_script("ufw.sh")
    assert result.returncode == 0
    assert "allow in on tailscale0 from 100.70.57.112 to any port 8790 proto tcp" in result.stdout
    assert "default deny incoming" in result.stdout
    assert "ssh" in result.stdout.lower()
    assert "ufw enable" not in result.stdout


def test_primary_docker_contract() -> None:
    compose = (ROOT / "docker/compose.yaml").read_text()
    for required in (
        '"100.90.12.104:7860:8790"',
        "container_name: filament-lumina",
        "image: filament-lumina:${LUMINA_COMMIT:?",
        "cpus: 6",
        "mem_limit: 8G",
        "LUMINA_MAX_WORKERS: 4",
    ):
        assert required in compose
    dockerfile = (ROOT / "docker/Dockerfile").read_text()
    assert "FROM python:3.12-slim" in dockerfile
    assert "ARG LUMINA_COMMIT" in dockerfile
    assert 'check-commit.sh "$LUMINA_COMMIT"' in dockerfile
    assert "USER lumina" in dockerfile and "HEALTHCHECK" in dockerfile
    assert "--index-url https://download.pytorch.org/whl/cpu" in dockerfile


def test_no_retired_port_in_deliverables() -> None:
    forbidden = str(7860 + 1)
    for path in ROOT.rglob("*"):
        if path.is_file() and not {"materials-seed", "__pycache__", ".pytest_cache"} & set(
            path.parts
        ):
            assert forbidden not in path.read_text(), str(path)


def test_nginx_primary_and_failover_contract() -> None:
    config = (ROOT / "nginx-b-stack.conf").read_text()
    for required in (
        "100.90.12.104:7860 max_fails=2 fail_timeout=30s;",
        "100.121.76.35:8790 max_fails=2 fail_timeout=30s backup;",
        "proxy_connect_timeout 3s;",
        "proxy_read_timeout 300s;",
        "proxy_send_timeout 300s;",
        "client_max_body_size 50m;",
        "proxy_next_upstream error timeout http_502 http_503;",
        "proxy_next_upstream_tries 2;",
    ):
        assert required in config
    directives = "\n".join(line.split("#", 1)[0] for line in config.splitlines())
    assert "non_idempotent" not in directives and "ip_hash" not in directives
    primary = run_script("ufw.sh", "--port", "7860")
    assert primary.returncode == 0 and "port 7860 proto tcp" in primary.stdout
    assert "DOCKER-USER" in primary.stdout


def test_commit_mismatch_rejected_before_install(tmp_path: Path) -> None:
    archive = release_archive(tmp_path / "lumina.tar.gz")
    for expected in ("a" * 40, "short", ""):
        result = run_script(
            "install.sh", "--profile", "c", "--expected-commit", expected, str(archive)
        )
        assert result.returncode != 0
        assert "LUMINA_COMMIT" in result.stderr
        assert "root" not in result.stderr
        docker_result = run_script("docker/build-image.sh", expected, str(archive))
        assert docker_result.returncode != 0
        assert "LUMINA_COMMIT" in docker_result.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == [archive.name]


def test_install_accepts_explicit_environment_commit(tmp_path: Path) -> None:
    archive = release_archive(tmp_path / "lumina.tar.gz")
    result = run_script(
        "install.sh",
        "--dry-run",
        "--profile",
        "c",
        str(archive),
        env={**os.environ, "LUMINA_COMMIT": COMMIT},
    )
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == [archive.name]


def test_docker_and_installer_share_commit_guard(tmp_path: Path) -> None:
    marker = tmp_path / "LUMINA_COMMIT"
    marker.write_text(COMMIT + "\n")
    assert run_script("check-commit.sh", COMMIT, str(marker)).returncode == 0
    for actual in ("a" * 40, "invalid", ""):
        marker.write_text(actual + "\n")
        result = run_script("check-commit.sh", COMMIT, str(marker))
        assert result.returncode != 0 and "LUMINA_COMMIT" in result.stderr
    assert "LUMINA_COMMIT" in (ROOT / "build.sh").read_text()


def test_docker_build_stages_verified_release_without_containers(tmp_path: Path) -> None:
    archive = release_archive(tmp_path / "lumina.tar.gz")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".gz.sha256").write_text(f"{digest}  {archive.name}\n")
    commands = tmp_path / "bin"
    commands.mkdir()
    (commands / "python3.12").symlink_to(sys.executable)
    docker = commands / "docker"
    docker.write_text("""#!/usr/bin/env bash
set -euo pipefail
[[ $1 == build ]]
printf '%s\\n' "$@" > "$LUMINA_TEST_DOCKER_ARGS"
context=${!#}
for name in Dockerfile .dockerignore LUMINA_COMMIT frontend/dist/index.html \\
    _deploy/check-commit.sh _deploy/deploy_support.py _deploy/cleanup-output.sh; do
    [[ -f $context/$name ]]
done
""")
    docker.chmod(0o755)
    trace = tmp_path / "docker-args"
    result = run_script(
        "docker/build-image.sh",
        COMMIT,
        str(archive),
        env={
            **os.environ,
            "PATH": f"{commands}:{os.environ['PATH']}",
            "LUMINA_TEST_DOCKER_ARGS": str(trace),
        },
    )
    assert result.returncode == 0, result.stderr
    arguments = trace.read_text().splitlines()
    assert arguments[:5] == [
        "build",
        "--build-arg",
        f"LUMINA_COMMIT={COMMIT}",
        "--tag",
        f"filament-lumina:{COMMIT}",
    ]
    assert not Path(arguments[-1]).exists(), "临时构建上下文必须清理"


def test_smoke_limit_order_and_peak_reporting() -> None:
    script = (ROOT / "smoke-box.sh").read_text()
    probes = (
        "systemd-run --user --scope",
        "systemd-run --scope",
        "/sys/fs/cgroup/lumina-smoke-$$",
        "prlimit --as",
    )
    assert [script.index(probe) for probe in probes] == sorted(script.index(p) for p in probes)
    for required in (
        "memory.max",
        "2684354560",
        "memory.swap.max",
        "cgroup.procs",
        "memory.peak",
        "rmdir",
        "peak-rss-kib",
    ):
        assert required in script


def support_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("deploy_support", ROOT / "deploy_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_archive_rejects_escape_and_links(tmp_path: Path) -> None:
    support = support_module()
    for name, kind in (
        ("../escape", tarfile.REGTYPE),
        ("/escape", tarfile.REGTYPE),
        ("output", tarfile.SYMTYPE),
    ):
        archive = tmp_path / "bad.tgz"
        with tarfile.open(archive, "w:gz") as handle:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.linkname = "/tmp"
            handle.addfile(item, io.BytesIO())
        try:
            support.validate_archive(archive)
        except ValueError:
            pass
        else:
            raise AssertionError(name)


def test_atomic_switch_and_rollback_pointer(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    releases.mkdir()
    for name in ("a", "b"):
        (releases / name).mkdir()
    command = """source "$1/common.sh"
atomic_link "$2/releases/a" "$2/current"
atomic_link "$2/releases/b" "$2/current"
atomic_link "$2/releases/a" "$2/current"
readlink -f "$2/current"
"""
    result = subprocess.run(
        ["bash", "-c", command, "test", str(ROOT), str(tmp_path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(releases / "a")


def test_cpu_requirements_fail_closed(tmp_path: Path) -> None:
    support = support_module()
    req = tmp_path / "requirements.txt"
    req.write_text("numpy\ntorch==2.5.1\ntorchvision==0.20.1\nopencv-python\n")
    normal, cpu = support.split_requirements(req)
    assert cpu == ["torch==2.5.1", "torchvision==0.20.1"]
    assert "torch" not in normal
    assert "opencv-python" in normal
    req.write_text("nvidia-cublas-cu12\n")
    try:
        support.split_requirements(req)
    except ValueError:
        pass
    else:
        raise AssertionError("CUDA dependency must be refused")


def test_first_install_has_no_previous_release(tmp_path: Path) -> None:
    command = 'set -e; source "$1/common.sh"; current_release "$2"'
    result = subprocess.run(
        ["bash", "-c", command, "test", str(ROOT), str(tmp_path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_smoke_real_protocol_with_mock_transport() -> None:
    # 此测试只验证客户端协议/3MF 校验，不声称实际 Lumina 算法已运行。
    if sys.prefix != "/workspace/lumina-venv":
        subprocess.run(
            [
                "/workspace/lumina-venv/bin/python",
                "-B",
                "-c",
                "import runpy,sys; runpy.run_path(sys.argv[1])"
                '["test_smoke_real_protocol_with_mock_transport"]()',
                str(Path(__file__).resolve()),
            ],
            check=True,
        )
        return

    import httpx

    spec = importlib.util.spec_from_file_location("smoke", ROOT / "smoke.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(
            "3D/3dmodel.model",
            '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"/>',
        )
    seen = []
    polls = {}
    jobs = {
        "1" * 32: {"session_id": "session", "preview_url": "/api/files/png"},
        "2" * 32: {"download_url": "/api/files/3mf"},
    }

    def pending(job: str) -> httpx.Response:
        return httpx.Response(
            202,
            headers={"X-Lumina-Job": job},
            json={"status": "running", "job_id": job, "elapsed_seconds": 10.0},
        )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        seen.append(path)
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "worker_pool": {"healthy": True}})
        if path == "/api/lut/list":
            return httpx.Response(
                200,
                json={
                    "luts": [
                        {
                            "name": "bambulab - bambulab_pla_basic_rybw",
                            "color_mode": "4-Color (RYBW)",
                            "brand": "Bambu Lab",
                            "path": "lut-preset/bambulab/bambulab_pla_basic_rybw.npy",
                        }
                    ]
                },
            )
        if path == "/api/convert/preview":
            assert b"bambulab - bambulab_pla_basic_rybw" in request.content
            assert b"legacy_single" in request.content
            assert b"image/png" in request.content
            assert request.headers["X-Lumina-Async"] == "1"
            return pending("1" * 32)
        if path == "/api/convert/export-materials":
            assert json.loads(request.content)["session_id"] == "session"
            return httpx.Response(200, json={"ready": True})
        if path == "/api/convert/generate":
            body = json.loads(request.content)
            assert body["params"]["lut_name"] == "bambulab - bambulab_pla_basic_rybw"
            assert body["session_id"] == "session"
            assert request.headers["X-Lumina-Async"] == "1"
            return pending("2" * 32)
        if path.startswith("/api/jobs/"):
            job = path.rsplit("/", 1)[-1]
            assert request.method == "GET" and not request.content
            polls[job] = polls.get(job, 0) + 1
            return pending(job) if polls[job] == 1 else httpx.Response(200, json=jobs[job])
        return httpx.Response(200, content=package.getvalue() if path.endswith("3mf") else b"png")

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as client:
        smoke.run_smoke(client, time.perf_counter())
    assert seen[-1] == "/api/files/3mf"
    assert polls == {"1" * 32: 2, "2" * 32: 2}


def test_resolver_report_rejects_transitive_cuda(tmp_path: Path) -> None:
    support = support_module()
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"install": [{"metadata": {"name": "nvidia-cudnn-cu12", "version": "9"}}]})
    )
    try:
        support.validate_pip_report(report)
    except ValueError:
        pass
    else:
        raise AssertionError("必须在实际安装前拒绝传递 CUDA 依赖")
    report.write_text(
        json.dumps({"install": [{"metadata": {"name": "torch", "version": "2.5.1+cpu"}}]})
    )
    support.validate_pip_report(report)


def test_env_never_executes_shell(tmp_path: Path) -> None:
    env = tmp_path / "unsafe.env"
    marker = tmp_path / "must-not-exist"
    env.write_text(f"LUMINA_API_PORT=$(touch {marker})\n")
    result = subprocess.run(
        ["bash", "-c", 'source "$1/common.sh"; load_env "$2"', "test", str(ROOT), str(env)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not marker.exists()
