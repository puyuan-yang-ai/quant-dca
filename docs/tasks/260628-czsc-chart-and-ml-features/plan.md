# 实施方案

## 一、图表可视化（已完成）

### 数据与规模

SPY 全周期 `1993-01-29 ~ 2026-06-26`，8409 根日线：

- 结构：分型（笔端点）677、笔 676、中枢 89。
- 买卖点：实时触发 1057（后确认 532 / 后被重绘 525）；确认实战 532（买 312 / 卖 220）；**确认延迟中位 3 个交易日**。

### 三视图语义（共用同一套分型/笔/中枢，仅买卖点不同）

| 视图 | 含义 | 标记位置 | 可否进 ML |
|---|---|---|---|
| 实时回放（默认） | 实时真正触发过的全部信号 | 首次出现日 | ✅ 因果可用 |
| 确认实战 | 被 czsc `finished_bis` 确认、不再重绘 | 确认日 | ✅ 因果可用（偏慢） |
| 事后复盘 | 同确认集合 | 拐点极值 | ❌ 含前视偏差 |

- 实时回放中：幸存信号 = 彩色箭头；被重绘信号 = **灰色带方向箭头 + ✗**（↑买 / ↓卖），悬停显示原类型。
- **重绘机制**：最近一笔在价格创出新极值时被丢弃重画 → 挂在其上的买卖点消失。

### 改动文件

- **新增 `src/chan/czsc_chart_adapter.py`**：构建叠加层数据。
  - 一次性全量 CZSC + 均线缓存预填（SMA21/34）+ 单次增量回放 → 全周期约 1.3s（避免逐根重算均线的 O(n²)）。
  - `confirmed` = 对最终结构按 `di` 扫描得到；确认日 = 该笔首次进入 `finished_bis` 的日期；`realtime` = 逐根 `di=1` 首次触发；`survived = realtime ∈ confirmed`。
  - 中枢箱体：取 ≥3 笔且 `zg ≥ zd`。
  - 输出：`fractals / bi / zs / marker_sets{hindsight,realtime,confirmed} / detail_map / counts / confirm_lag_median`。
- **修改 `src/interactive_chart.py`**：
  - 渲染笔折线、中枢（Baseline 半透明填充 + 上下沿横线）、分型/买卖点标记。
  - 顶部三视图切换 + 方向/类型过滤（全部 / 只看买点 / 只看卖点 / 一买 / 二买 / 三买）+ 悬停明细浮窗。
  - czsc 模式隐藏 EMA 与副图、顶部改显缠论统计；lightweight-charts 改为本地引用。
  - 顺带修复 `{{}}` f-string 隐患（`swing_lows / breadth_consec` 为空时崩溃）。
- **修改 `scripts/show_chart.py`**：新增 `--czsc` 开关（全周期 SPY、跳过回测、隐藏非缠论标记）。
- **修改 `src/data_loader.py`**：读取 `成交量` 列（一买/一卖量能背驰所需）。
- **新增 `src/assets/lightweight-charts.standalone.production.js`**：绘图库本地化，运行时复制到 `output/`。

### 运行

```bash
python scripts/show_chart.py --czsc
```

浏览器打开终端提示的地址；默认进入"实时回放"视图。

---

## 二、czsc 作为 ML 特征（待实施，A 方案）

### 1. 指标模块 `src/indicators/czsc_bsp.py`（新增）

- 输入 SPY 日线 df，输出每个交易日的 czsc 特征列。
- **纯实时因果口径，含全部被重绘信号、不事后剔除**。
- **因果实现**：单次增量回放，对每个交易日**快照当时的笔/中枢/买卖点状态**来算特征（严禁使用最终结构，否则偷看未来）。
- 5 列特征（连续型为主，保证每个候选行都携带信息）：

  | 特征列 | 含义 | 无信号时取值 |
  |---|---|---|
  | `czsc_days_since_rt_buy` | 距上一个实时买点的交易日数 | 大数（如 999） |
  | `czsc_last_buy_type` | 上个实时买点类别（1/2/3） | 0 |
  | `czsc_beichi_strength` | 最近下跌笔背驰强度（价差/量能/长度相对前段衰减比） | 中性值 |
  | `czsc_in_zs` | 当日是否在"截至当日已成立"的中枢内 | 0 |
  | `czsc_zs_pos` | 当日价格在该中枢内相对位置 `(close−zd)/(zg−zd)` | 中性值 |

