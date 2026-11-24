"""Validate one upload inside a short-lived process. No network access."""

from __future__ import annotations

import contextlib
import hashlib
import sys
from pathlib import Path

from .mesh_derive import DeriveError, derive_file, save_derived_scene
from .submissions import SubmissionError, _parse_stl, _reject_zip_bomb


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 5:
        print("参数无效", file=sys.stderr)
        return 2
    suffix, source_text, root_text, model_id, content_sha = args
    source = Path(source_text)
    root = Path(root_text)
    try:
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != content_sha:
            raise SubmissionError("内容和记录的校验不一致")
        if suffix == ".3mf":
            if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                raise SubmissionError("3MF 含有 DTD")
            _reject_zip_bomb(data)
            derive_file(root, model_id, source, force=True)
        elif suffix == ".stl":
            positions, indices = _parse_stl(data)
            save_derived_scene(
                root,
                model_id,
                content_sha,
                {
                    "unit": "millimeter",
                    "scope": "overall",
                    "parts": [{"positions": positions, "indices": indices}],
                },
            )
        elif suffix in {".step", ".stp"}:
            _convert_step(source, root, model_id)
        else:
            raise SubmissionError("不支持的格式")
    except (SubmissionError, DeriveError) as exc:
        print(exc.detail, file=sys.stderr)
        return 1
    except OSError:
        print("处理失败", file=sys.stderr)
        return 1
    print("ok")
    return 0


def _convert_step(source: Path, root: Path, model_id: str) -> None:
    import os
    import signal
    import subprocess

    if os.environ.get("FILAMENT_PICKER_STEP", "0") != "1":
        raise SubmissionError(
            "STEP 转换默认关闭。需要 FILAMENT_PICKER_STEP=1，以及 occt-draw 或 freecadcmd。"
            "缺命令时的拒绝不是已经执行的转换。"
        )
    payload = source.read_bytes()
    lowered = payload.lower()
    if b"://" in lowered or b"file:" in lowered or b"\\\\" in payload:
        raise SubmissionError("STEP 含有外部地址，不会自动抓取")
    if not payload.lstrip().startswith(b"ISO-10303-21"):
        raise SubmissionError("不是 STEP 文件，没有按扩展名解析")
    out_dir = (root / "accounts" / ".step-out").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    destination = (out_dir / f"{model_id}.stl").resolve()
    source_ok = _safe_converter_path(source)
    dest_ok = _safe_converter_path(destination) and destination.parent == out_dir
    if not source_ok or not dest_ok:
        raise SubmissionError("STEP 输出路径不安全")
    command = _converter_command(source.resolve(), destination)
    timeout = float(os.environ.get("FILAMENT_PICKER_STEP_TIMEOUT", "20"))
    proc = subprocess.Popen(
        command,
        cwd=out_dir,
        env=_converter_env(),
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=_converter_limits,
    )
    try:
        _stdout, _stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise SubmissionError("STEP 转换超时，已停止该进程") from None
    max_stl = int(os.environ.get("FILAMENT_PICKER_STEP_MAX_STL", str(32 * 1024 * 1024)))
    if proc.returncode != 0 or not destination.is_file() or destination.stat().st_size > max_stl:
        destination.unlink(missing_ok=True)
        raise SubmissionError("STEP 转换没有产出可用的 STL")
    try:
        positions, indices = _parse_stl(destination.read_bytes())
    finally:
        destination.unlink(missing_ok=True)
    save_derived_scene(
        root,
        model_id,
        hashlib.sha256(payload).hexdigest(),
        {
            "unit": "millimeter",
            "scope": "overall",
            "parts": [{"positions": positions, "indices": indices}],
        },
    )


def _safe_converter_path(path: Path) -> bool:
    text = str(path)
    return bool(text) and not any(char in text for char in " \t\n;$'\"\\`")


def _converter_command(source: Path, destination: Path) -> list[str]:
    import shutil

    freecad = shutil.which("freecadcmd")
    if freecad is not None:
        script = Path(__file__).with_name("freecad_step.py")
        return [freecad, str(script), str(source), str(destination)]
    draw = shutil.which("occt-draw")
    if draw is None:
        raise SubmissionError(
            "STEP 转换器没有安装。Ubuntu 24.04 用 apt 安装 occt-draw 和 libocct-draw-dev；"
            "freecadcmd 可用时优先调用它。转换没有执行。"
        )
    return [
        draw,
        "-b",
        "-c",
        f"pload ALL; testreadstep {source} shape; incmesh shape 0.1; writestl shape {destination}",
    ]


def _converter_env() -> dict[str, str]:
    import os

    blocked = {"http_proxy", "https_proxy", "all_proxy", "ftp_proxy", "no_proxy"}
    return {key: value for key, value in os.environ.items() if key.lower() not in blocked}


def _converter_limits() -> None:
    import os
    import resource

    cpu = int(os.environ.get("FILAMENT_PICKER_STEP_CPU", "20"))
    fsize = int(os.environ.get("FILAMENT_PICKER_STEP_FSIZE", str(32 * 1024 * 1024)))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))


if __name__ == "__main__":
    raise SystemExit(main())
