# 技术实施方案：定投策略逐层优化实验

## 一、架构总览

### 1.1 现状问题

当前系统是**无状态**设计：`execute_day(open, low, fee_rate, orders)` 只看当天的开盘价和最低价，无法实现：

- 波动率动态档口（需要 14 天历史跌幅）
- EMA 均线过滤（需要 20 天历史收盘价）
- 自适应仓位（需要趋势判断）
- 止盈策略（需要偏离度序列、持仓状态、挂单跨日管理）
- SMH 利润分流（需要持仓和卖出管理）

### 1.2 重构目标

升级为**有状态、可组合**的架构：策略由 4 个独立模块组合而成，回测引擎管理历史数据、持仓状态和挂单生命周期。

### 1.3 重构后目录结构

```
quant-dca/
├── main.py                          # 保留（向后兼容单次回测）
├── run_experiments.py               # 新增：实验批量运行入口
│
├── src/
│   ├── data_loader.py               # 保留不变
│   ├── indicators.py                # 新增：技术指标计算（EMA、波动率等）
│   ├── portfolio.py                 # 新增：持仓管理（SOXL + SMH）
│   ├── metrics.py                   # 新增：评估指标（Sharpe/Sortino/Calmar/DD Duration）
│   ├── backtest.py                  # 保留（旧引擎，向后兼容）
│   ├── backtest_engine.py           # 新增：有状态回测引擎
│   ├── chart.py                     # 保留，后续扩展
│   ├── utils.py                     # 保留（旧工具函数）
│   │
│   ├── modules/                     # 新增：可组合策略模块
│   │   ├── __init__.py
│   │   ├── tiers.py                 # 档口设置模块
│   │   ├── entry.py                 # 入场条件模块
│   │   ├── position.py              # 仓位分布模块
│   │   └── take_profit.py           # 止盈策略模块
│   │
│   └── strategies/
│       ├── baseline.py              # 保留不变
│       └── composable.py            # 新增：组合策略（调度 4 个模块）
│
├── experiments/                     # 新增：实验管理
│   ├── __init__.py
│   ├── configs.py                   # 所有实验参数定义
│   ├── runner.py                    # 实验批量执行器
│   └── reporter.py                  # 实验报告生成器
│
├── config/                          # 保留不变
├── data/                            # 保留不变
├── experiments_result/              # 结果输出目录
└── output/                          # 图表输出目录
```

---

## 二、核心模块设计

### 2.1 技术指标模块 `src/indicators.py`

提供纯函数，输入历史数据，输出指标值。

```python
def calc_ema(closes: list[float], period: int) -> float:
    """计算 EMA（指数移动平均）"""

def calc_volatility_tiers(history: list[dict], lookback: int = 14) -> tuple[float, float, float]:
    """
    计算波动率动态档口
    输入：历史 K 线数据（至少 lookback+1 天）
    输出：(tier1_drop%, tier2_drop%, tier3_drop%)

    算法：
    1. 取最近 lookback 天的日跌幅 = max(0, (昨收 - 今低) / 昨收)
    2. tier1 = 30th 分位数
    3. tier2 = 60th 分位数
    4. tier3 = 最大跌幅 × 90%
    """

def calc_deviation(close: float, ema: float) -> float:
    """计算偏离度 = (close - ema) / ema"""

def calc_max_abs_change(history: list[dict], lookback: int = 7) -> float:
    """计算 N 日最大涨跌幅绝对值"""
```

### 2.2 持仓管理模块 `src/portfolio.py`

