# CLAUDE.md

供未来 AI 智能体使用的操作宪法 + 导航索引。本文件只留宪法条款与指针；详细细则拆在 `.claude/docs/`，按需阅读（指针处标注了"何时读"）。

## 目的（Purpose）

SPY/SMH 多层次定投（DCA）回测系统 + ML 底部识别信号研究。在不同市场环境下对 SPY 跑多种 DCA 策略回测，SMH 作基准与利润分流标的；ML 方向用 XGBoost 对规则初级信号做 Meta-Labeling 筛选（近期扩展缠论/MACD/TD 技术指标特征）。

技术栈：Python（venv 在 `.venv/`）。核心依赖 pandas、numpy、scipy、scikit-learn、xgboost、yfinance、matplotlib、lightweight-charts、pyyaml、curl_cffi（见 `requirements.txt`）。

## 命令（Commands）

高频入口如下。**需要某脚本的完整参数/全部子命令时，读 `.claude/docs/commands.md`。**

```bash
bash show_chart.sh                        # 交互式图表（K线+RSI/Breadth/VIX 副图，启 HTTP 服务）
python run_experiments.py                # 4 阶段执行层参数优化（网格搜索）
python scripts/compare_signals.py        # 信号策略比较（标准化执行，纯比较择时质量）
python -m ml.run_mvp                     # ML 研究入口（标注→特征→训练→评估→画图，不存模型）
python -m ml.train_export --holdout 0.2  # 全量训练并导出生产模型到 models/（含元数据 JSON）
python -m ml.predict --json out.json     # 每日推理：加载激活版本模型预测最新交易日（--version 指定版本）
python scripts/fetch_daily_data.py       # 拉取日线数据（联网；fetch_intraday_data.py 拉盘中）
```

无测试框架：`tests/test_strategies.py` 为空文件，不存在可运行的测试套件。

## 目录结构（Directory Map）

```
src/backtest_engine.py       引擎路径主系统：BacktestEngine + Context（每日上下文）
src/strategies/composable.py ComposableStrategy：组装 4 模块成完整策略
src/modules/                 4 模块：tiers / entry / position / take_profit
src/indicators/__init__.py   经典技术指标纯函数（单文件包）
src/indicators/{macd,td_sequential,czsc_bsp}.py  MACD / TD九转 / 缠论买卖点特征
src/chan/                    缠论子系统：czsc_vendor（vendored核心,勿改）+ czsc_chart_adapter
src/rsi_signals.py           RSI v2 三事件信号系统
src/breadth_divergence.py    Market Breadth 背离检测
src/backtest.py main.py      旧版路径（YAML 驱动，仅 baseline，勿用于研究）
experiments/configs.py       实验参数 + MARKET_ENVS + BEST_* 最优组合常量
ml/                          ML 体系：versions.py(版本注册表) / labeling / features_v1~v5 / train_export / predict
ml/research/                 一次性研究脚本（非生产路径）
models/                      导出的生产模型 .ubj + .json 元数据（进 git）
scripts/                     数据拉取 + 可视化 + 比较 + 扫描脚本（含 MMA 子系统）
data/*.csv  data/intraday/   日/周线行情指标 + 盘中多周期 K 线
.claude/rules/ docs/ commands/  拆出的铁律 / 按需细则 / MMA 斜杠命令
docs/tasks/  docs/indicators/    按日期的任务记录与结论 / 指标口径基准(pine)
```

## 关键规则（Critical Rules）

