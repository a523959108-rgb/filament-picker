"""扫描 inbox/，调用 put.sh，把 photoURL 写进 ready/。

不连接钉钉，不发送消息。钉钉助手只读 ready/，发送成功后调用 ack。
"""

from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import logging
import os
import select
import shutil
import signal
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TOKYO = ZoneInfo("Asia/Tokyo")
ALLOWED_EXT = frozenset({"jpg", "jpeg", "png", "gif", "webp", "bmp"})
DEFAULT_ROOT = "/home/box/agent-data/shared/dingtalk-outbox"
DEFAULT_PUT_SH = "/home/box/agent-data/shared/dingtalk-media/put.sh"
DEFAULT_MAX_BYTES = 10_485_760
TEMP_SUFFIXES = (".tmp", ".temp", ".partial", ".part", ".swp", ".swx", "~")
RETRY_CAP_SEC = 60.0
PUT_TIMEOUT_SEC = 120.0
LOG = logging.getLogger("dtimg_outbox")

IN_NONBLOCK = 0x00000800
IN_CLOEXEC = 0x00080000
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100


class OutboxError(Exception):
    """操作失败。permanent=False 表示还可以重试。"""

    def __init__(self, message: str, *, permanent: bool = True, exit_code: int = 1) -> None:
        super().__init__(message)
        self.permanent = permanent
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class Settings:
    root: Path
    put_sh: Path
    max_bytes: int = DEFAULT_MAX_BYTES
    max_attempts: int = 3
    retry_base_sec: float = 2.0
    retry_cap_sec: float = RETRY_CAP_SEC
    stable_sec: float = 1.0
    poll_interval: float = 2.0
    put_timeout: float = PUT_TIMEOUT_SEC
    log_path: Path | None = None

    @property
    def inbox(self) -> Path:
        return self.root / "inbox"

    @property
    def ready(self) -> Path:
        return self.root / "ready"

    @property
    def done(self) -> Path:
        return self.root / "done"

    @property
    def failed(self) -> Path:
        return self.root / "failed"

    @property
    def sent(self) -> Path:
        return self.root / "sent"

    @property
    def state(self) -> Path:
        return self.root / "state"

    @property
    def log_file(self) -> Path:
        if self.log_path is not None:
            return self.log_path
        return self.root / "log" / "dtimg-outbox.log"


@dataclass(frozen=True, slots=True)
class ProcessReport:
    ready: tuple[str, ...]
    failed: tuple[str, ...]
    skipped: tuple[str, ...]


class TokyoFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        moment = datetime.fromtimestamp(record.created, TOKYO)
        return moment.isoformat(timespec="seconds")


def one_line(text: str) -> str:
    return " ".join(text.split())


def isoformat_tokyo(moment: datetime) -> str:
    zoned = moment.replace(tzinfo=TOKYO) if moment.tzinfo is None else moment.astimezone(TOKYO)
    return zoned.isoformat(timespec="seconds")