```python
class Portfolio:
    """管理 SOXL 主仓位 + SMH 分流仓位"""

    def __init__(self):
        self.soxl_shares: float = 0.0
        self.soxl_cost: float = 0.0

        self.smh_shares: float = 0.0
        self.smh_cost: float = 0.0

        self.realized_profit: float = 0.0    # 累计已实现利润
        self.total_diverted: float = 0.0     # 累计分流到 SMH 的金额

        self.pending_tp_orders: list = []    # 跨日止盈挂单

    def buy_soxl(self, shares, price, fee_rate):
        """买入 SOXL"""

    def sell_soxl(self, pct, price, fee_rate):
        """按比例卖出 SOXL，返回利润"""

    def divert_to_smh(self, profit, smh_close_price, fee_rate):
        """将利润的 50% 按当日 SMH 收盘价买入 SMH（长期持有）"""

    def add_tp_order(self, trigger_price, sell_pct):
        """添加止盈限价挂单（跨日有效）"""

    def check_tp_orders(self, high_price):
        """检查止盈挂单是否触发（当日最高价 >= 挂单价）"""

    def soxl_value(self, close) -> float:
        """SOXL 当前市值"""

    def smh_value(self, smh_close) -> float:
        """SMH 当前市值"""

    def total_value(self, soxl_close, smh_close) -> float:
        """总资产 = SOXL 市值 + SMH 市值 + 已实现利润中未分流部分"""
```

### 2.3 评估指标模块 `src/metrics.py`

```python
def calc_sharpe_ratio(daily_returns: list[float], risk_free_rate: float = 0.0) -> float:
    """
    夏普比率 = (年化收益率 - 无风险利率) / 年化波动率
    年化波动率 = 日收益率标准差 × √252
    """

def calc_sortino_ratio(daily_returns: list[float], risk_free_rate: float = 0.0) -> float:
    """
    Sortino 比率 = (年化收益率 - 无风险利率) / 年化下行波动率
    下行波动率 = 仅负收益率的标准差 × √252
    比 Sharpe 更合理：上行波动不算"风险"
    """

def calc_calmar_ratio(annualized_return: float, max_drawdown: float) -> float:
    """Calmar 比率 = 年化收益率 / 最大回撤"""

def calc_max_drawdown_duration(daily_values: list[float]) -> int:
    """
    最大回撤恢复天数
    从峰值跌落到恢复到（或超过）峰值的最长天数
    如果到回测结束仍未恢复，返回从峰值到回测结束的天数
    """

def calc_cost_advantage(avg_cost: float, period_avg_price: float) -> float:
    """成本优势比 = (期间均价 - 平均成本) / 期间均价"""

def calc_all_metrics(result: dict) -> dict:
    """一次性计算所有指标并返回"""
```

**完整指标列表：**

| 指标 | 类型 | 公式 | 说明 |
|------|------|------|------|
| total_return | 收益 | (期末市值 - 总成本) / 总成本 | 总收益率 |
| annualized_return | 收益 | (1 + total_return)^(365/days) - 1 | 年化收益率 |
| max_drawdown | 风险 | max((peak - valley) / peak) | 最大回撤 |
| max_dd_duration | 风险 | 峰值到恢复的最长天数 | 回撤恢复时间 |
| **sharpe_ratio** | **核心** | **(年化收益 - Rf) / 年化波动率** | **主排序指标** |
| sortino_ratio | 核心 | (年化收益 - Rf) / 年化下行波动率 | 只惩罚下行风险 |
| calmar_ratio | 核心 | 年化收益率 / 最大回撤 | 收益回撤比 |
| avg_cost | 效率 | 总成本 / 总股数 | 平均买入成本 |
| cost_advantage | 效率 | (期间均价 - 平均成本) / 期间均价 | 成本优势比 |
| limit_fill_rate | 效率 | 成交限价单 / 挂出限价单 | 各档成交率 |
| total_value | 综合 | SOXL 市值 + SMH 市值 | 含分流仓位的总资产 |

### 2.4 可组合策略模块 `src/modules/`

策略由 4 个模块组合而成，每个模块只负责一个决策维度。

#### 2.4.1 档口设置模块 `tiers.py`

