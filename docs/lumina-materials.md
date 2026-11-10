# Lumina 耗材与 LUT 交付说明

本目录为 filament-picker（`https://filament.ibaozi.com`，非商业、小规模公益站点）准备 Lumina-Layers 自托管 fork 的离线耗材 seed。源码 fork 地址是 `https://github.com/a523959108-rgb/filament-lumina`；Lumina 自身代码仍按 AGPL-3.0-only 及其第三方声明发布。

## LUT 选择

完整机器可读清单见 [`deploy/lumina/materials-seed/lut-selection.json`](../deploy/lumina/materials-seed/lut-selection.json)。当前建议预装 `lut-preset/bambulab/bambulab_pla_basic_rybw.npy` 和 `lut-preset/bambulab/bambulab_pla_basic_cmyw.npy`，分别对应 RYBW（红、黄、蓝、白）与 CMYW（青、品红、黄、白）四通道。`_new` CMYW、Custom 下的 Bambulab RYBW/CMYW/8 色/BW 文件都保留为可手选参考，但不设为默认，原因是修订版本或实测条件没有在文件名中完整表达，且六/八/二色的槽位与本次四色托盘不同。

Lumina 的 `utils.lut_manager.LUTManager` 从源码根的 `lut-preset/` 递归发现预设。已检查这些文件在 Lumina git 中被跟踪，所以自托管部署只要保留源码发行包中的 `lut-preset/` 即可；不需要把 LUT 另打进耗材 ZIP。若部署工具会裁剪源码目录，必须把整个 `lut-preset/` 作为运行时资源一并打包。

## Seed 内容与真实格式

运行 `build_seed.py` 会读取本仓库只读快照 `data/build/filament-catalog.json`，筛选 Bambu Lab 的 PLA Basic、PLA Matte 条目，要求 `hex_source` 为 `official`，并排除渐变/多色条目。当前快照生成 55 条档案，覆盖 `data/four-color-tray-map.json` 的 RYBW 与 CMYW 槽位，并包含常用 Basic/Matte 颜色。

输出是确定性的 ZIP：

```text
lumina-materials-seed-20261106.zip
├── materials/Bambu Lab/<系列 - 颜色 [色号]>/material.json
├── materials/Bambu Lab/<系列 - 颜色 [色号]>/stage_A_parameters.json
└── lumina_material_bundle.json
```

`lumina_material_bundle.json` 使用 Lumina 的 `kind=lumina_material_bundle`、`schema_version=2.0`。每个 package 含 `material_id`、`revision_id`、`content_hash=sha256:<hex>`、`local_directory`、display 信息及必需文件记录。文件记录保存字节数和 SHA256；content hash 按 Lumina 的 `material.json:<hash>`、`stage_A_parameters.json:<hash>` 两行规则计算。ZIP 条目按路径排序、时间戳固定为 2020-01-01 00:00:00，JSON 使用 UTF-8、`ensure_ascii=False`、缩进 2 格并以换行结束，因此相同输入的 ZIP 字节和 `.sha256` 会相同。

每个 `material.json` 都明确写有 `catalog_id`、`material_product_id`、`material_profile_id`、官方 hex 来源和以下文字：**近似（由官方 hex 估算，非实测光谱/透光数据）**。Stage-A `E` 是 sRGB hex 转线性 RGB 后乘固定保守比例 0.35，`k=[2,2,2]`，白底 `C0=[1,1,1]`，黑底 `C0=[0.01,0.01,0.01]`。Lumina 所需的 TD/透光率等实测物理量并不在选色站目录中，因此没有伪造测量值；这些占位参数只能用于启动和预览，不能代替实际梯度色卡校准。正式打印前应在目标打印机、层高、喷嘴和填充条件下重新拍摄白/黑底梯度卡，导入 Lumina 后覆盖或合并档案。

## 构建、校验与首次启动

在仓库根目录执行：

```bash
/workspace/lumina-venv/bin/python deploy/lumina/materials-seed/build_seed.py
/workspace/lumina-venv/bin/python deploy/lumina/materials-seed/build_seed.py --verify \
  --seed deploy/lumina/materials-seed/dist/lumina-materials-seed-20261106.zip
```

`--verify` 会把 Lumina 的 Python 源码复制到临时目录，设置临时 `LUMINA_MATERIALS_DIR`，调用 Lumina 自己的 `install_material_seed_if_needed`，验证 ZIP、文件 SHA256、Stage-A 参数和安装索引，并列出安装数量与档案。这样不会写入源码 checkout 或真实用户耗材目录。

部署到 C 服务器时，把 ZIP 和 `.sha256` 放在部署可读目录，设置（变量名来自 Lumina `api/material_seed.py`）：

```text
LUMINA_MATERIALS_SEED_PATH=/srv/lumina-seed/lumina-materials-seed-20261106.zip
LUMINA_MATERIALS_SEED_SHA256=<.sha256 文件中的 64 位摘要>
LUMINA_MATERIALS_DIR=/srv/lumina-data/materials
```

启动时只有目标耗材库为空才会安装；已有用户档案不会被覆盖。更新 seed 前先备份 `LUMINA_MATERIALS_DIR`，再换路径或清空目录进行一次有意的首次安装。也可以通过 Lumina 耗材库 UI 的「导入」导入同一个 ZIP；它接受 Lumina v2 material bundle ZIP，不接受 `.sha256` 文件。

外部截图执行者可在 box 上按上述环境变量启动自建 Lumina，打开耗材库确认档案列表；若使用 UI，则选择 `lumina-materials-seed-20261106.zip`，导入完成后应看到 Bambu Lab 的 PLA Basic/PLA Matte 档案。截图不在本任务中生成。

## 更新流程

1. 更新选色站数据快照后，先核对 RYBW/CMYW 托盘映射和 `hex_source=official`，确认没有把渐变、透明或碳纤条目混入普通 PLA seed。
2. 重新运行构建脚本和 `--verify`，比较两次构建 SHA256；若 Lumina schema 或导入校验发生变化，先按上游 `api/material_seed.py`、`core/single_stage/material_package.py` 与测试修正生成器。
3. 用新 ZIP 的摘要更新部署环境变量，保留旧 ZIP 以便回滚；部署后只在明确为空的耗材目录验证首次安装。
4. LUT 更新单独遵循 `lut-selection.json`，从 Lumina 源码版本中核对 git 跟踪状态和通道顺序，不把 LUT 放入耗材 seed。