def configure_logging(path: Path) -> None:
    LOG.setLevel(logging.INFO)
    LOG.propagate = False
    for handler in list(LOG.handlers):
        handler.close()
        LOG.removeHandler(handler)
    path.parent.mkdir(parents=True, exist_ok=True)
    formatter = TokyoFormatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(
        path,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    LOG.addHandler(file_handler)
    LOG.addHandler(stream)


def ensure_dirs(settings: Settings) -> None:
    for name in ("inbox", "ready", "done", "failed", "sent", "state", "log"):
        (settings.root / name).mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(blob)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        broken = path.with_name(f"{path.name}.broken")
        os.replace(path, broken)
        LOG.error("state broken, moved aside name=%s", path.name)
        return {}
    if not isinstance(data, dict):
        broken = path.with_name(f"{path.name}.broken")
        os.replace(path, broken)
        LOG.error("state not an object, moved aside name=%s", path.name)
        return {}
    return data


def extension_of(path: Path) -> str:
    suffix = path.suffix
    if not suffix:
        return ""
    return suffix[1:].lower()


def is_temp_name(name: str) -> bool:
    if not name or name.startswith("."):
        return True
    return name.lower().endswith(TEMP_SUFFIXES)


def assert_safe_id(item_id: str) -> None:
    if item_id in {"", ".", ".."} or item_id.startswith("."):
        raise OutboxError("id 不合法", exit_code=2)
    if any(char in item_id for char in "/\\\x00"):
        raise OutboxError("id 不合法", exit_code=2)
    if any(ord(char) < 32 for char in item_id):
        raise OutboxError("id 不合法", exit_code=2)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_image(path: Path, max_bytes: int) -> None:
    if is_temp_name(path.name):
        raise OutboxError(f"文件名看起来像临时文件：{path.name}", exit_code=2)
    if path.is_symlink():
        raise OutboxError(f"拒绝符号链接：{path.name}", exit_code=2)
    if not path.is_file():
        raise OutboxError(f"不是普通文件：{path.name}", exit_code=2)
    ext = extension_of(path)
    if ext not in ALLOWED_EXT:
        shown = f".{ext}" if ext else "(无)"
        raise OutboxError(
            f"不支持的扩展名 {shown}（仅限 jpg/jpeg/png/gif/webp/bmp）",
            exit_code=2,
        )
    try:
        size = path.stat(follow_symlinks=False).st_size
    except OSError as exc:
        raise OutboxError(f"无法读取文件：{path.name}", exit_code=2) from exc
    if size <= 0:
        raise OutboxError(f"空文件：{path.name}", exit_code=2)
    if size > max_bytes:
        raise OutboxError(f"文件过大：{size} 字节（上限 {max_bytes}）", exit_code=2)


def parse_https_url(stdout: str) -> str | None:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    url = lines[-1]
    if url.startswith("https://") and not any(char.isspace() for char in url):
        return url
    return None


def run_put(settings: Settings, image: Path) -> str:
    script = settings.put_sh
    if not script.is_file():
        raise OutboxError(f"找不到 put.sh：{script}", permanent=False)
    if not os.access(script, os.X_OK):
        raise OutboxError(f"put.sh 不可执行：{script}", permanent=False)
    try:
        completed = subprocess.run(
            [str(script), str(image)],
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.put_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise OutboxError("put.sh 超时", permanent=False) from exc
    except OSError as exc:
        raise OutboxError(f"无法执行 put.sh：{exc}", permanent=False) from exc
    if completed.returncode != 0:
        detail = one_line(completed.stderr or completed.stdout or "")
        message = f"put.sh 退出码 {completed.returncode}"
        if detail:
            message = f"{message}：{detail}"
        raise OutboxError(message, permanent=completed.returncode == 2)
    url = parse_https_url(completed.stdout)
    if url is None:
        raise OutboxError("put.sh 成功退出但没有输出 https URL", permanent=True)
    return url


def _env_int(explicit: int | None, env_name: str, default: int) -> int:
    if explicit is not None:
        return explicit
    raw = os.environ.get(env_name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise OutboxError(f"环境变量 {env_name} 不是整数：{raw}", exit_code=2) from exc


def _env_float(explicit: float | None, env_name: str, default: float) -> float:
    if explicit is not None:
        return explicit
    raw = os.environ.get(env_name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise OutboxError(f"环境变量 {env_name} 不是数字：{raw}", exit_code=2) from exc


def load_settings(
    *,
    root: str | None = None,
    put_sh: str | None = None,
    max_bytes: int | None = None,
    max_attempts: int | None = None,
    retry_base_sec: float | None = None,
    stable_sec: float | None = None,
    poll_interval: float | None = None,
    log_path: str | None = None,
) -> Settings:
    root_text = root if root is not None else os.environ.get("DTIMG_OUTBOX", DEFAULT_ROOT)
    put_text = put_sh if put_sh is not None else os.environ.get("DTIMG_PUT_SH", DEFAULT_PUT_SH)
    log_text = log_path if log_path is not None else os.environ.get("DTIMG_LOG_PATH")
    settings = Settings(
        root=Path(root_text).expanduser(),
        put_sh=Path(put_text).expanduser(),
        max_bytes=_env_int(max_bytes, "DTIMG_MAX_BYTES", DEFAULT_MAX_BYTES),
        max_attempts=_env_int(max_attempts, "DTIMG_MAX_ATTEMPTS", 3),
        retry_base_sec=_env_float(retry_base_sec, "DTIMG_RETRY_BASE_SEC", 2.0),
        stable_sec=_env_float(stable_sec, "DTIMG_STABLE_SEC", 1.0),
        poll_interval=_env_float(poll_interval, "DTIMG_POLL_INTERVAL", 2.0),
        log_path=Path(log_text).expanduser() if log_text else None,
    )
    if settings.max_bytes < 1 or settings.max_attempts < 1:
        raise OutboxError("大小上限和重试次数必须 >= 1", exit_code=2)
    if settings.retry_base_sec < 0 or settings.stable_sec < 0:
        raise OutboxError("重试间隔和稳定等待不能为负数", exit_code=2)
    if settings.poll_interval <= 0:
        raise OutboxError("扫描间隔必须 > 0", exit_code=2)
    return settings


@contextmanager
def watcher_lock(settings: Settings) -> Iterator[None]:
    ensure_dirs(settings)
    handle = (settings.state / "watcher.lock").open("a", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise OutboxError("另一个 dtimg-outbox 正在运行") from exc
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _observed_path(settings: Settings) -> Path:
    return settings.state / "observed.json"


def _index_path(settings: Settings) -> Path:
    return settings.state / "sha256.json"


def _attempts_path(settings: Settings) -> Path:
    return settings.state / "attempts.json"


def settle(settings: Settings, path: Path, observed: dict[str, Any], now_ts: float) -> str:
    """返回 ready、skip 或 empty。会更新 observed。"""
    try:
        stat = path.stat(follow_symlinks=False)
    except OSError:
        return "skip"
    previous = observed.get(path.name)
    previous_size = previous.get("size") if isinstance(previous, dict) else None
    observed[path.name] = {"size": int(stat.st_size)}
    if stat.st_size <= 0:
        if settings.stable_sec > 0 and now_ts - stat.st_mtime < settings.stable_sec:
            return "skip"
        return "empty"
    if settings.stable_sec <= 0:
        return "ready"
    if now_ts - stat.st_mtime < settings.stable_sec:
        return "skip"
    if previous_size is not None and previous_size != stat.st_size:
        return "skip"
    return "ready"


def sidecar_for(image: Path) -> Path:
    return image.with_suffix(".json")


def sidecar_pending(
    settings: Settings,
    image: Path,
    observed: dict[str, Any],
    now_ts: float,
) -> bool:
    stem = image.stem
    inbox = image.parent
    pending_names = (
        f".{stem}.json",
        f".{stem}.json.partial",
        f".{stem}.json.tmp",
        f".{stem}.json.temp",
        f"{stem}.json.tmp",
        f"{stem}.json.temp",
        f"{stem}.json.partial",
        f"{stem}.json.part",
    )
    if any((inbox / name).exists() for name in pending_names):
        return True
    side = sidecar_for(image)
    if not side.exists():
        return False
    return settle(settings, side, observed, now_ts) == "skip"


def classify(path: Path) -> str:
    if is_temp_name(path.name):
        return "temp"
    if path.is_symlink():
        return "symlink"
    ext = extension_of(path)
    if ext == "json":
        return "sidecar"
    if ext in ALLOWED_EXT:
        return "image"
    return "other"


def failure_id(path: Path) -> str:
    try:
        assert_safe_id(path.stem)
    except OutboxError:
        return "invalid"
    return path.stem


def load_sidecar(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OutboxError(f"sidecar 不是合法 JSON：{path.name}") from exc
    except OSError as exc:
        raise OutboxError(f"无法读取 sidecar：{path.name}") from exc
    if not isinstance(data, dict):
        raise OutboxError(f"sidecar 必须是 JSON 对象：{path.name}")
    return data


def choose_id(stem: str, digest: str, source_name: str, settings: Settings) -> str:
    assert_safe_id(stem)
    candidates = (stem, f"{stem}-{digest[:8]}")
    for candidate in candidates:
        assert_safe_id(candidate)
        ready = settings.ready / f"{candidate}.json"
        if not ready.exists():
            return candidate
        try:
            existing = json.loads(ready.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if (
            isinstance(existing, dict)
            and existing.get("sha256") == digest
            and existing.get("source_name") == source_name
        ):
            return candidate
    raise OutboxError(f"ready 里已经有同名记录：{stem}")


def unique_dest(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    for number in range(1, 1000):
        candidate = directory / f"{stem}-{number}{suffix}"
        if not candidate.exists():
            return candidate
    raise OutboxError(f"目标目录里没有可用文件名：{name}")


def move_into(src: Path, directory: Path) -> None:
    if not src.exists():
        return
    directory.mkdir(parents=True, exist_ok=True)
    shutil.move(src, unique_dest(directory, src.name))


def move_pair(image: Path, side: Path, directory: Path) -> None:
    move_into(image, directory)
    if side.exists():
        move_into(side, directory)


def clear_attempt(settings: Settings, item_id: str) -> None:
    path = _attempts_path(settings)
    data = read_state(path)
    if item_id not in data:
        return
    del data[item_id]
    write_json(path, data)


def attempt_row(settings: Settings, item_id: str) -> dict[str, Any]:
    raw = read_state(_attempts_path(settings)).get(item_id, {})
    return raw if isinstance(raw, dict) else {}


def attempt_count(row: dict[str, Any]) -> int:
    try:
        return int(row.get("attempts") or 0)
    except (TypeError, ValueError):
        return 0


def retry_due(row: dict[str, Any], now: datetime) -> bool:
    raw = row.get("next_retry_at")
    if not isinstance(raw, str) or not raw:
        return True
    try:
        nxt = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=TOKYO)
    return nxt <= now


def save_attempt(
    settings: Settings,
    item_id: str,
    attempts: int,
    error: str,
    next_at: str,
) -> None:
    path = _attempts_path(settings)
    data = read_state(path)
    data[item_id] = {
        "attempts": attempts,
        "last_error": one_line(error),
        "next_retry_at": next_at,
    }
    write_json(path, data)


def fail_item(
    settings: Settings,
    image: Path,
    item_id: str,
    message: str,
    *,
    attempts: int,
    now: datetime,
    meta: dict[str, Any],
    digest: str | None,
) -> None:
    payload = {
        "id": item_id,
        "source_name": image.name,
        "sha256": digest,
        "error": one_line(message),
        "attempts": attempts,
        "failed_at": isoformat_tokyo(now),
        "sidecar": meta,
    }
    write_json(settings.failed / f"{item_id}.error.json", payload)
    move_pair(image, sidecar_for(image), settings.failed)
    clear_attempt(settings, item_id)
    LOG.error("failed id=%s error=%s", item_id, one_line(message))


def resolve_url(
    settings: Settings,
    image: Path,
    digest: str,
    size: int,
    uploaded_at: str,
) -> tuple[str, bool]:
    path = _index_path(settings)
    index = read_state(path)
    hit = index.get(digest)
    if isinstance(hit, dict) and isinstance(hit.get("photoURL"), str):
        return hit["photoURL"], True
    url = run_put(settings, image)
    index[digest] = {"photoURL": url, "uploaded_at": uploaded_at, "size_bytes": size}
    write_json(path, index)
    return url, False


def _schedule_retry(
    settings: Settings,
    image: Path,
    item_id: str,
    exc: OutboxError,
    *,
    attempts: int,
    now: datetime,
    meta: dict[str, Any],
    digest: str,
) -> str:
    used = attempts + 1
    if used >= settings.max_attempts:
        fail_item(
            settings,
            image,
            item_id,
            str(exc),
            attempts=used,
            now=now,
            meta=meta,
            digest=digest,
        )
        return "failed"
    delay = min(settings.retry_cap_sec, settings.retry_base_sec * (2 ** (used - 1)))
    next_at = isoformat_tokyo(now + timedelta(seconds=delay))
    save_attempt(settings, item_id, used, str(exc), next_at)
    LOG.warning(
        "retry id=%s attempt=%s/%s error=%s next=%s",
        item_id,
        used,
        settings.max_attempts,
        one_line(str(exc)),
        next_at,
    )
    return "skipped"


def handle_image(
    settings: Settings,
    path: Path,
    observed: dict[str, Any],
    now: datetime,
    now_ts: float,
) -> tuple[str, str | None]:
    if sidecar_pending(settings, path, observed, now_ts):
        return "skipped", None
    side = sidecar_for(path)
    meta: dict[str, Any] = {}
    if side.exists():
        try:
            meta = load_sidecar(side)
        except OutboxError as exc:
            item_id = failure_id(path)
            fail_item(
                settings,
                path,
                item_id,
                str(exc),
                attempts=0,
                now=now,
                meta={},
                digest=None,
            )
            return "failed", item_id
    try:
        validate_image(path, settings.max_bytes)
        digest = file_sha256(path)
        size = path.stat(follow_symlinks=False).st_size
    except OutboxError as exc:
        item_id = failure_id(path)
        fail_item(
            settings,
            path,
            item_id,
            str(exc),
            attempts=0,
            now=now,
            meta=meta,
            digest=None,
        )
        return "failed", item_id
    except OSError as exc:
        item_id = failure_id(path)
        fail_item(
            settings,
            path,
            item_id,
            f"无法读取文件：{exc}",
            attempts=0,
            now=now,
            meta=meta,
            digest=None,
        )
        return "failed", item_id

    try:
        item_id = choose_id(path.stem, digest, path.name, settings)
    except OutboxError as exc:
        item_id = failure_id(path)
        fail_item(
            settings,
            path,
            item_id,
            str(exc),
            attempts=0,
            now=now,
            meta=meta,
            digest=digest,
        )
        return "failed", item_id

    ready_path = settings.ready / f"{item_id}.json"
    if ready_path.is_file():
        try:
            existing = json.loads(ready_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if (
            isinstance(existing, dict)
            and existing.get("sha256") == digest
            and existing.get("source_name") == path.name
        ):
            move_pair(path, side, settings.done)
            clear_attempt(settings, item_id)
            LOG.info("replay id=%s", item_id)
            return "ready", item_id

    row = attempt_row(settings, item_id)
    attempts = attempt_count(row)
    if not retry_due(row, now):
        return "skipped", item_id

    uploaded_at = isoformat_tokyo(now)
    try:
        url, deduped = resolve_url(settings, path, digest, size, uploaded_at)
    except OutboxError as exc:
        if exc.permanent:
            fail_item(
                settings,
                path,
                item_id,
                str(exc),
                attempts=attempts + 1,
                now=now,
                meta=meta,
                digest=digest,
            )
            return "failed", item_id
        status = _schedule_retry(
            settings,
            path,
            item_id,
            exc,
            attempts=attempts,
            now=now,
            meta=meta,
            digest=digest,
        )
        return status, item_id

    record = dict(meta)
    record.update(
        {
            "id": item_id,
            "photoURL": url,
            "sha256": digest,
            "uploaded_at": uploaded_at,
            "source_name": path.name,
            "size_bytes": size,
            "attempts": 0 if deduped else attempts + 1,
            "deduped": deduped,
        }
    )
    write_json(ready_path, record)
    clear_attempt(settings, item_id)
    move_pair(path, side, settings.done)
    if deduped:
        LOG.info("deduped id=%s sha256=%s url=%s", item_id, digest, url)
    else:
        LOG.info(
            "uploaded id=%s sha256=%s url=%s deduped=0 attempts=%s",
            item_id,
            digest,
            url,
            attempts + 1,
        )
    return "ready", item_id


def _fail_settled(
    settings: Settings,
    path: Path,
    message: str,
    now: datetime,
) -> str:
    item_id = failure_id(path)
    fail_item(
        settings,
        path,
        item_id,
        message,
        attempts=0,
        now=now,
        meta={},
        digest=None,
    )
    return item_id


def _process_once_unlocked(settings: Settings, *, now: datetime | None) -> ProcessReport:
    ensure_dirs(settings)
    moment = now if now is not None else datetime.now(TOKYO)
    now_ts = moment.timestamp()
    observed = read_state(_observed_path(settings))
    present = {
        path.name: path
        for path in sorted(settings.inbox.iterdir(), key=lambda item: item.name)
        if path.name
    }
    for name in list(observed):
        if name not in present:
            del observed[name]

    ready: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    for path in present.values():
        kind = classify(path)
        if kind in {"temp", "sidecar"}:
            continue
        if not path.is_symlink() and not path.is_file():
            LOG.warning("skip non-file name=%s", path.name)
            skipped.append(path.name)
            continue
        if kind == "symlink":
            failed.append(_fail_settled(settings, path, f"拒绝符号链接：{path.name}", moment))
            continue
        state = settle(settings, path, observed, now_ts)
        if state == "skip":
            skipped.append(path.name)
            continue
        if state == "empty":
            failed.append(_fail_settled(settings, path, f"空文件：{path.name}", moment))
            continue
        if kind == "other":
            ext = extension_of(path)
            shown = f".{ext}" if ext else "(无)"
            message = f"不支持的扩展名 {shown}（仅限 jpg/jpeg/png/gif/webp/bmp）"
            failed.append(_fail_settled(settings, path, message, moment))
            continue
        status, item_id = handle_image(settings, path, observed, moment, now_ts)
        if item_id is None:
            skipped.append(path.name)
            continue
        if status == "ready":
            ready.append(item_id)
        elif status == "failed":
            failed.append(item_id)
        else:
            skipped.append(path.name)
    write_json(_observed_path(settings), observed)
    return ProcessReport(tuple(ready), tuple(failed), tuple(skipped))


def process_once(settings: Settings, *, now: datetime | None = None) -> ProcessReport:
    ensure_dirs(settings)
    configure_logging(settings.log_file)
    with watcher_lock(settings):
        return _process_once_unlocked(settings, now=now)


def enqueue_image(
    settings: Settings,
    source: str | Path,
    *,
    to: str | None,
    text: str | None,
    requested_by: str | None,
    now: datetime | None = None,
) -> Path:
    src = Path(source)
    if not src.exists():
        raise OutboxError(f"找不到文件：{src}", exit_code=2)
    validate_image(src, settings.max_bytes)
    try:
        assert_safe_id(src.stem)
    except OutboxError as exc:
        raise OutboxError(f"文件名不能作为 id：{src.name}", exit_code=2) from exc
    ensure_dirs(settings)
    configure_logging(settings.log_file)
    moment = now if now is not None else datetime.now(TOKYO)
    dest = settings.inbox / src.name
    side = sidecar_for(dest)
    if dest.exists() or side.exists():
        digest = file_sha256(src)[:8]
        dest = settings.inbox / f"{src.stem}-{digest}{src.suffix}"
        side = sidecar_for(dest)
    meta: dict[str, Any] = {"created_at": isoformat_tokyo(moment)}
    if to is not None:
        meta["to"] = to
    if text is not None:
        meta["text"] = text
    if requested_by is not None:
        meta["requested_by"] = requested_by
    write_json(side, meta)
    temporary = settings.inbox / f".{dest.name}.partial"
    shutil.copyfile(src, temporary)
    os.replace(temporary, dest)
    LOG.info("queued id=%s path=%s", dest.stem, dest.name)
    return dest


def list_ready(settings: Settings) -> list[dict[str, Any]]:
    ensure_dirs(settings)
    records: list[dict[str, Any]] = []
    for path in sorted(settings.ready.glob("*.json")):
        if is_temp_name(path.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOG.warning("skip unreadable ready file name=%s", path.name)
            continue
        if isinstance(data, dict):
            records.append(data)
    records.sort(
        key=lambda rec: (str(rec.get("uploaded_at") or ""), str(rec.get("id") or "")),
    )
    return records


def ack(settings: Settings, item_id: str, *, now: datetime | None = None) -> Path:
    assert_safe_id(item_id)
    ensure_dirs(settings)
    configure_logging(settings.log_file)
    src = settings.ready / f"{item_id}.json"
    sent = settings.sent / f"{item_id}.json"
    if not src.is_file():
        if sent.is_file():
            raise OutboxError(f"已经确认过：{item_id}")
        raise OutboxError(f"没有这条待发记录：{item_id}")
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OutboxError(f"待发记录不是合法 JSON：{item_id}") from exc
    if not isinstance(data, dict):
        raise OutboxError(f"待发记录必须是 JSON 对象：{item_id}")
    moment = now if now is not None else datetime.now(TOKYO)
    data["acked_at"] = isoformat_tokyo(moment)
    write_json(sent, data)
    src.unlink()
    LOG.info("acked id=%s", item_id)
    return sent


def open_inotify(inbox: Path) -> int | None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.inotify_init1.argtypes = [ctypes.c_int]
        libc.inotify_init1.restype = ctypes.c_int
        libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        libc.inotify_add_watch.restype = ctypes.c_int
        fd = libc.inotify_init1(IN_CLOEXEC | IN_NONBLOCK)
        if fd < 0:
            return None
        mask = IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE
        watch = libc.inotify_add_watch(fd, os.fsencode(inbox), mask)
        if watch < 0:
            os.close(fd)
            return None
        return fd
    except (AttributeError, OSError):
        return None


def _wait_fd(fd: int, timeout: float) -> bool:
    poller = select.poll()
    poller.register(fd, select.POLLIN)
    try:
        return bool(poller.poll(max(0, int(timeout * 1000))))
    except InterruptedError:
        return False


def _drain(fd: int) -> None:
    while True:
        try:
            os.read(fd, 65536)
        except BlockingIOError:
            return
        except OSError as exc:
            if exc.errno == errno.EAGAIN:
                return
            raise


def _install_stop() -> Any:
    flag = {"stop": False}

    def handle(signum: int, frame: object) -> None:
        del signum, frame
        flag["stop"] = True

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    return lambda: flag["stop"]


def watch(settings: Settings, *, once: bool, force_poll: bool) -> ProcessReport | None:
    ensure_dirs(settings)
    configure_logging(settings.log_file)
    if once:
        return process_once(settings)
    stop = _install_stop()
    with watcher_lock(settings):
        fd = None if force_poll else open_inotify(settings.inbox)
        if fd is None:
            LOG.info("watcher poll root=%s interval=%s", settings.root, settings.poll_interval)
        else:
            LOG.info("watcher inotify root=%s", settings.root)
        try:
            while not stop():
                report = _process_once_unlocked(settings)
                if report.ready or report.failed:
                    LOG.info(
                        "scan ready=%s failed=%s",
                        len(report.ready),
                        len(report.failed),
                    )
                if stop():
                    break
                if fd is None:
                    time.sleep(settings.poll_interval)
                elif _wait_fd(fd, settings.poll_interval):
                    _drain(fd)
        finally:
            if fd is not None:
                os.close(fd)
    LOG.info("watcher stopped")
    return None
