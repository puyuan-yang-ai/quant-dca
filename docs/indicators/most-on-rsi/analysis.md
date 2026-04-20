# MOST on RSI 指标深度解析

## 一句话概括

**在 RSI 上套一层 MOST（Moving Stop Loss）趋势跟踪止损线，再叠加经典 RSI 背离检测**——用"RSI 的趋势"来过滤噪音，解决裸 RSI 反复假突破、难以定义明确买卖点的痛点。

---

## 1. 整体架构

```
原始价格 (close)
    │
    ▼
┌──────────┐
│  RSI(14) │  ← 第一层：动量振荡器
└────┬─────┘
     │
     ▼
┌──────────────────┐
│  MA 平滑 (VAR/5) │  ← 第二层：对 RSI 做均线平滑（默认用 VAR 自适应均线）
└────┬─────────────┘
     │ (exMov)
     ▼
┌──────────────────────────┐
│  MOST 止损跟踪           │  ← 第三层：在平滑后的 RSI 上计算动态止损线
│  longStop / shortStop    │
│  方向翻转 → BUY / SELL   │
└────┬─────────────────────┘
     │
     ▼
  交易信号 (BUY / SELL)

     + 独立并行模块：
┌──────────────────────────┐
│  RSI 背离检测             │  ← 辅助确认：价格与 RSI 的 Regular Divergence
│  Bull Divergence          │
│  Bear Divergence          │
└───────────────────────────┘
```

指标由 **三个核心层** + **一个辅助模块** 组成，下面逐层拆解。

---

## 2. 逐层拆解

### 2.1 第一层：RSI 计算（第 37-39 行）

```
标准 RSI 计算：
  up   = RMA(max(change(close), 0), 14)
  down = RMA(-min(change(close), 0), 14)
  rsi  = 100 - 100 / (1 + up / down)
```

就是标准的 Wilder RSI，没有任何魔改。周期默认 14，数据源默认 close。

**输出**：0-100 之间的振荡值 `rsi`。

### 2.2 第二层：MA 平滑（第 18-26、40 行）

对 RSI 再做一次均线平滑，支持 7 种均线类型：

| 类型 | 说明 |
|------|------|
| SMA | 简单移动平均 |
| EMA | 指数移动平均 |
| WMA | 加权移动平均 |
| SMMA (RMA) | Wilder 平滑均线 |
| VWMA | 成交量加权均线 |
| Bollinger Bands | 本质是 SMA，额外画上下轨 |
| **VAR**（默认） | Chande 动量自适应均线 |

**重点：VAR 均线（第 5-14 行）**

```
伪代码：
  valpha = 2 / (length + 1)                    # 基础平滑系数（类似 EMA 的 alpha）
  vud1 = price > prev_price ? delta : 0        # 上涨幅度
  vdd1 = price < prev_price ? delta : 0        # 下跌幅度
  vUD = sum(vud1, 9)                            # 9 日累计上涨
  vDD = sum(vdd1, 9)                            # 9 日累计下跌
  vCMO = (vUD - vDD) / (vUD + vDD)             # Chande 动量振荡器，范围 [-1, 1]
  VAR = valpha * |vCMO| * source + (1 - valpha * |vCMO|) * VAR[1]
```

核心思想：**趋势强时跟得快（|vCMO| 大 → alpha 大），震荡时跟得慢（|vCMO| 小 → alpha 小）**。这比固定周期的 EMA/SMA 更能在"RSI 趋势明确时快速响应，RSI 震荡时少发假信号"。

**输出**：平滑后的 RSI 值 `rsiMA`（代码中赋值给 `exMov`）。

### 2.3 第三层：MOST 止损跟踪（第 43-58 行）

这是整个指标的核心创新——**在 RSI 的均线上计算 Trailing Stop**。

