# 计划：Breadth 连续弱势曲线阈值搜索

## Step 1：新建 BreadthConsecutiveEntry 入场模块

在 `src/modules/entry.py` 中新增 `BreadthConsecutiveEntry` 类：

```python
class BreadthConsecutiveEntry:
    def __init__(self, breadth_csv, n, threshold):
        # n: 连续天数（2/3/4/5）
        # threshold: 买入阈值，breadth_cN < threshold 时触发
        # 从 CSV 加载 breadth_cN 列，预计算买入日期集合

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False
```

## Step 2：接入 compare_signals.py

在 `scripts/compare_signals.py` 中新增搜索模式 `--mode breadth-consecutive`：

- 对 c2~c5 四条曲线，各自遍历阈值 20, 22, 24, 26, 28, 30, 32, 34
- 使用标准化执行层（市价买 1 股、无限价、不止盈）
- 输出各组合的成本优势比排名

## Step 3：执行搜索

运行：

```bash
python scripts/compare_signals.py --mode breadth-consecutive
```

## Step 4：结果分析与沉淀

- 整理各曲线最优阈值 + 成本优势到 `note.md`
- 与 breadth < 20（成本优势 +6.63%）做对比
- 判断是否值得加入 ground-truth.md
