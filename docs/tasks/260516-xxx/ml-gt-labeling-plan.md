# ML 训练 GT 标签方案设计

## 背景

为后续接入 ML(XGBoost / Logistic Regression)做 SPY 择时,需要先解决一个关键问题:**训练样本的 Ground Truth(GT)标签从哪里来**。

手动标注不可行:
- 主观(不同人对"买点"判断不同)
- 模糊(一个大底区域应该标 1 个点还是多个点?没有客观答案)
- 不可扩展(几千个样本手标会崩溃)

因此采用**公式化标签**(Algorithmic Labeling),用确定性算法从历史价格数据自动生成标签。

## 概念澄清:标签方法 vs 训练架构

容易混淆的两个维度,实际是**正交的、可以组合的**:

| 维度 | 选项 | 回答什么问题 |
|------|------|-----------|
| **标签方法** | Fixed Horizon / Triple Barrier | 某一天的 GT 是 0 还是 1? |
| **训练架构** | 全数据训练 / Meta-Labeling | ML 应该在哪些天上训练? |

López de Prado 原版方案 = **Triple Barrier(标签)+ Meta-Labeling(架构)**。

## 标签方法详解

### Fixed Horizon(简单版)

**规则**:第 i 天向后看 N 天,如果期间最高价相对当前收盘价的涨幅 > 阈值,标 1;否则标 0。

```python
def label_fixed_horizon(data, i, horizon=10, threshold=0.03):
    future_high = max(d['high'] for d in data[i+1 : i+horizon+1])
    return 1 if (future_high - data[i]['close']) / data[i]['close'] > threshold else 0
```

- 优点:实现简单(5 行)、易调试
- 缺点:只看"终点最高价",忽略过程中的回撤;可能把"先涨 3% 再跌 10%"这种垃圾点也标为正样本

### Triple Barrier(进阶版,López de Prado 推荐)

**规则**:从第 i 天起,设置上沿(止盈线)、下沿(止损线)、时限(超时);向后扫描,先碰到哪条线决定标签。

```
上沿(止盈): close[i] × (1 + 5%)   → 先碰 → 标 +1
下沿(止损): close[i] × (1 - 3%)   → 先碰 → 标 -1
时限(超时): i + 20 天             → 都没碰 → 标 0
```

- 优点:模拟真实交易的"止盈+止损+时限"三要素,标签与实盘对齐
- 优点:同时编码方向 + 持有期 + 风险
- 缺点:实现稍复杂(~30 行)

## 训练架构详解

### 架构 A:全数据训练

所有 1640 天(2018-2024.06 训练集)都作为训练样本,每天用上述标签方法打 GT,ML 任务是"判断这 1640 天中每一天是否为买点"。

问题:
- 正样本约 80~150/1640,正负比 1:15~20(仍失衡)
- 模型大部分容量用在拟合"无聊日子",而这些日子靠规则就能过滤
- 类别不均衡,易过拟合

### 架构 B:Meta-Labeling(López de Prado 推荐)

**核心思想**:不让 ML 从零判断买点,而是让 ML 判断"现有规则给出的候选买点中,哪些是真信号、哪些是规则误报"。

**三步流程**:
1. 用项目已有的 9 个 Entry 规则(Breadth / VIX / RSI / SafeHaven / BreadthDiv 等)OR 组合,从 1640 天中筛出候选(预估 ~200~400 个)
2. 对每个候选,用 Triple Barrier 生成 GT
3. ML 在这些候选上训练,输出 P(success);非候选天直接不买

优势:
- 训练集自带平衡(候选筛后正负比约 1:2 ~ 1:4)
- 充分利用项目已有的领域知识(9 个规则)
- ML 角色明确:**二次筛选 / 误报过滤**,而不是从零判断
- 可解释性强(每个 ML 信号都对应一个规则候选 + ML 置信度)
- **Primary 阶段追求 Recall(粗粒度),Meta 阶段追求 Precision(细粒度)**——经典的"两阶段级联"模式

## 实施计划

### 阶段 1:Fixed Horizon + 全数据训练(baseline)