```
伪代码：

  fark = exMov * percent * 0.01        # 止损距离 = 当前值 × 百分比（默认 9%）

  # ── 多头止损线（只升不降） ──
  longStop  = exMov - fark
  longStop  = exMov > longStopPrev ? max(longStop, longStopPrev) : longStop
  # 含义：RSI 均线在涨时，longStop 只会向上抬；RSI 均线跌破时，longStop 允许下降

  # ── 空头止损线（只降不升） ──
  shortStop = exMov + fark
  shortStop = exMov < shortStopPrev ? min(shortStop, shortStopPrev) : shortStop
  # 含义：RSI 均线在跌时，shortStop 只会向下压；RSI 均线突破时，shortStop 允许上升

  # ── 方向判定 ──
  if dir == -1 and exMov > shortStopPrev:
      dir = 1        # 空翻多
  elif dir == 1 and exMov < longStopPrev:
      dir = -1       # 多翻空

  # ── 最终 MOST 线 ──
  MOST = dir == 1 ? longStop : shortStop

  # ── 交易信号 ──
  BUY  = crossover(exMov, MOST)     # RSI 均线上穿 MOST → 买入
  SELL = crossunder(exMov, MOST)    # RSI 均线下穿 MOST → 卖出
```

**MOST 的本质**：Trailing Stop Loss 应用在 RSI 的均线上。在多头趋势中，MOST 是一条"只升不降"的支撑线；在空头趋势中，MOST 是一条"只降不升"的压力线。RSI 均线穿越 MOST 时触发方向翻转。

**关键参数**：`percent = 9.0`（止损百分比）。因为 RSI 范围是 0-100，9% 意味着 MOST 距离 RSI 均线约 ±4.5 个点（RSI=50 时）。这个宽度决定了信号的灵敏度——越小越灵敏但假信号多，越大越迟钝但更稳定。

### 2.4 辅助模块：RSI 背离检测（第 79-159 行）

独立于 MOST 信号的经典背离检测：

```
伪代码：

  lookbackLeft = 5, lookbackRight = 5
  rangeUpper = 60, rangeLower = 5

  # 找 RSI 的 pivot 高低点
  plFound = pivotlow(rsi, 5, 5)     # RSI 出现局部低点
  phFound = pivothigh(rsi, 5, 5)    # RSI 出现局部高点

  # ── 常规看涨背离 ──
  条件：价格创新低（Lower Low） + RSI 却走高（Higher Low）
  → 标记 "Bull" 标签

  # ── 常规看跌背离 ──
  条件：价格创新高（Higher High） + RSI 却走低（Lower High）
  → 标记 "Bear" 标签
```

背离信号有 5 根 K 线的滞后（`lookbackRight = 5`），因为需要确认 pivot 点。两次 pivot 之间的距离限制在 5-60 根 K 线内（`rangeLower`/`rangeUpper`），太近或太远的不算。

---

## 3. 信号生成逻辑总结

| 信号 | 条件 | 含义 |
|------|------|------|
| **BUY** | `exMov`（RSI 均线）上穿 `MOST` | RSI 趋势由空转多，RSI 的下跌动量衰竭 |
| **SELL** | `exMov`（RSI 均线）下穿 `MOST` | RSI 趋势由多转空，RSI 的上涨动量衰竭 |
| **Bull Divergence** | 价格新低 + RSI 更高低点 | 下跌力量减弱，潜在反转（辅助确认） |
| **Bear Divergence** | 价格新高 + RSI 更低高点 | 上涨力量减弱，潜在反转（辅助确认） |

**理想用法**：MOST 信号为主，背离为辅助确认。当 MOST 发出 BUY 且近期有 Bull Divergence 时，信号置信度最高。

---

## 4. 解决的痛点

### 痛点 1：裸 RSI 的假信号泛滥

裸 RSI 的经典用法是"超买超卖"（>70 卖，<30 买），但在强趋势中：
- 牛市里 RSI 可以在 60-80 之间反复震荡，始终不给买入信号
- 熊市里 RSI 可以在 20-40 之间反复震荡，始终不给卖出信号

**MOST 的解法**：不看绝对水位（70/30），而是看 **RSI 自身的趋势方向是否翻转**。RSI 从 65 跌到 55 可能就触发 SELL，不需要等到 30。

### 痛点 2：RSI 均线交叉太频繁

直接用"RSI 上穿/下穿其均线"做信号，在震荡市会来回穿越产生大量假信号。

