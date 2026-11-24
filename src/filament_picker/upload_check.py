"""Validate one upload inside a short-lived process. No network access."""

from __future__ import annotations

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
    import shutil
    import subprocess

    if os.environ.get("FILAMENT_PICKER_STEP", "0") != "1":
        raise SubmissionError(
            "STEP 转换默认关闭。设置 FILAMENT_PICKER_STEP=1 且安装 freecadcmd 后才会尝试。"
        )
    binary = shutil.which("freecadcmd")
    if binary is None:
        raise SubmissionError(
            "STEP 需要本机命令 freecadcmd（FreeCAD）。当前没有安装，转换没有执行。"
        )
    out_dir = root / "accounts" / ".step-out"
    out_dir.mkdir(parents=True, exist_ok=True)
    destination = out_dir / f"{model_id}.stl"
    completed = subprocess.run(
        [binary, str(source), str(destination)],
        timeout=20,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or not destination.is_file():
        raise SubmissionError("freecadcmd 没有产出 STL")
    positions, indices = _parse_stl(destination.read_bytes())
    save_derived_scene(
        root,
        model_id,
        hashlib.sha256(source.read_bytes()).hexdigest(),
        {
            "unit": "millimeter",
            "scope": "overall",
            "parts": [{"positions": positions, "indices": indices}],
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
