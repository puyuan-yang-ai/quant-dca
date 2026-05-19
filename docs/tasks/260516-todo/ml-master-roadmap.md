# ML 接入总路线图(Master Roadmap)

## 文档定位

本文是 `260516-xxx/` 目录的**总览索引**,串联起整个 ML 接入流程的 6 个阶段。

细节文档:
- `ml-gt-labeling-plan.md`:标签方法详解(Fixed Horizon / Triple Barrier)
- `meta-labeling-implementation-plan.md`:Meta-Labeling 架构详解
- `indicator-evaluation-sop.md`:新指标评估 SOP(5 道门)
- `ml-execution-details-faq.md`:实施细节 FAQ(6 个常见疑问)

**任何时候迷茫,先打开本文,定位当前阶段,再去读对应的细节文档。**

## 数据集划分(基础前提,所有阶段都基于此)

### 物理时间切分

```
训练集(Train):    2018-01 ~ 2024-06   (~1640 样本,6.5 年)
验证集(Val):     2024-07 ~ 2025-06   (~250 样本,1 年)
测试集(Test):    2025-07 ~ 至今       (rolling,~250+ 样本)
```

**为什么从 2018 开始?** 此前是 QE 主导的低波动单边牛市,此后市场重新有了正常的波动特征(贸易战、COVID、加息、AI 周期),数据风格与未来更接近。

### ⭐ 关键:**Train + Val 合并为"建模池",内部做 Walk-Forward CV**

**这是工业标准做法**(详见 FAQ Part 8):

```
─── 建模池(Modeling Pool) = Train + Val 合并 ───
2018-01 ~ 2025-06(~1890 样本)
    ↓
在池内做 Walk-Forward CV(TimeSeriesSplit, n_splits=5)
    ↓
用于:特征工程迭代 + 模型超参搜索 + 阈值调优
    ↓
每个 fold 算 AUC-PR / Sharpe,取 mean ± std

─── 测试集(Test) = Holdout,永不触碰 ───
2025-07 ~ 至今
    ↓
模型 + 阈值全部锁定后,只跑一次
    ↓
报告:Sharpe / Calmar / 最大回撤
```

**两条硬性规则**:
1. **测试集只用一次,任何超参数都不可再调**(包括阈值)
2. **建模池内严禁普通 K-Fold**,必须用 `TimeSeriesSplit` 或自定义滚动窗口(防止未来信息泄漏)

## 最终目标

在现有规则系统之上,接入一个基于 Meta-Labeling 的 XGBoost 信号模块,**在不破坏现有架构的前提下**提升 SPY 择时质量。

**判定标准**:测试集 Sharpe ≥ Buy & Hold + 0.2,且最大回撤未恶化。

## 6 阶段总览

| 阶段 | 名称 | 周期 | 核心交付物 | 进入下一阶段的判定 |
|------|------|------|-----------|----------------|
| **0** | 基础设施 | 1 周 | `ml/` 目录脚手架 + 评估辅助函数 | 空跑通过 |
| **1** | GT 生成 + 规则重评估 | 1~2 周 | 标签函数 + 规则 t-stat 排名 | 全样本正样本数 ≥ 80 |
| **2** | 特征工程 | 1~2 周 | `ml/features.py`(~35~45 个特征) | 特征矩阵无 NaN、已平稳化 |
| **3** | Baseline ML | 2 周 | Baseline 模型 + AUC-PR / IC 数字 | AUC-PR > 正样本占比 × 2 |
| **4** | Meta-Labeling 升级 | 2~4 周 | Meta 模型 + 对比报告 | AUC-PR 比 baseline 高 0.05+ |
| **5** | 回测引擎接入 | 1 周 | `MetaLabelingEntry` 模块 | 测试集 Sharpe ≥ B&H + 0.2 |

**总周期**:8~12 周(2~3 个月)。

## 阶段详解

### 阶段 0:基础设施(1 周)

**目的**:搭建空脚手架,后续阶段填内容。

**任务**:
- 创建 `ml/` 目录:`labeling.py`、`features.py`、`train.py`、`evaluate.py`、`candidate_generator.py`
- 实现数据加载接口(复用 `src/data_loader.py`)
- 实现评估辅助函数(放 `src/metrics.py` 扩展):
  - `calc_signal_t_statistic()` ⭐ **主指标**(纯信号比较用)
  - `calc_per_signal_forward_return()`(诊断:效应大小 + 胜率)
  - `calc_signal_ic()`(连续分数版本)
  - `calc_auc_pr()`(ML 训练迭代用)