**MOST 的解法**：止损线有"棘轮效应"（只升不降 / 只降不升），必须突破一个有意义的距离（percent）才会翻转方向，天然过滤了小幅震荡。

### 痛点 3：进出场时机模糊

RSI 背离虽然能预警反转，但"什么时候进场"缺乏明确定义。

**MOST 的解法**：提供精确的 crossover/crossunder 信号作为入场点，背离作为方向确认。

---

## 5. 使用场景

### 适合的场景

| 场景 | 原因 |
|------|------|
| **中长周期趋势跟踪**（日线/4H） | MOST 止损跟踪的设计初衷就是捕捉趋势 |
| **趋势型资产**（如 SOXL、BTC） | 高波动 + 有明显趋势的标的最能发挥 MOST 的优势 |
| **作为过滤器叠加到 DCA 策略** | BUY 信号期间执行定投，SELL 信号期间暂停，避免"越投越跌" |
| **与其他趋势指标组合** | 比如 MOST BUY + 价格在 EMA 上方 → 加大定投金额 |

### 不适合的场景

| 场景 | 原因 |
|------|------|
| **短线日内交易**（1m/5m） | RSI(14) + MA(5) + pivot(5,5) 的组合太慢 |
| **窄幅震荡市** | 即使有 MOST 过滤，长期横盘仍会产生来回翻转的亏损信号 |
| **精确止损/止盈** | 这是 RSI 空间的指标，不直接对应价格空间的止损位 |

---

## 6. 参数敏感度分析

| 参数 | 默认值 | 影响 | 调参建议 |
|------|--------|------|----------|
| RSI Length | 14 | RSI 平滑度。越大越平滑、信号越滞后 | 大周期可试 21；小周期可试 7-10 |
| MA Type | VAR | 对 RSI 的二次平滑方式 | VAR 在多数情况下最优；EMA 更通用 |
| MA Length | 5 | 均线周期。越大越平滑 | 与 RSI Length 配合，一般 3-7 |
| **STOP LOSS Percent** | **9.0** | **MOST 的灵敏度，最关键的参数** | **越小信号越频繁；越大信号越少但更可靠。建议 5-15 范围测试** |
| Pivot Lookback | 5/5 | 背离检测的回溯窗口 | 硬编码，无法通过 UI 调整 |

---

## 7. 伪代码总览

```python
def MOST_on_RSI(prices, rsi_len=14, ma_len=5, ma_type="VAR", pct=9.0):
    # === 第一层：计算 RSI ===
    rsi = calc_rsi(prices, rsi_len)

    # === 第二层：对 RSI 做均线平滑 ===
    if ma_type == "VAR":
        exMov = calc_var(rsi, ma_len)   # 自适应均线
    else:
        exMov = calc_ma(rsi, ma_len, ma_type)

    # === 第三层：MOST 止损跟踪 ===
    dir = 1  # 初始方向：多头
    MOST = []
    signals = []

    for i in range(len(exMov)):
        fark = exMov[i] * pct * 0.01

        # 计算多头止损线（只升不降）
        longStop = exMov[i] - fark
        if exMov[i] > longStop_prev:
            longStop = max(longStop, longStop_prev)

        # 计算空头止损线（只降不升）
        shortStop = exMov[i] + fark
        if exMov[i] < shortStop_prev:
            shortStop = min(shortStop, shortStop_prev)

        # 方向翻转判定
        if dir == -1 and exMov[i] > shortStop_prev:
            dir = 1    # 空翻多
        elif dir == 1 and exMov[i] < longStop_prev:
            dir = -1   # 多翻空

        MOST[i] = longStop if dir == 1 else shortStop

        # 信号
        if crossover(exMov, MOST, i):
            signals.append("BUY")
        elif crossunder(exMov, MOST, i):
            signals.append("SELL")

    # === 辅助：背离检测 ===
    for each pivot_low in rsi:
        if price_makes_lower_low and rsi_makes_higher_low:
            mark("Bull Divergence")
    for each pivot_high in rsi:
        if price_makes_higher_high and rsi_makes_lower_high:
            mark("Bear Divergence")

    return MOST, signals, divergences
```

