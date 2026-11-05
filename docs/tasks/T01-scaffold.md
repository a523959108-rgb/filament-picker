# T01 — 仓库脚手架、常量与 schema 校验

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M0 | — | 半天 | AGENTS.md 全文；SPEC §0–§4、§11 |

## 目标
建立可安装的 Python 包 `filament_picker`：锁定版本的 `pyproject.toml`、全部常量 `config.py`、4 个 JSON Schema 的校验函数、带 `--version` 和 `validate` 子命令的 CLI 骨架、pytest 公共 fixture。之后所有任务都在这个骨架上加东西。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- `/workspace/dev/filament-picker/docs/` 存在，里面有 `SPEC.md`、`AGENTS.md`、`schemas/`、`fixtures/`。
- `uv --version` 能运行；`/home/box/.local/share/uv/python/` 下有 cpython-3.11。
- 仓库里除 `docs/` 外没有别的文件（有 → 停下报告）。

## 要创建/修改的文件（只能动这些）
- `pyproject.toml`（SPEC §2.3 **逐字**）、`.python-version`（内容 `3.11`）、`.gitignore`（SPEC §3 列出的那几行）、`README.md`（一段话 + §11 常用命令）
- `AGENTS.md`（`cp docs/AGENTS.md AGENTS.md`，不准改内容）
- `src/filament_picker/__init__.py`、`config.py`、`validate.py`、`cli.py`
- `src/filament_picker/schemas/*.schema.json`（`cp docs/schemas/*.schema.json src/filament_picker/schemas/`，逐字节相同）
- `tests/conftest.py`、`tests/test_config.py`、`tests/test_validate.py`、`tests/test_cli.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
# __init__.py
__version__ = "0.3.0"

# config.py —— SPEC §4 表中每个常量逐字定义为模块级常量（名字、值、类型一致；元组就写元组）
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
TZ: str = "Asia/Tokyo"
MAX_SLUG_LEN: int = 60
# ……§4 其余全部常量……
# 注意：错误码文案 ERROR_MESSAGES 不在这里，在 T10 的 errors.py

@dataclass(frozen=True, slots=True)
class Settings:
    root: Path
    catalog: Path
    card_base_url: str | None
    shots_dir: Path
    font_regular: Path
    font_bold: Path
    font_index: int

def get_settings() -> Settings: ...
    # 每次调用都重新读 os.environ（SPEC §2.4 的 7 个变量与默认值）
    # FP_CARD_BASE_URL 设置了但不以 "https://" 开头 → raise ValueError("FP_CARD_BASE_URL must start with https://")
    # FP_CARD_BASE_URL 为空串视为未设置

# validate.py
SCHEMA_FILES: dict[str, str] = {"catalog": "filament-catalog.schema.json", "lock": "ids.lock.schema.json",
                                "request": "request.schema.json", "result": "result.schema.json"}
class SchemaValidationError(ValueError):
    def __init__(self, name: str, errors: list[str]) -> None: ...
def load_schema(name: str) -> dict[str, Any]: ...        # functools.cache；从包内 schemas/ 读（importlib.resources）；未知 name → KeyError
def validate_json(name: str, obj: Any) -> list[str]: ... # Draft202012Validator；每条错误格式 f"{路径或 '<root>'}: {message}"，路径用 "/" 连接；结果排序
def assert_valid(name: str, obj: Any) -> None: ...      # 有错误 → raise SchemaValidationError(name, errors)

# cli.py
def build_parser() -> argparse.ArgumentParser: ...  # prog="filament-picker"；--version；subparsers(dest="command")
def main(argv: list[str] | None = None) -> int: ...  # 返回退出码；无子命令 → 打印帮助，返回 2
# 每个子命令写成一个私有函数 _add_<name>(sub) 注册 + 一个 _cmd_<name>(args) -> int 执行。
# 之后的任务只能「新增」_add_xxx/_cmd_xxx 和 build_parser 里的一行调用，不准改已有子命令。

# tests/conftest.py 的 fixtures
@pytest.fixture(scope="session") def repo_root() -> Path
@pytest.fixture(scope="session") def raw_rows(repo_root) -> list[dict]   # json.load(data/raw/page_rows.json)；文件不存在 → pytest.skip("data/raw 未就绪（T02）")
@pytest.fixture(scope="session") def golden_ids(repo_root) -> list[dict]  # docs/fixtures/ids_golden.json 的 "rows"
@pytest.fixture(scope="session") def golden_merges(repo_root) -> list[dict] # docs/fixtures/merges_golden.json 的 "merges"
@pytest.fixture def tmp_root(tmp_path) -> Path   # 在 tmp_path 下建 SPEC §9.1 的 7 个子目录，返回根
```

