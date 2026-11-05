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

## T12: 官方校准行数与单色筛选条件不一致

- 位置：`docs/tasks/T12-batch-extract-calibrate.md`「接口签名」`calibrate` 筛选规则、测试断言和验收命令；`data/build/filament-catalog.json` 的 Bambu 条目。
- 现象：真实目录中有商品图的 Bambu 条目共 43 条，但其中 `bambu-lab/pla-silk-multi-color/blue-hawaii-13904`、`bambu-lab/pla-silk-multi-color/midnight-blaze-13902`、`bambu-lab/pla-silk-multi-color/neon-city-13903` 的 `hex` 各有 2 个值。严格按 `hex_source == "official"` 且 `len(hex) == 1` 且提取结果 `status == "ok"` 筛选，`calibrate` 官方行数为 40；验收命令要求最后输出 `bambu n=43`，无法同时满足两者。
- 可选方案：A. 保持 `len(hex)==1` 规则，将验收期望和测试断言改为 `bambu n=40`；B. 官方校准包含这 3 个多色条目并定义多 hex 的比较规则（例如逐色或聚合），保留 `n=43`；C. 修改目录中这 3 个条目的官方 hex 结构。需要明确后才能完成 T12 校准验收。


## T12: bambu calibrate n=43 vs n=40 — 已解决（方案 A）
保持 `len(hex)==1` 过滤；验收改为 `bambu n=40`。3 条多色丝绸不参与单色 ΔE 校准。参考：median 8.0 / p80 14.6。

## T15: #00AE42 金标 ΔE00 四舍五入结果矛盾

- 位置：`docs/SPEC.md` §6.2、§9.4；`docs/tasks/T15-matcher.md`「测试」金标表。
- 现象：按 §6.2 的 CIEDE2000 公式，用 T15 要求的 `PaletteColor.lab=(62.22, -60.41, 43.97)` 和 M0 目录条目 `bambu-lab/pla-lite/green-16501` 的 `lab=[66.34, -66.06, 55.35]` 计算，结果为 `4.696922525...`，按「delta_e 输出 round 2 位」应为 `4.70`；SPEC/T15 金标同时写死为 `4.69`。使用未取整的 `#00AE42` Lab 也得到 `4.696081879...`，仍为 `4.70`。当前 T15 测试因此失败，不能在不改变算法、阈值或断言的情况下完成。
- 可选方案：A. 保持 §6.2 和标准四舍五入，将金标期望改为 `4.70`；B. 明确参考实现的 CIEDE2000/取整差异，使该值计算为 `<4.695` 并保留 `4.69`；C. 明确 `delta_e` 的非标准截断规则。需要确认后才能继续 T15。


## T15: green-16501 ΔE 4.69 vs 4.70 — 已解决（方案 A）
标准 `round(ΔE, 2)`；金标改为 4.70。

## T15: price_text 空串 — 已解决
匹配结果输出用 `price_text or None`（空串 → null），与 result.example.json / schema 一致。

## T16: card_height(3) 示例与公式矛盾

- 位置：`docs/SPEC.md` §9.6「画布」及 `docs/tasks/T16-card.md`「输入/输出示例」。
- 现象：按任务卡和 SPEC 写死的公式 `40 + 120 + max(360, 140*n) + 60 + 40`，`card_height(3)` 应为 680；同一任务卡明确断言 `card_height(3) == 620`。测试按该断言运行失败，无法同时满足公式和示例。
- 可选方案：A. 保留公式，将 `card_height(3)` 期望改为 680；B. 保留 620 期望，明确高度公式在 3 色时的特殊规则；C. 统一修改 SPEC 与 T16 任务卡中的其中一项。需要确认后才能完成 T16。