```python
class FixedTiers:
    """固定比例档口"""
    def __init__(self, drops=(0.02, 0.05, 0.10)):
        self.drops = drops

    def get_tiers(self, context) -> tuple[float, float, float]:
        return self.drops


class VolatilityTiers:
    """波动率动态档口"""
    def __init__(self, lookback=14, percentiles=(30, 60), max_scale=0.90):
        self.lookback = lookback
        self.percentiles = percentiles
        self.max_scale = max_scale

    def get_tiers(self, context) -> tuple[float, float, float]:
        """根据历史波动率计算三档位置"""
        # 如果历史数据不足 lookback+1 天，回退到固定档口
```

#### 2.4.2 入场条件模块 `entry.py`

```python
class UnconditionalEntry:
    """无条件每日买入"""
    def should_market_buy(self, context) -> bool:
        return True

    def should_place_limits(self, context) -> bool:
        return True


class EMAFilterEntry:
    """EMA 均线过滤"""
    def __init__(self, ema_period=20):
        self.ema_period = ema_period

    def should_market_buy(self, context) -> bool:
        # 昨日收盘价 < EMA → 市价买入
        return context.prev_close < context.ema

    def should_place_limits(self, context) -> bool:
        # 无论趋势如何，始终挂限价单
        return True


class NDayConfirmEntry:
    """连续 N 天确认"""
    def __init__(self, ema_period=20, n_days=3):
        self.ema_period = ema_period
        self.n_days = n_days

    def should_market_buy(self, context) -> bool:
        # 连续 N 天收盘价 < EMA 才买入
        return context.consecutive_below_ema >= self.n_days

    def should_place_limits(self, context) -> bool:
        return context.consecutive_below_ema >= self.n_days
```

#### 2.4.3 仓位分布模块 `position.py`

```python
class FixedPyramid:
    """固定金字塔分布"""
    def __init__(self, market_shares=0.70, limit_shares=(0.40, 0.25, 0.15)):
        self.market_shares = market_shares
        self.limit_shares = limit_shares

    def get_shares(self, context) -> tuple[float, tuple]:
        return self.market_shares, self.limit_shares


class AdaptivePyramid:
    """自适应金字塔：上涨倒金字塔 / 下跌正金字塔"""
    def __init__(self, ema_period=20):
        self.ema_period = ema_period
        self.up_market = 0.70
        self.up_limits = (0.40, 0.25, 0.15)   # 倒金字塔
        self.down_market = 0.15
        self.down_limits = (0.25, 0.40, 0.70)  # 正金字塔

    def get_shares(self, context) -> tuple[float, tuple]:
        if context.prev_close >= context.ema:
            return self.up_market, self.up_limits
        else:
            return self.down_market, self.down_limits


class DowntrendOnly:
    """仅下跌买入：上涨不买，下跌正金字塔"""
    def __init__(self, ema_period=20):
        self.ema_period = ema_period
        self.market_shares = 0.15
        self.limit_shares = (0.25, 0.40, 0.70)  # 正金字塔

    def get_shares(self, context) -> tuple[float, tuple]:
        if context.prev_close < context.ema:
            return self.market_shares, self.limit_shares
        else:
            return 0.0, (0.0, 0.0, 0.0)  # 不买
```

#### 2.4.4 止盈模块 `take_profit.py`