## 输入/输出示例
```text
$ .venv/bin/filament-picker --version
filament-picker 0.3.0
$ .venv/bin/filament-picker validate request docs/schemas/examples/request.example.json
OK
$ echo '{"schema_version":1}' > /tmp/bad.json && .venv/bin/filament-picker validate request /tmp/bad.json; echo $?
<root>: 'request_id' is a required property
...（每条错误一行）
1
```

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_config.py`
- `config.MAX_SLUG_LEN == 60`、`config.EXTRACT_MIN_CONF == 0.40`、`config.MATCH_MAX_DE == 10.0`、`config.MATCH_MIN_CONF == 0.5`、`config.MERGE_DE == 6.0`、`config.SMALL_SHARE == 0.02`、`config.LABEL_THRESHOLDS == ((2.0,"几乎一样"),(5.0,"接近"),(10.0,"勉强"))`、`config.SOURCE_RANK == {"official":0,"store_swatch":1,"manual":2,"image_extracted":3}`、`config.CARD_TOKEN_BYTES == 24`、`config.RETENTION_DAYS == 7`。
- 用一个参数化测试把 SPEC §4 表里**每一个**常量都断言一遍（表里有多少个就写多少个）。
- `config.CONF_PENALTY_FACTOR == 0.6`；`config.HIGHLIGHT_L == 92.0`；`config.HIGHLIGHT_C == 10.0`（「A / B」写法的行拆成两个常量）。
- `monkeypatch.delenv` 掉 7 个 FP_ 变量后：`get_settings().root == Path("/home/box/agent-data/shared/filament-picker")`，`.card_base_url is None`，`.font_index == 2`，`.catalog == REPO_ROOT/"data/build/filament-catalog.json"`。
- `FP_CARD_BASE_URL="http://x.example.invalid"` → `pytest.raises(ValueError)`；`"https://x.example.invalid/c"` → 原样返回；`""` → None。
- `FP_FONT_INDEX="0"` → `font_index == 0`（int）。

`tests/test_validate.py`
- `docs/schemas/examples/` 下 5 个例子各自对应 schema 校验结果为 `[]`（catalog / lock / request / result / result.error→result）。
- 包内 `schemas/*.schema.json` 与 `docs/schemas/*.schema.json` 逐字节相等（4 个文件）。
- 把 catalog 例子第 1 个条目的 `hex` 改成 `["#00ae42"]`（小写）→ 错误列表非空，且至少一条以 `entries/0/hex/0` 开头。
- request 例子 `context` 里加 `"sessionWebhook": "x"` → 错误列表非空。
- `assert_valid("request", {})` → `pytest.raises(SchemaValidationError)`。
- `load_schema("nope")` → `pytest.raises(KeyError)`。

`tests/test_cli.py`
- `main(["--version"])` 打印 `filament-picker 0.3.0`（用 `capsys`；argparse 的 version action 会 SystemExit(0)，断言退出码 0）。
- `main(["validate","request","docs/schemas/examples/request.example.json"]) == 0` 且 stdout 为 `OK\n`。
- 不合法文件 → 返回 1，stdout 至少 1 行。
- `main([]) == 2`。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && test -d .venv || uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -e '.[dev]' && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q && .venv/bin/filament-picker --version && cmp AGENTS.md docs/AGENTS.md && diff -r docs/schemas/ src/filament_picker/schemas/ -x examples
```

## 不要做
- 不要写任何业务模块（ingest、names……），哪怕是空文件。
- 不要改 pyproject 里的版本号、依赖、ruff 规则（逐字照抄 SPEC §2.3）。
- 不要用 pydantic、click、typer。
- 不要创建 `data/` 下的任何文件。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
