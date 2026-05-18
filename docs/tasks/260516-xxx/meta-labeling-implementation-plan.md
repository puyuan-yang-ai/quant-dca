# Meta-Labeling 实施方案

## 背景与目标

直接在 1640 天 SPY 数据(2018-2024.06)上训练 ML 判断"是否买点",存在三个本质问题:

1. **类别极度不均衡**:正样本约 80~150 个,正负比 ~1:15~20,模型容易躺平输出全 0
2. **学习目标过宽**:大部分天是"无聊日子",规则就能过滤,ML 把容量浪费在这里
3. **领域知识浪费**:项目已有 9 个规则化 Entry 模块,直接弃用可惜

**Meta-Labeling 用一个串行的"两层结构"重新组织 ML 任务**:

- **第一层 Primary**:用现有 9 个 Entry 规则筛候选(高召回、可解释)
- **第二层 Meta(ML)**:在候选中判断"真信号 vs 规则误报"(高精度)

**目标**:让 ML 解决一个更聚焦、更可学的子问题,从而在小样本下也能稳健提升信号质量。

## 架构说明(串行级联)

```
原始数据 1640 天(2018-2024.06)
       ↓
─── Primary 层(规则,无需训练)───
   9 个 Entry 模块 OR 组合
       ↓
   触发的候选日(预估 ~200~400 天)
       ↓
─── Meta 层(XGBoost / Logistic)───
   对每个候选日,用 Triple Barrier 生成 GT(+1/-1/0)
       ↓
   仅在这 ~200~400 个候选上训练 ML
       ↓
   ML 输出 P(success) ∈ [0, 1]
       ↓
─── 决策层 ───
   Primary 未触发 → 不买
   Primary 触发 + Meta 概率 > 阈值 → 买
   Primary 触发 + Meta 概率 < 阈值 → 不买(过滤误报)
```

**关键认知**:

- **训练数据 = 候选(~200~400),不是全部 1640 天**
- **预测数据 = 候选(~200~400),非候选日直接不买,不进入 ML**
- Primary 是规则,不训练;只有 Meta(ML)需要训练

**关于 Recall / Precision 分工**(粗粒度 → 细粒度的级联):

- **Primary 阶段追求高召回**(目标 ≥ 80%):宁错杀不放过,允许大量误报
- **Meta 阶段追求高精度**(目标 ≥ 60%):在 Primary 过滤后,集中精力做精细判断
- 这是 ML 经典级联模式(Viola-Jones 人脸检测、信息检索等都用)

## 实施计划

### 前置条件

阶段 1(`ml-gt-labeling-plan.md` 描述的 Fixed Horizon + 全数据 baseline)已完成,有 baseline AUC-PR / Sharpe 数字可供对比。

### Step 1:候选生成器

| 内容 | 说明 |
|------|------|
| 文件 | `ml/candidate_generator.py` |
| 输入 | 数据 + 9 个 Entry 模块配置 |
| 输出 | 候选日索引列表 + 每天哪些规则触发(用于后续诊断) |
| 验收 | 1640 天 → 候选数 200~400(占总样本 10%~20%,过少 / 过多都不适用) |

### Step 2:Triple Barrier 标签生成

| 内容 | 说明 |
|------|------|
| 文件 | `ml/labeling.py`(扩展) |
| 函数 | `label_triple_barrier(data, i, tp_pct, sl_pct, time_limit)` |
| 参数起点 | tp=+5%, sl=-3%, time_limit=20 天 |
| 输出 | 每个候选的 GT:+1(止盈先)/ -1(止损先)/ 0(超时) |
| 验收 | 在候选上正负比落在 1:1 ~ 1:3 之间,接近平衡 |

### Step 3:特征工程

| 内容 | 说明 |
|------|------|
| 文件 | `ml/features.py`(复用阶段 2 产出) |
| 特征数 | **35~45 个**(1640 样本遵循 √n 经验) |
| 特征结构 | **9 布尔触发 + ~15 底层连续值 + ~15 衍生交互**(详见 master-roadmap 阶段 2) |
| 关键提醒 | 布尔丢了"程度信息",必须配连续值;不要只用 9 个布尔 |
| 验收 | 特征矩阵无 NaN、无 lookahead bias、所有连续特征已平稳化 |

