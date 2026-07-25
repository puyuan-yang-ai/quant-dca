# ML 多版本体系 + 缠论/MACD/TD 指标细则

本文件是宪法 `## 已知事实` 中 ML 与技术指标条款的实施细则。改 ML 版本、特征、缠论/MACD/TD 指标前读本文件。

## ML 版本注册表（`ml/versions.py`）

**唯一真相源是 `ml/versions.py` 的 `VERSIONS` 字典 + `ACTIVE_VERSION`；切版本只改 `ACTIVE_VERSION`，禁止在别处硬编码版本参数。** 每个版本 = 标注方式(labeling) + 初级信号(signal) + 特征模块(features_module) + 模型超参(model)。

当前版本谱系（截至 2026-06-29；精确指标以 `versions.py` 与 `docs/tasks/` 为准，勿内联到宪法）：

| 版本 | 特征模块 | 初级信号 | 说明 |
|------|---------|---------|------|
| v1 / v2 / v3 | features_v1/v2/v3 | NDay N=5 (v3) | 早期基线；v3=窗口化+confluence |
| **v3_n2**（★激活）| features_v3 | **NDay N=2** | v3 配置 + NDay 门槛 5→2（抓底诊断结论） |
| v4 / v4b | features_v4 / v4b | NDay N=2 | v3_n2 + czsc 缠论特征（v4=5列 / v4b=单布尔），只加不减 |
| v5_pa / _c1 / _c5 / _orth | v3 / v4b / v4 / v5_orth | **nearbottom** n30 p05 | 路径 A：初级信号从 NDay 改为对称"近底"（收盘距近 30 日低 ≤5%）+ czsc 消融臂 |

- **初级信号有两族**：`generate_nday_signals`（连续 N 日收盘在 EMA20 下方）与 `generate_nearbottom_signals`（对称近底）。定义在 `ml/labeling.py`。
- **标注方法**：激活谱系统一用 `sl_proximity`（SL7 ±k 交易 bar，k=2）。`ml/labeling.py` 还有 `triple_barrier`/`relative_low`/`sl_multi` 等（研究用）。

## 生产模型（`models/`，进 git）

- 训练/推理分离：`ml/train_export.py` 全量训练并导出 `models/<name>.ubj` + 同名 `.json` 元数据（含 `feature_cols` 顺序契约、训练期、feature_importance、holdout 指标）；`ml/predict.py` 只加载推理、不训练，可独立部署到 Mac mini。
- 现有模型：`spy_nday2_v3_n2`（激活生产模型）、`spy_trough_v1`（v5_pa 路径 A 底部识别）。**旧 `spy_nday5_v3` 已删除。**
- **推理特征契约**：`predict.py` 校验 `build_features` 输出顺序与元数据 `feature_cols` 完全一致，不一致直接报错——改任何特征模块后必须重新 `train_export`。
- `predict.py --version <ver>` 可指定版本；不传用 `ACTIVE_VERSION`。每天都出概率但用 `is_signal_day` 区分：非信号日概率属未训练分布，仅供参考不可作交易依据。

## 缠论子系统（`src/chan/`）

- `src/chan/czsc_vendor/`：vendored 的 czsc 缠论核心（analyze/objects/signals_cxt 等），**是外部依赖快照，勿改**。
- `src/chan/czsc_chart_adapter.py`：把 K 线喂入 czsc，提取分型/笔/中枢 + 一二三类买卖点，并区分三种视图：`hindsight`（事后复盘，有前视偏差，仅供人看）/ `realtime`（实时回放）/ 逐日增量。
- `src/indicators/czsc_bsp.py`：`compute_czsc_bsp(spy_df)` 为每个交易日产出缠论衍生特征列（v4/v4b 用）。

**缠论特征铁律（防 look-ahead）**：ML 特征只能用「截至当日」的逐根增量缠论状态，**绝对禁止**使用全量最终结构或事后剔除被重绘的信号——重绘与否是未来信息。买卖点取实时触发（含此后会被重绘的）。违反即数据泄漏。详见 `docs/tasks/260628-czsc-chart-and-ml-features/`。

## MACD / TD Sequential 指标

- `src/indicators/macd.py`：口径对齐 TradingView Pine（DIF=EMA12-EMA26，DEA=EMA(DIF,9)，hist=DIF-DEA **单倍不×2**；EMA 首值用第一个数据点初始化）。基准 `docs/indicators/macd/macd.pine`。
- `src/indicators/td_sequential.py`：神奇九转，蓝本 Perl《DeMark Indicators》2008，以买入(低)方向为主。**Countdown 的 recycle/取消/TDST 各家实现有出入，改动务必对照 TradingView 人工校验**。口径与校验清单见 `docs/indicators/TD-sequential/note.md`。

## 盘中数据与研究脚本

- `data/intraday/`：ESF 多周期 K 线（5m~120m）+ box_events/samples json，由 `scripts/fetch_intraday_data.py` 抓取（联网）。
- `ml/research/`：一次性研究脚本（阈值扫描、消融、口径诊断、绘图），**非生产路径**，结论沉淀在 `docs/tasks/` 对应目录。