---

## 8. 需要改进的地方

### 8.1 硬编码参数

背离检测的参数全部硬编码，无法通过 UI 调整：

```pinescript
lookbackRight = 5    // 无法通过 input 调整
lookbackLeft = 5
rangeUpper = 60
rangeLower = 5
```

**建议**：改为 `input.int()`，允许用户根据不同周期和标的调整。

### 8.2 缺少隐藏背离（Hidden Divergence）

当前只检测 **Regular Divergence**（反转信号），缺少 **Hidden Divergence**（趋势延续信号）：
- Hidden Bullish：价格更高低点 + RSI 更低低点 → 上升趋势延续
- Hidden Bearish：价格更低高点 + RSI 更高高点 → 下降趋势延续

Hidden Divergence 与 MOST 的趋势跟踪逻辑更匹配——在 MOST 已经指示多头时，Hidden Bullish Divergence 可以作为加仓信号。

### 8.3 VAR 均线的 9 日窗口硬编码

```pinescript
vUD = math.sum(vud1, 9)   // CMO 的回溯窗口固定为 9
vDD = math.sum(vdd1, 9)
```

CMO 的计算窗口固定为 9，与 `maLengthInput` 独立。这意味着 MA Length 只影响 alpha 的基数，但 CMO 的自适应灵敏度始终基于 9 日窗口。

**建议**：考虑让 CMO 窗口与 MA Length 联动，或独立暴露为参数。

### 8.4 MOST 信号与背离信号没有联动

两套信号完全独立运行，没有"MOST BUY + Bull Divergence 同时出现 → 强信号"这样的复合逻辑。

**建议**：增加复合信号标记，比如：
```
STRONG_BUY  = MOST_BUY 且最近 N 根 K 线内有 Bull Divergence
STRONG_SELL = MOST_SELL 且最近 N 根 K 线内有 Bear Divergence
```

### 8.5 没有信号强度分级

所有 BUY/SELL 信号权重相同，但实际上：
- RSI 在 30 附近的 BUY 比 RSI 在 55 附近的 BUY 更有意义
- 带背离确认的信号比单独 MOST 交叉更可靠

**建议**：输出信号强度（如 1-3 级），供下游策略做仓位管理。

### 8.6 缺少趋势强度输出

MOST 只输出方向（多/空），不输出强度。可以考虑输出 `exMov` 与 `MOST` 之间的距离百分比作为趋势强度指标，距离越大趋势越强。

### 8.7 无回测验证

PineScript indicator 模式只能显示图形，不能回测交易绩效。如果要验证信号有效性，需要改成 `strategy()` 模式或者在 Python 中重新实现（正好契合本项目的回测引擎）。

---

## 9. 与本项目 DCA 系统的整合思路

这个指标可以作为 `src/modules/entry.py` 中的一个新 Entry 模块：

| 整合方式 | 做法 | 效果 |
|----------|------|------|
| **作为入场过滤器** | MOST 方向 = 多头时才执行当日定投 | 在 RSI 趋势下行时暂停买入，避免"接飞刀" |
| **作为仓位调节器** | MOST 多头 → 正常仓位；MOST 空头 → 减半或暂停 | 更灵活，不完全停止定投 |
| **背离作为加仓信号** | Bull Divergence 出现时加倍买入 | 在潜在反转底部加大投入 |

需要在 Python 中重新实现 RSI → VAR → MOST 的计算链，然后封装为符合 `EntryModule` 接口的类。

---

## 10. 总结

MOST on RSI 的核心价值在于**用 Trailing Stop 的思想解决 RSI 信号模糊的问题**：

1. RSI 把价格映射到 0-100 空间 → 标准化了动量
2. VAR 均线自适应平滑 RSI → 过滤了 RSI 本身的噪音
3. MOST 在平滑 RSI 上做方向跟踪 → 给出明确的多空翻转点
4. 背离检测提供额外的反转预警 → 辅助确认

这是一个"层层过滤、逐步提纯"的设计哲学——每一层都在减少噪音、增加信号的可靠性。