```python
class NoTakeProfit:
    """不止盈"""
    def check(self, context) -> dict | None:
        return None


class DeviationPeakTP:
    """
    偏离度峰值止盈
    偏离度连续下降 2 天 → 前日为峰值 → 挂止盈单
    """
    def __init__(self, ema_period=20, sell_pct=0.50, lookback_change=7):
        self.ema_period = ema_period
        self.sell_pct = sell_pct
        self.lookback_change = lookback_change

    def check(self, context) -> dict | None:
        # 需要至少 3 天的偏离度数据
        # 条件：dev[i] < dev[i-1] < dev[i-2]（连续下降 2 天）
        # 触发：tp_price = day[i-2].close × (1 + max_abs_change_7d)
        # 返回 {'trigger_price': ..., 'sell_pct': 0.50}


class TrendConfirmTP:
    """
    趋势确认止盈
    连续 3 天收盘价 > EMA → 挂止盈单
    """
    def __init__(self, ema_period=20, n_days=3, sell_pct=0.25, lookback_change=7):
        self.ema_period = ema_period
        self.n_days = n_days
        self.sell_pct = sell_pct
        self.lookback_change = lookback_change

    def check(self, context) -> dict | None:
        # 条件：连续 n_days 天 close > EMA
        # 触发：tp_price = day[n].close × (1 + max_abs_change_7d)
        # 返回 {'trigger_price': ..., 'sell_pct': 0.25}
```

### 2.5 有状态回测引擎 `src/backtest_engine.py`

```python
class Context:
    """策略每日收到的上下文信息"""
    day: dict             # 当日 {date, open, high, low, close}
    day_index: int        # 当前是第几个交易日
    history: list[dict]   # 所有历史日数据（含当日）
    prev_close: float     # 昨日收盘价（挂单基准）
    ema: float            # 当日 EMA20
    consecutive_below_ema: int  # 连续低于 EMA 的天数
    consecutive_above_ema: int  # 连续高于 EMA 的天数
    deviation: float      # 当日偏离度
    deviation_history: list[float]  # 近期偏离度序列
    portfolio: Portfolio  # 当前持仓状态


class BacktestEngine:
    def __init__(self, data, smh_data, fee_rate, strategy):
        self.data = data
        self.smh_data = smh_data
        self.fee_rate = fee_rate
        self.strategy = strategy  # ComposableStrategy 实例

    def run(self) -> dict:
        """
        主回测循环：
        1. 预计算当日指标（EMA、偏离度、波动率档口等）
        2. 检查待成交的止盈挂单（high >= 挂单价？）
        3. 调用策略获取当日买入订单
        4. 执行订单，更新持仓
        5. 如果止盈成交，计算利润并分流 50% 到 SMH
        6. 记录当日市值（含 SMH 仓位）
        7. 回测结束后计算所有评估指标
        """
```

### 2.6 组合策略 `src/strategies/composable.py`

```python
class ComposableStrategy:
    """将 4 个模块组合成完整策略"""

    def __init__(self, tiers, entry, position, take_profit):
        self.tiers = tiers          # 档口设置模块
        self.entry = entry          # 入场条件模块
        self.position = position    # 仓位分布模块
        self.take_profit = take_profit  # 止盈模块

    def on_day(self, context) -> dict:
        """
        每日策略决策流程：

        1. 档口模块 → 获取三档价格偏移 (drop1, drop2, drop3)
        2. 入场模块 → 是否市价买入？是否挂限价单？
        3. 仓位模块 → 市价单和各档的股数
        4. 止盈模块 → 是否触发止盈信号？

        返回：
        {
            'buy_orders': [(price_ratio, shares), ...],  # 买入订单
            'tp_order': {'trigger_price': ..., 'sell_pct': ...} | None  # 止盈挂单
        }
        """
        # 步骤 1：获取档口
        tier1, tier2, tier3 = self.tiers.get_tiers(context)

        # 步骤 2：入场判断
        do_market = self.entry.should_market_buy(context)
        do_limits = self.entry.should_place_limits(context)

        # 步骤 3：获取仓位
        market_shares, limit_shares = self.position.get_shares(context)

        # 步骤 4：组装订单
        orders = []
        if do_market and market_shares > 0:
            orders.append((1.0, market_shares))
        if do_limits:
            orders.append((1.0 - tier1, limit_shares[0]))
            orders.append((1.0 - tier2, limit_shares[1]))
            orders.append((1.0 - tier3, limit_shares[2]))

        # 步骤 5：止盈检查
        tp_order = self.take_profit.check(context)

        return {'buy_orders': orders, 'tp_order': tp_order}
```

