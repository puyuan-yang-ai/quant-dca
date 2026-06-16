# 命令参考（完整版）

CLAUDE.md 的「命令」章节只列高频入口，本文件是逐字可粘贴的完整用法。

## 脚本一览

| 脚本 | 用途 |
|------|------|
| `bash show_chart.sh` | 交互式图表（K 线 + RSI/Breadth/VIX 副图），启动 HTTP 服务 |
| `python run_experiments.py` | 4 阶段执行层参数优化（网格搜索） |
| `python scripts/compare_signals.py` | 信号策略比较（标准化执行，纯比较择时质量） |
| `python scripts/run_sota_comparison.py` | 两套 SOTA 策略在 7 种环境下完整回测对比 |
| `python scripts/validate_signal_returns.py` | 信号前瞻收益验证（5/10/20 日涨幅、胜率） |
| `python scripts/plot_signals.py` | K 线买点可视化 |
| `python scripts/fetch_daily_data.py` | 拉取 SPY/SMH/SOXL 复权日线 OHLCV（联网） |
| `python scripts/fetch_weekly_data.py` | 拉取 SPY/SMH 周线 + 周线 Breadth（联网） |
| `python scripts/fetch_breadth.py` | 预计算 S&P 500 Market Breadth（联网） |
| `python scripts/fetch_sentiment.py` | 拉取 VIX + Safe Haven 情绪指标（联网） |
| `python scripts/fetch_spy_options.py` | SPY 期权链实时快照（联网） |
| `python scripts/lunar_analysis.py` | 月相周期 vs SPY 收益率研究分析 |
| `python scripts/plot_smh_open.py` | SMH 开盘价日线图 |
| `python -m ml.run_mvp` | ML Meta-Labeling 一键运行 |
| `python -m ml.compare_entry_signals` | ML 信号 vs 各 Entry 规则横向对比 |
| `python -m ml.show_signals_chart` | ML 信号交互式图表可视化 |
| `python main.py` | 旧版单次回测（YAML 配置，仅 baseline，已不常用） |

MMA 期权研究相关脚本（独立子系统，由 mma-* skill 驱动）：
`scripts/fetch_es_for_mma.py`、`scripts/fetch_spy_for_mma.py`、`scripts/plot_mma_scenario.py`、`scripts/plot_mma_weekly_20260601.py`、`scripts/plot_scenario_chart.py`。

## 交互式图表

```bash
bash show_chart.sh                        # 默认 bear-bull 环境 + best 策略
bash show_chart.sh --env all              # 近四年全量（2022-2026）
bash show_chart.sh --env bear             # 纯熊市（2022）
bash show_chart.sh --env bull             # 纯牛市（2022.10-2024.07）
bash show_chart.sh --env bear-bull        # 熊转牛（2022-2024.07）
bash show_chart.sh --env bull-bear        # 牛转熊（2022.10-2025.04）
bash show_chart.sh --strategy baseline    # 使用 baseline 策略（默认 best）
bash show_chart.sh --port 9871            # 指定端口（默认 9870）
```

## 信号策略比较（快速迭代）

标准化执行（市价买 1 股、无限价单、不止盈），5 个环境自动跑完，秒级输出对比表 + 加权 Sharpe 排名。

```bash
python scripts/compare_signals.py                            # 默认：兼容旧版策略列表
python scripts/compare_signals.py --mode nday                # NDay 参数搜索（1-5）
python scripts/compare_signals.py --mode vix                 # VIX 阈值搜索（30/35/40/45/50）
python scripts/compare_signals.py --mode safehaven           # Safe Haven 阈值搜索（0.02-0.10）
python scripts/compare_signals.py --mode breadth-div         # Breadth 背离参数搜索（15/20/25/30）
python scripts/compare_signals.py --mode full --best-nday 5 --best-vix 30 --best-sh 0.02
```

## ML Meta-Labeling

```bash
python -m ml.run_mvp                          # 使用 versions.py 中激活版本（当前 v3）
python -m ml.run_mvp --method sl_proximity    # 指定标注方法
python -m ml.run_mvp --method all             # 全部标注方法横向对比
```

`--method` 可选值（run_mvp.py:45）：`fixed_horizon`、`triple_barrier`、`relative_low`、`sl_proximity`、`sl_multi`、`all`。

## 数据更新

```bash
python scripts/fetch_daily_data.py             # 拉取全部日线数据
python scripts/fetch_daily_data.py --ticker SPY  # 只拉取 SPY
python scripts/fetch_weekly_data.py            # 拉取周线数据
python scripts/fetch_breadth.py                # 更新 Breadth
python scripts/fetch_sentiment.py              # 更新 VIX + Safe Haven
```
