# Market Breadth 入场策略 + SPY 全量信号比较

## 背景

前置任务（260504-sp500-market-breadth-chart-integration）已完成 S&P 500 Market Breadth 指标的计算和可视化。现在要将其从"观察指标"升级为"可回测的入场策略"，并通过标准化信号比较框架评估其择时质量。

此外，项目从 SOXL 切换到 SPY 后，尚未重新评估各 Entry 策略的排名。当前 `BEST_ENTRY = NDayConfirmEntry(n_days=5)` 是 SOXL 时代的结论，SPY 下的最优 NDay 参数可能不同。本次需要重新确认。

## 需求

### 1. 新建 BreadthEntry 入场模块

在 `src/modules/entry.py` 中新增 `BreadthEntry` 类：

- **买入条件**：当天 Breadth < 20 时触发买入（恐慌区抄底），Breadth < 20 是唯一触发信号
- **数据来源**：读取预计算好的 `data/sp500_breadth.csv`
- **实现方式**：方案 A（与 `RSISignalEntry` 一致），构造时预计算所有 Breadth < 20 的日期集合，`should_market_buy()` 只查日期匹配

### 2. 分两步确定 SPY 最优策略

#### 第一步：确定 SPY 下最优的 NDay 参数

跑 NDayConfirm-1 到 NDayConfirm-5，在 5 个市场环境下对比**成本优势比**，人工审核后确定最优 N。

成本优势比直接反映"择时有没有让你买得更便宜"，比 Sharpe 更适合用来选参数。

#### 第二步：用最优 N 构建最终策略列表做全量比较

确认最优 N 后，构建 7 个策略做全量比较：

| # | 策略 | 说明 |
|---|------|------|
| 1 | Unconditional | 无条件每天买 |
| 2 | EMAFilter | EMA 过滤 |
| 3 | NDayConfirm-**N** | SPY 下最优 N（第一步确定） |
| 4 | RSISignal | RSI v2 信号 |
| 5 | AND-NDay**N**+RSI | 最优 N 且 RSI |
| 6 | OR-NDay**N**+RSI | 最优 N 或 RSI |
| 7 | Breadth<20 | Breadth 恐慌买入（新增） |

### 标准化执行层（统一配置）

```python
tiers     = FixedTiers(drops=(0.02, 0.05, 0.10))
position  = FixedPyramid(market_shares=1, limit_shares=(0, 0, 0))
take_profit = NoTakeProfit()
```

市价单买 1 股、限价单份额全为 0、不止盈。消除执行层差异，纯粹比较信号质量。