---

## 三、市场环境配置

所有实验在以下 4 种环境中分别运行：

| 环境 ID | 名称 | 时间区间 | 特征 | 评估权重 |
|---------|------|----------|------|----------|
| bear | 纯熊市 | 2022-01-01 ~ 2022-12-31 | 压力测试 | 15% |
| bull | 纯牛市 | 2022-10-10 ~ 2024-07-08 | 最佳情况 | 15% |
| bear-bull | 熊转牛 | 2022-01-01 ~ 2024-07-08 | **完整周期（主评估）** | **35%** |
| bull-bear | 牛转熊 | 2022-10-14 ~ 2025-04-08 | 完整周期（逆向） | **35%** |

**综合评分公式：**

```
Composite Sharpe = 0.15 × Sharpe(bear) + 0.15 × Sharpe(bull) + 0.35 × Sharpe(bear-bull) + 0.35 × Sharpe(bull-bear)
```

**辅助决策规则：**
- 如果两个方案 Composite Sharpe 接近（差值 < 0.05），优先选 Calmar Ratio 更高的
- 如果一个方案在某个周期的 Max DD > 85%，标记为"高风险"降权处理

---

## 四、实验阶段详细参数

### 4.1 第一阶段：档口设置

**目标**：确定最优的挂单价格层级方案

**锁定变量**：入场=无条件每日买入，仓位=固定倒金字塔，止盈=无

| 实验 | 档口方案 | 市价单 | 一档 | 二档 | 三档 | 说明 |
|------|----------|--------|------|------|------|------|
| **1-A** | 固定比例 2%/5%/10% | 0.70@1.00 | 0.40@0.98 | 0.25@0.95 | 0.15@0.90 | Baseline（已完成） |
| **1-B** | 波动率动态 | 0.70@1.00 | 0.40@动态 | 0.25@动态 | 0.15@动态 | 14日波动率分位数 |
| **1-C** | 波动率动态（无市价单） | 无 | 0.40@动态 | 0.25@动态 | 0.15@动态 | 消融：去掉定投 |

**波动率动态参数：**

| 参数 | 值 | 说明 |
|------|------|------|
| lookback | 14 个交易日 | 波动率计算窗口 |
| 日跌幅 | max(0, (昨收 - 今低) / 昨收) | 基于昨日收盘价 |
| 一档 | 30th 分位数 | 预期 ~70% 成交率 |
| 二档 | 60th 分位数 | 预期 ~40% 成交率 |
| 三档 | 最大跌幅 × 90% | 预期 ~10% 成交率 |
| 最小档距 | tier2 >= tier1 + 0.5%, tier3 >= tier2 + 1.0% | 防止档口重叠 |
| 回退 | 历史不足 15 天时，使用固定比例 2%/5%/10% | 冷启动处理 |

**选优标准**：Composite Sharpe 最高者胜出，锁定进入第二阶段。

---

### 4.2 第二阶段：入场条件

**目标**：确定最优的买入触发条件

**锁定变量**：档口=第一阶段最优，仓位=固定倒金字塔，止盈=无

| 实验 | 入场条件 | 逻辑 |
|------|----------|------|
| **2-A** | 无条件每日买入 | 沿用第一阶段最优 |
| **2-B** | EMA 过滤 | 昨收 < EMA20 → 市价+挂单<br>昨收 >= EMA20 → 仅挂限价单 |
| **2-C-2** | 连续 2 天确认 | 连续 2 天收盘 < EMA20 → 市价+挂单<br>否则 → 不买 |
| **2-C-3** | 连续 3 天确认 | 连续 3 天收盘 < EMA20 → 市价+挂单<br>否则 → 不买 |
| **2-C-4** | 连续 4 天确认 | 连续 4 天收盘 < EMA20 → 市价+挂单<br>否则 → 不买 |

**EMA 参数：**

