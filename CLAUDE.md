# CLAUDE.md

供未来 AI 智能体使用的操作宪法 + 导航索引。本文件只留宪法条款与指针；详细细则拆在 `.claude/docs/`，按需阅读（指针处标注了"何时读"）。

## 目的（Purpose）

SPY/SMH 多层次定投（DCA）回测系统 + ML Meta-Labeling 信号研究。在不同市场环境下对 SPY 跑多种 DCA 策略回测，SMH 作基准与利润分流标的；ML 方向用 XGBoost 对规则信号做 Meta-Labeling 筛选。

技术栈：Python（venv 在 `.venv/`）。核心依赖 pandas、numpy、scipy、scikit-learn、xgboost、yfinance、matplotlib、lightweight-charts、pyyaml、curl_cffi（见 `requirements.txt`）。

## 命令（Commands）

高频入口如下。**需要某脚本的完整参数/全部子命令时，读 `.claude/docs/commands.md`。**

```bash
bash show_chart.sh                  # 交互式图表（K线+RSI/Breadth/VIX 副图，启 HTTP 服务）
python run_experiments.py          # 4 阶段执行层参数优化（网格搜索）
python scripts/compare_signals.py  # 信号策略比较（标准化执行，纯比较择时质量）
python -m ml.run_mvp               # ML Meta-Labeling 一键运行（标注→特征→训练→评估）
python scripts/fetch_daily_data.py # 拉取日线数据（联网；其余 fetch_* 同理）
```

无测试框架：`tests/test_strategies.py` 为空文件，不存在可运行的测试套件。

## 目录结构（Directory Map）

```
src/backtest_engine.py     引擎路径主系统：BacktestEngine + Context（每日上下文）
src/strategies/composable.py  ComposableStrategy：组装 4 模块成完整策略
src/modules/               4 模块：tiers / entry / position / take_profit
src/indicators/__init__.py  全部技术指标纯函数（单文件包，无其他子文件）
src/rsi_signals.py         RSI v2 三事件信号系统
src/breadth_divergence.py  Market Breadth 背离检测
src/backtest.py main.py    旧版路径（YAML 驱动，仅 baseline，勿用于研究）
experiments/configs.py     实验参数 + MARKET_ENVS + BEST_* 最优组合常量
ml/                        ML Meta-Labeling（versions.py 管理版本，run_mvp 入口）
scripts/                   数据拉取 + 可视化 + 比较脚本（含 MMA 子系统）
data/*.csv                 行情/指标数据（SPY/SMH/SOXL 日线周线、breadth、vix、safe_haven）
.claude/docs/              本宪法拆出的实施细则（按需读）
docs/tasks/                按日期前缀的历史任务记录与实验结论
```

## 关键规则（Critical Rules）

- **注释、日志、文档必须用中文；策略/模块名与代码标识符必须用英文。** 项目既定约定，保持一致性。
- **策略研究必须走引擎路径**（`run_experiments.py` / `scripts/show_chart.py` → `src/backtest_engine.py`）；**禁止用旧版 `main.py` / `src/backtest.py` 做研究**——后者仅支持 baseline，已废弃。
- **比较 Entry 信号时必须用标准化执行层**（`FixedTiers(drops=())` + `FixedPyramid(market_shares=1)` + `NoTakeProfit()`）。否则执行层差异会污染信号质量比较。**改 entry/做信号比较前，读 `.claude/docs/strategy-system.md`。**
- **最优组合以 `experiments/configs.py` 的 `BEST_*` 常量为准，禁止在别处复刻其参数值。** 复刻会随 configs.py 修改而漂移。
- **实验结论的精确数值（成本优势%、Oracle 极值等）禁止内联到本文件**——属易腐数据，需要时查 `docs/tasks/` 对应目录或重跑。
- **`fetch_*` 数据脚本需联网**，会覆盖 `data/*.csv`，运行前确认网络与意图。
- **实验配置是 Python 代码不是 YAML**（`experiments/configs.py`），改参数改这里，不要找 YAML。

## 已知事实（Known Facts）

- **市场环境有且仅 6 个**：`bear` / `bull` / `bear-bull` / `bull-bear` / `all` / `ml-test`（定义在 `experiments/configs.py` 的 `MARKET_ENVS`）。
- **每日决策固定顺序**：档口 → 入场 → 仓位 → 止盈。
- **引擎运行时自动计算 RSI v2 信号并存入 metrics**，无需手动注入。
- **ML 当前激活版本 `v3`**（`ml/versions.py` 的 `ACTIVE_VERSION`），v3 实际标注方法为 `sl_proximity`；`run_mvp --method` 还支持 `relative_low`、`sl_multi` 等（比 versions.py 用到的多）。
- **入场组合器类名为 `AndEntry` / `OrEntry`**（非 `CombinedAndEntry` / `CombinedOrEntry`，后者不存在）。
- **方向性结论**：情绪信号中 VIX>30 入场综合最优、SafeHaven 垫底；最终锁定 `NoTakeProfit`。**需要精确数值/依据时，读 `.claude/docs/strategy-system.md` 及 `docs/tasks/` 对应目录。**
- **Breadth 数据有幸存者偏差**（用当前 S&P 500 成分股回算历史），2020 后影响很小。
- **改指标/读数据/找核心模块职责时，读 `.claude/docs/indicators-data-modules.md`**（指标原理、数据文件、核心模块详解）。
