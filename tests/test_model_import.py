from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
from pathlib import Path

import httpx
import pytest
from PIL import Image

from filament_picker.auth import AuthStore
from filament_picker.cli import main
from filament_picker.model_import import import_previews, plain_text
from filament_picker.server import build_server_app

FIXTURES = Path(__file__).parent / "fixtures" / "model_previews"
META_0020 = "0020be7b6727aed7"
META_004A = "004adc13231dfbe7"
META_0059 = "00592de532226d95"
ALIAS_ID = "aa20alias0000001"
FALLBACK_ID = "bb00000000000001"
FALLBACK_ALIAS = "bb00000000000002"
XSS_ID = "ee00000000000001"
BLACK_ID = "ff00000000000001"
MISSING_ID = "cc00000000000001"
FAILED_ID = "dd00000000000001"


def _load_meta(model_id: str) -> dict:
    return json.loads((FIXTURES / f"{model_id}.meta.json").read_text(encoding="utf-8"))


def _write_image(path: Path, color: str, kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (4, 3), color)
    if kind == "jpg":
        image.save(path, format="JPEG")
    else:
        image.save(path, format="PNG")


def _stage(directory: Path, model_id: str, meta: dict, *, extra: tuple[str, ...] = ()) -> None:
    dest = directory / "models" / model_id
    dest.mkdir(parents=True, exist_ok=True)
    meta = dict(meta)
    meta["id"] = model_id
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_image(dest / "thumb_1.jpg", "#336699", "jpg")
    _write_image(dest / "plate_1.png", "#C04040", "png")
    _write_image(dest / "top_1.png", "#4080C0", "png")
    for name in extra:
        _write_image(dest / name, "#101010", "png")
    _write_image(dest / "pick_1.png", "#010101", "png")
    _write_image(dest / "plate_no_light_1.png", "#020202", "png")
    (dest / "ignored.3mf").write_bytes(b"not-a-website-file")
    (dest / "._plate_1.png").write_bytes(b"appledouble")


def _row(model_id: str, meta: dict, **overrides: object) -> dict:
    row = {
        "id": model_id,
        "rel_path": meta["rel_path"],
        "file_name": meta["file_name"],
        "size_bytes": meta["size_bytes"],
        "mtime": meta["mtime"],
        "title": meta["title"],
        "designer": meta["designer"],
        "source": meta["source"],
        "colors": ["#ffffff", "#FFFFFF", "not-a-color"],
        "plates": len(meta["plates"]),
        "ok": True,
        "errors": [],
    }
    row.update(overrides)
    return row


def _synthetic(model_id: str, title: str, designer: str, colors: list[str], source: dict) -> dict:
    return {
        "id": model_id,
        "rel_path": f"1-系列分类/测试/{title}/{model_id}.3mf",
        "file_name": f"{model_id}.3mf",
        "size_bytes": 128,
        "mtime": 1_700_000_000,
        "title": title,
        "designer": designer,
        "source": source,
        "colors": colors,
        "plates": 1,
        "ok": True,
        "errors": [],
    }


