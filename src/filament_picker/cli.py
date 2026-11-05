import argparse
import json
from pathlib import Path

from . import __version__
from .ingest import RAW_DIR, SnapshotMismatchError, load_inventory, load_rows, verify_snapshots
from .validate import validate_json


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="filament-picker")
    parser.add_argument("--version", action="version", version=f"filament-picker {__version__}")
    sub = parser.add_subparsers(dest="command")
    _add_validate(sub)
    _add_ingest(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)
