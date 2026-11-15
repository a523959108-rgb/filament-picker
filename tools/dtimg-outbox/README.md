# 钉钉图片发件箱（dtimg-outbox）

图片助手把图放进共享目录，这个工具调用现有的 `put.sh` 上传，并在 `ready/` 写下一条待发记录。钉钉助手读这条记录，自己发图片消息，发完再 `ack`。

本工具**不调用钉钉，不发送消息**。公网地址只由 `put.sh` 产生。这里没有密钥，也没有写死的 IP。

它是仓库里的独立运维工具，不导入、不修改耗材选色站的网站代码。

## 目录

默认根目录：`/home/box/agent-data/shared/dingtalk-outbox/`

| 目录 | 谁写 | 内容 |
| --- | --- | --- |
| `inbox/` | 图片助手 | 待上传的图片，以及可选的同名 sidecar |
| `ready/` | 本工具 | 已上传、还没发出去的记录 |
| `done/` | 本工具 | 上传成功的原图和 sidecar |
| `failed/` | 本工具 | 失败的原图，以及 `<id>.error.json` |
| `sent/` | 钉钉助手（通过 ack） | 已确认发送的记录 |
| `state/` | 本工具 | sha256 索引、重试次数、进程锁 |
| `log/dtimg-outbox.log` | 本工具 | 一行一条，按 2MB 轮转，保留 5 份 |

投放口是 `inbox/`，不是发件箱根目录。根目录下面还有 `ready/`、`done/` 这些结果目录；如果直接监听根目录，结果文件会被再当成新图片。

## 记录里有什么

`ready/<id>.json` 会保留 sidecar 里的原字段，并加上这些字段（同名时以这里为准）：

- `id`：图片主文件名，例如 `配色.png` 的 id 是 `配色`
- `photoURL`：`put.sh` 打印的 https 地址
- `sha256`：文件内容
- `uploaded_at`：上传时间，Asia/Tokyo，形如 `2026-11-15T11:09:00+09:00`
- `source_name`、`size_bytes`、`attempts`、`deduped`

sidecar 建议使用这些字段：

- `to`：群名或会话名
- `text`：图片说明
- `requested_by`：哪个助手放进来的
- `created_at`：放入时间

钉钉助手把 `photoURL` 填进图片消息的 photoURL（sampleImageMsg）。说明可以用 `text`。发成功后再 ack，不要让本工具代发。

## 在盒子上安装

在放这个仓库的用户下执行（通常是 `box`）。服务用系统的 `python3`，不要用网站的 `.venv`。

```bash
cd /path/to/filament-picker
loginctl enable-linger "$USER"
bash tools/dtimg-outbox/install-user-service.sh
systemctl --user enable --now dtimg-outbox.service
systemctl --user status dtimg-outbox.service --no-pager
```

安装脚本会创建上面的目录，并写入 `~/.config/systemd/user/dtimg-outbox.service`。当前用户的 systemd 可用时，它会自己 `enable --now`。`loginctl enable-linger` 让服务在登出、重启之后还在。

看日志：

```bash
journalctl --user -u dtimg-outbox.service -f
tail -f /home/box/agent-data/shared/dingtalk-outbox/log/dtimg-outbox.log
```

没有 systemd --user 时，用 nohup：

```bash
cd /path/to/filament-picker
bash tools/dtimg-outbox/run-nohup.sh
```

停掉 nohup 进程：

```bash
kill "$(cat /home/box/agent-data/shared/dingtalk-outbox/state/dtimg-outbox.pid)"
```

只扫一轮（排障或 cron）：

```bash
tools/dtimg-outbox/dtimg-outbox watch --once
```

仓库换了路径之后，重新跑一次 `install-user-service.sh`，unit 里的启动路径才会跟着变。

多个系统用户要一起读写时，目录需要同一组可写。本工具不替你改组：

```bash
sudo chgrp -R shared /home/box/agent-data/shared/dingtalk-outbox
sudo chmod -R 2775 /home/box/agent-data/shared/dingtalk-outbox
```

同一用户跑所有助手时，不需要这两条。

## 图片助手怎么放文件

优先用命令。它会先检查扩展名和大小，再把 sidecar 和图片原子放进 `inbox/`：

```bash
tools/dtimg-outbox/dtimg-outbox put /tmp/配色.png --to "耗材群" --text "今日配色" --requested-by image-assistant
```

标准输出：

```text
已放入发件箱：/home/box/agent-data/shared/dingtalk-outbox/inbox/配色.png
id=配色
```

手工放也可以。先写 sidecar，再把图片改名放进去（图片出现才算提交）：

