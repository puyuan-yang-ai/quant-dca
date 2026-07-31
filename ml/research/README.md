# ml/research — 抓底模型研究脚本

可复用的只读研究脚本。**不修改生产代码**，通过 monkey-patch 复用 `train_export` / `eval_walkforward` 的逻辑做参数实验。

## 脚本

| 脚本 | 作用 | 运行 |
|------|------|------|
**全部脚本均已统一为 label 列口径（训练口径=评估口径），结论一致指向 N=2 @0.35。**

| 脚本 | 作用 | 运行 |
|------|------|------|
| ⭐ `eval_by_label.py` | **【权威】**用 label 列评估各 N 抓底 P/R，门槛决策主依据 | `python -m ml.research.eval_by_label` |
| `eval_spatial_gt.py` | 空间 GT 参数遍历、价格权重消融、等预算离底溢价与 v3_n2 公平对比 | `python -m ml.research.eval_spatial_gt` |
| `eval_spatial_e2e.py` | 开发段校准、下一开盘执行的空间 GT 因果端到端评估 | `python -m ml.research.eval_spatial_e2e` |
| `diag_threshold_quality.py` | 秒级静态诊断：各 NDay 门槛信号数/质量/池内可分性 | `python -m ml.research.diag_threshold_quality` |
| `sweep_ndays_precision_recall.py` | NDay 门槛遍历 P/R（label 口径） | `python -m ml.research.sweep_ndays_precision_recall` |
| `plot_precision_recall.py` | 各 N 的 P-R 权衡曲线 + F1/F2（label 口径） | `python -m ml.research.plot_precision_recall` |
| `sweep_threshold_event.py` | 阈值扫描 P/R（label 口径）+ 信号簇（连续加仓洞察） | `python -m ml.research.sweep_threshold_event --n 2` |
| `plot_threshold_event.py` | 阈值 vs 信号簇曲线 | `python -m ml.research.plot_threshold_event --n 2` |
| `grid_search_n_threshold.py` | N×阈值 网格搜索（label 口径 F1 选优） | `python -m ml.research.grid_search_n_threshold` |
| `plot_n1_vs_n2.py` | N=1 vs N=2 曲线对比（label 口径） | `python -m ml.research.plot_n1_vs_n2` |

> 历史教训：早期 `grid_search_n_threshold.py` / `plot_n1_vs_n2.py` 曾用"几何比对"（信号日 vs swing low 中心 ±k）口径，与训练 label 不一致，夸大低 N 的 Recall 误推"N=1 最优"。**已全部改回 label 口径**，结论修正为 N=2。详见 diagnosis.md §11。

## 核心方法论结论（2026-06-26 研究）

1. **评判抓底模型不能用收益率**。SPY 长牛，买越多收益越高，任何"减少买入"的过滤器都会系统性拉低收益率——这是对"抓底"目标不公平的尺子。正确指标是**抓底 Precision（命中率）+ Recall（覆盖率）**，真值 GT = `sl_proximity` 标签（swing low ± k 天）。

2. **ML 确实在抓底**：基线（NDay 信号本身）抓底命中率 ~38%，ML 高概率放行后提升到 46~58%（+8~21pp）。

3. **门槛 N 的最终结论（label 口径，权威）：N=2 最优**。候选池正样本率最高（41.2%），@阈值0.35 时 Precision 46.5% / Recall 80% 双优。⚠️ 早期用"几何比对"口径曾误推 N=1，已更正——**评估口径必须 = 训练 label 口径**（详见 diagnosis.md §11）。

4. **XGBoost 无需手动特征分箱**：树模型本身在每个节点做最优切分（自适应分箱），手动分箱反而丢失分辨率。分箱主要对线性模型有用。

5. **阈值要用"事件级"指标定，不是日级 F2**：目的是抓独立的局部低点，计量单位应是"抓到几个不同的真底"而非"几个信号日"。推荐阈值区间 [0.30, 0.45]。**反直觉：阈值过低反而造成最严重的连续加仓**（底部区域连续多天报底黏成大簇），适度抬高阈值让信号回归稀疏。详见 `docs/tasks/260626-ml-bottom-catch-diagnosis/diagnosis.md` §8。
