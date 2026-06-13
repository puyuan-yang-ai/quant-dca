# 特征升级：从通用指标到规则信号特征

## 背景

MVP v1 使用了 8 个通用连续值特征（rsi_14, ema20_dist, ret_5d 等），AUC 仅 0.535。核心问题：部分特征缺乏可解释性，且没有利用项目已有的 9 个 Entry 规则信号。

## 目标

用"高可解释性"原则重构特征集：每个特征都能用一句话解释它代表什么市场状态，且与现有规则系统有直接关联。

## 特征设计

### 保留的连续值特征（4 个）

| 特征 | 可解释性 | 理由 |
|------|----------|------|
| rsi_14 | RSI 超买超卖水平 | RSISignalEntry 的底层数据 |
| vix | 市场恐慌程度 | VIXEntry 的底层数据 |
| breadth | 市场参与宽度 | BreadthEntry 的底层数据 |
| ema20_dist | 价格偏离均线程度 | EMAFilter/NDayConfirm 的底层数据 |

### 移除的特征（4 个）

| 特征 | 移除原因 |
|------|----------|
| ema50_dist | 系统用 EMA20 不用 EMA50，关联弱 |
| ret_5d | 纯动量，无对应规则逻辑 |
| ret_20d | 同上 |
| vol_5d | 系统用 volatility_tiers 分位数，不是简单 std |

### 新增布尔特征（9 个 Entry 信号）

每个 Entry 规则在信号日当天是否触发（0/1）：

| 特征 | 来源 | 含义 |
|------|------|------|
| sig_ema_filter | EMAFilterEntry | 价格在 EMA 下方 |
| sig_nday3 | NDayConfirmEntry(n=3) | 连续 3 天低于 EMA |
| sig_rsi | RSISignalEntry | 当天有 RSI v2 买入信号 |
| sig_breadth | BreadthEntry(threshold=20) | 市场宽度极低 |
| sig_vix | VIXEntry(threshold=30) | VIX 极高 |
| sig_safe_haven | SafeHavenEntry(threshold=0.05) | 避险资产跑赢 |
| sig_breadth_consec | BreadthConsecutiveEntry | 连续宽度衰减 |
| sig_spread_conv | SpreadConvergenceEntry | 宽度收敛信号 |
| sig_breadth_div | BreadthDivergenceEntry | 价格新低+宽度背离 |

### 新增连续/离散特征（5 个）

| 特征 | 类型 | 含义 |
|------|------|------|
| consecutive_below_ema | 离散整数 | 连续低于 EMA 天数 |
| deviation | 连续 | (close - EMA) / EMA |
| breadth_c2 | 连续 | 2日连续宽度 |
| safe_haven | 连续 | TLT 20d ret - SPY 20d ret |
| rsi_signal_strength | 离散 0-3 | RSI v2 信号强度（无/B/B+/B++） |

### 最终特征集（18 个）

- 连续值：4（保留）+ 4（新增）= 8
- 布尔值：9（Entry 信号）
- 离散值：1（rsi_signal_strength）
- **合计 18 个特征，全部高可解释性**

## 实施方案

1. 重写 `ml/features.py`，将 9 个 Entry 规则的判断逻辑独立实现为逐日计算（不依赖 BacktestEngine 的 context 对象）
2. 对每个信号日提取当天所有 18 个特征值
3. 重新运行 `python -m ml.run_mvp` 对比升级前后的 AUC 和胜率变化

## 预期收益

- 模型输入更丰富（18 vs 8），且每个特征都有明确的市场含义
- XGBoost 可以学到"哪些规则组合同时触发时信号更可靠"
- 特征重要度可直接解读为"哪个规则对信号质量贡献最大"
