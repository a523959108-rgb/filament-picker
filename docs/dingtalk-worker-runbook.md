# 耗材选色 worker 常驻运行手册

本手册只说明 **怎样准备** 让 `filament-picker worker` 作为常驻进程跑。它不是上线许可。

**在负责人明确说可以之前：不要在任何机器上启动常驻进程，不要 `systemctl enable` / `systemctl start`，不要让 supervisord 拉起它，也不要对真实共享目录跑冒烟。** 本仓库不连接钉钉、不发消息。真机跑通之前不要说「已上线」。

worker 只读写共享目录。监听器把图片放进 `inbox/`，钉钉助手写 `inbox/<key>.request.json`，本仓库的 worker 认领后跑配色，写出 `outbox/<key>.json` 和 `public/cards/`。助手自己读 outbox，把 `reply_markdown` 当作回复正文。协议见 SPEC §9.1、§9.5；下面第 8 节可以单独转发给助手侧。

## 1. 共享目录

内置默认根目录（只作文档，测试和冒烟都用临时目录）：

`/home/box/agent-data/shared/filament-picker`

worker 启动时会创建这些子目录（已存在则不动）：

| 路径 | 谁写 | 作用 |
|---|---|---|
| `inbox/` | 监听器写图片；助手写 `*.request.json` | worker 只认领 `*.request.json`，不碰 `*.request.json.tmp` 和图片 |
| `processing/` | worker | 认领后的请求。正常情况下，空闲时这里应是空的 |
| `done/` | worker | `status=ok` 的请求原文 |
| `failed/` | worker | `status=error` 的请求原文。outbox 里仍有对应结果 |
| `outbox/` | worker | `<request_id>.json`，助手读这个 |
| `public/cards/` | worker | 色卡 PNG。文件名是随机 token |
| `logs/` | worker | `worker.log`（JSON 行）和 `worker.lock`（回收锁，里面是持锁进程的 pid） |

`inbox/`、`processing/`、`done/`、`failed/`、`outbox/` 必须在**同一个文件系统**上。跨盘 `rename` / `link` 会失败；失败的请求留在原地，循环继续，并在日志里记 `INTERNAL`。

## 2. 环境变量

worker 实际会读到的变量（值以 `src/filament_picker/config.py` 为准，这里不改任何常量）：

| 变量 | 默认 | 谁用 |
|---|---|---|
| `FP_ROOT` | `/home/box/agent-data/shared/filament-picker` | 只有 `scripts/run_worker.sh` 把它传给 `--root`。直接调 CLI 时以 `--root` 为准 |
| `FP_CATALOG` | `<repo>/data/build/filament-catalog.json` | 未传 `--catalog` 时使用。脚本不接收 `--catalog` 参数 |
| `FP_CARD_BASE_URL` | 未设置 | 未设置则结果里 `card_url` 为 null，回复正文不带图。设置了就必须以 `https://` 开头，否则进程在读配置时直接失败 |
| `FP_FONT_REGULAR` | `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` | 画色卡时读取 |
| `FP_FONT_BOLD` | `/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc` | 画色卡时读取 |
| `FP_FONT_INDEX` | `2` | TTC 里的 Noto Sans CJK SC |

字体打不开时，这一张请求变成 `INTERNAL`，循环不会退出。`FP_SHOTS_DIR` 与这条 worker 循环无关。

轮询间隔 `WORKER_POLL_S=1` 秒，清理间隔 `CLEANUP_INTERVAL_S=3600` 秒，保留 `RETENTION_DAYS=7` 天。这些数不要在部署时改。

## 3. 跑一次，和跑循环

在仓库根目录执行。两种都**先对着临时目录**，不要把 `--root` 指到真实共享目录，除非负责人已经同意。

跑一次（处理当前 inbox 后退出，退出码 0）：

```bash
ROOT="$(mktemp -d)"
.venv/bin/filament-picker worker \
  --root "$ROOT" \
  --once \
  --catalog docs/schemas/examples/filament-catalog.example.json
```

冒烟（自己建临时目录，退出时删除，最后一行是 `smoke ok`）：

```bash
scripts/smoke_worker.sh
```

这个脚本忽略 `FP_ROOT`，只用示例目录，不读真实共享目录。

跑循环的正式入口是 `scripts/run_worker.sh`。它没有参数，也不会加上 `--once`。它 `cd` 到脚本所在仓库并 `exec` 下面这条命令，所以信号直接交给 Python，而不是留在 shell 里：

```bash
exec .venv/bin/filament-picker worker --root "${FP_ROOT:-/home/box/agent-data/shared/filament-picker}"
```

因此循环模式下目录路径用 `FP_CATALOG`，色卡 URL 用 `FP_CARD_BASE_URL`。机器上要已经有这个仓库的 `.venv`。示例（仍然不要现在执行）：

```bash
FP_ROOT=/path/to/shared/filament-picker \
FP_CATALOG=/path/to/filament-picker/data/build/filament-catalog.json \
FP_CARD_BASE_URL=https://cards.example.invalid/c \
scripts/run_worker.sh
```