def _library(tmp_path: Path) -> Path:
    directory = tmp_path / "incoming"
    directory.mkdir()
    meta_0020 = _load_meta(META_0020)
    meta_004a = _load_meta(META_004A)
    meta_0059 = _load_meta(META_0059)
    _stage(directory, META_0020, meta_0020)
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"secret-png")
    (directory / "models" / META_0020 / "plate_9.png").symlink_to(outside)
    _stage(directory, ALIAS_ID, meta_0020)
    _stage(directory, META_004A, meta_004a)
    _stage(directory, META_0059, meta_0059, extra=("plate_2.png", "top_2.png"))
    fallback_meta = {
        "id": FALLBACK_ID,
        "title": "回退去重模型",
        "designer": "测试作者",
        "source": {"description": "同一份说明"},
        "plates": [{"index": 1, "filaments": [{"hex": "#123456"}]}],
        "extracted_at": "2026-11-07T00:00:00+00:00",
    }
    _stage(directory, FALLBACK_ID, fallback_meta)
    _stage(directory, FALLBACK_ALIAS, fallback_meta)
    xss_meta = {
        "id": XSS_ID,
        "title": "安全标题",
        "designer": "测试作者",
        "source": {"description": "<script>alert(1)</script>"},
        "plates": [],
        "extracted_at": "2026-11-07T00:00:00+00:00",
    }
    _stage(directory, XSS_ID, xss_meta)
    black_meta = {
        "id": BLACK_ID,
        "title": "纯黑试色",
        "designer": "测试作者",
        "source": {"description": "黑色耗材"},
        "plates": [{"index": 1, "filaments": [{"hex": "#000000"}]}],
        "extracted_at": "2026-11-07T00:00:00+00:00",
    }
    _stage(directory, BLACK_ID, black_meta)
    rows = [
        _row(META_0020, meta_0020),
        _row(ALIAS_ID, meta_0020, title="完全不同的标题", designer="另一个人"),
        _row(
            META_004A,
            meta_004a,
            colors=["#161616", "#FFFFFF", "#F95D73", "#FCECD6"],
        ),
        _row(META_0059, meta_0059, colors=[]),
        _synthetic(
            FALLBACK_ID,
            "回退去重模型",
            "测试作者",
            ["#123456"],
            {"description": "同一份说明", "design_model_id": "", "design_profile_id": None},
        ),
        _synthetic(
            FALLBACK_ALIAS,
            "回退去重模型",
            "测试作者",
            ["#123456"],
            {"description": "同一份说明"},
        ),
        _synthetic(
            XSS_ID,
            "安全标题 &lt;b&gt;加粗&lt;/b&gt;",
            "测试作者",
            ["#ABCDEF"],
            {
                "description": (
                    "&lt;script&gt;alert(1)&lt;/script&gt;&lt;img src=x onerror=alert(1)&gt;"
                )
            },
        ),
        _synthetic(BLACK_ID, "纯黑试色", "测试作者", ["#000000"], {"description": "黑色耗材"}),
        _synthetic(MISSING_ID, "缺文件", "测试作者", ["#010203"], {"description": "没有目录"}),
        {
            "id": FAILED_ID,
            "rel_path": "bad/failed.3mf",
            "file_name": "failed.3mf",
            "size_bytes": 1,
            "mtime": 1,
            "title": "失败件",
            "designer": "",
            "source": {},
            "colors": [],
            "plates": 0,
            "ok": False,
            "errors": ["boom"],
        },
        "{",
        _row(META_0020, meta_0020),
    ]
    lines = [row if isinstance(row, str) else json.dumps(row, ensure_ascii=False) for row in rows]
    (directory / "index.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return directory


def _parse_stats(text: str) -> dict[str, int]:
    return {key: int(value) for key, value in (part.split("=") for part in text.split())}


def _request(app, method: str, path: str, cookie: str = "", **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.request(method, path, headers={"cookie": cookie}, **kwargs)

    return asyncio.run(send())


def test_plain_text_decodes_sample_markup_and_drops_script() -> None:
    meta = _load_meta(META_0020)
    text = plain_text(meta["source"]["description"])
    assert "无需AMS" in text
    assert "为我助力" in text
    assert "感谢各位老铁" in text
    assert "<" not in text and ">" not in text
    profile = plain_text(meta["model_metadata"]["ProfileDescription"])
    assert "zimomo大首领，带尾巴" in profile
    assert "点击此处转到Zimomo背鳍小牙下载链接" in profile
    assert "https://" not in profile
    encoded = "&lt;script&gt;alert(1)&lt;/script&gt;&lt;img src=x onerror=alert(1)&gt;"
    assert plain_text(encoded) == ""
    assert plain_text("安全标题 &lt;b&gt;加粗&lt;/b&gt;") == "安全标题 加粗"


def test_dry_run_reports_duplicates_without_writing(tmp_path: Path) -> None:
    directory = _library(tmp_path)
    root = tmp_path / "models-private"
    stats = import_previews(directory, root, dry_run=True)
    parsed = _parse_stats(stats.format())
    assert parsed == {
        "lines": 12,
        "groups": 7,
        "canonical": 6,
        "aliases": 2,
        "duplicate_groups": 2,
        "duplicate_rows": 2,
        "skipped_missing": 1,
        "skipped_failed": 1,
        "skipped_invalid": 1,
        "skipped_duplicate_id": 1,
        "inserted": 6,
        "updated": 0,
        "unchanged": 0,
        "images": 20,
        "dry_run": 1,
    }
    assert not root.exists()


def test_import_copies_previews_dedupes_and_strips_html(tmp_path: Path) -> None:
    directory = _library(tmp_path)
    root = tmp_path / "models-private"
    stats = _parse_stats(import_previews(directory, root).format())
    assert stats["canonical"] == 6
    assert stats["aliases"] == 2
    assert stats["images"] == 20
    assert stats["dry_run"] == 0
    with sqlite3.connect(root / "manifest.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        ids = [row["id"] for row in conn.execute("SELECT id FROM models ORDER BY id")]
        assert ids == sorted([META_0020, META_004A, META_0059, FALLBACK_ID, XSS_ID, BLACK_ID])
        aliases = conn.execute(
            "SELECT alias_id, model_id FROM model_aliases ORDER BY alias_id"
        ).fetchall()
        assert [(row["alias_id"], row["model_id"]) for row in aliases] == [
            (ALIAS_ID, META_0020),
            (FALLBACK_ALIAS, FALLBACK_ID),
        ]
        kept = conn.execute("SELECT * FROM models WHERE id = ?", (META_0020,)).fetchone()
        assert kept["created_at"] == "2026-11-07T11:38:00+09:00"
        assert json.loads(kept["colours"]) == ["#FFFFFF"]
        assert "无需AMS" in kept["description"]
        assert "zimomo大首领，带尾巴" in kept["description"]
        assert "<" not in kept["description"]
        assert "1-系列分类" not in kept["description"]
        multi = conn.execute("SELECT colours FROM models WHERE id = ?", (META_0059,)).fetchone()
        assert json.loads(multi["colours"]) == ["#F7E6DE", "#F73CA0", "#FFFFFF", "#0086D6"]
        xss = conn.execute(
            "SELECT title, description FROM models WHERE id = ?", (XSS_ID,)
        ).fetchone()
        assert xss["title"] == "安全标题 加粗"
        assert "<" not in xss["description"]
        assert "onerror" not in xss["description"]
        assert "alert" not in xss["description"]
    assert (root / "thumbs" / f"{META_0020}.jpg").is_file()
    assert (root / "images" / META_0020 / "plate_1.png").is_file()
    assert (root / "images" / META_0020 / "top_1.png").is_file()
    assert not (root / "images" / META_0020 / "plate_9.png").exists()
    assert not (root / "images" / ALIAS_ID).exists()
    assert not (root / "thumbs" / f"{ALIAS_ID}.jpg").exists()
    assert (root / "images" / META_0059 / "plate_2.png").is_file()
    assert (root / "images" / META_0059 / "top_2.png").is_file()
    assert list(root.rglob("*.3mf")) == []
    assert list(root.rglob("pick_*")) == []
    assert list(root.rglob("plate_no_light_*")) == []
    assert list(root.rglob("._*")) == []
    assert b"secret-png" not in (root / "images" / META_0020 / "plate_1.png").read_bytes()


def test_reimport_updates_by_id_and_dry_run_does_not_touch_files(tmp_path: Path) -> None:
    directory = _library(tmp_path)
    root = tmp_path / "models-private"
    import_previews(directory, root)
    with sqlite3.connect(root / "manifest.sqlite") as conn:
        created = conn.execute(
            "SELECT created_at FROM models WHERE id = ?", (META_004A,)
        ).fetchone()[0]
    lines = (directory / "index.jsonl").read_text(encoding="utf-8").splitlines()
    rewritten = []
    for line in lines:
        if line == "{":
            rewritten.append(line)
            continue
        row = json.loads(line)
        if row.get("id") == META_004A:
            row["title"] = "更新后的标题"
        rewritten.append(json.dumps(row, ensure_ascii=False))
    (directory / "index.jsonl").write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    updated = _parse_stats(import_previews(directory, root).format())
    assert updated["inserted"] == 0
    assert updated["updated"] == 1
    assert updated["unchanged"] == 5
    assert updated["canonical"] == 6
    thumb = root / "thumbs" / f"{META_0020}.jpg"
    manifest = root / "manifest.sqlite"
    before = (thumb.stat().st_mtime_ns, manifest.stat().st_mtime_ns)
    dry = _parse_stats(import_previews(directory, root, dry_run=True).format())
    assert dry["inserted"] == 0
    assert dry["updated"] == 0
    assert dry["unchanged"] == 6
    assert dry["dry_run"] == 1
    assert (thumb.stat().st_mtime_ns, manifest.stat().st_mtime_ns) == before
    with sqlite3.connect(root / "manifest.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT title, created_at FROM models WHERE id = ?", (META_004A,)
        ).fetchone()
        assert row["title"] == "更新后的标题"
        assert row["created_at"] == created
        assert conn.execute("SELECT COUNT(*) FROM models").fetchone()[0] == 6


def test_smaller_id_replaces_previous_canonical(tmp_path: Path) -> None:
    directory = tmp_path / "incoming"
    root = tmp_path / "models-private"
    meta = _load_meta(META_0020)
    _stage(directory, ALIAS_ID, meta)
    row = _row(ALIAS_ID, meta)
    (directory / "index.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    import_previews(directory, root)
    _stage(directory, META_0020, meta)
    both = [_row(META_0020, meta), row]
    (directory / "index.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in both) + "\n", encoding="utf-8"
    )
    stats = _parse_stats(import_previews(directory, root).format())
    assert stats["canonical"] == 1
    assert stats["aliases"] == 1
    with sqlite3.connect(root / "manifest.sqlite") as conn:
        ids = [item[0] for item in conn.execute("SELECT id FROM models")]
        assert ids == [META_0020]
        alias = conn.execute(
            "SELECT model_id FROM model_aliases WHERE alias_id = ?", (ALIAS_ID,)
        ).fetchone()
        assert alias[0] == META_0020
    assert not (root / "thumbs" / f"{ALIAS_ID}.jpg").exists()
    assert (root / "thumbs" / f"{META_0020}.jpg").is_file()


def test_cli_dry_run_and_refuses_overlapping_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _library(tmp_path)
    root = tmp_path / "models-private"
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_ROOT", str(root))
    assert main(["models", "import-previews", str(directory), "--dry-run"]) == 0
    parsed = _parse_stats(capsys.readouterr().out.strip())
    assert parsed["dry_run"] == 1
    assert parsed["canonical"] == 6
    assert parsed["aliases"] == 2
    assert not root.exists()
    assert main(["models", "import-previews", str(tmp_path / "missing")]) == 1
    nested = directory / "nested-root"
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_ROOT", str(nested))
    assert main(["models", "import-previews", str(directory), "--dry-run"]) == 1


def test_detail_uses_thumb_plate_top_and_catalog_match(
    tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _library(tmp_path)
    root = tmp_path / "models-private"
    import_previews(directory, root)
    db = tmp_path / "auth" / "users.sqlite"
    monkeypatch.setenv("FILAMENT_PICKER_AUTH_DB", str(db))
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_ROOT", str(root))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("FILAMENT_PICKER_SESSION_SECURE", "0")
    monkeypatch.setenv("FILAMENT_PICKER_MODELS_DIRECT", "1")
    password = secrets.token_urlsafe(24)
    AuthStore(db).create_user("yulanmoxing", password)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>\n', encoding="utf-8")
    app = build_server_app(
        dist, repo_root / "docs/schemas/examples/filament-catalog.example.json", tmp_path, None
    )
    login = _request(
        app, "POST", "/api/models/login", json={"username": "yulanmoxing", "password": password}
    )
    cookie = login.headers["set-cookie"].split(";", 1)[0]
    listing = _request(app, "GET", "/api/models?page_size=100", cookie).json()
    assert {item["id"] for item in listing["items"]} == {
        META_0020,
        META_004A,
        META_0059,
        FALLBACK_ID,
        XSS_ID,
        BLACK_ID,
    }
    detail = _request(app, "GET", f"/api/models/{META_0020}", cookie)
    body = detail.json()
    assert detail.status_code == 200
    assert "source_relpath" not in body
    assert "1-系列分类" not in detail.text
    assert "<" not in body["description"]
    assert "无需AMS" in body["description"]
    assert [item["url"] for item in body["images"]] == [
        f"/api/models/{META_0020}/media/plate_1.png",
        f"/api/models/{META_0020}/media/top_1.png",
    ]
    assert body["thumb_url"] == f"/api/models/{META_0020}/thumb"
    thumb = _request(app, "GET", body["thumb_url"], cookie)
    assert thumb.status_code == 200
    assert thumb.headers["content-type"].startswith("image/jpeg")
    assert thumb.content == (root / "thumbs" / f"{META_0020}.jpg").read_bytes()
    plate = _request(app, "GET", body["images"][0]["url"], cookie)
    assert plate.status_code == 200
    assert plate.headers["content-type"].startswith("image/png")
    assert plate.content == (root / "images" / META_0020 / "plate_1.png").read_bytes()
    hidden = (
        f"/api/models/{META_0020}/media/plate_9.png",
        f"/api/models/{META_0020}/media/pick_1.png",
        f"/api/models/{META_0020}/media/..%2Fmanifest.sqlite",
    )
    assert all(_request(app, "GET", path, cookie).status_code == 404 for path in hidden)
    black = _request(app, "GET", f"/api/models/{BLACK_ID}", cookie).json()
    picks = black["colour_matches"][0]["picks"]
    assert black["colour_matches"][0]["hex"] == "#000000"
    assert picks[0]["id"] == "bambu-lab/petg-basic/black-30105"
    assert picks[0]["brand_name"] == "Bambu Lab"
    assert picks[0]["label"] == "几乎一样"
    assert picks[0]["delta_e"] <= 2
    assert _request(app, "GET", f"/api/models/{META_0020}/media/plate_1.png").status_code == 401