- 编写最小可运行测试:加载 SPY → 计算 fwd_return → 打印一行

**输入**:无
**输出**:可运行的空脚手架
**判定**:`python -m ml.evaluate --quick-test` 能跑通

---

### 阶段 1:GT 生成 + 规则重评估(1~2 周)⭐ 关键阶段

**目的**:用统一的 GT 标签,把规则世界和 ML 世界连接起来。

**任务**:

**1.1 标签生成**
- 实现 `label_fixed_horizon(data, horizon, threshold)`
- 实现 `label_triple_barrier(data, tp_pct, sl_pct, time_limit)`
- 用网格参数(horizon ∈ {5,10,20}, threshold ∈ {2%,3%,5%})统计正样本数和分布
- **目标**:选定一组参数,使正样本占比落在 **5~15%**

**1.2 规则重评估**(关键中间步骤)
- 用选定的 GT,评估现有 9 个 Entry 规则:
  - **主排序指标:t-statistic**(防稀疏偏置)
  - **辅助指标:IC、Hit Rate、Precision / Recall / F1**
  - 9 个规则 **OR 组合的总 Recall**(作为 Meta-Labeling Primary 层的候选源)
- **顺便抽象出 `evaluate_indicator()` 函数**(SOP 雏形,详见 `indicator-evaluation-sop.md`)
- 输出对比表 + 简短分析

**1.3 正样本数统计**(关键决策依据)
- **全样本视角**(给阶段 3 Baseline 用):全部 1640 天的正样本数和占比
- **候选视角**(给阶段 4 Meta-Labeling 用):9 规则 OR 筛出候选后,候选内正样本数和正负比

**输入**:`data/SPY_adjusted.csv` + 现有 9 个 Entry 模块
**输出**:
- `ml/labeling.py`(两种标签函数)
- `docs/tasks/260516-xxx/phase1-rule-evaluation-report.md`(规则评估报告)

**判定**:
- ✅ **全样本正样本数 ≥ 80**(1640 样本场景,占比 5~15%;否则调标签参数)
- ✅ **候选内正负比落在 1:1 ~ 1:3**(否则调 Triple Barrier 参数)
- ✅ 9 个规则 OR 组合的 Recall ≥ 70%(否则需要补充规则或放宽)

---

### 阶段 2:特征工程(1~2 周)

**目的**:生成可喂给 ML 的特征矩阵。

**任务**:
- 设计 **35~45 个特征**(1640 样本遵循 √n 规则)
- **三类特征,缺一不可**:

```
第 1 类:布尔触发(9 个)
  - breadth_signal_today / vix_signal_today / rsi_signal_today / ...
  - 即现有 9 个 Entry 模块的触发状态(0/1)

第 2 类:底层连续值(~15 个)
  - breadth_value、breadth_5d_change
  - vix_value、vix_5d_change
  - rsi_value、rsi_5d_ma
  - safe_haven_value
  - 价格距 EMA20/50/200 偏离度(平稳化)
  - 近 5/20 日 log return 累加
  - ATR / close(归一化波动率)
  - (布尔丢了"程度信息",必须配连续值)

第 3 类:衍生/交互(~15 个,可选)
  - lag 特征(主要指标的 lag-1/5/10)
  - 滚动统计(RSI 的 5/20 日均值、std)
  - 交互项(Breadth × VIX 等)
  - 时间特征(距上一次买信号天数等)
```

- 严格检查 **lookahead bias**(任何特征只能用 t 时刻及之前的数据)
- 严格 **平稳化**(价格类必须转为偏离度/收益率/z-score)

**输入**:阶段 1 的 GT + 原始数据
**输出**:`ml/features.py`,可生成完整特征矩阵 X、标签 y

**判定**:
- ✅ 特征矩阵无 NaN
- ✅ 所有连续特征均值/方差稳定(用滚动统计验证)
- ✅ 特征数 ≤ 45(1640 样本对应 √n 上限约 40)

---

### 阶段 3:Baseline ML(2 周)

**目的**:用最简单的方式跑通完整 ML 流程,拿到第一个数字。

**任务**:
- 标签:Fixed Horizon(简单版)
- **数据**:**建模池**(Train + Val 合并,~1890 样本,2018-01 ~ 2025-06)
- **链式 Baseline**(不是全网格,详见 FAQ Part 1):
  1. **Logistic Regression**(必做基线)
  2. **XGBoost**(强正则:n_estimators=50, max_depth=3, reg_alpha=1, reg_lambda=1)
  3. **Random Forest**(可选,看树集成 vs 单线性)
