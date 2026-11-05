# T19 — M2 端到端测试与冒烟脚本

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M2 | T18 | 半天 | SPEC §9.1、§9.5、§13 M2 |

## 目标
用真实子进程跑一遍完整的 inbox→outbox 流程（成功 / 图片缺失 / 非法请求三种），并提供一个人可以直接跑的冒烟脚本。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T18 验收通过。

## 要创建/修改的文件（只能动这些）
- `tests/test_e2e_worker.py`
- `scripts/smoke_worker.sh`（`chmod +x`）

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```bash
# scripts/smoke_worker.sh —— 行为固定如下
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
CAT=docs/schemas/examples/filament-catalog.example.json
# 1) .venv/bin/python -c "import sys; sys.path.insert(0, 'tests'); from helpers_images import square_on_white; ..." 在 $ROOT/inbox/smoke1.png 画 fg=#000000 方块
# 2) 写 $ROOT/inbox/smoke1.request.json.tmp 再 mv 成 smoke1.request.json
#    内容：schema_version 1, request_id "smoke1", created_at 当前时间, image_paths [该 png], note "", constraints {"materials":["PETG"]}, context {"conversationId":"cidSMOKE"}
# 3) 写 smoke2.request.json：image_paths 指向不存在的 $ROOT/inbox/missing.png
# 4) .venv/bin/filament-picker worker --root "$ROOT" --once --catalog "$CAT"
# 5) 对两个 outbox 文件跑 filament-picker validate result；断言 smoke1 status ok、smoke2 error.code == IMAGE_MISSING
# 6) 断言 done/smoke1.request.json 与 failed/smoke2.request.json 存在
echo "smoke ok"
```

## 输入/输出示例
```text
$ scripts/smoke_worker.sh
OK
OK
smoke ok
```

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_e2e_worker.py`（`subprocess.run([".venv/bin/filament-picker", "worker", "--root", tmp_root, "--once", "--catalog", 示例目录], timeout=60)`）
- 3 个请求：ok（黑方块 + PETG）、IMAGE_MISSING、`"{"`（INVALID_REQUEST）→ 进程退出码 0；outbox 3 个文件都通过 result schema；status 分别 ok / error / error；done 1 个、failed 2 个；`context` 原样回写。
- `ok` 那个的 `reply_markdown` 第一行 `### 配色方案（1 色）`，含 `bambu-lab` 的品牌名 `Bambu Lab PETG Basic`。
- `subprocess.run(["scripts/smoke_worker.sh"])` 退出码 0，stdout 最后一行 `smoke ok`。
- `rg`/grep 检查：`src/` 与 `scripts/` 中不出现 `dingtalk`、`sessionWebhook`、`bambu-print-agent`（大小写不敏感，测试里用 Python 遍历文件实现）。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_e2e_worker.py -q && scripts/smoke_worker.sh && .venv/bin/pytest -q
```

## 不要做
- 不要在真实 `FP_ROOT` 下跑；脚本必须用 mktemp 目录并在退出时删除。
- 不要在脚本里调用网络、钉钉、`curl`。
- 不要修改 worker 代码来"配合"测试；测试不过 → 报告。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