| 参数 | 值 | 说明 |
|------|------|------|
| 类型 | EMA（指数移动平均） | 行业标准，比 SMA 更灵敏 |
| 周期 | 20 日 | 约一个月的交易日 |
| 计算 | EMA_t = α × Close_t + (1-α) × EMA_{t-1}, α = 2/(20+1) | 标准公式 |
| 冷启动 | 前 20 天使用 SMA 作为初始 EMA 值 | 收敛后差异可忽略 |

**说明**：2-C 实验中 N=2,3,4 虽然在 task.md 中归为一组，但因为 N 值不同实际是 3 个独立方案。在比较时作为 3 个方案分别参与排名。

**选优标准**：Composite Sharpe 最高者胜出。

---

### 4.3 第三阶段：仓位分布

**目标**：确定最优的各档股数分配方式

**锁定变量**：档口=第一阶段最优，入场=第二阶段最优，止盈=无

| 实验 | 分布策略 | 市价单 | 一档 | 二档 | 三档 |
|------|----------|--------|------|------|------|
| **3-A** | 固定倒金字塔 | 0.70 | 0.40 | 0.25 | 0.15 |
| **3-B** | 自适应金字塔 | 趋势决定 | 趋势决定 | 趋势决定 | 趋势决定 |
| **3-C** | 仅下跌买入 | 趋势决定 | 趋势决定 | 趋势决定 | 趋势决定 |

**3-B 自适应金字塔详细参数：**

| 趋势判断 | 市价单 | 一档 | 二档 | 三档 | 分布类型 |
|----------|--------|------|------|------|----------|
| 昨收 >= EMA20（上涨） | 0.70 | 0.40 | 0.25 | 0.15 | 倒金字塔 |
| 昨收 < EMA20（下跌） | 0.15 | 0.25 | 0.40 | 0.70 | 正金字塔 |

**3-C 仅下跌买入详细参数：**

| 趋势判断 | 市价单 | 一档 | 二档 | 三档 | 说明 |
|----------|--------|------|------|------|------|
| 昨收 >= EMA20（上涨） | 0 | 0 | 0 | 0 | 不买入 |
| 昨收 < EMA20（下跌） | 0.15 | 0.25 | 0.40 | 0.70 | 正金字塔 |

**选优标准**：Composite Sharpe 最高者胜出。

---

### 4.4 第四阶段：止盈策略

**目标**：验证止盈策略能否降低回撤、提升 Calmar

**锁定变量**：档口=第一阶段最优，入场=第二阶段最优，仓位=第三阶段最优

| 实验 | 止盈策略 | 触发条件 | 卖出比例 | SMH 分流 |
|------|----------|----------|----------|----------|
| **4-0** | 无止盈 | - | - | - |
| **4-A** | 偏离度峰值 | 偏离度连续下降 2 天 | 50% | 利润 50% → SMH |
| **4-B** | 趋势确认 | 连续 3 天收盘 > EMA20 | 25% | 利润 50% → SMH |
| **4-AB** | 双层止盈（4-A + 4-B 同时启用） | 各自独立触发 | 各自比例 | 利润 50% → SMH |

**4-0 作为 baseline 对照**：沿用第三阶段最优（不止盈），用于量化止盈策略的边际贡献。

**4-A 偏离度峰值止盈参数：**

| 参数 | 值 | 说明 |
|------|------|------|
| 偏离度 | (close - EMA20) / EMA20 | 标准偏离度 |
| 峰值确认 | 偏离度连续下降 2 天 | dev[t] < dev[t-1] < dev[t-2] |
| 止盈价格 | 峰值日收盘价 × (1 + 7日最大\|涨跌幅\|) | 统一尺子 |
| 卖出比例 | 50% 仓位 | 大信号、大仓位 |
| 挂单有效期 | 5 个交易日（未触发则取消） | 防止挂单长期悬挂 |

**4-B 趋势确认止盈参数：**