- **关键规则**:每升级一档,必须证明平均 AUC-PR 提升 > 0.03 且 > 2×std;否则停在更简单的模型
- ⭐ **Walk-Forward CV**:`TimeSeriesSplit(n_splits=5)`,在建模池上跑 5 个 fold,取 mean ± std(详见 FAQ Part 8)
- **概率校准**:`CalibratedClassifierCV(method='isotonic', cv='prefit')`
- 评估:**AUC-PR**(主,跨 fold mean ± std) + **IC**(辅助,SOP 门 2 必须用) + **Log Loss**

**输入**:阶段 2 的特征矩阵 + 阶段 1 的 GT
**输出**:
- `ml/train.py`(模型阶梯的训练 + 评估)
- `docs/tasks/260516-xxx/phase3-baseline-report.md`(baseline 性能数字)

**判定**:
- ✅ AUC-PR > 正样本占比 × 2(基本及格线)
- ✅ 链式 baseline 每升级一档,AUC-PR 提升 > 0.03;否则停在更简单的模型
- ✅ 没有训练集 AUC-PR 远高于验证集(差 > 0.15 → 过拟合)
- ✅ 最坏 3 个实验,最好 2 个就能停

---

### 阶段 4:Meta-Labeling 升级(2~4 周)

**目的**:用 Meta-Labeling 架构精细化 baseline。

**任务**:
- **Primary 层**:9 个 Entry 规则 OR 生成候选(1640 天 → 目标 200~400 个)
- **标签**:Triple Barrier(进阶版)
- **Meta 层**:**只用阶段 3 胜出的模型**(链式 baseline 思想,不再重跑模型阶梯)
- **特征**:复用阶段 2,可针对候选样本特性微调
- 与阶段 3 baseline 对比 AUC-PR、IC、Sharpe

**输入**:阶段 1~3 的全部产出
**输出**:
- `ml/candidate_generator.py`
- `docs/tasks/260516-xxx/phase4-meta-labeling-report.md`(对比报告)

**判定**:
- ✅ AUC-PR 比 baseline 提升 > 0.05;否则停在 baseline
- ✅ 候选数 ≥ 100;否则 Meta-Labeling 不适用,退回阶段 3
- ✅ 候选上正负比落在 1:2 ~ 1:4(否则调 Triple Barrier 参数)

---

### 阶段 5:回测引擎接入(1 周)

**目的**:把 ML 模型包装为可与现有 Entry 模块并列的组件,并完成**两阶段优化**(详见 FAQ Part 7)。

**任务**:
- 实现 `MetaLabelingEntry` 类(`src/modules/entry.py`)
- 加载训练好的模型,运行时输出概率
- ⭐ **【关键】两阶段优化流程(Decoupled Optimization)**:

```
Step 1:阈值调优(在【建模池】上做 Walk-Forward CV)
   - grid search 阈值组合:(thr_low, thr_high) ∈ {0.4~0.6} × {0.7~0.9}
   - 分档式仓位映射:< thr_low 不买 / thr_low~thr_high 买 1 档 / > thr_high 买 2 档
   - 在 walk-forward 5 个 fold 上跑回测,取平均 Sharpe
   - 优化目标:【建模池平均 Sharpe】(防止单 val 巧合)
   - 锁定最优阈值组合

Step 2:最终评估(在【测试集】上做)
   - 固定模型 + 固定阈值,Walk-Forward 跑测试集
   - ⚠️ 【硬性规则】任何参数都不可再调!测试集只用一次!
   - 报告:测试集 Sharpe + Calmar + 最大回撤
```

- 在 5 个市场环境(bear/bull/bear-bull/bull-bear/all)上回测
- 用 `scripts/compare_signals.py` 与现有 9 个规则信号对比

**输入**:阶段 4 的最终模型
**输出**:
- `src/modules/entry.py` 新增 `MetaLabelingEntry`
- `docs/tasks/260516-xxx/phase5-backtest-report.md`(最终性能报告)

**判定**:
- ✅ 测试集 Sharpe ≥ Buy & Hold + 0.2
- ✅ 最大回撤未恶化(对比 baseline)
- ✅ 在 5 个市场环境中至少 3 个有正向贡献

**核心原则提醒**:
- 阈值调优**只能用验证集**(不能用测试集!)
- 测试集**只用一次**做最终评估,任何超参数都不可再调
- 否则测试集就被"二次过拟合",失去无偏评估的意义

