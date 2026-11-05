## T01: 锁定依赖安装因 DNS 解析失败而阻塞

- 位置：`docs/SPEC.md` §2.1、`docs/tasks/T01-scaffold.md`「验收命令」。SPEC 要求安装失败时停止报告，不得更换版本。
- 现象：已写入 T01 测试和逐字提取的 `pyproject.toml`，并用 `uv venv --python 3.11 .venv` 创建 Python 3.11.18 环境。执行 `uv pip install --python .venv/bin/python -e '.[dev]'` 时，访问 `https://pypi.org/simple/pillow/` 的 DNS 解析失败（`Temporary failure in name resolution`），退出码为 2；因此尚未完成规定的测试红灯、实现、ruff 和全量 pytest。
- 可选方案：恢复该环境在验收依赖安装期间的 PyPI DNS/网络访问后重跑 T01；或由外部准备包含规格全部锁定版本及所需构建依赖的本地安装缓存后重跑 T01。依赖版本与断言均不调整。

> 已解决（2026-11-05 17:50 JST，外部协调者）：Codex 沙箱无网络。已在沙箱外用 `uv pip install` 把 SPEC §2.1 的全部锁定版本（及 setuptools==80.9.0）装进 `.venv/` 并预热 uv 缓存，版本未改。沙箱内可用 `uv pip install --offline --python .venv/bin/python -e '.[dev]'` 代替联网安装；协调者在沙箱外复跑原样验收命令。

## T01: 锁定 Ruff 的 Markdown 格式检查与只读文档规则冲突

- 位置：`docs/SPEC.md` §2.1、§2.3；`docs/AGENTS.md` §1.5、§1.11、§4.5；`docs/tasks/T01-scaffold.md`「要创建/修改的文件」及「验收命令」。
- 现象：锁定的 `ruff 0.17.3` 执行 `.venv/bin/ruff format --check .` 时检查 Markdown 内的 Python 代码块，报告 `docs/SPEC.md` 和多张任务卡共 20 个只读文件需要格式化，退出码 1；T01 的 Python 文件已通过格式检查，但验收在此中止。规格要求 `pyproject.toml` 逐字写入、不得修改 Ruff 规则，且禁止修改这些文档，因此无法在现有授权内使验收通过。未修改上述文档、配置和验收命令。
- 可选方案：由外部协调者统一授权在 Ruff 配置中排除 `docs/` 并更新 SPEC §2.3；或由外部协调者把所有任务的格式检查命令改为仅检查实现和测试文件；或由外部协调者统一格式化只读需求中的代码块。Codex 不自行选择方案。

> 已解决（2026-11-05 JST）：采用方案 1，SPEC §2.3 已加 extend-exclude = ["docs"]（提交 8e7c39d），pyproject.toml 已同步。

## T10: 四象限前景测试与阴影规则冲突

- 位置：`docs/SPEC.md` §8.2「前景掩码」及 `docs/tasks/T10-images.md`「输入/输出示例」「测试」中的四象限断言。
- 现象：四象限图包含约 25% 黑色（Lab 的 L 约为 0）、25% 白色、25% 绿色、25% 红色。任务卡要求 `foreground_mask(lab, drop_highlights=True).mean()` 约为 0.75，说明只删除白色高光；但 §8.2 又要求在掩码选出的像素上应用阴影规则，`keep = L >= SHADOW_L`，且保留比例约 2/3 大于 `SHADOW_KEEP_MIN_FRAC=0.15`，因此会删除黑色象限，结果约为 0.50。`apply_shadow_rule` 的独立测试同时明确要求此类 L<8 像素在保留比例足够时被删除。
- 可选方案：A. `foreground_mask` 按 §8.2 应用阴影规则，并将四象限期望改为约 0.50；B. `foreground_mask` 只做背景/高光掩码，阴影规则仅由调用方另行应用，从而保留四象限期望 0.75；C. 明确其他阴影适用条件或调整合成图/断言。需要确认后才能实现。


## T10: 四象限前景测试与阴影规则冲突 — 已解决（方案 B）
`foreground_mask` 只做背景/高光，不删阴影；阴影由 `apply_shadow_rule` 在取色（§8.3）里单独调用。SPEC §8.2 与 T10 任务卡已改清。四象限期望仍为 0.75。
