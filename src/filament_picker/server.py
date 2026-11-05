from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import create_app


def build_server_app(
    dist: Path, catalog_path: Path, root: Path, card_base_url: str | None
) -> FastAPI:
    if not dist.is_dir() or not (dist / "index.html").is_file():
        raise RuntimeError("web/dist 不存在，先运行 scripts/build_web.sh")
    app = create_app(catalog_path, root, card_base_url)
    app.mount("/", StaticFiles(directory=dist, html=True))
    return app
