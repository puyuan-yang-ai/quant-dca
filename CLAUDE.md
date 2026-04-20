# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指引。

## 项目概述

SOXL/SMH 多层次定投（DCA）回测系统。在不同市场环境（熊市、牛市、熊转牛、牛转熊）下，对杠杆 ETF（SOXL）进行多种 DCA 策略回测，以 SMH 作为基准和利润分流标的。

代码中的注释、日志、文档均为中文，策略/模块名称和代码标识符为英文。

## 常用命令

```bash
# 交互式图表（引擎路径，启动 HTTP 服务，浏览器访问）
bash show_chart.sh                        # 默认 bear-bull 环境 + best 策略
bash show_chart.sh --env all              # 全量数据（2010-2025）
bash show_chart.sh --env bear             # 纯熊市（2022）
bash show_chart.sh --env bull             # 纯牛市（2022.10-2024.07）
bash show_chart.sh --env bear-bull        # 熊转牛（2022-2024.07）
bash show_chart.sh --env bull-bear        # 牛转熊（2022.10-2025.04）
bash show_chart.sh --strategy baseline    # 使用 baseline 策略（默认 best）
bash show_chart.sh --port 9871            # 指定端口（默认 9870）

# 运行单次回测（旧版路径，通过 config/settings.yaml 选择场景配置）
python main.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]

# 运行完整 4 阶段实验流水线（所有策略组合 × 所有市场环境）
python run_experiments.py

# 辅助脚本
python scripts/plot_smh_open.py
python scripts/plot_signals.py
python scripts/run_sota_comparison.py
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
| **入场** | `entry.py` | `UnconditionalEntry`、`EMAFilterEntry`、`NDayConfirmEntry` | 当日是否下市价单/挂限价单 |
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

### 交互式图表

`scripts/show_chart.py`（通过 `bash show_chart.sh` 调用）执行回测后启动 HTTP 服务，在浏览器中展示：

- **主图**：K 线 + EMA 均线 + 交易标记（买入/止盈箭头）
- **RSI 副图**：RSI(14) 曲线 + EMA(5) 快均线 + B/B+/B++/S/S+/S++ 信号标记
- 两图时间轴和十字光标同步

市场环境配置在 `experiments/configs.py` 的 `MARKET_ENVS` 字典中。

### RSI v2 指标系统

`src/rsi_signals.py` 实现了 RSI v2 三事件信号系统（翻译自 TradingView PineScript `docs/indicators/most-on-rsi/most-on-rsi-v2.pine`）：

| 事件 | 触发条件 | 信号 |
|------|---------|------|
| 事件 1（左侧预警） | RSI 下破 30 / 上破 70 | B / S |
| 事件 2（右侧确认） | RSI 上穿/下穿快均线 + 门槛 + 评分升级 | B / B+ / B++ |
| 事件 3（背离） | 价格创新低但 RSI 未新低（参考点 RSI ≤ 30） | B+ / B++ |

信号强度：B（1 分）< B+（2 分）< B++（3 分）。目前仅用于可视化，未接入策略决策流程。

详细设计文档见 `docs/indicators/most-on-rsi/v2-design.md`，使用指南见 `usage-guide-v2.md`，局限性分析见 `rsi-limitations.md`。

### 核心支撑模块

- `src/backtest_engine.py`：`BacktestEngine` + `Context`（每日上下文，包含 EMA、偏离度、持仓状态等）。运行时自动计算 RSI v2 信号并存入 metrics。
- `src/portfolio.py`：`Portfolio` 类，管理 SOXL 仓位、SMH 分流、带 TTL 过期的止盈挂单
- `src/indicators/`：技术指标模块（`calc_ema`、`calc_rsi`、偏离度、波动率档口）。纯函数，list 输入 list 输出。
- `src/rsi_signals.py`：RSI v2 三事件信号系统（见上文）
- `src/metrics.py`：绩效指标（Sharpe、Calmar、最大回撤、年化收益率）
- `src/data_loader.py`：CSV 加载器，输出 `[{'date', 'open', 'high', 'low', 'close'}, ...]`
- `src/chart.py`：Matplotlib 图表生成 → `output/`（旧版路径）
- `src/interactive_chart.py`：Lightweight Charts 交互式图表 + RSI 副图 → HTTP 服务（引擎路径）

### 配置系统（旧版路径）

`config/settings.yaml` 通过 `use_config` 字段指向场景 YAML 文件。场景配置定义：策略名、日期范围、数据文件、手续费率、订单层级 `[价格系数, 股数]`。

### 数据

`data/` 下的 CSV 文件：`SOXL_adjusted.csv`（2010-2025）、`SOXL_unadjusted_price.csv`、`SMH_adjusted.csv`（2000-2025）。列：date, open, high, low, close。

## 依赖

`pyyaml`、`matplotlib`（见 `requirements.txt`）。使用 venv 虚拟环境（`.venv/`）。
