# AGENTS.md — 给 Codex 助手的通用规则（filament-picker）

> 本文件放在 `docs/AGENTS.md`。T01 会把它**原样复制**到仓库根目录 `AGENTS.md`（Codex CLI 默认读根目录）。两份内容必须一致，以 `docs/AGENTS.md` 为准。

## 0. 你是谁、你在干什么
你在实现「耗材选色站」（filament-picker）。所有需求、算法、阈值、文件名都已经写死在 `docs/SPEC.md` 和 `docs/tasks/Txx-*.md` 里。**你的工作是照着做，不是设计。**

## 1. 硬规则（违反任何一条 = 任务失败）
1. **一次只做一个任务。** 只做人指定的那个 `Txx`。不要顺手做下一个，不要"先把后面要用的也写了"。
2. **先写测试。** 先把任务文件「测试」一节里的每条断言写成 pytest / vitest 用例，运行一次确认它们失败（红），再写实现直到通过（绿）。
3. **验收命令通过才算完成。** 每个任务文件末尾有一条「验收命令」。它的退出码必须是 0。没跑、跑不了、跑了失败 → 都不算完成，如实报告。
4. **规格没写的，停下来报告，不要自己发挥。** 包括但不限于：新增字段、新增依赖、改阈值、改文件名、改函数签名、改 JSON 结构、改错误码、改文案。写进报告的「需要人决定的问题」。
5. **只碰任务文件「要创建/修改的文件」列出的文件。** 其他文件一律不改（包括格式化、改 import 顺序、改注释）。如果不改别的文件就做不下去，停下来报告。
6. **不准大重构。** 不重命名已有模块/函数，不移动文件，不"顺便优化"。
7. **不准加依赖。** 依赖只能是 `docs/SPEC.md §2` 里锁定的包和版本。`pyproject.toml` / `web/package.json` 只有 T01 / T20 可以写依赖。
8. **不准改阈值和常量。** 所有数值常量在 `src/filament_picker/config.py`（Python）和 `web/src/config.ts`（前端），值以 SPEC 为准。标了「待校准」的也不准改——校准由人决定。
9. **不准联网。** 代码和测试都不发网络请求（`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外，且只装锁定版本）。测试里不准下载图片。
10. **不准碰钉钉、不准碰 bambu-print-agent。** 不 import、不读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。不发任何消息。
11. **不准改 `docs/` 下任何文件**（`docs/` 是需求，只读）。T01 复制 AGENTS.md 和 schemas 是唯一例外（复制，不是修改）。
12. **不准手改数据文件。** `data/raw/` 是只读快照；`data/ids.lock.json` 只能由 `filament-picker assign-ids` 命令写出。
13. **不准吞异常。** 不写裸 `except:`；`except Exception` 只允许出现在 `worker.py` 的最外层（SPEC §9.5 规定的位置）。
14. **不准用随机数而不设种子。** 需要随机时用 `numpy.random.default_rng(0)`（任务文件指定了别的种子时用指定的）。唯一例外：色卡文件名用 `secrets.token_urlsafe`（SPEC §9.6），测试里用正则断言格式，不断言具体值。
15. **不准写 `TODO` 然后宣称完成。** 未完成的部分写进报告。

## 2. 工作环境（固定）
- 仓库：`/workspace/dev/filament-picker`
- Python：3.11，虚拟环境 `.venv/`（T01 创建）。所有命令用 `.venv/bin/python`、`.venv/bin/pytest`、`.venv/bin/ruff`，不要用系统 python。
- Node：24.x（盒子上已有 v24.22.1），npm 11.x。前端在 `web/`。
- 时区：Asia/Tokyo。代码里生成时间一律 `datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")`。
- 编码：所有文件 UTF-8，JSON 写出用 `ensure_ascii=False, indent=2`，末尾加换行。

## 3. 代码风格（固定）
- `ruff check` 和 `ruff format --check` 必须干净（配置在 `pyproject.toml`，见 SPEC §2.3）。
- 所有公开函数要有类型注解，签名与任务文件**逐字一致**（参数名、顺序、默认值、返回类型）。
- 数据结构用 `@dataclass(frozen=True, slots=True)`；不要引入 pydantic。
- 路径用 `pathlib.Path`。
- 不写 print 调试；日志用 `logging.getLogger(__name__)`。CLI 的正常输出用 `print`（见各任务）。
- 测试文件名 `tests/test_<模块>.py`；测试函数名 `test_<行为>`。依赖真实数据/图片的测试加 `@pytest.mark.data`，在数据缺失时 `pytest.skip`。

## 4. 每个任务的固定流程
1. 读 `docs/AGENTS.md`（本文件）、`docs/SPEC.md` 中任务文件引用的章节、任务文件本身。
2. 检查「前置任务」的验收命令都能通过；不能通过就停止并报告。
3. 写测试 → 跑一次看到失败。
4. 写实现 → 跑任务的测试直到通过。
5. 跑 `.venv/bin/ruff check . && .venv/bin/ruff format --check .`（前端任务跑 `npm run lint`）。
6. 跑**全量**测试 `.venv/bin/pytest -q`，确认没有把之前的任务弄坏。
7. 跑任务的「验收命令」。
8. 按第 5 节格式报告。

## 5. 报告格式（必须严格使用，Markdown）
```
## Txx 报告
状态：完成 / 未完成 / 阻塞
### 改动的文件
- 新增 path/to/file.py（N 行）
- 修改 path/to/other.py（+a / -b 行）
### 测试输出
（粘贴验收命令的完整输出最后 30 行，以及 `pytest -q` 的最后一行）
### 与规格的偏差
- 无  （或逐条列出：规格原文 → 实际做法 → 原因）
### 需要人决定的问题
- 无  （或逐条列出，每条带：在哪个文件/哪一节、可选方案）
```

## 6. 遇到这些情况，立刻停下来报告
- 验收命令里引用的文件/命令不存在。
- 规格前后矛盾（例如任务文件和 SPEC 的函数签名不一致）——以 SPEC 为准还是任务为准，不要猜，报告。
- 真实数据跑出来的数字和任务文件里写的期望值不一致（例如条目数不是 3821）。
- 需要新增依赖、新增配置项、新增错误码、新增文案。
- 测试只有放宽断言才能通过。**不准放宽断言。**
