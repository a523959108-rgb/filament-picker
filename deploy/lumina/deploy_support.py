"""仅用标准库校验发布包、拆分 CPU 依赖及采样进程树 RSS。"""

import argparse
import json
import re
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath


def validate_archive(path: Path) -> None:
    """拒绝路径逃逸、特殊文件和链接，再检查必需的发布文件。"""
    names = set()
    with tarfile.open(path, "r:gz") as archive:
        for item in archive:
            parts = PurePosixPath(item.name)
            if parts.is_absolute() or ".." in parts.parts:
                raise ValueError("发布包含越界路径")
            if not (item.isfile() or item.isdir()):
                raise ValueError("发布包含链接或特殊文件")
            if parts.parts and parts.parts[0] in {".venv", "output", "materials", "logs"}:
                raise ValueError("发布包混入运行时目录")
            names.add(str(parts))
    required = {
        "api_server.py",
        "config.py",
        "requirements.txt",
        "LICENSE",
        "frontend/dist/index.html",
        "BUILD-INFO",
        "LUMINA_COMMIT",
    }
    if not required <= names:
        raise ValueError("发布包缺少入口、前端、许可证、BUILD-INFO 或 LUMINA_COMMIT")


def split_requirements(path: Path) -> tuple[str, list[str]]:
    """保留上游版本约束；torch 家族单独从 CPU wheel 源安装。"""
    normal, cpu = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            normal.append(line)
            continue
        if stripped.startswith("--only-binary="):
            normal.append(line)
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(\s*(?:[<>=!~].*)?)", stripped)
        if not match or ";" in stripped or "\\" in stripped:
            raise ValueError("requirements 包含需人工核对的 URL、递归引用或条件语法")
        name = match[1].lower().replace("_", "-")
        if any(word in name for word in ("cuda", "nvidia", "triton", "cupy")):
            raise ValueError("仅支持 CPU：requirements 包含 CUDA 相关依赖")
        if name in {"torch", "torchvision", "torchaudio"}:
            if "+cu" in stripped.lower():
                raise ValueError("拒绝 CUDA torch 版本，请人工明确 CPU 对应版本")
            cpu.append(stripped)
        else:
            normal.append(line)
    return "\n".join(normal) + "\n", cpu


def validate_pip_report(path: Path) -> None:
    """在实际安装前拦截解析器选出的传递 CUDA 包和非 CPU torch。"""
    report = json.loads(path.read_text(encoding="utf-8"))
    for item in report["install"]:
        name = item["metadata"]["name"].lower().replace("_", "-")
        version = item["metadata"]["version"].lower()
        if any(word in name for word in ("cuda", "nvidia", "triton", "cupy")):
            raise ValueError("pip 解析结果包含 CUDA 相关依赖，未安装")
        if name in {"torch", "torchvision", "torchaudio"} and "+cpu" not in version:
            raise ValueError("pip 解析结果不是 +cpu torch wheel，未安装")


def sample_rss(pid: int, stop: Path, result: Path) -> None:
    """每 0.5 秒累加 /proc 中后端及子孙进程的 RSS，单位 KiB。"""
    peak = 0
    while not stop.exists():
        records = {}
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                values = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                status = (entry / "status").read_text()
                rss = re.search(r"^VmRSS:\s+(\d+)", status, re.MULTILINE)
                records[int(entry.name)] = (int(values[1]), int(rss[1]) if rss else 0)
            except (OSError, ValueError, IndexError):
                continue  # /proc 的进程可能在采样时退出。
        family = {pid}
        while True:
            expanded = family | {p for p, (parent, _) in records.items() if parent in family}
            if expanded == family:
                break
            family = expanded
        peak = max(peak, sum(records.get(p, (0, 0))[1] for p in family))
        result.write_text(f"{peak}\n", encoding="utf-8")
        time.sleep(0.5)
    print(f"后端进程树峰值 RSS：{peak / 1024:.1f} MiB（0.5 秒采样）", flush=True)


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "requirements", "report", "sample"))
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    if args.action == "validate":
        validate_archive(Path(args.paths[0]))
    elif args.action == "report":
        validate_pip_report(Path(args.paths[0]))
    elif args.action == "requirements":
        normal, cpu = split_requirements(Path(args.paths[0]))
        target = Path(args.paths[1])
        (target / "requirements.txt").write_text(normal, encoding="utf-8")
        (target / "torch.txt").write_text("\n".join(cpu) + "\n", encoding="utf-8")
    else:
        sample_rss(int(args.paths[0]), Path(args.paths[1]), Path(args.paths[2]))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, tarfile.TarError) as error:
        print(f"部署校验失败：{error}", file=sys.stderr)
        raise SystemExit(1) from error
