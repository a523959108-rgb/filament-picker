"""Lumina 真实 API 冒烟；httpx 已存在于 Lumina venv，无需安装依赖。"""

import argparse
import io
import re
import signal
import struct
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx

T = TypeVar("T")


class SmokeFailure(RuntimeError):
    """API 响应、计时或产物校验失败。"""


def small_png() -> bytes:
    """生成确定性的 16×16 RGB 测试图，不下载图片。"""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    colors = ((230, 40, 40), (245, 220, 40), (40, 70, 200), (245, 245, 245))
    rows = b"".join(
        b"\x00" + b"".join(bytes(colors[(x // 8) + 2 * (y // 8)]) for x in range(16))
        for y in range(16)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", 16, 16, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def run_smoke(client: httpx.Client, started: float) -> None:
    """按前端真实协议上传并生成 3MF，总用时必须小于等于 30 秒。"""
    deadline = started + 30

    def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not path.startswith("/api/") or path.startswith("//"):
            raise SmokeFailure("拒绝下载非本服务 API 路径")
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise SmokeFailure("总用时超过 30 秒")
        if method == "POST" and path in {"/api/convert/preview", "/api/convert/generate"}:
            kwargs["headers"] = {"X-Lumina-Async": "1"}
        response = client.request(method, path, timeout=remaining, **kwargs)
        job_id = None
        while response.status_code == 202:
            current_id = response.headers.get("X-Lumina-Job") or response.json().get("job_id")
            if not isinstance(current_id, str) or not re.fullmatch(r"[0-9a-f]{32}", current_id):
                raise SmokeFailure("202 响应缺少合法 job_id")
            if job_id is not None and current_id != job_id:
                raise SmokeFailure("轮询返回了不同 job_id")
            job_id = current_id
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise SmokeFailure("轮询总用时超过 30 秒")
            # 上游长轮询直接重放最终 HTTP 状态/JSON；没有 result/status 成功包装层。
            response = client.get(f"/api/jobs/{job_id}", timeout=remaining)
        if response.status_code != 200:
            raise SmokeFailure(f"{method} {path.split('?')[0]} 返回 HTTP {response.status_code}")
        return response

    def step(label: str, operation: Callable[[], T]) -> T:
        before = time.perf_counter()
        result = operation()
        print(f"{label}：{time.perf_counter() - before:.3f} 秒", flush=True)
        return result

    health = step("健康检查", lambda: request("GET", "/api/health").json())
    if health.get("status") != "ok" or health.get("worker_pool", {}).get("healthy") is not True:
        raise SmokeFailure("worker pool 不健康")
    luts = step("获取 LUT 列表", lambda: request("GET", "/api/lut/list").json())["luts"]
    candidates = [
        lut
        for lut in luts
        if lut["name"] == "bambulab - bambulab_pla_basic_rybw"
        and lut["path"]
        .replace("\\", "/")
        .endswith("lut-preset/bambulab/bambulab_pla_basic_rybw.npy")
        and lut.get("color_mode") == "4-Color (RYBW)"
    ]
    if not candidates:
        raise SmokeFailure("未找到经典 LUT bambulab - bambulab_pla_basic_rybw（4 色 RYBW）")
    lut = candidates[0]
    print(f"经典 LUT：{lut['name']}", flush=True)
    params = {
        "source_kind": "legacy_single",
        "lut_name": lut["name"],
        "color_mode": "4-Color (RYBW)",
        "modeling_mode": "high-fidelity",
        "target_width_mm": 10.0,
        "quantize_colors": 8,
        "enable_cleanup": True,
    }
    preview = step(
        "上传 PNG 并生成预览",
        lambda: request(
            "POST",
            "/api/convert/preview",
            files={"image": ("smoke.png", small_png(), "image/png")},
            data={
                key: str(value).lower() if isinstance(value, bool) else str(value)
                for key, value in params.items()
            },
        ).json(),
    )
    if not preview.get("session_id") or not preview.get("preview_url"):
        raise SmokeFailure("预览未返回 session_id/preview_url")
    step("下载预览", lambda: request("GET", preview["preview_url"]))
    body = {
        "session_id": preview["session_id"],
        "params": {
            **params,
            "printer_id": "bambu-h2d",
            "slicer": "BambuStudio",
            "nozzle_size": "0.4",
        },
    }
    selection = step(
        "预检原生耗材", lambda: request("POST", "/api/convert/export-materials", json=body).json()
    )
    if not selection["ready"]:
        # 仅为冒烟选择实际 API 返回的 PLA 候选及共同兼容打印板，不臆造 preset ID。
        profiles = {}
        for material in selection["materials"]:
            choices = sorted(
                (p for p in material["profiles"] if p["available"]),
                key=lambda p: ("bambu pla basic" not in p["name"].lower(), p["name"]),
            )
            if not choices:
                raise SmokeFailure("原生耗材无可用候选")
            profiles[material["name"]] = material.get("selected_profile_name") or choices[0]["name"]
        body["params"]["native_filament_profiles"] = profiles
        selection = step(
            "复查耗材选择",
            lambda: request("POST", "/api/convert/export-materials", json=body).json(),
        )
        plates = [plate for plate in selection["build_plates"] if plate["compatible"]]
        if plates:
            body["params"].update(
                device_profile_id=selection["device_profile_id"], build_plate_id=plates[0]["id"]
            )
        selection = step(
            "复查打印板", lambda: request("POST", "/api/convert/export-materials", json=body).json()
        )
        if not selection["ready"]:
            raise SmokeFailure("原生耗材/打印板仍不兼容")
    generated = step("生成 3MF", lambda: request("POST", "/api/convert/generate", json=body).json())
    package = step("下载 3MF", lambda: request("GET", generated["download_url"]).content)

    def validate() -> None:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            if archive.testzip() is not None:
                raise SmokeFailure("3MF ZIP CRC 校验失败")
            model = ET.fromstring(archive.read("3D/3dmodel.model"))
            if model.tag.rsplit("}", 1)[-1] != "model":
                raise SmokeFailure("3MF model XML 不合法")

    step("校验 ZIP 和 3D/3dmodel.model", validate)
    elapsed = time.perf_counter() - started
    if elapsed > 30:
        raise SmokeFailure(f"总用时 {elapsed:.3f} 秒，超过 30 秒")
    print(f"冒烟通过，总用时：{elapsed:.3f} 秒；3MF：{len(package)} 字节", flush=True)


def main() -> None:
    """可对 HTTP 服务运行，或在隔离副本内用 TestClient 运行。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:18101")
    parser.add_argument("--in-process", action="store_true")
    parser.add_argument("--source", type=Path, help="仅进程内模式：可写隔离副本，绝不能传只读源码")
    args = parser.parse_args()
    started = time.perf_counter()

    def expired(signum: int, frame: object) -> None:
        raise SmokeFailure("全程超过 30 秒")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        if args.in_process:
            if args.source is None:
                parser.error("--in-process 必须指定 --source 隔离副本")
            sys.path.insert(0, str(args.source.resolve()))
            from api.app import app
            from fastapi.testclient import TestClient

            with TestClient(app, base_url="http://testserver") as client:
                run_smoke(client, started)
        else:
            with httpx.Client(
                base_url=args.base_url, trust_env=False, follow_redirects=False
            ) as client:
                run_smoke(client, started)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    try:
        main()
    except (
        SmokeFailure,
        httpx.HTTPError,
        OSError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        ET.ParseError,
    ) as error:
        print(f"冒烟失败：{error}", file=sys.stderr, flush=True)
        raise SystemExit(1) from error