### 2. 特征版本 `ml/features_v4.py`（新增）

- `= features_v3` 全部特征 + 上述 czsc 5 列（**只加不减**）。

### 3. 版本注册 `ml/versions.py`

- 新增 `v4`：沿用 `v3_n2` 全部配置（labeling `sl_proximity, sl_n=7, k=3`；signal `n_days=2`；相同模型超参），仅 `features_module = ml.features_v4`。
- **不改 `ACTIVE_VERSION`**（不动现有活模型）。

### 4. 评估（沿用项目现有全套量具，v3 / v3_n2 / v4 三版并排）

**统计层**（`ml/walk_forward.py` + `ml/eval_walkforward.py`）：扩展窗 WF（4 折）+ Purge/Embargo（28 天）+ 样本唯一性权重 → 整体 AUC-ROC + 95% bootstrap CI、AUC-PR、单折 AUC；输出 `oos_proba_{version}.csv`。

**经济层**（`ml/eval_economics.py`）：OOS 概率 → Entry 过滤器 → 标准化执行层接 `backtest_engine`。**每版用自身候选全集做 A**（v3→全 NDay5；v3_n2/v4→全 NDay2），各比各自的 B（模型过滤）。读数：扣成本 Sharpe / 回撤 / 总收益 / 买入数、条件 20 日收益（打 vs 不打）、收益差 t 检验、阈值扫描曲线。

**三条验收判据**：① 统计可信（AUC CI 下沿 > 0.5、各折稳定）；② 阈值稳健（B 在一大片阈值优于 A）；③ 经济价值（扣成本 Sharpe / 收益差显著）。

**三版定位**：

| 版本 | 特征 | NDay | 角色 |
|---|---|---|---|
| v3 | features_v3 | 5 | 历史基准 |
| v3_n2 | features_v3 | 2 | 当前活模型 |
| v4 | features_v4(=v3+czsc) | 2 | 新 |

- **干净隔离 czsc 贡献 = `v3_n2 ↔ v4`**（候选完全相同，唯一变量 = czsc 5 列）；`v3 ↔ v3_n2` 变的是候选门槛。

**实现缺口与做法**：现有 `eval_walkforward.py` 写死了 active 配置 + NDay5（未按版本取 `features_module` / `signal.n_days`）。做法：

- 加一条**按版本参数化**的评估路径（从各版本 config 取 `features_module` + `labeling` + `signal.n_days`，与 `train_export._build_dataset` 同款），
- 新增**三版对比驱动脚本**（如 `ml/research/compare_v3_v3n2_v4.py`），并排输出统计 + 经济 + 判据。
- **不改 `ACTIVE_VERSION`、不动现有活模型。**

---

## 关键决策记录

- **用实时口径而非确认口径做特征**：确认延迟中位 3 个交易日偏慢，实时更及时且同样因果有效。
- **重绘信号全量入模型**：触发当时不可区分其去留，事后剔除即 look-ahead；它们是模型学习的"难负样本"。
- **特征用连续型（距离/强度/位置）而非稀疏 0/1**：避免大多数行取值恒为 0、信息量过低。
- **两层过滤定位**：第一层 NDay（n=2）圈定抄底候选；第二层 ML 打分过滤。czsc 5 列是给第二层**增加情报**，并非新增第三层。
- **A 方案天花板**：czsc 特征仅在 NDay 候选行被读取，提升取决于"缠论视角"与"NDay 抄底日"的互补性；若提升有限，再转 **B 方案**（以 czsc 买点为候选事件）。
- **评估对齐既有方法论**：统计 + 经济 + 三判据全套、三版并排，不单看 AUC。
- **预判（管理预期）**：瓶颈在标签（`sl_proximity` 标"底部邻近度"而非"收益幅度"）。v4 可能 AUC 略升但经济判据仍不过——这本身是有价值的结论（量化 czsc 特征单独贡献）。
- **各版 OOS 区间可能不同**（候选数不同所致）：采取"各版自比自 A/B"，跨版主要对比判据结论与 AUC 趋势，可接受。