## 4. 常驻时的进程行为

启动顺序：

1. 创建第 1 节的子目录。
2. 装上 `SIGTERM` / `SIGINT` 处理（只把一个标志设为真）。
3. 加载目录。失败则写一条 `CATALOG_ERROR` 并退出码 **2**。加载过程中如果已经收到停止信号，改为退出码 **0**。
4. 非阻塞独占锁 `logs/worker.lock`，写入自己的 pid。拿到锁的进程把 `processing/*.request.json` 放回 `inbox/`（见下）。没拿到锁的进程不回收，`start` 的 `detail` 为 `lock_busy`，然后仍然处理 inbox。
5. 进入循环：认领 → 处理 → 到期则清理 → 目录 mtime 变了则重载 → `--once` 或已收到停止信号则退出码 0，否则睡眠 1 秒。

生产环境只跑 **一个** 常驻进程。第二个进程仍能用原子 `rename` 认领 inbox（这是规格里的并发认领），但锁被占用时它不会把别人正在 `processing/` 里的文件偷走。

### 信号

`SIGTERM` 和 `SIGINT`：如果正在处理某一张，处理完这一张再退出，退出码 0。不会把 inbox 里其余请求都做完。空闲时（睡在轮询里）大约 1 秒内退出。

`SIGKILL` 或断电：请求会留在 `processing/`。下次**拿到锁**的启动会把它放回 `inbox/` 再做一遍，outbox 里同名结果会被重新写一遍。日志是 `event=claimed`、`detail=requeued`，这条会出现在同一次启动的 `start` **之前**。

`inbox/` 里已经有同名 `*.request.json` 时，不覆盖它；`processing/` 里的那份改放到 `failed/`（`failed/` 里还没有同名文件时），并记一条 `INTERNAL`，detail 为 `requeue skipped; inbox already has request`。

### 目录热加载

更新目录时在**同一目录**写临时文件，再 `rename` 到正式路径上，不要写到一半就让 worker 去读。

- 启动后第一次加载失败：退出码 2，不会空转。
- 运行中 mtime 变了且新文件合法：换上新目录，记 `catalog_reload`。最迟在当前这一轮请求结束之后的下一轮生效。
- 运行中新文件读失败或校验失败：继续用内存里的旧目录。同一种错误正文只记 **一条** `CATALOG_ERROR`，避免每秒一条把 `worker.log` 写满。文件后来修好后会再记 `catalog_reload`。

### 清理

每 3600 秒，以及每次进程启动后的第一轮（计时从 0 开始），删除下面目录里 **mtime 早于 7 天的普通文件**（不递归、不删子目录）：

`inbox/`、`done/`、`failed/`、`outbox/`、`public/cards/`

不删 `processing/`，不删 `logs/`。某个文件删不掉（例如仍被占用）时记一条 `INTERNAL` 并继续，不让整个进程退出。

### 日志

`logs/worker.log` 每行一个 JSON 对象，字段固定为：

`ts`（Asia/Tokyo，秒）、`event`（`start` | `claimed` | `done` | `cleanup` | `catalog_reload` | `error`）、`request_id`、`status`（`ok` | `error` | null）、`code`、`elapsed_ms`、`detail`。

请求成功或业务失败都记 `done`，用 `status` 和 `code` 区分。`INTERNAL` 的 traceback 只在 `detail` 里，不写进 outbox。

日志文件写失败时 worker 继续跑（避免日志盘满把队列卡死）。清理任务不删日志。上线之后用 logrotate，路径换成真实共享目录，用户和组换成运行账号：

```
/path/to/shared/filament-picker/logs/worker.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
    create 0640 WORKER_USER WORKER_GROUP
}
```

worker 每次写日志都是重新打开文件，所以按上面这样 `rename` 走是安全的。标准输出里没有业务日志；Python 未捕获异常才会出现在 systemd/supervisord 的 stderr。

## 5. 健康检查

下面这些等负责人同意启动之后再做。不要现在对真实目录执行。

- 只有一个 `filament-picker worker` 进程，并且 `logs/worker.lock` 里的 pid 就是它。
- 空闲时大约每小时有一条 `event=cleanup`。如果进程还在，但最新一条日志超过两小时，并且 `inbox/*.request.json` 已经放了好几分钟，循环可能卡在某一张图上。
- 服务停着的时候，`processing/*.request.json` 可以留着；下次拿到锁的启动会放回 inbox。服务跑着且空闲时，`processing/` 应为空。
- 退出码 2 只表示**启动时**目录加载失败。示例 unit 里 `Restart=on-failure` 会隔 5 秒重试，300 秒内最多 5 次，然后停在 failed，需要人看 `worker.log` 里的 `CATALOG_ERROR`。
- 助手侧的 90 秒是助手自己的等待，不是 worker 的请求超时。worker 没有单张超时；一张很慢的图会挡住后面的队列，助手可以先按第 8 节回复超时，worker 稍后仍会把结果写入 outbox。

## 6. 示例 unit（不要安装、不要启动）

- systemd：`deploy/filament-picker-worker.service.example`
- supervisord：`deploy/filament-picker-worker.supervisord.conf.example`

