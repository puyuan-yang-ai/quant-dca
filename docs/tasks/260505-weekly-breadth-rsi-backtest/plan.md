# 周线回测实施方案

## 数据准备

### 1. SPY/SMH 周线数据

- 用 yfinance `interval='1wk'` 拉取周线 OHLC
- 保存为 `data/SPY_weekly.csv`、`data/SMH_weekly.csv`
- 列格式与日线一致：date, open, high, low, close

### 2. S&P 500 周线 Breadth

- 修改 `scripts/fetch_breadth.py`（或新建 `fetch_breadth_weekly.py`），拉取 500 只成分股的**周线**收盘价
- 计算 20 **周** SMA，统计 `close > 20周SMA` 的百分比
- 保存为 `data/sp500_breadth_weekly.csv`（date, breadth）
- 日期对齐：确保与 SPY 周线日期一致（yfinance 统一用周一）

## 引擎适配

### 3. Sharpe 年化因子

- `src/metrics.py` 的 `calc_sharpe_ratio` 当前硬编码 252
- 改为支持参数传入（252 日线 / 52 周线），不破坏已有日线调用
- 涉及函数：`calc_sharpe_ratio`、`calc_sortino_ratio`、`calc_all_metrics`

### 4. Entry 模块

- `BreadthEntry`：无需改动，只要 CSV 路径指向周线 Breadth 文件即可
- `RSISignalEntry`：无需改动，引擎自动在周线数据上算 14 周 RSI
- **新增** Breadth + RSI 的 AND/OR 组合（当前 `CombinedAndEntry` 是 NDay + RSI）
  - 方案：新建 `BreadthAndRSIEntry` / `BreadthOrRSIEntry`，或复用现有组合器

## 回测执行

### 5. 周线信号比较

- 在 `scripts/compare_signals.py` 中添加 `--weekly` 模式，或新建独立脚本
- 标准化执行层不变：市价买 1 股、无限价单、不止盈
- 5 个策略：无条件买入 / Breadth<20 / RSI v2 / AND / OR
- 环境：近三年全量（2022-01-01 ~ 2025-06-01）

### 6. 结果记录

- `docs/ground-truth.md` 新增"周线指标总表"
- 指标列与日线表一致：年化收益、总收益率、最大回撤、Sharpe、Calmar、成本优势、买入次数
- 手动更新

## 执行顺序

```
Step 1 → 拉取数据（SPY/SMH 周线 + Breadth 周线）
Step 2 → 改 metrics.py 支持周线年化因子
Step 3 → 新建 Breadth+RSI 组合 Entry
Step 4 → 跑回测，记录结果到 GT 表
```
