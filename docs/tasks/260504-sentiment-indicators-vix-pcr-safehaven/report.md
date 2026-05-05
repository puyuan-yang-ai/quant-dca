# 报告：VIX / Safe Haven Demand 情绪指标扩展

## 概要

本次扩展了两个情绪指标（VIX、Safe Haven Demand），作为数据源、入场策略、副图指标接入现有系统。Put/Call Ratio 因 Yahoo Finance 数据不可用（^CPCE 已下架）暂时跳过。

## 数据获取

| 指标 | 数据源 | 文件 | 范围 | 记录数 |
|------|--------|------|------|--------|
| VIX | Yahoo Finance `^VIX` | `data/vix_daily.csv` | 1990-01-02 ~ 2026-05-04 | 9,151 |
| Safe Haven | SPY + TLT 滚动收益差 | `data/safe_haven.csv` | 2002-08-27 ~ 2025-04-24 | 5,702 |

## 参数搜索结果

### VIX 阈值搜索

| 阈值 | 成本优势（近三年） | 买入次数 |
|------|----------------|---------|
| **VIX>30** | **+9.71%** ★ | 61 |
| VIX>35 | -7.22% | 8 |
| VIX>40 | -13.39% | 4 |
| VIX>45 | -12.26% | 3 |
| VIX>50 | -14.52% | 1 |

最优阈值：**VIX=30**。阈值越高信号越少，VIX>40 以上在近三年几乎不触发。

### Safe Haven 阈值搜索

| 阈值 | 成本优势（近三年） | 买入次数 |
|------|----------------|---------|
| **SH>0.02** | **+1.03%** ★ | 188 |
| SH>0.05 | -0.99% | 85 |
| SH>0.08 | -2.85% | 33 |
| SH>0.10 | -11.85% | 11 |

最优阈值：**SH=0.02**（唯一正值）。加权 Sharpe 排名与成本优势矛盾（Sharpe 选 0.10），原因是 SH>0.10 仅买 11 次，组合几乎全是现金，Sharpe 被"不交易"抬高。详见 `parameter-search-analysis.md`。

## 全量比较结果（9 策略，近三年成本优势排名）

| 排名 | 策略 | 成本优势 | 买入次数 |
|------|------|---------|---------|
| 1 | **VIX>30** | **+9.71%** | 61 |
| 2 | Breadth<20 | +6.63% | 95 |
| 3 | NDay5 | +5.52% | 162 |
| 4 | NDay5 AND RSI | +5.46% | 42 |
| 5 | NDay5 OR RSI | +5.09% | 168 |
| 6 | RSI v2 | +4.00% | 48 |
| 7 | EMA Filter | +3.36% | 335 |
| 8 | SafeHaven>0.02 | +1.03% | 188 |
| 9 | 无条件买入 | -0.99% | 830 |

### 关键发现

1. **VIX>30 成为新的最优入场信号**，超过此前的冠军 Breadth<20（+6.63%）。VIX 衡量隐含波动率（前瞻性恐慌），而 Breadth 衡量已实现价格位置（当前状态），VIX 的前瞻性可能是其优势来源。

2. **SafeHaven>0.02 排名垫底**（+1.03%），仅比无条件买入好 2 个百分点。验证了"2022 后股债双杀导致避险信号失效"的假说。在传统股债负相关环境中（如 2008、2020），该信号可能有效，但在加息周期下失去预测力。

3. **Put/Call Ratio 数据不可用**。^CPCE 已从 Yahoo Finance 下架，CBOE 官网封锁直接下载。后续如需此数据，需寻找替代数据源或手动从 CBOE DataShop 购买。

## 变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/fetch_sentiment.py` | 新增 | VIX + Safe Haven 数据获取 |
| `data/vix_daily.csv` | 新增 | VIX 日线数据 |
| `data/safe_haven.csv` | 新增 | Safe Haven 数据 |
| `src/modules/entry.py` | 修改 | 新增 VIXEntry、SafeHavenEntry |
| `scripts/compare_signals.py` | 修改 | 新增 --mode vix/safehaven，更新 --mode full |
| `src/interactive_chart.py` | 修改 | 新增 VIX 副图面板（四图同步） |
| `scripts/show_chart.py` | 修改 | 加载 VIX 数据 |
