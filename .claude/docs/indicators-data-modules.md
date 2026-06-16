# 指标体系、数据与核心模块（完整版）

CLAUDE.md 只留指针，本文件汇总指标原理、数据文件、核心支撑模块。深度设计文档另有专门位置，本文给出指针。

## RSI v2 三事件信号系统

`src/rsi_signals.py`（翻译自 `docs/indicators/most-on-rsi/most-on-rsi-v2.pine`）：

| 事件 | 触发 | 信号 |
|------|------|------|
| 事件 1（左侧预警） | RSI 下破 30 / 上破 70 | B / S |
| 事件 2（右侧确认） | RSI 上穿/下穿快均线 + 门槛 + 评分升级 | B / B+ / B++ |
| 事件 3（背离） | 价格新低但 RSI 未新低（参考点 RSI ≤ 30） | B+ / B++ |

强度 B(1) < B+(2) < B++(3)。已接入决策流程（`RSISignalEntry` 及组合器）。引擎运行时自动计算 RSI v2 信号并存入 metrics。
深度文档：`docs/indicators/most-on-rsi/v2-design.md`（设计）、`usage-guide-v2.md`（用法）、`rsi-limitations.md`（局限）。

## S&P 500 Market Breadth

`data/sp500_breadth.csv`（1993-2026，由 `scripts/fetch_breadth.py` 生成）。
**Breadth = S&P 500 成分股中股价站上 20 日均线的百分比（0-100）。** >80 过热 / ~50 正常 / <20 恐慌抄底区。
存在幸存者偏差（用当前成分股回算历史），2020 后影响很小。
背离检测：`src/breadth_divergence.py`（触发区 Breadth<25，swing low 窗口 N=5）。详见 `docs/tasks/260505-market-breadth-divergence-entry/`。

## VIX / Safe Haven Demand

- `data/vix_daily.csv`（1990-2026）：VIX = S&P 500 期权隐含波动率。12-15 平静 / 20-25 紧张 / 30+ 恐慌 / 40+ 极度恐慌。
- `data/safe_haven.csv`（2002-2025）：Safe Haven = TLT 20 日收益 − SPY 20 日收益，正值=避险。2022 后股债双杀致信号失效。
- 由 `scripts/fetch_sentiment.py` 生成。接入 `VIXEntry`、`SafeHavenEntry`。详见 `docs/tasks/260504-sentiment-indicators-vix-pcr-safehaven/`。

## Swing Low 波段底部检测

`src/indicators/__init__.py`：`detect_swing_lows()`、`detect_swing_highs()`、`filter_swing_lows_by_drop()`。
- Swing Low：第 i 天收盘价严格小于左右各 N 天。日线 N=10，周线 N=5。
- 最小跌幅过滤：对每个 Swing Low 找前最近 Swing High，跌幅 <3% 视为横盘噪声过滤。
- 用途：图表标注（橙点保留/灰× 过滤）；Oracle 基准（低于均价的 Swing Low 均价）。极值见 `docs/ground-truth.md`。

## 交互式图表

`scripts/show_chart.py`（`bash show_chart.sh` 调用）回测后启动 HTTP 服务：
- 主图：K 线 + EMA + 交易标记（买入/止盈箭头）+ Swing Low 标注
- RSI 副图：RSI(14) + EMA(5) + B/B+/B++/S/S+/S++ 标记
- Breadth 副图：0-100 曲线 + 20/50/80 参考线 + 背离信号（橙箭头 + 连线）
- VIX 副图：曲线 + 20/30 参考线 + >30 恐慌区填充
- 四图时间轴与十字光标同步。环境配置在 `experiments/configs.py` 的 `MARKET_ENVS`。

## ML Meta-Labeling

`ml/` 用 XGBoost 对规则买入信号做二次筛选。版本化管理（`ml/versions.py`，当前 `ACTIVE_VERSION = "v3"`）。
- 4 套特征：`features_v1.py`(18) / `features_v2.py`(15) / `features_v3.py`(21)
- 标注方法：`labeling.py`（fixed_horizon / triple_barrier / relative_low / sl_proximity / sl_multi）
- 入口 `python -m ml.run_mvp`，评估 `ml/evaluate.py`。

## 核心支撑模块（src/）

| 文件 | 职责 |
|------|------|
| `backtest_engine.py` | `BacktestEngine` + `Context`（每日上下文：EMA、偏离度、持仓等）。自动算 RSI v2 存入 metrics |
| `portfolio.py` | `Portfolio`：SPY 仓位 + SMH 分流 + 带 TTL 过期的止盈挂单 |
| `indicators/__init__.py` | 技术指标纯函数（calc_ema、calc_rsi、swing low/high、偏离度、波动率档口）。list 入 list 出 |
| `rsi_signals.py` | RSI v2 三事件信号 |
| `breadth_divergence.py` | Breadth 背离检测 |
| `metrics.py` | Sharpe、Calmar、最大回撤、年化收益 |
| `utils.py` | 工具（最大回撤计算等） |
| `data_loader.py` | CSV 加载器，输出 `[{'date','open','high','low','close'}, ...]` |
| `chart.py` | Matplotlib 图表 → `output/`（旧版路径） |
| `interactive_chart.py` | Lightweight Charts 交互式图表 → HTTP（引擎路径） |

注意：`src/indicators/` 是单文件包，所有指标函数都在 `__init__.py` 里，无其他子文件。

## 数据文件（data/）

- 日线：`SPY_adjusted.csv`(1993-2026)、`SMH_adjusted.csv`(2000-2026)、`SOXL_adjusted.csv`、`SOXL_unadjusted_price.csv`、`es_daily.csv`
- 周线：`SPY_weekly.csv`、`SMH_weekly.csv`、`sp500_breadth_weekly.csv`、`vix_weekly.csv`
- 指标：`sp500_breadth.csv`、`vix_daily.csv`、`safe_haven.csv`
- K 线列：date, open, high, low, close