## 阶段依赖图

```
[0 基础设施]
    ↓
[1 GT + 规则重评估] ⭐ 不能跳过
    ↓
[2 特征工程]
    ↓
[3 Baseline ML] ⭐ 必须有,作为对比基准
    ↓
[4 Meta-Labeling] ⭐ 可能停在阶段 3(如果 baseline 已经很好)
    ↓
[5 回测引擎接入]
```

**关键原则**:
- **每个阶段都有独立的判定**,不达标必须回退或调整,不要硬推
- **阶段 3 baseline 不能跳过**:没有 baseline,你无法判断阶段 4 是否真的提升了
- **如果阶段 3 已经很好(AUC-PR 显著超出预期),可以跳过阶段 4 直接上阶段 5**

## 本周第一步(具体清单)

1. ✅ 创建 `ml/` 目录:`labeling.py`、`features.py`、`train.py`、`evaluate.py`、`candidate_generator.py`(空文件即可)
2. ✅ 实现 `label_fixed_horizon(data, i, horizon=10, threshold=0.03)`(20 行)
3. ✅ 在 `src/metrics.py` 扩展评估函数:
   - `calc_signal_t_statistic()` ⭐ **主指标**
   - `calc_per_signal_forward_return()`
   - `calc_signal_ic()`
4. ✅ 用 9 组参数(horizon × threshold)统计 SPY 历史正样本数,选定一组
5. ✅ 用选定的 GT 评估 9 个现有 Entry 规则:**主排序按 t-statistic**,辅助看 IC / Hit Rate / Precision / Recall / F1
6. ✅ 输出对比表到 `phase1-rule-evaluation-report.md`
7. ✅ 顺便抽象出 `evaluate_indicator()` 通用函数(SOP 雏形,详见 `indicator-evaluation-sop.md`)

**完成后,你会拿到**:
- 量化的目标基准(全样本正样本数、Recall 上限)
- 现有 9 个规则的优劣排序(数据驱动,按 t-stat 排)
- Meta-Labeling Primary 层的规则选择依据
- Baseline ML 训练的明确目标
- 可复用的 SOP 函数(后续每加新指标都跑它)

## 关键技术约束(贯穿所有阶段)

| 约束 | 说明 | 违反后果 |
|------|------|---------|
| **特征数 ≤ √n** | 1640 样本 ≤ 40 个特征(800 样本 ≤ 28) | 过拟合,泛化失败 |
| **特征结构 = 布尔 + 连续 + 衍生** | 不要只用布尔,必须配连续值(梯度信息) | 信息丢失,模型欠拟合 |
| **Walk-Forward CV** | Train + Val 合并为建模池,内部 `TimeSeriesSplit(n_splits=5)`;禁用普通 K-Fold | 未来信息泄漏,回测虚高;单 fold 评估不稳定 |
| **特征必须平稳化** | 价格类特征转为收益率/偏离度/z-score | 不同时期失效 |
| **概率必须校准** | XGBoost 必须包 `CalibratedClassifierCV` | 概率不可信,仓位映射失真 |
| **训练/验证/测试严格按时间切分** | 2018-2024.06 / 2024.07-2025.06 / 2025.07+ | 未来信息泄漏 |
| **每阶段独立判定** | 不达标必须调整,不能硬推 | 错上叠错 |
| **纯信号比较用 t-stat** | 不要用成本优势比(有稀疏偏置) | 排序失真,错选稀疏策略 |
| **链式 baseline,不全网格** | 模型先定,架构 + 标签后定 | 实验数爆炸,无法管理 |

## 参考资料

- López de Prado, M. (2018). *Advances in Financial Machine Learning*. 第 3 章(Labeling)、第 4 章(Sample Weights)、第 7 章(Cross-Validation)。
- 同目录细节文档:
  - `ml-gt-labeling-plan.md`(标签方法详解)
  - `meta-labeling-implementation-plan.md`(Meta-Labeling 架构详解)
  - `indicator-evaluation-sop.md`(新指标评估 SOP)
  - `ml-execution-details-faq.md`(实施细节 FAQ,6 个常见疑问)
- 现有项目模块:
  - `src/modules/entry.py`(9 个 Entry 规则)
  - `src/metrics.py`(Sharpe / Calmar / 各种指标)
  - `src/backtest_engine.py`(回测引擎)
  - `scripts/compare_signals.py`(信号对比框架)