**目标**:跑通完整 ML 流水线,拿到 baseline 数字。

| 步骤 | 产出 |
|------|------|
| 1. 实现 `label_fixed_horizon()` | `ml/labeling.py` |
| 2. 统计不同参数下的正样本数(horizon ∈ {5,10,20}, threshold ∈ {2%,3%,5%}) | 终端表格 |
| 3. 特征工程(参考已有 9 个 Entry 信号 + 平稳化处理) | `ml/features.py` |
| 4. Logistic Regression baseline + XGBoost,Walk-Forward CV | `ml/train.py` |
| 5. 评估:AUC-PR(主) + IC(辅) + 回测 Sharpe(终判) | 报告 md |

**预计周期**:2~3 周。

### 阶段 2:Triple Barrier + Meta-Labeling(终极方案)

**前提**:阶段 1 已稳定,baseline AUC-PR / Sharpe 已记录。

| 步骤 | 产出 |
|------|------|
| 1. 实现 `label_triple_barrier()` | `ml/labeling.py` 扩展 |
| 2. 实现候选生成器(9 个 Entry 规则 OR 组合) | `ml/candidate_generator.py` |
| 3. 在候选上生成 Triple Barrier 标签,统计候选数 / 正负比 | 终端表格 |
| 4. ML 训练(仅在候选上) | 复用 `ml/train.py` |
| 5. 与阶段 1 对比 AUC-PR、IC、Sharpe | 对比报告 md |

**预计周期**:阶段 1 完成后 1~2 个月。

**判定**:阶段 2 必须在 AUC-PR 或 Sharpe 上显著超越阶段 1(差距 > 0.05 AUC-PR 或 > 0.2 Sharpe),否则停在阶段 1。

## 关键参数建议

| 参数 | 推荐起始值 | 说明 |
|------|---------|------|
| Fixed Horizon - horizon | 10 天 | 与波段操作时间尺度匹配 |
| Fixed Horizon - threshold | 3% | SPY 月波动率约 4~6% |
| Triple Barrier - 止盈 | +5% | 略大于一次波段反弹 |
| Triple Barrier - 止损 | -3% | 风险/回报比 ≈ 5/3 |
| Triple Barrier - 时限 | 20 天 | 给波段足够展开时间 |
| 候选生成 - 规则组合 | 9 个 Entry OR | 高召回率,后续靠 ML 提高精度 |

实际参数需在阶段 1 完成后,根据正样本数量和回测效果调优。

## 风险与注意事项

1. **数据集划分**:训练 2018-01 ~ 2024-06(~1640 样本),验证 2024-07 ~ 2025-06,测试 2025-07+。从 2018 开始避免 QE 时代的低波动数据污染。
2. **正样本数依赖参数**:threshold 太严 → 正样本太少;太松 → 训练目标失去意义。实施前必须先统计**全样本正样本数**(目标 ≥ 80)和**候选内正样本数**(目标正负比 1:2 ~ 1:4)。
3. **Walk-Forward 必须**:严禁使用普通 K-Fold,会泄漏未来信息。统一用 `TimeSeriesSplit` 或自定义滚动窗口。
4. **Meta-Labeling 的代价**:训练样本从 1640 缩到 ~200~400。若候选数 < 100,Meta-Labeling 不适用,退回架构 A。
5. **两个"正样本数"要分清**:全样本视角(给 Baseline 用)和候选视角(给 Meta-Labeling 用)是不同的统计量,详见 `ml-master-roadmap.md` 阶段 1.3。

## 参考资料

- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Chapter 3 (Labeling), Chapter 4 (Sample Weights).
- 同目录文档:
  - `ml-master-roadmap.md`(总路线图)
  - `meta-labeling-implementation-plan.md`(架构详解)
  - `indicator-evaluation-sop.md`(SOP)
  - `ml-execution-details-faq.md`(FAQ)
- 项目已有 Entry 模块:`src/modules/entry.py`(候选生成的基础)
- 项目已有评估指标:`src/metrics.py`(Sharpe / Calmar / Cost Advantage,将新增 t-stat / IC / 前瞻收益)
