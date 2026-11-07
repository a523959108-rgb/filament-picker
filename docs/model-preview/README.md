# 本地模型预览

本任务只交付同站 `/models` 登录画廊、API、假样例和部署示例。样例均为程序生成的纯色 PNG，标题、作者、大小和 sha256 都是合成元数据，没有真实模型文件。没有执行部署、上传、原件扫描或 3D 转换。

## 本地启动

使用已装好的 `.venv` 和 `web/node_modules`，不要重新安装依赖。以下命令从本仓库根目录执行：

```sh
.venv/bin/python scripts/seed_model_preview_samples.py
export FILAMENT_PICKER_SESSION_SECURE=0
export FILAMENT_PICKER_MODELS_DIRECT=1
# 仅在当前进程环境生成密钥；命令不打印密钥，也不写入仓库。
export FILAMENT_PICKER_SESSION_SECRET="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
.venv/bin/filament-picker auth create-user --username yulanmoxing
cd web
npm run build
cd ..
.venv/bin/filament-picker serve
```

浏览 `http://127.0.0.1:8787/`，点击「模型预览」，或直接打开 `/models/login`。`serve` 同时提供现有选色 API 与前端；后端挂载受保护的 pathname 回退，不需要增加 npm 路由依赖。生产使用构建后的 SPA；Vite 单独运行时只代理 API，页面保护应通过 `serve` 验收。

建号需要交互式终端，两次 `getpass` 输入一致且非空才写入数据库。无法隐藏输入时直接失败；没有密码命令行参数。仅支持首次创建 `yulanmoxing`，不支持密码重置或第二账号。`auth list-users` 仅输出用户名。实际用户凭据不得放入脚本、聊天、日志或 fixtures。

样例脚本默认创建 `data/models-private/manifest.sqlite` 和 `thumbs/sample-01.png` 至 `sample-08.png`。可用 `--root` 指向单独的测试目录。重复运行只接受完全匹配的合成清单，拒绝覆盖非样例记录。认证测试 fixture 在临时目录用内存随机密码创建用户，仅哈希落盘；没有测试明文密码文件。

## 环境变量

| 名称 | 默认 / 说明 |
| --- | --- |
| `FILAMENT_PICKER_SESSION_SECRET` | 必须设置；缺失或 `change-me` 时登录返回 503，其他模型资源仍拒绝匿名访问，选色站可用。 |
| `FILAMENT_PICKER_AUTH_DB` | 仓库下 `data/auth/users.sqlite`；新建目录 0700，库文件 0600。 |
| `FILAMENT_PICKER_MODELS_ROOT` | 仓库下 `data/models-private`，不是公开 static 目录。 |
| `FILAMENT_PICKER_SESSION_TTL` | 正整数秒，默认 604800（7 天）。 |
| `FILAMENT_PICKER_SESSION_SECURE` | 默认 1；仅本机 HTTP 调试设 0。 |
| `FILAMENT_PICKER_MODELS_DIRECT` | 默认 1（应用 FileResponse）；Nginx 模式显式设 0。 |

设置在应用启动时读取。应用只读取进程环境，不自动解析 env 文件。`deploy/filament-picker.env.example` 仅含占位符；协调者可在另行授权的部署流程中通过 systemd `EnvironmentFile=/etc/filament-picker.env` 注入，真实 env 文件放仓库外，权限 `root:filament` 0640 或更严。不要把 `change-me` 直接用于服务。

## 认证与资源边界

- Argon2id 哈希、itsdangerous 签名 `fp_session` cookie；`HttpOnly`、`SameSite=Lax`、`Path=/`、可配 `Secure` 与 TTL。SQLite 仅保存会话 token 的 SHA256 摘要、用户名和过期时间，登出删除会话，重放旧 cookie 也被拒绝；数据库不能公开或纳入公开备份。密钥变更使现有 cookie 失效。
- 每 IP 在 60 秒内连续失败 5 次，后续请求返回 429 及 `Retry-After`；锁定时间自最近一次失败起 60 秒，成功登录清零。计数只在当前应用进程内，重启清空；当前本地/单进程部署不使用 Redis。反向代理须覆盖客户端提供的转发头，并且 Uvicorn 只信任本机代理，否则不能可靠按 IP 限流。
- `/models`、`/models/*`（登录页除外）、`/api/models*`（POST login 除外）统一先认证，再校验参数或查清单。匿名页面 302 到 `/models/login`，API 401，响应不暴露模型名或存在性。受保护响应和登录页/API 均带 `Cache-Control: no-store`、`X-Robots-Tag: noindex, nofollow`；robots 禁止索引模型路径。
- `/`、`#/plan`、`/api/health`、`/api/plan`、`/api/cards/*`、`/web-catalog.json` 继续公开。前端始终显示「仅私人收藏预览、禁止外传」。
- 缩略图限定在清单根目录的 `thumbs/` 单层 PNG/WebP 内，拒绝目录穿越、绝对路径、非图片与符号链接逃逸。API 不返回源路径或绝对磁盘路径。模型私有目录不得复制进 `web/public`、`web/dist` 或挂成匿名 alias。

