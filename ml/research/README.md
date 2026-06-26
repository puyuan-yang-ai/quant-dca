# ml/research — 抓底模型研究脚本

可复用的只读研究脚本。**不修改生产代码**，通过 monkey-patch 复用 `train_export` / `eval_walkforward` 的逻辑做参数实验。

## 脚本

| 脚本 | 作用 | 运行 |
|------|------|------|
| `diag_threshold_quality.py` | 秒级静态诊断：各 NDay 门槛的信号数、信号质量、池内可分性 | `python -m ml.research.diag_threshold_quality` |
| `sweep_ndays_precision_recall.py` | NDay 门槛遍历，以**抓底 Precision/Recall** 为指标（非收益率） | `python -m ml.research.sweep_ndays_precision_recall` |

## 核心方法论结论（2026-06-26 研究）

1. **评判抓底模型不能用收益率**。SPY 长牛，买越多收益越高，任何"减少买入"的过滤器都会系统性拉低收益率——这是对"抓底"目标不公平的尺子。正确指标是**抓底 Precision（命中率）+ Recall（覆盖率）**，真值 GT = `sl_proximity` 标签（swing low ± k 天）。

2. **ML 确实在抓底**：基线（NDay 信号本身）抓底命中率 ~38%，ML 高概率放行后提升到 46~58%（+8~21pp）。

3. **门槛 N 的 Precision/Recall 权衡**：N 越大单点 Precision 越高，但候选池"真底总数"越少（N=1 有 653 个真底，N=5 只剩 298 个，门槛在源头过滤掉一半机会），Recall 上限被压低。**最优 N 取决于对 Precision/Recall 的偏好，不是越大越好。**

4. **XGBoost 无需手动特征分箱**：树模型本身在每个节点做最优切分（自适应分箱），手动分箱反而丢失分辨率。分箱主要对线性模型有用。
