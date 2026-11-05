import argparse
import json
from pathlib import Path

from . import __version__
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="filament-picker")
    parser.add_argument("--version", action="version", version=f"filament-picker {__version__}")
    sub = parser.add_subparsers(dest="command")
    _add_validate(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)