## API 与清单

`POST /api/models/login` 接收 JSON `{username, password}`，成功返回 `{username}` 并设置 cookie；错误凭据 401、限流 429。`POST /api/models/logout` 撤销会话并清除 cookie；`GET /api/models/me` 返回 `{username}`。

`GET /api/models?page=1&page_size=12&q=&series=&author=` 返回 `{items, total, page, page_size, series, authors}`。page 为 1–1000000，page_size 为 1–100；q 对标题作字面子串搜索（LIKE 通配字符会转义），系列/作者精确筛选，按 id 稳定排序。series/authors 是整个库的筛选选项；空清单返回空列表。`GET /api/models/{id}` 返回单条；`GET /api/models/{id}/thumb` 返回图片。

列表和详情条目包含 `id, title, series, author, size_bytes, plate_count, colours, created_at, thumb_url`。不提供清单文件下载或原始文件 URL。

SQLite 清单表 `models` 包含任务书要求的 `id, sha256, title, series, author, source_relpath, size_bytes, plate_count, colours, thumb_path, created_at`；colours 为 JSON 数组，thumb_path 为相对路径。真实导入流程不在本地任务范围，后续应从 `filament_colour` 提取颜色并对整文件 sha256 去重；假数据不能作为真实去重数量或体积验收依据。

## Nginx 示例（未部署）

参见 `nginx-internal-models.example.conf`。`FILAMENT_PICKER_MODELS_DIRECT=0` 时，认证成功后应用仅返回 `X-Accel-Redirect: /internal-models/thumbs/...`，由 `internal` location 发送文件。示例 alias 必须与模型根目录一致；Nginx 需要读取权限，但目录不得成为公开目录。直接请求 `/internal-models/...` 应为 404/403。应用保留模型路由认证；不能让 Nginx 的 SPA 静态 fallback 跳过它。外部集成后确认最终图片响应保留 no-store/noindex。本地应用测试只验证内部重定向响应头，不能替代真实 Nginx 验收。

## 验证与交接

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
cd web
npm run lint
npm test
npm run build
```

新增 Python HTTP 测试使用 httpx ASGITransport，不开端口。若沙箱的线程/事件循环唤醒受限，仍可能卡住；协调者需在沙箱外原样跑全量测试，包含一期 TestClient 用例。新测试覆盖匿名保护、限流、登录/登出与旧 cookie 重放、分页筛选、两种缩略图模式、路径保护、建号哈希/权限和合成 seed。前端覆盖 pathname 分支、登录、画廊、横幅、搜索筛选分页、详情和登出。

随后在本机交互启动 `serve`，验证登录前后页面、图片、登出及选色站共存。真实 Nginx 的 `internal` 直接访问检查和配置检查留给后续授权部署流程；本任务不修改服务器配置。

外部任务书 §7.2 仍待决定：真实缩略图规格、首次上传方式与执行人、是否开展 3D，以及可选的原件私有冷备。均不阻塞本地假数据画廊；本任务未启动这些动作。

本次沙箱验证：Ruff 检查与格式检查通过；前端 51 个测试、TypeScript lint 和生产 build 通过；8 条样例和纯色缩略图生成并验证通过。普通 `pytest -q` 在事件循环等待线程结果时超时。仅在临时测试进程中将 `selectors.EpollSelector.select` 的等待上限设为 10ms 后，全量为 **312 passed、1 skipped**（178.23 秒）；跳过项是已有校准测试所需 `extracted.json` 未生成。另行运行非 data 测试为 277 passed、36 deselected。工作树代码、测试断言及依赖未为此修改。这些结果不能替代协调者沙箱外的普通全量 `pytest -q` 验收。
