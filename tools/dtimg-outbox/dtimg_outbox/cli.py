"""命令行：put、list-ready、ack、watch。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from dtimg_outbox import __version__
from dtimg_outbox.outbox import (
    OutboxError,
    ack,
    enqueue_image,
    list_ready,
    load_settings,
    watch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dtimg-outbox",
        description="把发件箱里的图片上传到公网，并写成待发记录。不发送钉钉消息。",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--root", default=None, help="发件箱根目录，默认读 DTIMG_OUTBOX")
    parser.add_argument("--put-sh", default=None, help="put.sh 路径，默认读 DTIMG_PUT_SH")
    sub = parser.add_subparsers(dest="cmd", required=True)

    put = sub.add_parser("put", help="把一张图放进 inbox/，等 watcher 上传")
    put.add_argument("image", help="本地图片路径")
    put.add_argument("--to", default=None, help="目标群名或会话名")
    put.add_argument("--text", default=None, help="图片说明")
    put.add_argument("--requested-by", default=None, help="请求方，默认 DTIMG_REQUESTED_BY")

    listing = sub.add_parser("list-ready", help="列出 ready/ 里还没发送的记录")
    listing.add_argument("--json", action="store_true", help="输出 JSON 数组")

    ack_cmd = sub.add_parser("ack", help="钉钉助手确认已发送，把记录移到 sent/")
    ack_cmd.add_argument("id", help="ready/<id>.json 的 id")

    watch_cmd = sub.add_parser("watch", help="扫描 inbox/ 并上传")
    watch_cmd.add_argument("--once", action="store_true", help="只扫一轮就退出")
    watch_cmd.add_argument("--poll", action="store_true", help="不用 inotify，固定间隔轮询")
    watch_cmd.add_argument("--interval", type=float, default=None, help="扫描间隔秒数")
    watch_cmd.add_argument("--max-attempts", type=int, default=None, help="临时失败最多尝试次数")
    watch_cmd.add_argument("--retry-base", type=float, default=None, help="第一次重试前等待的秒数")
    watch_cmd.add_argument("--stable-sec", type=float, default=None, help="文件静止多久才算写完")
    return parser


def format_ready(records: list[dict[str, Any]]) -> str:
    if not records:
        return "没有待发送的图片\n"
    blocks: list[str] = []
    for rec in records:
        blocks.append(
            "\n".join(
                (
                    f"id={rec.get('id', '')}",
                    f"  to={rec.get('to', '')}",
                    f"  text={rec.get('text', '')}",
                    f"  photoURL={rec.get('photoURL', '')}",
                    f"  sha256={rec.get('sha256', '')}",
                    f"  uploaded_at={rec.get('uploaded_at', '')}",
                )
            )
        )
    return "\n".join(blocks) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except OutboxError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130


def _dispatch(args: argparse.Namespace) -> int:
    settings = load_settings(
        root=args.root,
        put_sh=args.put_sh,
        max_attempts=getattr(args, "max_attempts", None),
        retry_base_sec=getattr(args, "retry_base", None),
        stable_sec=getattr(args, "stable_sec", None),
        poll_interval=getattr(args, "interval", None),
    )
    if args.cmd == "put":
        requested = args.requested_by
        if requested is None:
            requested = os.environ.get("DTIMG_REQUESTED_BY") or None
        dest = enqueue_image(
            settings,
            args.image,
            to=args.to,
            text=args.text,
            requested_by=requested,
        )
        print(f"已放入发件箱：{dest}")
        print(f"id={dest.stem}")
        return 0
    if args.cmd == "list-ready":
        records = list_ready(settings)
        if args.json:
            print(json.dumps(records, ensure_ascii=False, indent=2))
            return 0
        sys.stdout.write(format_ready(records))
        return 0
    if args.cmd == "ack":
        dest = ack(settings, args.id)
        print(f"已确认 id={args.id}")
        print(f"sent={dest}")
        return 0
    if args.cmd == "watch":
        report = watch(settings, once=args.once, force_poll=args.poll)
        if report is not None:
            print(f"ready={len(report.ready)} failed={len(report.failed)}")
        return 0
    raise OutboxError(f"未知命令：{args.cmd}", exit_code=2)
