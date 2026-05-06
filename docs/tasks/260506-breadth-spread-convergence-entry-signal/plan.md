# 计划：Breadth 曲线 spread 收敛买入信号实验

## Step 1：实现 SpreadConvergenceEntry 入场模块

在 `src/modules/entry.py` 中新增 `SpreadConvergenceEntry` 类，实现状态机逻辑：

```python
class SpreadConvergenceEntry:
    def __init__(self, breadth_csv, close_threshold=None, require_c1_rising=False):
        # close_threshold: c3-c1 < X 时停止买入（None = 无停止条件）
        # require_c1_rising: True = 实验B（需方向确认），False = 实验A
        # 从 CSV 加载 breadth, breadth_c3, breadth_c5
        # 预计算状态机，输出买入日期集合
```

状态机预计算逻辑：
1. 逐日遍历，维护当前状态（WAITING / OBSERVING / STOPPED）
2. WAITING → c1 < 20 → OBSERVING，记录昨日 spread
3. OBSERVING → 检查 spread 收敛（+ 可选方向确认）→ 买入
4. OBSERVING → c3 - c1 < close_threshold → STOPPED
5. OBSERVING / STOPPED → c1 >= 20 → WAITING

## Step 2：接入 compare_signals.py

新增搜索模式 `--mode spread-convergence`：

- 实验 A：5 组停止条件（1, 2, 3, 5, 无）× require_c1_rising=False
- 实验 B：5 组停止条件（1, 2, 3, 5, 无）× require_c1_rising=True
- 共 10 次回测

## Step 3：执行搜索

```bash
python scripts/compare_signals.py --mode spread-convergence
```

## Step 4：结果分析与沉淀

- 结果写入 `result.md`
- 对比实验 A vs B，找最优停止条件
- 与 breadth<20（+6.63%）和 breadthC3<20（+9.77%）对比
- 有价值的结果写入 `ground-truth.md`
