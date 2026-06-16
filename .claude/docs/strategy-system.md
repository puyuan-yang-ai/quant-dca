# 策略系统与实验框架（完整版）

CLAUDE.md 只保留宪法级规则，本文件是可组合策略、信号比较方法论、实验框架的实施细则。

## 回测路径

- **引擎路径（主系统）**：`run_experiments.py` / `scripts/show_chart.py` → `src/backtest_engine.py`。有状态的 `BacktestEngine` 类 + `ComposableStrategy`。**策略研究一律走这条路径。**
- **旧版路径（勿用于研究）**：`main.py` → `src/backtest.py`，由 `config/` 下 YAML 驱动，仅支持 baseline。

## 可组合策略系统

`ComposableStrategy`（`src/strategies/composable.py`）把 4 个独立模块组装成完整策略。每日决策流程：**档口 → 入场 → 仓位 → 止盈**。模块在 `src/modules/`：

| 模块 | 文件 | 实现类 |
|------|------|--------|
| 档口（限价挂单价格层级，距开盘价跌幅%） | `tiers.py` | `FixedTiers`、`VolatilityTiers` |
| 入场（当日是否下市价单/挂限价单） | `entry.py` | `UnconditionalEntry`、`EMAFilterEntry`、`NDayConfirmEntry`、`RSISignalEntry`、`BreadthEntry`、`VIXEntry`、`SafeHavenEntry`、`BreadthConsecutiveEntry`、`SpreadConvergenceEntry`、`BreadthDivergenceEntry`、`AndEntry`、`OrEntry` |
| 仓位（各档买入股数） | `position.py` | `FixedPyramid`、`AdaptivePyramid`、`DowntrendOnly` |
| 止盈（何时卖出并将利润分流至 SMH） | `take_profit.py` | `NoTakeProfit`、`DeviationPeakTP`、`TrendConfirmTP`、`DualTakeProfit` |

`AndEntry`/`OrEntry` 是入场组合器（旧文档曾误称 `CombinedAndEntry`/`CombinedOrEntry`，不存在）。

## 信号比较方法论（铁律）

比较不同 Entry 模块时**必须用标准化执行层**，消除执行层差异，纯比较信号质量：

```python
tiers       = FixedTiers(drops=())        # 只有市价单
position    = FixedPyramid(market_shares=1)  # 固定买 1 股
take_profit = NoTakeProfit()              # 不止盈
```

流程：标准化执行快速筛信号 → 锁定最优信号后再精细调优执行层。详见 `docs/tasks/260419-rsi-signal-comparison-and-strategy-reflection/strategy-comparison-guide.md`。

## 实验框架（4 阶段逐步优化）

`experiments/` 执行 4 阶段，每阶段锁定上阶段最优后只调一个维度：

1. **档口**：固定比例 vs 波动率自适应
2. **入场**：锁定最优档口
3. **仓位**：锁定档口 + 入场
4. **止盈**：锁定档口 + 入场 + 仓位

每阶段在 6 个市场环境（`bear` / `bull` / `bear-bull` / `bull-bear` / `all` / `ml-test`）下测试所有变体，用加权综合 Sharpe/Calmar 评分。参数配置在 `experiments/configs.py`（Python 代码，非 YAML），报告由 `experiments/reporter.py` 生成，结果输出到 `experiments_result/`。

## 最优组合（以代码为准）

当前锁定的最优组合定义为 `experiments/configs.py` 的 `BEST_*` 常量（`BEST_TIERS` / `BEST_ENTRY` / `BEST_POSITION` / `BEST_TP`）。**不要在别处复刻这些值——以 configs.py 实际定义为准，那里改了这里自动跟随。**

## 实验结论与易腐数值

以下为方向性结论（精确数值会随数据/参数重跑漂移，需要数字时查对应 task 文档或重跑）：

- VIX>30 入场在情绪类信号中综合最优，SafeHaven 垫底。详见 `docs/tasks/260504-sentiment-indicators-vix-pcr-safehaven/`。
- `BreadthEntry`（Breadth<20）、`BreadthDivergenceEntry`（价格新低但 Breadth 未新低，近三年信号稀少）有正成本优势。详见 `docs/tasks/260505-market-breadth-divergence-entry/`。
- Oracle 基准极值（日线/周线极值利用率分母）见 `docs/ground-truth.md`。