两个文件都是占位符：`/path/to/...`、`WORKER_USER`、`https://cards.example.invalid/c`。没有真实主机名，没有密钥。supervisord 示例写了 `autostart=false`。复制到系统目录之前必须改路径，并且仍然要等负责人点头。

`TimeoutStopSec` / `stopwaitsecs` 都是 90 秒，和助手侧的等待一致。停服务时发 `SIGTERM`。90 秒内当前这张还没写完，进程管理器才会强杀；强杀后的请求靠下次启动回收。

## 7. 冒烟在测什么

`scripts/smoke_worker.sh`：

1. `mktemp` 一个根目录，退出时删除。
2. 在 `inbox/smoke1.png` 画黑方块，用临时文件加 `mv` 写入 `smoke1.request.json`（材料 PETG）。
3. 再写 `smoke2.request.json`，图片路径不存在。
4. `worker --once` 使用 `docs/schemas/examples/filament-catalog.example.json`。
5. 两个 outbox 都过 result schema。`smoke1` 为 ok 并进入 `done/`，`smoke2` 为 `IMAGE_MISSING` 并进入 `failed/`。
6. `processing/` 为空；`logs/worker.log` 里有 `start`、两条 `done`、一条 `cleanup`。

`docs/schemas/examples/request.example.json`、`result.example.json`、`result.error.example.json`、`filament-catalog.example.json` 已对照当前 schema 校验通过，这次没有改它们。冒烟不用前三个例子，它自己写请求。

## 8. 交给钉钉助手的约定（可转发）

本节是文件约定，不是接口调用。助手不要让本仓库去发消息；本仓库也不会读助手的配置、也不会回调任何地址。

### 写请求

`key` 等于请求里的 `request_id`，也等于监听器清洗后的 msgId：把 msgId 里不在 `A-Za-z0-9_.=+-` 里的字符换成 `_`，长度 1–200。文件名和 JSON 里的 `request_id` 必须是同一个 `key`。worker 写出的结果文件名用的是 JSON 里的 `request_id`；两边不一致时，助手去轮询 `outbox/<文件名>.json` 会扑空。

图片先出现在共享目录里（绝对路径，后缀只能是 `png` `jpg` `gif` `webp` `bmp` `heic` `bin`）。然后：

1. 把完整 JSON 写到 `inbox/<key>.request.json.tmp`。
2. 写完后 `rename` 成 `inbox/<key>.request.json`。不要直接写最终文件名，worker 可能读到半截。
3. worker 不处理 `*.request.json.tmp`，也不处理图片本身。

最小字段：

```json
{
  "schema_version": 1,
  "request_id": "msgEXAMPLE0001",
  "created_at": "2026-11-05T14:03:12+09:00",
  "image_paths": ["/home/box/agent-data/shared/filament-picker/inbox/msgEXAMPLE0001.png"],
  "note": "",
  "constraints": {},
  "context": {"conversationId": "cidEXAMPLE"}
}
```

- `created_at` 用带时区的 ISO8601，建议 `Asia/Tokyo`。
- `note` 是用户随图文字，最长 500。显式条件放 `constraints`，优先级高于备注。材料只能是 `PLA` / `PETG`。
- `context` 原样回到结果里，助手用它找回会话。最多 20 个字段。
- **不要**在请求里放回调地址或密钥。schema 拒绝 `sessionWebhook` 和 `session_webhook`；放了会被判 `INVALID_REQUEST`，不会发出去。
- 多图时 v1 只用 `image_paths[0]`，其余忽略，并在 `warnings` 里写 `EXTRA_IMAGES_IGNORED:<张数>`。

完整字段以 `docs/schemas/request.schema.json` 和 `docs/schemas/examples/request.example.json` 为准。

### 读结果

从写出请求开始，最多等 **90 秒**，看 `outbox/<key>.json` 是否出现。文件一旦出现就是完整内容（worker 用临时文件加 `os.replace` 写）。不要读 `processing/`，不要删 outbox（7 天后由 worker 清理）。

- 出现了：回复正文用结果里的 `reply_markdown`（助手侧的 sampleMarkdown 就是这一个字符串）。不要改写，不要自己编一句。
- `status=ok` 时，正文是配色方案；有 `card_url` 时正文里已经包含图片链接。
- `status=error` 时，正文就是 `error.message_zh` 那一句。`error.code` 只给助手自己记日志，可选值是 `INVALID_REQUEST`、`IMAGE_MISSING`、`IMAGE_UNREADABLE`、`IMAGE_TOO_SMALL`、`NO_FOREGROUND`、`NO_MATCH`、`CATALOG_ERROR`、`INTERNAL`。
- `context` 与请求里相同，用来对上会话。
- 90 秒内文件还没有出现：回复这句，一个字都不要改：

> 处理超时，请稍后重试

超时之后 worker 仍可能把结果写进 outbox。助手不要为了超时去删 inbox 里的请求。

示例结果：`docs/schemas/examples/result.example.json`（成功）和 `docs/schemas/examples/result.error.example.json`（失败）。
