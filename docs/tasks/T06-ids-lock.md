# T06 — 去重、canonical 与 ID 锁定

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M0 | T02 T04 | 半天 | SPEC §5.6–§5.7；docs/schemas/ids.lock.schema.json |

## 目标
把 3845 行合并成 3821 个条目，为每个条目分配稳定 ID，并写入提交进仓库的 `data/ids.lock.json`（只增不改）。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T02、T03、T04 验收通过。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/ids.py`
- `src/filament_picker/cli.py`（只新增 `assign-ids` 子命令）
- `data/ids.lock.json`（**只能由命令生成**）
- `tests/test_ids.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
@dataclass(frozen=True, slots=True)
class RowInfo:
    row: RawRow
    parsed: ParsedName
    brand_slug: str
    series_slug: str
    row_id: str
    dedup_key: str

@dataclass(frozen=True, slots=True)
class AssignStats:
    keys: int
    new: int
    retired: int
    collisions: int        # 正常永远是 0（有冲突会抛异常）

class IdCollisionError(RuntimeError):
    def __init__(self, key: str, new_id: str) -> None: ...

LOCK_PATH: Path = REPO_ROOT / "data" / "ids.lock.json"
DOMESTIC_CHANNEL_WORDS: tuple[str, ...] = ("淘宝", "拼多多", "天猫")

def make_dedup_key(brand_slug: str, series_slug: str, parsed: ParsedName, raw: str) -> str: ...
def build_row_infos(rows: list[RawRow]) -> list[RowInfo]: ...
def group_rows(infos: list[RowInfo]) -> dict[str, list[RowInfo]]: ...  # 按首次出现顺序；组内按 row_index 升序
def canonical(group: list[RowInfo]) -> RowInfo: ...                    # SPEC §5.6 排序键
def empty_lock(today: str, source_sha256: str) -> dict[str, Any]: ...  # {"schema_version":1,"rules_version":"slug-v1","updated_at":today,"source_sha256":..,"entries":{}}
def load_lock(path: Path) -> dict[str, Any] | None: ...               # 不存在 → None；存在 → assert_valid("lock") 后返回
def assign_ids(groups: dict[str, list[RowInfo]], lock: dict[str, Any] | None,
               today: str, source_sha256: str) -> tuple[dict[str, Any], AssignStats]: ...
    # 不修改传入的 lock（先 copy.deepcopy）；lock 为 None 时从 empty_lock 开始；算法 SPEC §5.7
def write_lock(path: Path, lock: dict[str, Any]) -> None: ...
    # assert_valid("lock") → entries 按 key 排序 → json.dumps(ensure_ascii=False, indent=2) + "\n" → tmp + os.replace
```
CLI：`filament-picker assign-ids [--today YYYY-MM-DD]`（默认 Asia/Tokyo 今天）→ 打印 `keys=<n> new=<n> retired=<n> collisions=0`。

## 输入/输出示例
- `make_dedup_key("cailab", "rainbow-shift-pla", ParsedName("Bamboo", None, "RB009"), "Bamboo RB009") == "cailab|code|RB009"`
- `make_dedup_key("eryone", "pla-silk-dual-color", parse_color_name("Red&Blue-3KG"), "Red&Blue-3KG") == "eryone|pla-silk-dual-color|red-blue"`（真实行 1849，与行 1827 `Red&Blue` 同 key → 合并）
- 首次运行：`keys=3821 new=3821 retired=0 collisions=0`；再跑一次：`keys=3821 new=0 retired=0 collisions=0`。
- lock 条目形如（真实）：`"bambu-lab|code|30105": {"id": "bambu-lab/petg-basic/black-30105", "status": "active", "first_seen": "2026-11-05", "last_seen": "2026-11-05"}`

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_ids.py`
- 参数化 `golden_ids` 35 行：对应 RowInfo 的 `dedup_key == row["dedup_key"]`、`row_id == row["row_id"]`。
- `@pytest.mark.data`：`len(group_rows(build_row_infos(rows))) == 3821`；多于 1 行的组恰好 24 个；与 `golden_merges` 逐个比较：dedup_key 集合相等，每组 `canonical(group).row_id == merge["canonical_id"]`，组内 row_index 列表相等。
- `@pytest.mark.data`：所有 canonical row_id 互不相同（3821 个）。
- 首跑 `assign_ids(groups, None, "2026-11-05", "0"*64)` → stats == `AssignStats(3821, 3821, 0, 0)`；把结果再喂回去 `assign_ids(groups, lock1, "2026-11-06", ...)` → `new == 0`，每个 entry 的 `id` 与 `first_seen` 不变，`last_seen == "2026-11-06"`。
- 删掉一个组再跑 → 该 key 仍在 entries 里且 `status == "retired"`，stats.retired == 1；再把组加回来 → 变回 active，id 不变。
- 构造 lock，其中 `"zzz|x|y"` 已占用 id `"bambu-lab/petg-basic/black-30105"`，且不含 `"bambu-lab|code|30105"` → `pytest.raises(IdCollisionError)`。
- `assign_ids` 调用前后传入的 lock 对象 `==` 原副本（未被修改）。
- `write_lock` 到 tmp 两次（同输入）→ 文件字节相同；文件以 `\n` 结尾。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_ids.py -q && .venv/bin/filament-picker assign-ids --today 2026-11-05 && cp data/ids.lock.json /tmp/lock1.json && .venv/bin/filament-picker assign-ids --today 2026-11-05 | grep -x 'keys=3821 new=0 retired=0 collisions=0' && cmp data/ids.lock.json /tmp/lock1.json && .venv/bin/filament-picker validate lock data/ids.lock.json
```

## 不要做
- 不要在冲突时自动加后缀、自动改名、跳过；只能抛 `IdCollisionError`。
- 不要删除 lock 里的任何 key；不要手改 `data/ids.lock.json`。
- 不要把 `rules_version` 改成别的值。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
