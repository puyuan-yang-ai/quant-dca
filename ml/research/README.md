# ml/research — 抓底模型研究脚本

可复用的只读研究脚本。**不修改生产代码**，通过 monkey-patch 复用 `train_export` / `eval_walkforward` 的逻辑做参数实验。

## 脚本

| 脚本 | 作用 | 运行 |
|------|------|------|
| ⭐ `eval_by_label.py` | **【权威】**用 label 列（训练口径=评估口径）评估抓底 P/R。**门槛决策以此为准** | `python -m ml.research.eval_by_label` |
| `diag_threshold_quality.py` | 秒级静态诊断：各 NDay 门槛的信号数、信号质量、池内可分性 | `python -m ml.research.diag_threshold_quality` |
| `plot_threshold_event.py` | 画 阈值 vs 信号簇 曲线（连续加仓洞察，口径无关部分有效） | `python -m ml.research.plot_threshold_event --n 2` |

**⚠️ 以下脚本用了"几何比对"口径（与训练 label 不一致），仅作弯路记录，不可作门槛决策依据**（详见 `docs/tasks/260626-ml-bottom-catch-diagnosis/diagnosis.md` §11）：
`sweep_ndays_precision_recall.py`、`plot_precision_recall.py`、`sweep_threshold_event.py`、`grid_search_n_threshold.py`、`plot_n1_vs_n2.py`

## 核心方法论结论（2026-06-26 研究）

1. **评判抓底模型不能用收益率**。SPY 长牛，买越多收益越高，任何"减少买入"的过滤器都会系统性拉低收益率——这是对"抓底"目标不公平的尺子。正确指标是**抓底 Precision（命中率）+ Recall（覆盖率）**，真值 GT = `sl_proximity` 标签（swing low ± k 天）。

2. **ML 确实在抓底**：基线（NDay 信号本身）抓底命中率 ~38%，ML 高概率放行后提升到 46~58%（+8~21pp）。

3. **门槛 N 的最终结论（label 口径，权威）：N=2 最优**。候选池正样本率最高（41.2%），@阈值0.35 时 Precision 46.5% / Recall 80% 双优。⚠️ 早期用"几何比对"口径曾误推 N=1，已更正——**评估口径必须 = 训练 label 口径**（详见 diagnosis.md §11）。

4. **XGBoost 无需手动特征分箱**：树模型本身在每个节点做最优切分（自适应分箱），手动分箱反而丢失分辨率。分箱主要对线性模型有用。

5. **阈值要用"事件级"指标定，不是日级 F2**：目的是抓独立的局部低点，计量单位应是"抓到几个不同的真底"而非"几个信号日"。推荐阈值区间 [0.30, 0.45]。**反直觉：阈值过低反而造成最严重的连续加仓**（底部区域连续多天报底黏成大簇），适度抬高阈值让信号回归稀疏。详见 `docs/tasks/260626-ml-bottom-catch-diagnosis/diagnosis.md` §8。
