# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指引。

## 项目概述

SPY/SMH 多层次定投（DCA）回测系统。在不同市场环境（熊市、牛市、熊转牛、牛转熊）下，对 SPY 进行多种 DCA 策略回测，以 SMH 作为基准和利润分流标的。

代码中的注释、日志、文档均为中文，策略/模块名称和代码标识符为英文。

## 常用命令

### 脚本一览

| 脚本 | 用途 | 使用场景 |
|------|------|---------|
| `bash show_chart.sh` | 交互式图表（K 线 + RSI 副图 + Breadth 副图 + VIX 副图），启动 HTTP 服务 | 可视化查看策略回测效果 |
| `python scripts/compare_signals.py` | 信号策略比较（标准化执行，纯比较择时质量） | 快速筛选最优 Entry 模块 |
| `python scripts/fetch_breadth.py` | 预计算 S&P 500 Market Breadth 数据 | 生成 `data/sp500_breadth.csv`，需联网 |
| `python scripts/fetch_sentiment.py` | 获取 VIX + Safe Haven 情绪指标数据 | 生成 `data/vix_daily.csv` + `data/safe_haven.csv`，需联网 |
| `python run_experiments.py` | 4 阶段执行层参数优化（网格搜索） | 锁定信号后精细调优执行参数 |
| `python main.py` | 单次回测（旧版路径，YAML 配置） | 简单的 baseline 策略回测 |

### 详细用法

```bash
# ── 交互式图表 ──
bash show_chart.sh                        # 默认 bear-bull 环境 + best 策略
bash show_chart.sh --env all              # 近三年全量（2022-2025）
bash show_chart.sh --env bear             # 纯熊市（2022）
bash show_chart.sh --env bull             # 纯牛市（2022.10-2024.07）
bash show_chart.sh --env bear-bull        # 熊转牛（2022-2024.07）
bash show_chart.sh --env bull-bear        # 牛转熊（2022.10-2025.04）
bash show_chart.sh --strategy baseline    # 使用 baseline 策略（默认 best）
bash show_chart.sh --port 9871            # 指定端口（默认 9870）

# ── 信号策略比较（快速迭代用） ──
# 标准化执行（市价买1股、无限价单、不止盈），5 个环境自动跑完
# 输出对比表格 + 加权 Sharpe 排名，秒级完成
python scripts/compare_signals.py                            # 默认：兼容旧版策略列表
python scripts/compare_signals.py --mode nday                # NDay 参数搜索（1-5）
python scripts/compare_signals.py --mode vix                 # VIX 阈值搜索（30/35/40/45/50）
python scripts/compare_signals.py --mode safehaven           # Safe Haven 阈值搜索（0.02-0.10）
python scripts/compare_signals.py --mode full --best-nday 5 --best-vix 30 --best-sh 0.02  # 全量比较

# ── 执行层参数优化（精细调优用） ──
python run_experiments.py

# ── 旧版路径 ──
python main.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
```

目前没有配置测试框架。`tests/test_strategies.py` 存在但为空文件。

## 架构

### 两条回测路径

1. **旧版路径**（`main.py` → `src/backtest.py`）：简单循环，通过 `src/strategies/baseline.py` 的 `execute_day()` 函数执行。使用 `config/` 下的 YAML 配置驱动，仅支持 baseline 策略。

2. **引擎路径**（`run_experiments.py` / `scripts/show_chart.py` → `src/backtest_engine.py`）：有状态的 `BacktestEngine` 类，搭配 `ComposableStrategy` 使用。这是策略研究的主要系统。

### 可组合策略系统

`ComposableStrategy`（`src/strategies/composable.py`）将 4 个独立模块组装成完整策略。各模块位于 `src/modules/`：

