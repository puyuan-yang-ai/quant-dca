# 实施方案

## Step 1：重构 entry.py — 通用组合器

**新增**两个通用类：

```python
class AndEntry:
    def __init__(self, entry_a, entry_b):
        self.a, self.b = entry_a, entry_b
    def should_market_buy(self, context):
        return self.a.should_market_buy(context) and self.b.should_market_buy(context)
    def should_place_limits(self, context):
        return False

class OrEntry:
    def __init__(self, entry_a, entry_b):
        self.a, self.b = entry_a, entry_b
    def should_market_buy(self, context):
        return self.a.should_market_buy(context) or self.b.should_market_buy(context)
    def should_place_limits(self, context):
        return False
```

**删除**以下 4 个类：
- `CombinedAndEntry`、`CombinedOrEntry`（NDay + RSI 组合）
- `BreadthAndRSIEntry`、`BreadthOrRSIEntry`（Breadth + RSI 组合）

**同步修改引用**：
- `scripts/compare_signals.py`：`CombinedAndEntry` → `AndEntry(NDayConfirmEntry(5), RSISignalEntry(data))`，同理 OR
- `scripts/compare_signals.py` 的 `build_entries_full()`：更新所有组合策略的构建方式

## Step 2：准备周线 VIX 数据

VIX CSV 是日线日期，周线回测需要周一日期。方案：

- 重采样 `data/vix_daily.csv` 为周频（取每周最大值，因为关注"该周是否出现恐慌"）
- 保存为 `data/vix_weekly.csv`（date, close），日期对齐 SPY 周线
- 可在 `scripts/fetch_weekly_data.py` 中新增此逻辑

## Step 3：跑日线 6 个组合

在 `scripts/compare_signals.py` 的 `build_entries_full()` 中加入 6 个新组合，或写一个独立脚本。标准化执行层，近三年全量环境。

6 个组合：
- `AndEntry(NDayConfirmEntry(5), BreadthEntry(breadth_csv))`
- `OrEntry(NDayConfirmEntry(5), BreadthEntry(breadth_csv))`
- `AndEntry(VIXEntry(vix_csv, 30), BreadthEntry(breadth_csv))`
- `OrEntry(VIXEntry(vix_csv, 30), BreadthEntry(breadth_csv))`
- `AndEntry(VIXEntry(vix_csv, 30), NDayConfirmEntry(5))`
- `OrEntry(VIXEntry(vix_csv, 30), NDayConfirmEntry(5))`

## Step 4：跑周线 6 个组合

同 Step 3，但使用周线数据文件（SPY_weekly.csv、SMH_weekly.csv、sp500_breadth_weekly.csv、vix_weekly.csv），`periods_per_year=52`。

## Step 5：更新 GT 表

- 日线结果追加到 `docs/ground-truth.md` 指标总表，含 Oracle极值 和 极值利用率
- 周线结果追加到周线指标总表
- 更新两个表下方的 Insight

## 执行顺序

```
Step 1 → 重构 entry.py + 更新引用
Step 2 → 准备周线 VIX 数据
Step 3 → 跑日线 6 个组合
Step 4 → 跑周线 6 个组合
Step 5 → 更新 GT 表 + Insight
```

Step 1 和 Step 2 独立，可并行。Step 3/4 依赖 Step 1/2。Step 5 依赖 Step 3/4。
