# 路径 A：对称近底候选 + czsc 特征消融

> 承接前序结论：杠杆优先级 **候选 universe（第一层）≈ 标签 ＞＞ 特征**。
> czsc 特征在旧 universe(v3_n2) 上无增益；改第一层候选(NDay2→近底)后 AUC 0.638→0.698（CI 不重叠），
> 证明第一层是大杠杆。本阶段：把第一层调"对称近底"，并在新 universe 上对 czsc 做消融。

## 一、需求与目标

**需求**
1. 第一层候选从 `NDay2`（连续 2 天跌破 EMA20）改为**对称"近底"规则**，使 SL7 两侧的 GT **大体对称**。
2. 在新 universe 上做 **czsc 特征消融**，客观判断其边际价值。

**目标**
- 候选规则左右大体对称（右/左 ≈ 1，不求严格相等），并校验。
- 4 臂消融用 **Precision / Recall** 为主回答"换好 universe 后 czsc 到底有没有用"。
- 全程不动现有活模型（`ACTIVE_VERSION` 仍 `v3_n2`），仅作实验。

## 二、对齐后的方案

### 1. 第一层候选规则（参数已定）
- 规则：`close ≤ 近 N 日最低价 ×(1+pct)`（滚动低点邻近度，**因果**，仅用过去）。
- **参数：N=30, pct=0.05** → 实测 右/左 ≈ **1.03**、候选 4305、正例率 0.303（健康，非退化）。
- 实现：`labeling.generate_nearbottom_signals` + 版本 `v5_pa` 的 `signal={type:'nearbottom', n:30, pct:0.05}`。
- 改完**校验**：① 重测 SL7 两侧候选左右比；② 重验 walk-forward AUC。

### 2. 标签（不变）
- `sl_proximity`，`sl_n=7`，**`k=2`（交易 bar 口径）**：候选日距最近 SL7 低点 ≤2 个交易 bar 则 label=1。

### 3. 消融 4 臂（全部在同一 v5_pa universe + 同标签 + 同 walk-forward）
| 臂 | 特征 | 列数 | 隔离的问题 |
|---|---|---|---|
| A0 | features_v3 基线 | 21 | 新 universe 的基准 |
| A1 | base + czsc 单布尔 `czsc_buy_today` | 22 | 加 1 个"出现买点"标志有无用 |
| A2 | base + czsc 5 列 | 26 | 加全套结构特征有无用 |
| A3 | **v5_pa 上重选的正交精简 base** + czsc 5 列 | — | 排除"纯特征变多"干扰 |

- **唯一变量** = czsc（及 A3 的正交精简），其余全部固定。
- A3 的"正交精简"：在 v5_pa 数据集上用 相关聚类(|Spearman|>0.8 去冗余) + 单特征区分力(<0.52 去噪声) 重新筛选 base，再叠加 czsc 5 列。

### 4. 评估口径
- **主：Precision / Recall**（预测 label=1=真底）。在**折内阈值 `fold_threshold`** 上算，并给出 **0.4 / 0.5 / 0.6** 三阈值的 P/R 对照。
- **辅：AUC-ROC**。
- **不看收益率**（经济 A/B 需另写"近底"Entry，本阶段不做）。

### 5. 约束与决策记录
- **不动 `ACTIVE_VERSION`**：v5_pa 及消融版本仅注册为实验配置。
- **权衡（已知）**：要对称就得放松 pct，universe 变宽、正例率下降（0.356→0.303），可能影响 AUC——改完即重验，若明显下降再议"对称 vs 质量"。
- **因果限制**：SL7 需未来确认，第一层候选**不可能完美对称**，只能大体平衡；唯有"标签"可精确 ±2 对称。
- **最终天花板**：标签是"底部邻近度"而非"收益"，即便底部探测做准，"邻近≠收益"的经济天花板依旧存在（属后续"换标签"议题，不在本阶段）。

## 三、涉及的代码改动
- `ml/labeling.py`：新增 `generate_nearbottom_signals`；`run()` 支持 `signal_cfg`（已落地，参数待从 n20/pct0.03 改为 **n30/pct0.05**）。
- `ml/train_export.py`、`ml/eval_walkforward.py`：透传 `signal_cfg`（已落地）。
- `ml/versions.py`：`v5_pa`（待改参数）；新增消融版本 `v5_pa_c1`(features_v4b)、`v5_pa_c5`(features_v4)、`v5_pa_orth`(A3) —— 均 `signal=近底n30p05`、`labeling=sl_proximity k2`、不改 ACTIVE。
- 评估：复用 `ml/eval_walkforward`，补 Precision/Recall 统计与多阈值对照的对比脚本。