| 模块 | 文件 | 实现类 | 用途 |
|------|------|--------|------|
| **档口** | `tiers.py` | `FixedTiers`、`VolatilityTiers` | 限价挂单的价格层级（距开盘价的跌幅百分比） |
| **入场** | `entry.py` | `UnconditionalEntry`、`EMAFilterEntry`、`NDayConfirmEntry`、`RSISignalEntry`、`BreadthEntry`、`VIXEntry`、`SafeHavenEntry`、`CombinedAndEntry`、`CombinedOrEntry` | 当日是否下市价单/挂限价单 |
| **仓位** | `position.py` | `FixedPyramid`、`AdaptivePyramid`、`DowntrendOnly` | 各档买入股数 |
| **止盈** | `take_profit.py` | `NoTakeProfit`、`DeviationPeakTP`、`TrendConfirmTP`、`DualTakeProfit` | 何时卖出并将利润分流至 SMH |

每日决策流程：档口 → 入场 → 仓位 → 止盈。

### 实验框架

`experiments/` 执行 4 阶段逐步优化：
1. **第一阶段**：档口设置（固定比例 vs 波动率自适应）
2. **第二阶段**：入场条件（锁定最优档口）
3. **第三阶段**：仓位分布（锁定最优档口 + 入场）
4. **第四阶段**：止盈策略（锁定最优档口 + 入场 + 仓位）

每阶段在 5 个市场环境（bear / bull / bear-bull / bull-bear / all）下测试所有变体，使用加权综合 Sharpe/Calmar 评分。每阶段最优模块锁定后传递至下一阶段。结果输出到 `experiments_result/`。

实验参数配置在 `experiments/configs.py`（Python 代码，非 YAML）。报告由 `experiments/reporter.py` 生成。最优策略组合 `BEST_*` 常量也定义在 `configs.py` 中。

### 信号策略比较

比较不同信号策略（Entry 模块）时，使用**标准化执行层**：统一用最简配置（市价单买 1 股、无限价单、不止盈），消除执行层差异，纯粹比较信号质量。

```python
# 标准化执行层（所有信号比较统一使用）
tiers    = FixedTiers(drops=())           # 只有市价单
position = FixedPyramid(market_shares=1)  # 固定买 1 股
take_profit = NoTakeProfit()              # 不止盈
```

流程：先用标准化执行快速筛信号 → 找到最优信号后再精细调优执行层参数。详见 `docs/tasks/260419-rsi-signal-comparison-and-strategy-reflection/strategy-comparison-guide.md`。

### 交互式图表

`scripts/show_chart.py`（通过 `bash show_chart.sh` 调用）执行回测后启动 HTTP 服务，在浏览器中展示：

- **主图**：K 线 + EMA 均线 + 交易标记（买入/止盈箭头）
- **RSI 副图**：RSI(14) 曲线 + EMA(5) 快均线 + B/B+/B++/S/S+/S++ 信号标记
- **Breadth 副图**：S&P 500 Market Breadth 曲线（0-100），20/50/80 参考线，上方绿色填充/下方红色填充
- **VIX 副图**：VIX 曲线，20/30 参考线，>30 红色恐慌区域填充
- 四图时间轴和十字光标同步

市场环境配置在 `experiments/configs.py` 的 `MARKET_ENVS` 字典中。

### RSI v2 指标系统

`src/rsi_signals.py` 实现了 RSI v2 三事件信号系统（翻译自 TradingView PineScript `docs/indicators/most-on-rsi/most-on-rsi-v2.pine`）：

| 事件 | 触发条件 | 信号 |
|------|---------|------|
| 事件 1（左侧预警） | RSI 下破 30 / 上破 70 | B / S |
| 事件 2（右侧确认） | RSI 上穿/下穿快均线 + 门槛 + 评分升级 | B / B+ / B++ |
| 事件 3（背离） | 价格创新低但 RSI 未新低（参考点 RSI ≤ 30） | B+ / B++ |

信号强度：B（1 分）< B+（2 分）< B++（3 分）。已接入策略决策流程，通过 `RSISignalEntry`、`CombinedAndEntry`、`CombinedOrEntry` 参与回测。

详细设计文档见 `docs/indicators/most-on-rsi/v2-design.md`，使用指南见 `usage-guide-v2.md`，局限性分析见 `rsi-limitations.md`。

### S&P 500 Market Breadth 指标

