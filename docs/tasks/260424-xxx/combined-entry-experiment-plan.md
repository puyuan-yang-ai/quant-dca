# NDayConfirm + RSI 组合入场信号实验方案

> 目标：探索 NDayConfirm-5 和 RSI v2 两种入场信号的组合方式，验证组合过滤是否能在 SPY 上提升择时质量。

---

## 1. 实验动机

从单独测试的数据看，两种信号各有所长：

| 信号 | 优势环境 | 劣势环境 | 特点 |
|------|---------|---------|------|
| NDayConfirm-5 | 牛转熊（+2.18%） | 熊市（-3.32%） | 稳定，覆盖面广，无明显短板 |
| RSI v2 | 熊市（-2.54%）、熊转牛（+14.11%） | 牛转熊（-0.08%） | 精准，资金效率高，但信号稀疏 |

两者的过滤维度不同：
- **NDayConfirm-5** 看的是**趋势**（价格连续低于均线）
- **RSI v2** 看的是**动量超卖**（RSI 触发极端区域信号）

趋势 + 动量是经典的互补组合，值得验证。

---

## 2. 候选组合策略

### 策略 A：AND 交集（双重确认）

```
买入条件：NDayConfirm-5 触发 AND RSI 有 B/B+/B++ 信号
```

- 最严格的过滤，两个条件同时满足才买
- 预期：买入次数极少，但每次买入的质量极高
- 风险：信号太稀疏，可能长期空仓

### 策略 B：OR 并集（双通道）

```
买入条件：NDayConfirm-5 触发 OR RSI 有 B/B+/B++ 信号
```

- 最宽松的组合，任一条件满足就买
- 预期：买入次数比单独使用任一策略更多，覆盖更全
- 风险：过滤效果可能不如单独使用最优策略

### 策略 C：NDayConfirm 基础 + RSI 增强

```
买入条件：NDayConfirm-5 触发 → 买 1 股（基础仓位）
         RSI 有 B/B+/B++ 信号 → 额外买 1 股（加仓）
         两者同时触发 → 买 2 股（基础 + 加仓）
```

- 用 NDayConfirm-5 保证基础建仓节奏
- RSI 信号作为加仓时机，不改变基础策略
- 预期：保留 NDayConfirm-5 的稳定性，同时利用 RSI 的精准度在关键位置加重
- 注意：这个策略的买入股数不固定（1 或 2 股），需要注意与标准化执行层的兼容性

### 策略 D：RSI 信号强度分级

```
买入条件：
  - NDayConfirm-5 触发 → 买 1 股
  - RSI B 信号（1分）→ 买 1 股
  - RSI B+信号（2分）→ 买 2 股
  - RSI B++信号（3分）→ 买 3 股
```

- 利用 RSI v2 的三级信号强度（B < B+ < B++），信号越强买越多
- 预期：在极端超卖（B++）时重仓抄底，温和超卖（B）时轻仓试探
- 风险：B++ 信号极少，可能整段回测只出现几次

---

## 3. 实验设计

### 3.1 标准化执行层

与现有 `compare_signals.py` 保持一致，消除执行层差异：

```python
tiers     = FixedTiers(drops=())                        # 无限价单
position  = FixedPyramid(market_shares=1, limit_shares=(0,0,0))  # 固定买 1 股
take_profit = NoTakeProfit()                             # 不止盈
```

**例外**：策略 C 和 D 涉及动态股数，需要特殊处理（见 3.3）。

### 3.2 对比基准

将组合策略与现有 5 个单独策略一起跑，横向对比：

| 编号 | 策略 | 类型 |
|------|------|------|
| 1 | Unconditional | 基准（无过滤） |
| 2 | EMAFilter | 单信号 |
| 3 | NDayConfirm-5 | 单信号（当前最优） |
| 4 | RSI v2 | 单信号 |
| 5 | **AND（NDayConfirm-5 ∩ RSI）** | 组合 |
| 6 | **OR（NDayConfirm-5 ∪ RSI）** | 组合 |
| 7 | **NDayConfirm + RSI 增强** | 组合（动态仓位） |
| 8 | **RSI 信号强度分级** | 组合（动态仓位） |

### 3.3 动态仓位策略的公平比较问题

策略 C 和 D 的买入股数不固定（有时 1 股，有时 2-3 股），直接比年化收益不公平，因为投入的总资金不同。

**解决方案**：对策略 C 和 D，**同时输出两组指标**：
1. **原始指标**：直接跑，看绝对表现
2. **资金效率指标**：用 `年化收益 / 平均每日投入` 归一化，比较单位资金的回报