| 参数 | 值 | 说明 |
|------|------|------|
| 触发条件 | 连续 3 天 close > EMA20 | 趋势确认 |
| 止盈价格 | 第 3 天收盘价 × (1 + 7日最大\|涨跌幅\|) | 统一尺子 |
| 卖出比例 | 25% 仓位 | 小信号、小仓位 |
| 挂单有效期 | 5 个交易日 | 同上 |

**SMH 分流规则：**

| 参数 | 值 |
|------|------|
| 分流比例 | 止盈利润的 50% |
| 买入价格 | 止盈成交当日 SMH 收盘价 |
| 手续费 | 与 SOXL 相同（1%） |
| 持有策略 | 长期持有，不卖出 |

**选优标准**：Composite Sharpe 最高者胜出。同时重点对比 Calmar Ratio（止盈策略的核心价值在于降低回撤）。

---

## 五、交叉验证

完成 4 个阶段的贪心搜索后，做以下额外验证：

### 5.1 回归验证

最终最优组合 vs 原始 baseline（1-A），在 4 种环境下全面对比，确认各模块的贡献是**叠加**而非**抵消**。

### 5.2 模块交互效应检测

贪心搜索假设模块间独立，但可能存在交互效应。以下情况需要额外交叉验证：

| 场景 | 检测方法 |
|------|----------|
| 档口 × 入场 | 如果第一阶段选了波动率动态，第二阶段选了 EMA 过滤，需要额外测试：固定档口 + EMA 过滤 vs 波动率档口 + 无条件入场，确认不是档口-入场的特定组合在起作用 |
| 仓位 × 止盈 | 如果第三阶段选了自适应金字塔，第四阶段选了偏离度止盈，需要交叉：固定金字塔 + 偏离度止盈 vs 自适应金字塔 + 无止盈 |

**做法**：如果最终最优组合的 Composite Sharpe 比 baseline 提升 > 0.1，则进行 2-4 组交叉验证，确认优势来源。

---

## 六、实验运行器设计

### 6.1 实验配置 `experiments/configs.py`

```python
MARKET_ENVS = {
    'bear':      {'start': '2022-01-01', 'end': '2022-12-31', 'weight': 0.15},
    'bull':      {'start': '2022-10-10', 'end': '2024-07-08', 'weight': 0.15},
    'bear-bull': {'start': '2022-01-01', 'end': '2024-07-08', 'weight': 0.35},
    'bull-bear': {'start': '2022-10-14', 'end': '2025-04-08', 'weight': 0.35},
}

STAGE_1 = {
    '1-A': {  # 已完成，数据来自 experiments_result/1-A/
        'tiers': FixedTiers(drops=(0.02, 0.05, 0.10)),
        'entry': UnconditionalEntry(),
        'position': FixedPyramid(),
        'take_profit': NoTakeProfit(),
    },
    '1-B': {
        'tiers': VolatilityTiers(lookback=14, percentiles=(30, 60), max_scale=0.90),
        'entry': UnconditionalEntry(),
        'position': FixedPyramid(),
        'take_profit': NoTakeProfit(),
    },
    '1-C': {
        'tiers': VolatilityTiers(lookback=14, percentiles=(30, 60), max_scale=0.90),
        'entry': UnconditionalEntry(),
        'position': FixedPyramid(market_shares=0, limit_shares=(0.40, 0.25, 0.15)),
        'take_profit': NoTakeProfit(),
    },
}

# STAGE_2, STAGE_3, STAGE_4 类似结构
# 每阶段的 best_of_previous 在运行时动态填入
```

### 6.2 实验运行器 `experiments/runner.py`