`data/sp500_breadth.csv` 存储预计算的 Market Breadth 数据（1993-2025），由 `scripts/fetch_breadth.py` 生成。

**Breadth = S&P 500 成分股中，股价站在 20 日均线上方的百分比（0-100）。**

| Breadth 值 | 含义 |
|-----------|------|
| > 80 | 市场过热，绝大多数股票在涨 |
| ~50 | 正常分化 |
| < 20 | 市场恐慌，绝大多数股票在跌（恐慌抄底区） |

数据来源：用 yfinance 拉取当前 S&P 500 全部成分股历史收盘价，逐日计算"收盘价 > 20 日 SMA"的比例。存在幸存者偏差（用当前成分股回算历史），但在 2020 年后的近期数据中影响很小。

已接入策略决策流程：`BreadthEntry`（Breadth < 20 时买入）。在近三年数据中成本优势排名第二（+6.63%）。详见 `docs/tasks/260504-breadth-entry-spy-signal-comparison/`。

### VIX / Safe Haven Demand 情绪指标

`data/vix_daily.csv` 存储 VIX 日线数据（1990-2026），`data/safe_haven.csv` 存储 Safe Haven 数据（2002-2025），由 `scripts/fetch_sentiment.py` 生成。

**VIX = S&P 500 期权隐含波动率**，反映市场对未来 30 天波动的预期。12-15 平静 / 20-25 紧张 / 30+ 恐慌 / 40+ 极度恐慌。

**Safe Haven = TLT 20日收益 - SPY 20日收益**，正值表示资金流向国债（避险情绪）。2022 后股债双杀导致信号失效。

已接入策略决策流程：`VIXEntry`（VIX > 30 时买入，成本优势 +9.71%，排名第一）、`SafeHavenEntry`（Safe Haven > 0.02 时买入，成本优势 +1.03%，排名垫底）。详见 `docs/tasks/260504-sentiment-indicators-vix-pcr-safehaven/`。

### 核心支撑模块

- `src/backtest_engine.py`：`BacktestEngine` + `Context`（每日上下文，包含 EMA、偏离度、持仓状态等）。运行时自动计算 RSI v2 信号并存入 metrics。
- `src/portfolio.py`：`Portfolio` 类，管理 SPY 仓位、SMH 分流、带 TTL 过期的止盈挂单
- `src/indicators/`：技术指标模块（`calc_ema`、`calc_rsi`、偏离度、波动率档口）。纯函数，list 输入 list 输出。
- `src/rsi_signals.py`：RSI v2 三事件信号系统（见上文）
- `src/metrics.py`：绩效指标（Sharpe、Calmar、最大回撤、年化收益率）
- `src/data_loader.py`：CSV 加载器，输出 `[{'date', 'open', 'high', 'low', 'close'}, ...]`
- `src/chart.py`：Matplotlib 图表生成 → `output/`（旧版路径）
- `src/interactive_chart.py`：Lightweight Charts 交互式图表 + RSI 副图 + Breadth 副图 + VIX 副图 → HTTP 服务（引擎路径）

### 配置系统（旧版路径）

`config/settings.yaml` 通过 `use_config` 字段指向场景 YAML 文件。场景配置定义：策略名、日期范围、数据文件、手续费率、订单层级 `[价格系数, 股数]`。

### 数据

`data/` 下的 CSV 文件：`SPY_adjusted.csv`（1993-2025，主标的）、`SMH_adjusted.csv`（2000-2025）、`sp500_breadth.csv`（1993-2025，Market Breadth 预计算数据）、`vix_daily.csv`（1990-2026，VIX 日线）、`safe_haven.csv`（2002-2025，Safe Haven 数据）、`SOXL_adjusted.csv`（2010-2025，旧标的）。K 线数据列：date, open, high, low, close。Breadth 数据列：date, breadth（0-100 百分比）。VIX 数据列：date, close。Safe Haven 数据列：date, spy_ret_20d, tlt_ret_20d, safe_haven。

## 依赖

`pyyaml`、`matplotlib`、`yfinance`、`pandas`（见 `requirements.txt`）。使用 venv 虚拟环境（`.venv/`）。
