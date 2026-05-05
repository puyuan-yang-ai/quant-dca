# 情绪指标扩展：VIX / Put-Call Ratio / Safe Haven Demand

## 背景

项目已有两类市场情绪数据：
- **Market Breadth**（S&P 500 股价宽度）：成分股中站上 20 日均线的百分比，已实现为副图指标 + `BreadthEntry` 策略
- **RSI v2 信号**：个股动量超卖信号，已接入 `RSISignalEntry`

CNN Fear & Greed Index 由 7 个子指标合成，其中 Stock Price Breadth 已完成。本次任务扩展另外 3 个可复现的子指标，为后续 ML 量化提供更多维度的特征输入。

## 目标

获取 VIX、Put/Call Ratio、Safe Haven Demand 三项数据，作为 **数据源 + 副图指标 + 可选入场策略** 接入现有系统。主要价值在于为未来 ML pipeline 积累多维度情绪特征。

## 三个指标概述

### 1. VIX（市场波动率）

- **含义**：S&P 500 期权隐含波动率，反映市场对未来 30 天波动的预期
- **数据源**：Yahoo Finance `^VIX`，1990 年至今
- **解读**：12-15 平静 / 20-25 紧张 / 30+ 恐慌 / 40+ 极度恐慌
- **用途**：副图指标 + `VIXEntry(threshold=30)` 入场策略
- **与 Breadth 的关系**：高度相关（~60-70% 重叠）。大面积下跌 → Breadth 低 → 期权市场买 put 对冲 → VIX 高。本质是同一件事的两个视角：Breadth 看"多少股票在跌"，VIX 看"市场预期波动多大"
- **预期 ROI**：作为独立策略边际提升有限（和 Breadth 冗余），但作为 ML 特征有独立价值（隐含波动率 vs 已实现价格位置）

### 2. Put/Call Ratio（看跌/看涨期权比率）

- **含义**：CBOE 每日 Put 成交量 / Call 成交量
- **数据源**：Yahoo Finance `^CPCE`（Equity Put/Call Ratio），2003 年至今
- **解读**：< 0.7 过度乐观 / 0.7-1.0 正常 / > 1.0 恐慌对冲（逆向买入信号）
- **用途**：副图指标 + 可选策略（需 5 日均值平滑，阈值待定）
- **与 VIX/Breadth 的关系**：中等相关（~30-40% 重叠）。VIX 是波动率的"价格"，P/C Ratio 是交易者的"行为"。VIX 可因单一事件飙升，P/C 反映实际下注行为，有时会出现 VIX 不太高但 P/C 很高的情况（温水煮青蛙式恐慌）
- **预期 ROI**：作为 ML 特征价值最高——捕捉"交易者实际行为"维度是 Breadth 和 VIX 都没有的

### 3. Safe Haven Demand（避险需求）

- **含义**：SPY 与 TLT（20 年国债 ETF）的滚动收益差。TLT 跑赢 SPY → 资金逃离风险资产
- **数据源**：Yahoo Finance `TLT`（SPY 数据已有），2002 年至今
- **计算**：`safe_haven = tlt_20d_return - spy_20d_return`，正值 = 避险情绪
- **用途**：副图指标 + ML 特征
- **局限性**：2022 年后股债双杀（美联储激进加息），传统"股跌债涨"负相关被打破。在 2022-2025 回测区间内信号可能失真
- **预期 ROI**：作为独立策略不可靠，但作为 ML 特征仍有价值——"相关性变化"本身也是信息。实现成本极低（1 ticker + 简单计算），值得收集

## 定位说明

| 指标 | 副图指标 | 入场策略 | ML 特征 |
|------|---------|---------|---------|
| VIX | 是 | 是（VIXEntry） | 是 |
| Put/Call Ratio | 是 | 可选（需调参） | 是 |
| Safe Haven Demand | 是 | 不推荐 | 是 |

- **副图指标**：接入 interactive_chart.py，可视化参考
- **入场策略**：接入 compare_signals.py，通过标准化比较验证信号质量
- **ML 特征**：数据存 CSV，后续 ML pipeline 直接读取
