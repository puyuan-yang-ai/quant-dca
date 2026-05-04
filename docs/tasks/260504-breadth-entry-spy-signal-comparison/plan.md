# 实施方案：BreadthEntry 策略 + SPY 全量信号比较

## 整体流程

分两轮运行，中间需要人工审核：

```
第一轮：NDay 参数选择 → 人工审核 → 确定最优 N
第二轮：7 策略全量比较（含 BreadthEntry + 最优 N 的 AND/OR 组合）
```

## 变更范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/modules/entry.py` | 修改 | 新增 `BreadthEntry` 类 |
| `scripts/compare_signals.py` | 修改 | 支持两轮比较 |

---

## 第一步：新增 BreadthEntry 类

在 `src/modules/entry.py` 中新增，放在 `RSISignalEntry` 之后：

```python
class BreadthEntry:
    """
    Market Breadth 驱动入场

    Breadth < threshold 时买入。
    构造时传入 Breadth CSV 路径，预计算满足条件的日期集合。
    """

    def __init__(self, breadth_csv, threshold=20):
        self.threshold = threshold
        self._buy_dates = self._load_buy_dates(breadth_csv, threshold)

    @staticmethod
    def _load_buy_dates(csv_path, threshold):
        import csv as csv_mod
        buy_dates = set()
        with open(csv_path, 'r') as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                if float(row['breadth']) < threshold:
                    buy_dates.add(row['date'])
        return buy_dates

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False
```

设计要点：
- 与 `RSISignalEntry` 模式一致：构造时预计算日期集合，运行时只查集合
- 不需要修改 `BacktestEngine` 或 `Context`
- `threshold` 参数化，默认 20，后续可调整

## 第二步：修改 compare_signals.py

### 第一轮：NDay 参数选择

修改 `build_entries()` 函数，增加一个 `mode` 参数：

- `mode='nday_search'`：只跑 NDayConfirm-1 到 NDayConfirm-5
- `mode='full'`：跑完整 7 策略列表

第一轮运行命令：
```bash
python scripts/compare_signals.py --mode nday
```

输出每个 NDay 在 5 个市场环境下的**成本优势比**，用户审核后确定最优 N。

### 第二轮：全量比较

用户确认最优 N 后运行：
```bash
python scripts/compare_signals.py --mode full --best-nday N
```

构建 7 个策略（含 BreadthEntry、最优 N 的 AND/OR 组合），输出完整对比表格和排名。

## 执行顺序

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | 在 entry.py 新增 BreadthEntry 类 | 新模块可导入 |
| 2 | 修改 compare_signals.py 支持 `--mode nday` | 脚本支持两种模式 |
| 3 | 运行第一轮：`--mode nday` | NDay 1-5 的成本优势比对比表 |
| 4 | **人工审核**，确定最优 N | 用户决策 |
| 5 | 运行第二轮：`--mode full --best-nday N` | 7 策略全量对比 + 排名 |
| 6 | 记录结果到 report.md | 完整分析报告 |