- **注释、日志、文档必须用中文；策略/模块名与代码标识符必须用英文。** 项目既定约定。
- **策略研究必须走引擎路径**（`run_experiments.py` / `scripts/show_chart.py` → `src/backtest_engine.py`）；**禁止用旧版 `main.py` / `src/backtest.py` 做研究**——后者仅支持 baseline，已废弃。
- **比较 Entry 信号时必须用标准化执行层**（`FixedTiers(drops=())` + `FixedPyramid(market_shares=1)` + `NoTakeProfit()`）。否则执行层差异污染信号质量比较。**改 entry/做信号比较前，读 `.claude/docs/strategy-system.md`。**
- **ML 切换版本只改 `ml/versions.py` 的 `ACTIVE_VERSION`；禁止在别处硬编码版本参数**（labeling/signal/features/model）。**改 ML 版本、特征、模型前，读 `.claude/docs/ml-and-chan.md`。**
- **改任何特征模块后必须重新 `python -m ml.train_export`**——`predict.py` 校验特征顺序与模型元数据 `feature_cols` 完全一致，不一致直接报错。
- **缠论特征只能用「截至当日」的逐根增量状态，禁止使用全量最终结构或事后剔除被重绘信号**——否则是 look-ahead 泄漏。细则见 `.claude/docs/ml-and-chan.md`。
- **最优组合以 `experiments/configs.py` 的 `BEST_*` 常量为准，禁止在别处复刻其参数值。** 复刻会随 configs.py 修改而漂移。
- **实验结论的精确数值（成本优势%、AUC、Oracle 极值等）禁止内联到本文件与细则**——属易腐数据，查 `docs/tasks/` 对应目录或重跑。
- **`fetch_*` 数据脚本需联网**，会覆盖 `data/*.csv`，运行前确认网络与意图。
- **实验配置是 Python 代码不是 YAML**（`experiments/configs.py`），改参数改这里。
- **`src/chan/czsc_vendor/` 是 vendored 外部依赖快照，勿改。**

## 已知事实（Known Facts）

- **市场环境有且仅 6 个**：`bear` / `bull` / `bear-bull` / `bull-bear` / `all` / `ml-test`（`experiments/configs.py` 的 `MARKET_ENVS`）。
- **每日决策固定顺序**：档口 → 入场 → 仓位 → 止盈。引擎运行时自动计算 RSI v2 信号存入 metrics，无需手动注入。
- **ML 当前激活版本 `v3_n2`**（NDay 门槛=2）；生产模型 `models/spy_nday2_v3_n2.*`（另有路径 A 底部识别模型 `spy_trough_v1`）。旧 `v3` / `spy_nday5_v3` 已弃用删除。版本谱系（v1~v5_pa 及消融臂）见 `.claude/docs/ml-and-chan.md`。
- **训练/推理已分离**：`train_export` 导出模型+元数据；`predict.py` 只推理不训练，可独立部署 Mac mini。模型文件进 git。
- **每天都出概率但区分信号日**：`predict.py` 用 `is_signal_day` 标注今天是否满足初级信号；**非信号日概率属未训练分布，仅供参考不可作交易依据**。
- **信息泄漏结论**：v3 系特征均为当天/历史窗口（rolling 右对齐、shift 正向），无未来泄漏；泄漏仅在 label/forward_return（训练用）。缠论特征另有专门的因果口径铁律（见上）。
- **MACD/TD 指标有 Pine/文献口径基准**，改动须对照 `docs/indicators/` 下基准人工校验（MACD hist 单倍不×2；TD Countdown 各家有出入）。详见 `.claude/docs/ml-and-chan.md`。
- **入场组合器类名为 `AndEntry` / `OrEntry`**（非 `CombinedAndEntry` / `CombinedOrEntry`）。
- **方向性结论**：情绪信号中 VIX>30 入场综合最优、SafeHaven 垫底；最终锁定 `NoTakeProfit`。精确数值读 `.claude/docs/strategy-system.md` 及 `docs/tasks/`。
- **Breadth 数据有幸存者偏差**（用当前 S&P 500 成分股回算历史），2020 后影响很小。
- **改指标/读数据/找核心模块职责时，读 `.claude/docs/indicators-data-modules.md`**（经典指标原理、数据文件、核心模块详解）；ML/缠论/MACD/TD 读 `.claude/docs/ml-and-chan.md`。
- **MMA 子系统**有 4 个斜杠命令（`.claude/commands/mma-{1-analyze,2-strategy,3-verify,4-order}.md`），周/月报产物在 `docs/tasks/mma-report/`。
