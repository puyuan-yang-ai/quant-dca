# Sharpe 计算升级方案

> 目标：在不破坏现有横向比较能力的前提下，新增可与业界对标的 Sharpe 指标和 MWR 年化收益指标。

---

## 1. 改动原则

- **不修改**现有的 Sharpe / 年化收益计算（保持横向比较兼容性）
- **新增** TWR Sharpe 和 MWR 年化收益作为额外指标
- 新指标加入 `calc_all_metrics()` 的返回字典，各脚本按需展示

---

## 2. 需要新增的指标

### 2.1 TWR Sharpe（可对标业界的 Sharpe）

**用途**：让你的 Sharpe 数值能直接跟业界标准（SPY 买入持有 ≈ 0.6~0.7，好的策略 ≥ 1.5）比较。

**计算逻辑**：

```python
def calc_twr_sharpe(data, daily_values, buy_log, risk_free_rate=0.0):
    """
    基于时间加权收益率（TWR）计算 Sharpe

    核心思路：每天的收益率只反映"持仓的市场涨跌"，剥离新资金注入的影响。

    步骤：
    1. 对每个交易日，计算"如果今天没有新买入，市值会是多少"
       → 用昨日持有的股数 × 今日收盘价
    2. 日收益率 = (不含新买入的今日市值 - 昨日市值) / 昨日市值
       → 这就是纯市场回报，不含资金注入
    3. 用这个日收益率序列计算波动率和年化收益
    4. Sharpe = (TWR年化 - Rf) / TWR年化波动率
    """
```

**需要的数据**：
- `daily_values`：每日市值（已有）
- 每日新买入的金额（需要从 trade_log 或 portfolio 中提取）
- 或者更简单：用每日持仓股数 × 每日收盘价来反推

**实现位置**：`src/metrics.py` 新增 `calc_twr_sharpe()` 函数

### 2.2 MWR 年化收益（投资者真实回报）

**用途**：告诉你"考虑到每笔钱投入的时机，你实际赚了多少"。

**计算逻辑**：

```python
def calc_mwr_return(cash_flows, final_value):
    """
    基于资金加权的年化收益率（IRR / XIRR）

    步骤：
    1. 收集所有现金流：每次买入的金额和日期
    2. 最终市值作为最后一笔正向现金流
    3. 用数值方法求解 IRR
       → 即求 r 使得 Σ(CF_i × (1+r)^(T-t_i)) = 0

    cash_flows: [(date, amount), ...]  amount 为负数表示投入
    final_value: 最终市值
    """
```

**需要的数据**：
- 每次买入的日期和金额（从 trade_log 提取）
- 最终市值
- 最终日期

**实现位置**：`src/metrics.py` 新增 `calc_mwr_return()` 函数

---

## 3. 改动文件清单

### 3.1 src/metrics.py（核心改动）

新增两个函数：

```
calc_twr_sharpe(daily_shares, close_prices, daily_buy_costs, risk_free_rate=0.0)
  → 返回 {'twr_sharpe': float, 'twr_annualized_return': float, 'twr_annualized_vol': float}

calc_mwr_return(cash_flows, final_value, final_date)
  → 返回 {'mwr_annualized_return': float}
```

修改 `calc_all_metrics()` 签名，新增参数接收 trade_log 数据，在返回字典中补充新指标。

### 3.2 src/backtest_engine.py（传递数据）

`BacktestEngine.run()` 需要：
1. 记录每日持仓股数序列（目前只记录了市值，没记录股数）
2. 记录每日买入成本（可从 trade_log 提取）
3. 将这些数据传给 `calc_all_metrics()`

### 3.3 scripts/compare_signals.py（展示）

在输出表格中新增 TWR Sharpe 列，让用户可以直接看到可对标业界的 Sharpe 值。

综合排名仍然使用现有 Sharpe（因为它的横向排序已经验证过是准确的）。

### 3.4 不需要改的

- `src/modules/` 下的所有模块（Entry / Tiers / Position / TakeProfit）
- `src/strategies/composable.py`
- `experiments/configs.py`
- `show_chart.sh`

---

## 4. 预期效果

### 4.1 compare_signals.py 输出变化（示意）

修改前：

```
  策略                  年化收益    最大回撤   Sharpe   成本优势   买入次数
  连续5天低于EMA(best)    +13.59%   10.4%    0.16    +6.14%     125
```

修改后：

```
  策略                  年化收益    最大回撤   Sharpe  TWR-Sharpe  成本优势   买入次数
  连续5天低于EMA(best)    +13.59%   10.4%    0.16      0.85     +6.14%     125
```

### 4.2 可与业界对标

修改后你可以这样判断：

```
SPY 买入持有的 TWR Sharpe ≈ 0.6 ~ 0.7

如果你的 DCA 策略 TWR Sharpe：
  > 0.7  → 择时确实有价值，跑赢了买入持有
  0.5~0.7 → 跟买入持有差不多
  < 0.5  → 择时反而不如买入持有

如果达到 1.0+ → 非常好（对 SPY 日线级别 DCA 策略来说）
如果达到 1.5+ → 极优秀（可能需要检查是否过拟合）
```

---

## 5. 实现步骤

```
第 1 步：在 src/metrics.py 中新增 calc_twr_sharpe()
         → 核心：用"不含新买入的市值"算日收益率
         → 需要每日持仓股数和每日收盘价

第 2 步：在 src/metrics.py 中新增 calc_mwr_return()
         → 核心：收集现金流序列，求解 IRR
         → 需要每次买入的日期和金额

第 3 步：修改 src/backtest_engine.py
         → 新增每日持仓股数的记录
         → 将 trade_log 整理为现金流序列
         → 将新数据传给 calc_all_metrics()

第 4 步：修改 calc_all_metrics() 签名和返回值
         → 新增 twr_sharpe, twr_annualized_return, mwr_annualized_return

第 5 步：修改 scripts/compare_signals.py
         → 在表格中展示 TWR Sharpe 列

第 6 步：验证
         → 跑 compare_signals.py，检查 TWR Sharpe 是否在合理范围
         → 跟 SPY 买入持有的 Sharpe 做基准对比
```

**总改动量**：约 80-100 行新增代码 + 10 行修改。
