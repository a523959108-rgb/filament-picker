import argparse
import csv
import getpass
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import __version__
from .auth import AuthStore, auth_db_path
from .calibrate import (
    CALIBRATION_PATH,
    EXTRACTED_PATH,
    QA_SAMPLE_PATH,
    calibrate,
    qa_sample,
    run_extract,
    summarize,
)
from .catalog import (
    CATALOG_PATH,
    OVERRIDES_PATH,
    CatalogValidationError,
    build_catalog,
    load_catalog,
    write_catalog,
)
from .config import REPO_ROOT, TZ, get_settings
from .ids import LOCK_PATH, assign_ids, build_row_infos, group_rows, load_lock, write_lock
from .ingest import (
    RAW_DIR,
    SnapshotMismatchError,
    load_inventory,
    load_rows,
    sha256_file,
    verify_snapshots,
)
from .validate import validate_json
from .web_export import DEFAULT_WEB_CATALOG, export_web


def _add_validate(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("validate", help="validate a JSON document")
    parser.add_argument("schema", choices=("catalog", "lock", "request", "result"))
    parser.add_argument("json_file", type=Path)
    parser.set_defaults(handler=_cmd_validate)


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        obj = json.loads(args.json_file.read_text(encoding="utf-8"))
        errors = validate_json(args.schema, obj)
    except (OSError, ValueError, UnicodeError) as exc:
        print(str(exc))
        return 1
    if errors:
        print("\n".join(errors))
        return 1
    print("OK")
    return 0


def _add_ingest(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("ingest", help="verify and summarize raw snapshots")
    parser.set_defaults(handler=_cmd_ingest)


def _cmd_ingest(args: argparse.Namespace) -> int:
    try:
        verify_snapshots()
        rows = load_rows(RAW_DIR / "page_rows.json")
        load_inventory(RAW_DIR / "inventory.json")
    except (OSError, SnapshotMismatchError, ValueError) as exc:
        print(str(exc))
        return 1
    brands = {row.brand for row in rows}
    series = {(row.brand, row.series) for row in rows}
    print(f"rows={len(rows)} brands={len(brands)} series={len(series)}")
    return 0


def _add_assign_ids(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("assign-ids", help="assign stable IDs and update the lock")
    parser.add_argument("--today")
    parser.set_defaults(handler=_cmd_assign_ids)


def _add_build_catalog(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("build-catalog", help="build the filament catalog")
    parser.add_argument("--extracted", type=Path)
    parser.add_argument("--now")
    parser.set_defaults(handler=_cmd_build_catalog)


def _cmd_build_catalog(args: argparse.Namespace) -> int:
    rows_path = RAW_DIR / "page_rows.json"
    inventory_path = RAW_DIR / "inventory.json"
    try:
        verify_snapshots()
        rows = load_rows(rows_path)
        inventory = load_inventory(inventory_path)
        lock = load_lock(LOCK_PATH)
        if lock is None:
            raise CatalogValidationError("ids lock missing; please run assign-ids first")
        overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        source = {
            "page_rows_sha256": sha256_file(rows_path),
            "inventory_sha256": sha256_file(inventory_path),
            "ids_lock_sha256": sha256_file(LOCK_PATH),
        }
        now = args.now or datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")
        extracted = None
        if args.extracted is not None:
            extracted = json.loads(args.extracted.read_text(encoding="utf-8"))
        catalog = build_catalog(rows, lock, inventory, overrides, extracted, now, source)
        write_catalog(CATALOG_PATH, catalog)
    except (OSError, SnapshotMismatchError, RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1
    counts = catalog["counts"]
    print(
        "entries={entries} with_hex={with_hex} official={official} "
        "store_swatch={store_swatch} image_extracted={image_extracted}".format(**counts)
    )
    return 0


def _catalog_now() -> str:
    return datetime.now(ZoneInfo(TZ)).isoformat(timespec="seconds")


def _read_extracted(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _add_extract(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("extract", help="extract colors from product images")
    parser.add_argument("--limit", type=int)
    parser.set_defaults(handler=_cmd_extract)


def _cmd_extract(args: argparse.Namespace) -> int:
    try:
        catalog = load_catalog(CATALOG_PATH)
        extracted = run_extract(catalog, _catalog_now(), args.limit)
        EXTRACTED_PATH.parent.mkdir(parents=True, exist_ok=True)
        EXTRACTED_PATH.write_text(
            json.dumps(extracted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc))
        return 1
    counts = {status: 0 for status in ("ok", "no_foreground", "skipped")}
    for result in extracted["results"].values():
        counts[result["status"]] += 1
    print(f"ok={counts['ok']} no_foreground={counts['no_foreground']} skipped={counts['skipped']}")
    return 0


def _add_calibrate(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("calibrate", help="calibrate extracted colors")
    parser.set_defaults(handler=_cmd_calibrate)


def _cmd_calibrate(args: argparse.Namespace) -> int:
    del args
    try:
        catalog = load_catalog(CATALOG_PATH)
        extracted = _read_extracted(EXTRACTED_PATH)
        rows = calibrate(catalog, extracted)
        CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CALIBRATION_PATH.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "id",
                    "hex_source",
                    "catalog_hex",
                    "extracted_hex",
                    "delta_e",
                    "confidence",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc))
        return 1
    for line in summarize(rows):
        print(line)
    return 0


def _add_qa_sample(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("qa-sample", help="write an HTML QA sample")
    parser.add_argument("--n", type=int, default=50)
    parser.set_defaults(handler=_cmd_qa_sample)


def _add_plan(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("plan", help="plan colors for one image")
    parser.add_argument("image", type=Path)
    parser.add_argument("--note", default="")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "build" / "cli-root")
    parser.set_defaults(handler=_cmd_plan)


def _add_worker(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("worker", help="process inbox requests")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--catalog", type=Path)
    parser.set_defaults(handler=_cmd_worker)


def _add_export_web(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("export-web", help="export the catalog for the web app")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_WEB_CATALOG)
    parser.set_defaults(handler=_cmd_export_web)


def _add_serve(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("serve", help="serve the API and web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--dist", type=Path, default=REPO_ROOT / "web" / "dist")
    parser.set_defaults(handler=_cmd_serve)


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import build_server_app

    settings = get_settings()
    app = build_server_app(args.dist, settings.catalog, settings.root, settings.card_base_url)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _cmd_export_web(args: argparse.Namespace) -> int:
    settings = get_settings()
    catalog_path = args.catalog or settings.catalog
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        exported = export_web(catalog)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(exported, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(str(exc))
        return 1
    print(f"entries={len(exported['entries'])}")
    return 0


def _cmd_worker(args: argparse.Namespace) -> int:
    from .worker import run_worker

    settings = get_settings()
    catalog = args.catalog or settings.catalog
    return run_worker(args.root, catalog, args.once, settings.card_base_url)


def _cmd_plan(args: argparse.Namespace) -> int:
    from .planner import run_plan

    now = datetime.now(ZoneInfo(TZ))
    settings = get_settings()
    request = {
        "schema_version": 1,
        "request_id": f"cli-{now:%Y%m%d%H%M%S}",
        "created_at": now.isoformat(timespec="seconds"),
        "image_paths": [str(args.image.resolve())],
        "note": args.note,
        "constraints": {},
        "context": {},
    }
    try:
        catalog = load_catalog(settings.catalog)
        result = run_plan(
            request,
            catalog,
            args.out,
            lambda: datetime.now(ZoneInfo(TZ)),
            settings.card_base_url,
        )
    except (OSError, CatalogValidationError, ValueError) as exc:
        print(str(exc))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


def _cmd_qa_sample(args: argparse.Namespace) -> int:
    try:
        catalog = load_catalog(CATALOG_PATH)
        extracted = _read_extracted(EXTRACTED_PATH)
        sample = qa_sample(catalog, extracted, args.n)
        QA_SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        QA_SAMPLE_PATH.write_text(sample, encoding="utf-8")
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc))
        return 1
    print("wrote data/qa/sample.html")
    return 0


def _cmd_assign_ids(args: argparse.Namespace) -> int:
    today = args.today or datetime.now(ZoneInfo(TZ)).date().isoformat()
    source = RAW_DIR / "page_rows.json"
    try:
        verify_snapshots()
        rows = load_rows(source)
        groups = group_rows(build_row_infos(rows))
        lock, stats = assign_ids(groups, load_lock(LOCK_PATH), today, sha256_file(source))
        write_lock(LOCK_PATH, lock)
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1
    print(
        f"keys={stats.keys} new={stats.new} retired={stats.retired} collisions={stats.collisions}"
    )
    return 0


def _add_models(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("models", help="import model preview data")
    commands = parser.add_subparsers(dest="models_command", required=True)
    importer = commands.add_parser(
        "import-previews", help="import extracted 3MF plate previews into the model library"
    )
    importer.add_argument("directory", type=Path)
    importer.add_argument("--dry-run", action="store_true", help="print stats without writing")
    importer.set_defaults(handler=_cmd_import_previews)


def _cmd_import_previews(args: argparse.Namespace) -> int:
    from .model_import import import_previews
    from .models import models_root

    try:
        stats = import_previews(args.directory, models_root(), dry_run=args.dry_run)
    except (OSError, ValueError) as exc:
        print(str(exc))
        return 1
    print(stats.format())
    return 0


def _add_auth(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("auth", help="manage the single model-preview account")
    commands = parser.add_subparsers(dest="auth_command", required=True)
    create = commands.add_parser("create-user", help="create an account using interactive getpass")
    create.add_argument("--username", required=True)
    create.set_defaults(handler=_cmd_create_user)
    listing = commands.add_parser("list-users", help="print usernames only")
    listing.set_defaults(handler=_cmd_list_users)


def _cmd_create_user(args: argparse.Namespace) -> int:
    store = AuthStore(auth_db_path())
    try:
        if args.username != "yulanmoxing" or store.list_users():
            raise ValueError("仅允许首次创建单账号 yulanmoxing；不重置密码或追加账号")
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("密码：")
            confirmation = getpass.getpass("再次输入密码：")
        if not password or password != confirmation:
            raise ValueError("密码为空或两次输入不一致")
        store.create_user(args.username, password)
    except (OSError, ValueError, sqlite3.Error, EOFError, getpass.GetPassWarning):
        print("建号失败：请检查交互终端、账号状态及两次密码输入")
        return 1
    print(f"created user: {args.username}")
    return 0


def _cmd_list_users(args: argparse.Namespace) -> int:
    for username in AuthStore(auth_db_path()).list_users():
        print(username)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="filament-picker")
    parser.add_argument("--version", action="version", version=f"filament-picker {__version__}")
    sub = parser.add_subparsers(dest="command")
    _add_validate(sub)
    _add_ingest(sub)
    _add_assign_ids(sub)
    _add_build_catalog(sub)
    _add_extract(sub)
    _add_calibrate(sub)
    _add_qa_sample(sub)
    _add_plan(sub)
    _add_worker(sub)
    _add_export_web(sub)
    _add_serve(sub)
    _add_models(sub)
    _add_auth(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)