### Step 4:Meta 模型训练

| 内容 | 说明 |
|------|------|
| 文件 | `ml/train_meta.py` |
| 模型选择 | **直接用阶段 3 胜出模型**(链式 baseline 思想,不重复模型阶梯) |
| 验证 | Walk-Forward CV,`TimeSeriesSplit(n_splits=5)`,在 Train + Val 合并的建模池上做(详见 FAQ Part 8) |
| 概率校准 | `CalibratedClassifierCV(method='isotonic', cv='prefit')` |
| 主指标 | AUC-PR(特征工程迭代) |
| 辅指标 | IC、Log Loss |
| 验收 | AUC-PR 显著高于候选正样本占比(baseline) |

### Step 5:阈值调优与回测接入(两阶段优化)

**详细方法论见 `ml-execution-details-faq.md` Part 7**(Decoupled Optimization)。

| 内容 | 说明 |
|------|------|
| 文件 | `src/modules/entry.py`(新增 `MetaLabelingEntry`) |
| 阈值搜索 | **【验证集】**上 grid search,目标最大化 Sharpe |
| 仓位映射 | 分档式:概率 < thr_low 不买 / thr_low~thr_high 买 1 档 / > thr_high 买 2 档 |
| 终判 | **【测试集】**Sharpe + Calmar(Walk-Forward,**任何参数不可再调!**) |
| 上线条件 | 测试集 Sharpe ≥ B&H + 0.2,且最大回撤未恶化 |

**⚠️ 硬性规则**:阈值调优只能用验证集,测试集只用一次做最终评估,任何超参数都不可再调。否则测试集就被"二次过拟合",失去无偏评估意义。

## 关键技术约束

| 约束 | 说明 |
|------|------|
| **候选数** | 必须 ≥ 100(1640 样本场景),否则 Meta-Labeling 不适用,退回全数据训练 |
| **特征数** | ≤ √n ≈ 40(1640 样本);特征结构必须包含布尔 + 连续 + 衍生三类 |
| **CV 方式** | Train + Val 合并为建模池,内部 `TimeSeriesSplit(n_splits=5)`;禁用普通 K-Fold |
| **概率校准** | XGBoost 默认 `predict_proba` 非真概率,必须包 `CalibratedClassifierCV` |
| **数据隔离** | 训练/验证/测试集严格按时间切分(2018-2024.06 / 2024.07-2025.06 / 2025.07+) |

## 风险与回退方案

| 风险 | 触发条件 | 回退方案 |
|------|---------|---------|
| 候选数过少 | < 100(1640 样本场景) | 放宽 Primary 规则组合(增加 OR 条件)或退回全数据训练 |
| 类别仍失衡 | 候选上正负比 > 1:5 | 调 Triple Barrier 参数(放宽止盈、缩短时限) |
| Meta 模型未提升 | AUC-PR 比 baseline 提升 < 0.05 | 增加特征 / 检查特征是否平稳化 / 退回 baseline |
| 回测 Sharpe 反降 | 测试集 Sharpe < baseline | 检查是否过拟合阈值;退回 baseline |

## 与现有项目的集成方式

- **不替代,只增量**:Meta-Labeling 产出一个新的 Entry 模块 `MetaLabelingEntry`,与现有 9 个规则 Entry 并列
- **可对比**:用 `scripts/compare_signals.py` 跑标准化执行下的对比,看 ML 信号在统一执行框架下是否优于纯规则
- **可组合**:`MetaLabelingEntry` 可与其他 Entry 模块通过 `AndEntry` / `OrEntry` 进一步组合
- **可回滚**:即使 ML 失效,删除 `MetaLabelingEntry` 即可,主框架不受影响

## 参考资料

- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Chapter 3.6 (Meta-Labeling).
- 同目录文档:
  - `ml-master-roadmap.md`(总路线图)
  - `ml-gt-labeling-plan.md`(标签方法详解)
  - `indicator-evaluation-sop.md`(新指标评估 SOP)
  - `ml-execution-details-faq.md`(实施细节 FAQ,特别是 Part 1 链式 baseline、Part 5 特征结构)
- 现有 Entry 模块:`src/modules/entry.py`(候选生成的基础)