```bash
OUT=/home/box/agent-data/shared/dingtalk-outbox/inbox
cat > "$OUT/.配色.json.tmp" <<'EOF'
{"to":"耗材群","text":"今日配色","requested_by":"image-assistant","created_at":"2026-11-15T11:00:00+09:00"}
EOF
mv "$OUT/.配色.json.tmp" "$OUT/配色.json"
cp /tmp/配色.png "$OUT/.配色.png.partial"
mv "$OUT/.配色.png.partial" "$OUT/配色.png"
```

同一主文件名同时只放一张图。`配色.png` 的 sidecar 必须叫 `配色.json`。

这些名字会被当成还没写完，直接跳过：以 `.` 开头，或以 `.tmp`、`.temp`、`.partial`、`.part`、`.swp`、`.swx`、`~` 结尾。空文件会再等 `DTIMG_STABLE_SEC` 秒；仍然是空的，就进 `failed/`。

## 钉钉助手怎么读、怎么确认

读文件：

```bash
ls /home/box/agent-data/shared/dingtalk-outbox/ready
```

或：

```bash
tools/dtimg-outbox/dtimg-outbox list-ready
tools/dtimg-outbox/dtimg-outbox list-ready --json
```

没有待发记录时，普通输出是 `没有待发送的图片`。

发送成功后：

```bash
tools/dtimg-outbox/dtimg-outbox ack 配色
```

记录从 `ready/配色.json` 挪到 `sent/配色.json`，并写入 `acked_at`。重复 ack 会报「已经确认过」，不会把记录弄丢。

发送失败就不要 ack，记录会留在 `ready/`，下次还能看到。

## 上传、去重、重试

默认调用 `/home/box/agent-data/shared/dingtalk-media/put.sh`。上传前先在本地拒绝不符合限制的文件，避免先传上去再失败：

- 扩展名只接受 jpg、jpeg、png、gif、webp、bmp（大小写不限）
- 单张不超过 10MB（10485760 字节），和 put.sh 的默认上限一致
- 拒绝符号链接、空文件、临时文件名

`put.sh` 退出码 2、本地校验失败、成功但没有 https 地址：立刻进 `failed/`，不重试。网络错误、超时、退出码 1、暂时找不到 `put.sh`：按 2 秒、4 秒、8 秒……退避，最多 3 次，上限 60 秒。用尽后，原图进 `failed/`，旁边有 `<id>.error.json`。

同一内容（sha256 相同）已经传过的，不再调用 `put.sh`，新的投放仍然会写一条新的 `ready/` 记录，因为发给两个群是两条消息。索引在 `state/sha256.json`。上传成功后进程崩溃、文件还留在 `inbox/` 时，再扫一轮只会补写记录或把原图挪走，不会重新上传。

公网图床会删掉超过 7 天的文件。记录写好后应尽快发送。

想把失败的图再试一次：把图片（和 sidecar）移回 `inbox/`，删掉对应的 `.error.json`。内容没变的话会直接复用已有 URL。

## 环境变量

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `DTIMG_OUTBOX` | `/home/box/agent-data/shared/dingtalk-outbox` | 发件箱根目录 |
| `DTIMG_PUT_SH` | `/home/box/agent-data/shared/dingtalk-media/put.sh` | 上传脚本 |
| `DTIMG_MAX_BYTES` | `10485760` | 单张上限，应与 put.sh 一致 |
| `DTIMG_MAX_ATTEMPTS` | `3` | 临时失败最多试几次 |
| `DTIMG_RETRY_BASE_SEC` | `2` | 第一次失败后等待的秒数，之后翻倍 |
| `DTIMG_STABLE_SEC` | `1` | 文件写完后至少再静默这么久 |
| `DTIMG_POLL_INTERVAL` | `2` | 两轮扫描的间隔 |
| `DTIMG_LOG_PATH` | `<发件箱>/log/dtimg-outbox.log` | 日志文件 |
| `DTIMG_REQUESTED_BY` | 空 | `put` 没写 `--requested-by` 时使用 |

命令上的 `--root`、`--put-sh`、`--max-attempts`、`--retry-base`、`--stable-sec`、`--interval` 覆盖对应的环境变量。

watcher 优先用 inotify 提前醒来；每一轮仍会扫描 `inbox/`，这样重试不必等新文件，写了一半的文件也会继续等它稳定。`--poll` 强制只用轮询。内核不支持 inotify 时自动改成轮询。

日志一行一件事，时间是 Asia/Tokyo。程序自己按 2MB 轮转。如果另外用 logrotate，用 `copytruncate`，避免把正在写的文件改名。

## 测试

```bash
bash tools/dtimg-outbox/run-tests.sh
```

测试用假的 `put.sh`（成功时打印一条 URL，或按模式失败），不访问网络，也不碰真正的图床。