```python
def run_stage(stage_configs: dict, data: dict, smh_data: dict) -> dict:
    """
    运行一个阶段的所有实验

    1. 遍历每个实验配置
    2. 在 4 种市场环境中分别执行回测
    3. 计算 Composite Sharpe
    4. 输出排名和详细结果

    返回：
    {
        '1-B': {
            'bear':      { ... all metrics ... },
            'bull':      { ... },
            'bear-bull': { ... },
            'bull-bear': { ... },
            'composite_sharpe': 0.35,
            'composite_calmar': 1.20,
        },
        ...
    }
    """

def run_all_experiments():
    """
    按顺序执行 4 个阶段：
    1. 跑第一阶段，选出最优
    2. 用第一阶段最优锁定档口，跑第二阶段
    3. ...以此类推
    4. 最后跑回归验证和交叉验证
    """
```

### 6.3 报告生成器 `experiments/reporter.py`

每个实验生成标准化的 Markdown 报告，格式与现有 `experiments_result/1-A/bear/result.md` 对齐：

```
experiments_result/
├── 1-A/                    # 已有
├── 1-B/
│   ├── bear/result.md
│   ├── bull/result.md
│   ├── bear-bull/result.md
│   ├── bull-bear/result.md
│   └── summary.md          # 含 composite sharpe 排名
├── 1-C/
├── stage-1-comparison.md   # 第一阶段横向对比
├── 2-A/
├── 2-B/
├── ...
├── stage-2-comparison.md
├── stage-3-comparison.md
├── stage-4-comparison.md
├── cross-validation/       # 交叉验证
│   └── result.md
└── final-comparison.md     # 最终最优 vs baseline
```

---

## 七、实施顺序

按依赖关系分步实施，每步完成后可独立验证。

| 步骤 | 内容 | 依赖 | 验证方式 |
|------|------|------|----------|
| **Step 1** | `src/indicators.py` — EMA、波动率档口、偏离度 | 无 | 单元测试：用已知数据验证 EMA 计算正确 |
| **Step 2** | `src/metrics.py` — Sortino、Calmar、DD Duration | 无 | 用 1-A 已有数据验证，Sharpe 结果应与旧代码一致 |
| **Step 3** | `src/portfolio.py` — 持仓管理、SMH 分流 | 无 | 单元测试 |
| **Step 4** | `src/modules/` — 4 个可组合模块 | Step 1 | 用 baseline 参数组装 ComposableStrategy，输出应与旧 baseline 一致 |
| **Step 5** | `src/backtest_engine.py` — 有状态回测引擎 | Step 1-4 | **回归测试**：用 baseline 配置跑新引擎，结果应与 `experiments_result/1-A/` 匹配 |
| **Step 6** | `experiments/` — 配置、运行器、报告 | Step 5 | 先跑 1-A 和 1-B 验证流程正确 |
| **Step 7** | 执行第一阶段实验 | Step 6 | 输出 1-A/1-B/1-C 对比报告 |
| **Step 8** | 执行第二阶段实验 | Step 7 | 输出 2-A/2-B/2-C 对比报告 |
| **Step 9** | 执行第三阶段实验 | Step 8 | 输出 3-A/3-B/3-C 对比报告 |
| **Step 10** | 执行第四阶段实验 | Step 9 | 输出 4-0/4-A/4-B/4-AB 对比报告 |
| **Step 11** | 回归验证 + 交叉验证 | Step 10 | 最终对比报告 |

**预计产出**：11 组实验（每组 4 环境）= 44 次回测 + 交叉验证若干，全自动执行。

---

## 八、风险与注意事项

| 风险 | 缓解措施 |
|------|----------|
| 过拟合 | 参数先粗后细，不做全网格搜索；用 4 种环境做稳健性检验 |
| 波动率档口冷启动 | 历史不足 15 天时回退到固定比例 |
| EMA 冷启动 | 前 20 天用 SMA 初始化 |
| 止盈挂单长期悬挂 | 设置 5 天有效期，超期自动取消 |
| 模块交互效应 | 完成贪心搜索后进行交叉验证 |
| 旧代码兼容性 | 保留 `main.py` + `backtest.py` + `baseline.py` 不变 |