但为了第一轮实验简洁，**建议先只跑策略 A 和 B**（固定 1 股，与标准化执行层完全兼容），看看纯信号组合的效果。如果有价值再跑 C 和 D。

### 3.4 实验环境

与现有一致，5 个市场环境全跑：

| 环境 | 时间段 | 权重 |
|------|-------|------|
| bear | 2022-01-01 ~ 2022-12-31 | 0.15 |
| bull | 2022-10-10 ~ 2024-07-08 | 0.15 |
| bear-bull | 2022-01-01 ~ 2024-07-08 | 0.35 |
| bull-bear | 2022-10-14 ~ 2025-04-08 | 0.35 |
| all | 1993-01-29 ~ 2025-04-24 | 0.00（观察用） |

---

## 4. 实现步骤

### 第一步：新增 Entry 模块

在 `src/modules/entry.py` 中新增两个类：

```python
class CombinedAndEntry:
    """NDayConfirm-5 AND RSI：双重确认"""

    def __init__(self, data, n_days=5):
        self.n_days = n_days
        # 预计算 RSI 买入日期集合（复用 RSISignalEntry 的逻辑）
        result = calc_rsi_v2_signals(data)
        self._buy_dates = set()
        for i, sigs in enumerate(result['signals']):
            for sig in sigs:
                if sig['type'].startswith('B'):
                    self._buy_dates.add(data[i]['date'])

    def should_market_buy(self, context):
        nday_ok = context.consecutive_below_ema >= self.n_days
        rsi_ok = context.day['date'] in self._buy_dates
        return nday_ok and rsi_ok

    def should_place_limits(self, context):
        return False


class CombinedOrEntry:
    """NDayConfirm-5 OR RSI：双通道"""

    def __init__(self, data, n_days=5):
        self.n_days = n_days
        result = calc_rsi_v2_signals(data)
        self._buy_dates = set()
        for i, sigs in enumerate(result['signals']):
            for sig in sigs:
                if sig['type'].startswith('B'):
                    self._buy_dates.add(data[i]['date'])

    def should_market_buy(self, context):
        nday_ok = context.consecutive_below_ema >= self.n_days
        rsi_ok = context.day['date'] in self._buy_dates
        return nday_ok or rsi_ok

    def should_place_limits(self, context):
        return False
```

### 第二步：修改 compare_signals.py

在 `build_entries()` 函数中添加新的候选策略：

```python
from src.modules.entry import CombinedAndEntry, CombinedOrEntry

def build_entries(data):
    return {
        # ... 现有 5 个 ...
        'AND-NDay5+RSI':  {'label': 'NDayConfirm5 AND RSI', 'entry': CombinedAndEntry(data, n_days=5)},
        'OR-NDay5+RSI':   {'label': 'NDayConfirm5 OR RSI',  'entry': CombinedOrEntry(data, n_days=5)},
    }
```

### 第三步：运行

```bash
python scripts/compare_signals.py
```

输出会自动包含 7 个策略（原 5 + 新 2）在 5 个环境下的完整对比。

---

## 5. 预期与判断标准

### 5.1 对各策略的预期

| 策略 | 预期买入次数 | 预期效果 |
|------|-----------|---------|
| AND | 极少（可能 10 次以内/年） | 熊市亏损最小，牛市收益可能不佳（信号太少） |
| OR | 略多于 NDayConfirm-5 | 覆盖更全，可能在牛转熊中补上 RSI 的短板 |

### 5.2 判断标准

组合策略有价值的条件（满足任一即可）：
1. **加权 Sharpe 超过 NDayConfirm-5 单独使用**（0.0872）
2. **在某个环境中显著改善短板**（如 AND 在熊市中大幅减亏，或 OR 在牛转熊中改善 RSI 的 -0.08%）
3. **回撤更小的同时收益没有显著下降**

---

## 6. 执行流程总结

```
1. 在 src/modules/entry.py 新增 CombinedAndEntry、CombinedOrEntry  ← 新增代码
2. 在 scripts/compare_signals.py 的 build_entries() 中注册新策略     ← 修改 2 行
3. python scripts/compare_signals.py                               ← 运行（~15 秒）
4. 分析结果，写入报告                                                ← 文档
5. 如果 AND/OR 有价值，再实现策略 C 和 D（动态仓位版本）             ← 可选后续
```

总改动量：新增 ~30 行代码 + 修改 2 行注册代码。
