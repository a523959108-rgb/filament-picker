# T09 — k-means

| 里程碑 | 前置任务 | 预计 | 必读 |
|---|---|---|---|
| M1 | T01 | 半天 | SPEC §7 |

## 目标
用 numpy 实现确定性的 k-means++（Lab 欧氏距离）和采样函数，取色（T11）与配色（T14）共用。

## 前置条件（开始前逐条检查；任何一条不满足 → 停下报告，不要自己补）
- T01 验收通过。

## 要创建/修改的文件（只能动这些）
- `src/filament_picker/kmeans.py`
- `tests/test_kmeans.py`

## 接口签名（逐字实现：名字、参数顺序、默认值、返回类型都不能改）
```python
def sample_pixels(X: np.ndarray, max_n: int, seed: int = 0) -> np.ndarray: ...
    # X: (n,3) float64；n <= max_n 原样返回（同一个对象也可以）；否则无放回抽 max_n 行（default_rng(seed).choice）
def kmeans(X: np.ndarray, k: int, seed: int = 0, max_iter: int = KMEANS_MAX_ITER,
           tol: float = KMEANS_TOL) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...
    # 返回 (centers (k',3) float64, labels (n,) int64, shares (k',) float64)，k' = min(k, X 中不同行数)
    # 严格按 SPEC §7 伪代码；len(X) == 0 或 k < 1 → ValueError
```

## 输入/输出示例
```python
rng = np.random.default_rng(1)
X = np.vstack([np.array([20.0, 0, 0]) + rng.uniform(-0.5, 0.5, (500, 3)),
               np.array([80.0, 0, 0]) + rng.uniform(-0.5, 0.5, (500, 3))])
centers, labels, shares = kmeans(X, 2)
# centers 按任意顺序 ≈ [[20,0,0],[80,0,0]]；shares ≈ [0.5, 0.5]
```（合成数据，非真实图片）

## 测试（先写测试 → 运行确认失败 → 再写实现）
`tests/test_kmeans.py`
- 两团点（上例）：把 centers 按 L 排序后与 `[[20,0,0],[80,0,0]]` 的欧氏距离都 `< 1.0`；`abs(shares - 0.5).max() <= 0.01`；`shares.sum() == pytest.approx(1.0)`；`labels.shape == (1000,)`。
- 确定性：同输入跑两次，`np.array_equal(centers1, centers2)` 且 labels 完全相同。
- 全相同点：`X = np.tile([50.0, 10, 10], (100, 1))`，`kmeans(X, 4)` → `centers.shape == (1, 3)`，`shares.tolist() == [1.0]`。
- 两个不同点各 50 次，k=6 → `centers.shape == (2, 3)`。
- `kmeans(np.zeros((0, 3)), 2)` → ValueError；`kmeans(X, 0)` → ValueError。
- `sample_pixels(np.zeros((10,3)), 20).shape == (10, 3)`；`sample_pixels(np.arange(300.).reshape(100,3), 20).shape == (20, 3)`，结果中无重复行，两次调用结果相同。

## 验收命令（退出码 0 才算完成；完成报告里贴最后 20 行输出）
```bash
cd /workspace/dev/filament-picker && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest tests/test_kmeans.py -q
```

## 不要做
- 不要用 scikit-learn / scipy；不要换成 mini-batch 或 k-medoids。
- 不要改初始化方式或"多次重启取最优"。
- 不要在这里做簇合并（那是 T14）。
- 不要修改本任务「要创建/修改的文件」以外的任何文件（包括 `docs/`、其他任务的模块和测试、格式化别人的代码）。
- 不要修改 `config.py` / `web/src/config.ts` 里任何常量的值（标「待校准」的也不行）。
- 不要新增、删除或升级依赖（只有 T01 写 `pyproject.toml`，只有 T20 写 `web/package.json`）。
- 不要联网（代码、测试、脚本里都不准；`uv pip install` / `npm ci` / T20 生成 lock 的那一次 `npm install` 除外）。
- 不要 import / 调用 / 提及钉钉 API、sessionWebhook；不要读写 `~/.config/dingtalk/`、`/home/box/.local/share/dingtalk-listener/`、`/workspace/dev/bambu-print-agent*`。
- 不要为了让测试变绿去改断言里的数字或放宽容差；数字对不上 → 停下按 AGENTS.md §5 报告。
