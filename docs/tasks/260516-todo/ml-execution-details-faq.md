# ML 执行细节 FAQ

## 文档定位

本文档记录在 ML 接入流程**实施阶段才会冒出来的细节决策**,主要回答六个高频疑问:

**第一批 FAQ(Part 1~3)**:
1. 实验组合爆炸怎么办?
2. IC 是什么?要不要纳入评估体系?
3. 如何评估自己发现的指标?需要"核心池 + 候选池"两层架构吗?

**第二批 FAQ(Part 4~6)**:
4. SOP "全部丢给 ML" vs "用 SOP 筛"——到底听谁的?
5. 9 个 Entry 规则只做成 9 个布尔特征吗?
6. `calc_per_signal_forward_return` 和成本优势比改造,现在还推荐做吗?

**第三批 FAQ(Part 7~8)**:
7. 阈值如何调?两阶段优化怎么做(特征工程 vs 阈值调优)?
8. Walk-Forward CV 怎么做?数据切分和 CV 是一回事吗?

**与其他文档关系**:本文档是 `ml-master-roadmap.md`(总路线图)的执行补充,聚焦于"动手做的时候才会发现的问题",路线图本身没有展开这些细节。

---

## Part 1:实验组合爆炸的解决方案

### 问题

实施阶段会发现多个维度都要做选择:

- 标签维度:Fixed Horizon vs Triple Barrier(2 种)
- 架构维度:Direct vs Meta-Labeling(2 种)
- 模型维度:Logistic vs Random Forest vs XGBoost(3 种)

**理论全组合数**:2 × 2 × 3 = **12 个实验**。这种"全网格"做法不仅头大,而且**信息冗余**。

### 解决方案:**链式 Baseline**(不是全网格)

**核心思想**:**这三个维度不独立,有"优化顺序"**——先定模型(小影响维度),再定架构 + 标签(大影响维度)。

```
─── 阶段 3:Baseline 链(3 个实验)───
固定 [标签 = Fixed Horizon] + [架构 = Direct],只变 [模型]:

  实验 1:Logistic Regression(必做基线)
  实验 2:Random Forest         (可选,看树集成是否赢)
  实验 3:XGBoost              (主力模型)

锁定:取 AUC-PR 最高的模型,假设是 XGBoost

─── 阶段 4:架构升级(1 个实验)───
固定 [模型 = XGBoost(刚锁定的)],切换 [标签 + 架构]:

  实验 4:XGBoost + Triple Barrier + Meta-Labeling

对比实验 3 vs 实验 4 的 AUC-PR:
  提升 > 0.05 → 用 Meta-Labeling
  否则        → 用 Baseline 配置
```

**总实验数**:**3~4 个,不是 12 个**。

### 决策树(实施时照着走)

```
实验 1:Logistic on Direct + Fixed Horizon
    ↓
    AUC-PR > 正样本占比 × 2 吗?
    ├─ 否 → 回阶段 2 改特征工程,不是模型问题
    └─ 是 → 继续

实验 2:XGBoost on Direct + Fixed Horizon
    ↓
    比实验 1 提升 > 0.03 吗?
    ├─ 否 → 用 Logistic(更稳更简单),直接跳到阶段 5
    └─ 是 → 用 XGBoost,继续

实验 3:XGBoost on Meta-Labeling + Triple Barrier
    ↓
    比实验 2 提升 > 0.05 吗?
    ├─ 否 → 用 Baseline 配置(实验 2)进阶段 5
    └─ 是 → 用 Meta 配置进阶段 5
```

**最坏 3 个实验,最好 2 个就能停**。Random Forest 是可选项,不是必须。

### 为什么可以这么简化?

| 维度 | 通常的影响幅度 | 优化顺序 |
|------|-----------|--------|
| 模型(Logistic vs XGBoost) | AUC-PR 差异 0.03~0.10 | 先定 |
| 标签(Fixed vs Triple Barrier) | 提升 0.02~0.05 | 一起变 |
| 架构(Direct vs Meta) | 提升 0.02~0.10 | 后定 |

**链式而非网格**:每个维度依次锁定,避免组合爆炸的同时保留最优选择空间。这是工业界的标准做法。

---

## Part 2:IC(Information Coefficient)详解

### 定义

**IC = 模型预测分数与实际未来收益的 Spearman 秩相关系数**。

```python
# 二元信号(规则触发 0/1):用 point-biserial 相关
ic = point_biserial_correlation(signal_0_1, fwd_returns)

# ML 连续概率输出:用 Spearman 秩相关
ic = spearmanr(model.predict_proba()[:, 1], fwd_returns)
```

### 直觉解读

IC 衡量"预测分数高的样本,实际收益也高"的程度:

- IC = +1:完美预测(分数高的实际都涨)
- IC = 0:预测与实际无关
- IC = -1:完美反向(反着用也行)

### 经验门槛(日线数据)

| IC 范围 | 评级 |
|---------|------|
| > 0.05 | 优秀(私募基金主流因子水平) |
| 0.02 ~ 0.05 | 良好(可用) |
| 0.00 ~ 0.02 | 边缘(对独立策略不够,但对 ML 特征够) |
| < 0 | 反向信号(可考虑反着用) |

### IC vs t-statistic vs AUC-PR——本质区别

| 指标 | 测量对象 | 适合的输出 | 一句话解读 |
|------|---------|---------|----------|
| **t-statistic** | 触发后收益与基线差异的显著性 | **二元信号** | "信号显著吗?" |
| **IC** | 分数与未来收益的相关性 | **连续分数**(也兼容二元) | "分数排序对吗?" |
| **AUC-PR** | 分类器在不同阈值下的精度-召回 | **二元任务** | "排序能力如何?" |

**关键认知**:
- **二元信号场景**:IC(point-biserial)和 t-statistic 数学上几乎等价 → **t-stat 已经够,IC 冗余**
- **ML 连续概率场景**:AUC-PR 需要把概率二值化才能算,IC 直接用原始概率 → **IC 信息量更大**

### 在评估体系里的位置(对个人项目的修正版)

| 评估场景 | 主指标 | 辅助指标 | IC 必要性 |
|---------|--------|---------|----------|
| 纯信号比较(规则,二元) | t-stat | Hit Rate、信号数 | ❌ 冗余,不加 |
| **SOP 门 2(稳定性检验)** | — | — | ⭐⭐⭐⭐⭐ **必须用**(算 12 月滚动 IC 的 sign agreement) |
| ML 训练迭代 | AUC-PR | Log Loss | ⭐⭐⭐ 推荐报(辅助监控,可选) |
| 最终模型报告 | Sharpe | Calmar、最大回撤 | ⭐⭐⭐ 推荐报(若想跟外部对比) |

**对个人项目的诚实建议**:
- IC 在 **SOP 门 2** 是不可替代的(没有等价指标)
- IC 在 **ML 训练 / 最终报告** 是"推荐但非必须"——AUC-PR / Sharpe 已经覆盖大部分需求
- 之前说"ML 阶段必须报 IC",对机构合理(行业通用语言),**对个人项目过强**

### 为什么 IC 仍有独特价值(在某些场景)

1. **SOP 门 2 无替代**:测"信号方向跨时段一致性"必须用 IC
2. **跨项目通用语言**:AUC-PR 是 ML 内部指标,IC 是量化行业通用指标(若想跟外部研究员/资料对比)
3. **有公认经验门槛**:IC > 0.05 优秀 / > 0.02 可用 / > 0.005 弱可用,AUC-PR 没有跨项目绝对门槛
4. **配套指标 ICIR**:`mean(IC) / std(IC)` 跨时间窗口,衡量稳定性的金标准

### 落地建议

- **`src/metrics.py` 实现 `calc_signal_ic()` 函数**(一行 scipy,成本极低)
- 函数定位为**"诊断工具"**,不强制成为主要评估指标
- **SOP 门 2 必须调用**它做稳定性检验
- **ML 训练 / 最终报告**可选报告,看个人精力

---

## Part 3:特征评估流程 + 双池架构

### Part 3a:主观发现的指标如何客观评估?

**直接走 SOP**——这就是 SOP(`indicator-evaluation-sop.md`)的设计目的。

```
你的新指标
    ↓
门 1:可解释性(秒级)      → 通常通过(因为你能解释)
    ↓
门 2:稳定性(分钟级)      → 12 月滚动窗口 IC sign agreement ≥ 70%?
    ↓
门 3:显著性(分钟级)      → t-stat ≥ 1.5 OR IC ≥ 0.01?
    ↓
门 4:正交性(分钟级)      → max|corr(新, 已有特征)| < 0.7?
    ↓
门 5:边际贡献(阶段 3 后) → 加入后 AUC-PR 提升 ≥ 0.005?
    ↓
通过 → 入池
```

### 关于"图上看有效"的诚实评估

**人眼有严重的确认偏误(Confirmation Bias)**:

- 你记得指标在 5 个底部命中,**印象深刻**
- 它在 20 个非底部也触发(假信号),但你眼睛**自动过滤**
- 它在 10 个真底部漏报,你**注意不到**

所以 **"图上看有效" ≠ "实际有效"**。SOP 的门 2 + 门 3 用统计量**戳破人眼幻觉**:

```python
# 一行代码戳破幻觉
hit_rate = sum(fwd_ret[signal == 1] > 0) / sum(signal == 1)
print(f"Hit Rate: {hit_rate:.2%}")  # 经常你以为 70%,实际 53%
```

### Part 3b:核心池 + 候选池的双层架构

**这是工业标准做法,强烈推荐**。

#### 两个池的定义

| 池 | 包含什么 | 入池标准 | 训练时 |
|---|---------|---------|--------|
| **核心池(Core)** | 已验证 + 长期稳定的特征 | SOP 5 门全过 + 时间检验 | ✅ 参与训练 |
| **候选池(Candidate)** | 新加入 + 待验证的特征 | SOP 前 4 门通过(门 5 待验) | ✅ 参与训练 |

#### 关键认知:**训练时不区分,管理上严格区分**

**训练时**:两个池的特征**全部一起喂给 XGBoost**,不预先分级。

**为什么不预先分级?** 因为 XGBoost 会通过 feature importance / SHAP 自动告诉你谁有用——也许某个候选特征比某个核心特征更重要。预先区分反而限制了模型。

**管理上区分的意义**:**生命周期管理**,跟踪每个特征的"健康度"。

#### 特征生命周期流程

```
新特征发现
    ↓
跑 SOP 前 4 门
    ├─ 不过 → 直接丢弃,不进任何池
    └─ 过 4 门 → 进【候选池】,状态 = PENDING
                    ↓
                 参与训练
                    ↓
                 阶段 3 后跑门 5(边际贡献验证)
                    ├─ 提升 > 0.005 → 升入【核心池】,状态 = VALIDATED
                    └─ 没提升       → 移出候选池,状态 = REJECTED

─── 定期维护(每季度)───
对【核心池】每个特征:
    重新跑 SOP 门 2(稳定性)+ 门 5(当前边际贡献)
    ├─ 仍稳定 + 仍贡献 → 保留
    └─ 失效            → 降级回候选池,或直接移除
```

#### 关于正交性的常见误解

**只有正交性高 ≠ 应该加入**。完整的入池逻辑是 **5 门 AND 关系**(必须全部通过):

```
入候选池条件 = 可解释 AND 稳定 AND 显著 AND 正交
入核心池条件 = 在候选池 AND 边际贡献 > 0.005
```

**反例**:一个正交性高但不稳定的特征,只是引入了不稳定的噪声,**不是有用的互补信息**——依然要砍。

#### 代码组织建议

`ml/features.py`:

```python
CORE_FEATURES = [
    # 已通过 SOP 全 5 门,长期稳定贡献
    "rsi_14",
    "breadth",
    "vix",
    "safe_haven",
    "breadth_divergence_signal",
    # ... 持续维护
]

CANDIDATE_FEATURES = [
    # 通过 SOP 前 4 门,正在验证门 5
    "my_new_chart_pattern",
    "rsi_5d_change",
    "vix_breadth_interaction",
    # ... 持续增减
]

ALL_FEATURES = CORE_FEATURES + CANDIDATE_FEATURES  # 训练时用这个
```

**SOP 决策每个新特征的归属**;训练时统一用 `ALL_FEATURES`;Feature Importance 分析时**按池分别看**(核心池预期都重要;候选池里挑值得升级的)。

---

---

## Part 4:"全部丢给 ML" vs "用 SOP 筛"——其实没冲突

### 问题表象

之前给过两条看似矛盾的建议:
- **建议 A**:不要预先筛信号,全部丢给 ML 让模型自己筛
- **建议 B**:用 SOP(5 道门)严格评估每个特征

新手会困惑:到底听哪个?

### 答案:两条都对,因为它们说的是不同的"筛"

| 筛选类型 | 标准 | 该不该做? |
|---------|------|---------|
| **强度筛**(基于"独立有效性") | 这个信号单独胜率/Sharpe 高吗? | ❌ **不该** |
| **噪声筛**(基于 SOP 5 门) | 这个信号稳定吗?可解释吗?正交吗? | ✅ **应该** |

**关键认知**:**SOP 是噪声过滤器,不是强度过滤器**。

### 举例对照

**例 1:胜率 45% 的"看起来无效"信号**
- 如果它**稳定地是 45%**(t-stat 显著、不是随机噪声)、可解释、与其他特征正交
- SOP 判定:**ACCEPT** ✅
- 因为它有真实的反向信息,ML 能利用

**例 2:胜率 65% 的"看起来有效"信号**
- 如果它只在某段历史显著、其他时段失效(不稳定)
- SOP 判定:**REJECT** ❌
- 因为这是历史巧合,会害死模型

### 针对你的项目的具体工作流

```
─── 起点:9 个现有 Entry 规则 ───
这些已经过你长期使用 + Cost Advantage 验证
→ 直接进【核心池】,不需要重新跑 SOP 门 1~4
(它们已经通过"实战检验"这种更强的过滤了)

─── 第一版训练 ───
用 9 个核心特征(+ 必要衍生)训第一版 ML
→ 拿到 Baseline AUC-PR / IC / Sharpe

─── 后续迭代:每加一个新特征都走 SOP ───
你脑子里冒出/图表看到一个新指标
        ↓
跑 SOP 门 1~4(可解释、稳定、显著、正交)
        ├─ 不过 → 直接丢弃
        └─ 过 → 进【候选池】,标记 PENDING
        
定期(比如每加 3~5 个候选)重训模型 + 跑门 5(边际贡献):
        ├─ 提升 > 0.005 → 候选升核心
        └─ 没提升       → 候选移除
```

**"先核心,再候选"的工作流完全正确,不要再纠结**。

---

## Part 5:9 个 Entry 规则的特征结构——不只是 9 个布尔

### 问题

之前说"9 个 Entry 规则做成 9 个 0/1 特征",这个说法**简化过度**——实际特征数应远多于 9,且必须包含连续值。

### 正确的特征构成(每个 Entry 规则衍生 3 类特征)

```
─── 第 1 类:布尔触发(规则原貌)───
- breadth_signal_today:    1 if Breadth < 20 else 0
- vix_signal_today:        1 if VIX > 30 else 0
- rsi_signal_today:        1 if RSI < 30 else 0
- ... 共 9 个布尔特征

─── 第 2 类:底层连续值(信息更丰富)───
- breadth_value:           当日 Breadth 数值(0~100)
- breadth_5d_change:       近 5 日 Breadth 变化
- vix_value:               当日 VIX 数值
- vix_5d_change:           近 5 日 VIX 变化
- rsi_value:               当日 RSI 数值
- rsi_5d_ma:               RSI 5 日均值
- safe_haven_value:        Safe Haven 数值
- 价格距 EMA20/50/200 偏离度(平稳化)
- 近 5/20 日 log return 累加
- ATR / close(归一化波动率)
- ... 共 ~15 个连续特征

─── 第 3 类:衍生 / 交互(可选,看样本量)───
- lag 特征(主要指标的 lag-1/5/10)
- 滚动统计(RSI 的 5/20 日均值、std)
- 交互项(Breadth × VIX 等)
- 时间特征(距上一次买信号天数等)
- ... 共 ~15 个衍生特征
```

### 总特征数控制

| 训练集规模 | 总特征数目标 | 来源 |
|----------|-----------|------|
| 800 样本(3 年) | ~25~30(√n) | 严格 |
| 1640 样本(6.5 年,Master Roadmap 目标) | **~35~45** | 略宽松 |

**布尔(9) + 连续(~15) + 衍生(~15) ≈ 40 个,正好落在 1640 样本的 √n 合理区间**。

### 为什么连续值比布尔重要

**布尔信号丢了"程度信息"**:
- `Breadth < 20` 这个布尔无法区分 "Breadth = 5"(极度恐慌)和 "Breadth = 19"(轻微恐慌)
- 但 ML 能从 Breadth = 5 学到强买点,Breadth = 19 学到弱买点
- 连续值保留了这个"梯度",信息量大得多

**最佳做法**:**两个都给**(布尔 + 连续),让 ML 决定哪个更有用。

---

## Part 6:`calc_per_signal_forward_return` 改造——仍推荐,但有升级

### 直接回答:仍推荐,但建议升级版本

`metrics.py` 应该新增的函数:

```python
def calc_per_signal_forward_return(buy_dates, close_prices, horizon=20):
    """平均前瞻收益(效应大小)"""
    ...
    return avg_fwd_return, hit_rate

def calc_signal_t_statistic(signal_dates, all_dates, fwd_returns, horizon=20):
    """t 统计量(主指标,综合效应 × 样本量)"""
    ...
    return t_stat

def calc_signal_ic(signal_values, fwd_returns):
    """Information Coefficient(连续分数版本,可选)"""
    ...
    return ic
```

### `compare_signals.py` 输出表的最终建议

```
| 策略名 | t-stat ⭐ | IC | Hit Rate | 信号数 | 平均前瞻收益 | (参考)成本优势 |
                ↑                                                ↑
           按这列降序排序                               降级为参考列(可保留可删)
```

### 与最初建议的差异

| 最初建议 | 最终建议 |
|--------|--------|
| 用前瞻收益替换成本优势 | **用 t-statistic 作为主排序**(前瞻收益作为效应大小的诊断列) |
| 加 `calc_per_signal_forward_return` | 仍要加,但**还要加 `calc_signal_t_statistic` 作主指标** |
| 成本优势退到补充列 | 同意,可保留可删除(看回顾历史报告的需要) |

### 为什么 t-statistic 比前瞻收益好

前瞻收益**有稀疏偏置**(只触发 1 次的策略平均前瞻收益最高)。t-statistic 的公式 `t = SNR × √n` 天然处理这个问题:

- 稀疏策略:n 小 → √n 小 → t 小 → 被惩罚
- 密集弱策略:SNR 小 → t 小 → 被惩罚
- 中度好策略:SNR 中等 + n 中等 → t 大 → 被奖励

### 必要性与时机

| 改动 | 必要性 | 时机 |
|------|------|------|
| 加 `calc_signal_t_statistic`(主指标) | ⭐⭐⭐⭐⭐ 必须 | Master Roadmap **阶段 0** 完成评估辅助函数时 |
| 加 `calc_per_signal_forward_return`(诊断) | ⭐⭐⭐⭐ 强烈推荐 | 同上 |
| `compare_signals.py` 输出表重组 | ⭐⭐⭐ 推荐 | 阶段 1 评估现有 9 规则时(顺手就做了) |
| 删除/保留成本优势比列 | ⭐ 看个人偏好 | 不急 |

---

---

## Part 7:两阶段优化——特征工程 vs 阈值调优(解耦优化)

### 问题

ML 训练过程中至少有两个优化目标:
- 模型 / 特征质量(用 AUC-PR 衡量)
- 策略业务效果(用 Sharpe 衡量)

新手常犯的错:**两个目标混在一起优化**——结果就是迭代极慢、还容易过拟合。

### 答案:**Decoupled Optimization**(解耦优化)是工业标准范式

```
─── 阶段 A:特征工程 + 模型训练(阶段 2~4)───
优化目标:AUC-PR(阈值无关、秒级评估)
不断加减特征 / 调超参 / 换模型
锁定:产出最优模型,AUC-PR 达到瓶颈

       ↓

─── 阶段 B:阈值调优(阶段 5)───
固定模型,grid search 阈值 / 仓位映射
优化目标:验证集 Sharpe(业务指标、分钟级评估)
锁定:产出最优阈值组合

       ↓

─── 阶段 C:测试集最终评估(阶段 5)───
固定模型 + 固定阈值,在测试集上 Walk-Forward 跑
任何超参数都不可再调
报告:测试集 Sharpe + Calmar + 最大回撤
```

### 为什么必须分两阶段?

**理由 1:迭代速度差异巨大**

| 优化目标 | 单次评估耗时 | 适合场景 |
|--------|----------|---------|
| AUC-PR | < 1 秒 | 高频迭代(特征工程几百次循环) |
| Sharpe(需跑回测) | 30 秒~几分钟 | 低频决策(阈值搜索 10~20 次) |

如果直接用 Sharpe 做特征工程目标,一周才能跑完几十次实验。

**理由 2:避免"同时过拟合特征 + 阈值"**

如果特征工程时直接优化 Sharpe,模型可能学到"在某个特定阈值下表现好"的特征模式,**这个模式在其他阈值下完全失效**。分两阶段后:
- 特征工程优化 AUC-PR(阈值无关)→ 特征对所有阈值都有效
- 阈值优化只调一个超参数 → 过拟合空间小

### 阶段 B 的具体做法(阶段 5 核心)

```python
# 1. 加载阶段 3/4 训练好的最佳模型
model = load_best_model()

# 2. 在【验证集】上 grid search 阈值
best_sharpe = -np.inf
best_thresholds = None

for thr_low, thr_high in itertools.product([0.4, 0.5, 0.6], [0.7, 0.8, 0.9]):
    def map_to_position(p):
        if p < thr_low:    return 0       # 不买
        if p < thr_high:   return 1       # 买 1 档
        else:              return 2       # 买 2 档(强信号)
    
    signals_with_size = [map_to_position(p) for p in model.predict_proba(X_val)[:, 1]]
    sharpe = run_backtest(signals_with_size, val_data)
    
    if sharpe > best_sharpe:
        best_sharpe = sharpe
        best_thresholds = (thr_low, thr_high)

print(f"验证集最优:{best_thresholds},Sharpe = {best_sharpe}")
```

### 阶段 C 的硬性规则

```python
# 3. 在【测试集】上 Walk-Forward 评估,任何参数不可再调!
final_sharpe = run_walk_forward_backtest(
    model=model,                     # 不可改
    thresholds=best_thresholds,      # 不可改
    test_data=test_data              # 真实未来数据
)

# 4. 上线判定
if final_sharpe >= bh_sharpe + 0.2:
    print("✅ 上线")
else:
    print("❌ 不上线,回退 baseline")
```

**关键:测试集只用一次,只评估,不调整**。否则测试集就被"二次过拟合"了,失去无偏评估的意义。

### 三阶段优化的指标对照表

| 阶段 | 主指标 | 阈值依赖? | 优化频率 | 可用数据集 |
|------|--------|---------|--------|----------|
| **A(特征工程 + 训练)** | AUC-PR | ❌ 无关 | 高频(数百次) | 训练 + 验证(CV) |
| **B(阈值调优)** | 验证集 Sharpe | ✅ 强相关 | 中频(10~20 次) | **验证集** |
| **C(最终评估)** | 测试集 Sharpe | ✅ 已固定 | **只跑一次** | **测试集** |

### 跟其他 FAQ 的联动

- Part 1 链式 baseline 是阶段 A 内部的优化策略
- Part 2 IC 是阶段 A 的辅助指标
- Part 3 双池 + Part 4 SOP 是阶段 A 的特征管理工具
- Part 6 t-statistic 是阶段 1 规则评估和 SOP 评估时用的(不属于 A/B/C)
- **本 Part 7 是把所有阶段串起来的最高层框架**

---

---

## Part 8:Walk-Forward CV——数据切分 vs 交叉验证,两件事别混

### 容易混淆的两个概念

新手最容易混淆"**数据切分**"和"**交叉验证方法**":

| 概念 | 定义 | 对应内容 |
|------|------|--------|
| **数据切分** | 把全部数据按时间分成不重叠的 Train / Val / Test 三段 | 2018-2024.06 / 2024.07-2025.06 / 2025.07+ |
| **交叉验证(CV)方法** | 在 Train / Val 数据集**内部**如何反复划分子集做训练/验证 | TimeSeriesSplit / K-Fold / Leave-One-Out 等 |

**两个独立维度,可以组合搭配**。但金融时间序列**只能**用前向(walk-forward)型 CV,不能用普通 K-Fold(会泄漏未来信息)。

### 两种工作流对比

**简化版(入门级)**:
```
Train 训模型 → Val 调阈值评估 → Test 最终评估
```
- 缺点:只用一个 Val 评估,数值波动大,统计不可靠

**Walk-Forward 版(工业标准)** ⭐:
```
Train + Val 合并 → 内部 Walk-Forward CV(5 fold) → Test 最终评估
```
- 优点:每个超参组合有 5 个 fold 评分,可算 mean ± std
- 缺点:稍复杂

**对你的项目(1890 建模样本,大量超参搜索),必须用 Walk-Forward 版**。

### Walk-Forward CV 具体怎么做

```python
from sklearn.model_selection import TimeSeriesSplit

# 1. 合并 Train + Val 为建模池
modeling_pool = data[(data.date >= "2018-01-01") & (data.date <= "2025-06-30")]
test_set = data[data.date >= "2025-07-01"]  # 锁起来不要碰

# 2. 在建模池上做 Walk-Forward CV(5 fold)
tscv = TimeSeriesSplit(n_splits=5, test_size=63)  # 每 fold val 约 3 个月

auc_pr_per_fold = []
for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(modeling_pool)):
    # train_idx 严格在 val_idx 之前(walk-forward 关键)
    X_train, y_train = features[train_idx], labels[train_idx]
    X_val, y_val = features[val_idx], labels[val_idx]
    
    model.fit(X_train, y_train)
    auc_pr = average_precision_score(y_val, model.predict_proba(X_val)[:, 1])
    auc_pr_per_fold.append(auc_pr)

mean_auc_pr = np.mean(auc_pr_per_fold)
std_auc_pr = np.std(auc_pr_per_fold)
print(f"模型 AUC-PR: {mean_auc_pr:.3f} ± {std_auc_pr:.3f}")
```

### Walk-Forward 后续每一阶段如何用

| 用途 | 数据集 | 评估方式 |
|------|--------|---------|
| **特征工程迭代**(阶段 2~3) | 建模池 | walk-forward 5 fold 平均 AUC-PR |
| **模型超参搜索**(阶段 3~4) | 建模池 | walk-forward 5 fold 平均 AUC-PR |
| **阈值/仓位映射调优**(阶段 5 Step 1) | 建模池 | walk-forward 5 fold 平均 Sharpe |
| **最终评估**(阶段 5 Step 2) | **测试集** | **单次 Walk-Forward,不可调参** |

### 改进判定的统计严谨性

之前说"AUC-PR 提升 > 0.005 算改进",在 walk-forward 下更严谨的判定:

```python
# 5 个 fold 平均的对比
mean_improvement = mean(auc_pr_new_per_fold) - mean(auc_pr_old_per_fold)
fold_diffs = [n - o for n, o in zip(auc_pr_new_per_fold, auc_pr_old_per_fold)]
std_improvement = std(fold_diffs)

# 双重判定(AND 关系)
if mean_improvement > 0.005 and mean_improvement > 2 * std_improvement:
    print("改进显著")
else:
    print("改进不显著(可能只是随机波动)")
```

**核心:不只看平均值,还要看是否超过随机波动的 2 倍**。

### 关键铁律

| 铁律 | 违反后果 |
|------|---------|
| **CV 必须前向**(`TimeSeriesSplit` 或自定义滚动) | 未来信息泄漏,回测虚高 50%+ |
| **建模池和测试集严格隔离** | 测试集失去无偏评估意义 |
| **测试集只跑一次** | 二次过拟合 |
| **所有 fold 共用同一套超参** | 每个 fold 调参 = 把 CV 当训练用 |

### 与 Part 7 的关系

- Part 7 讲"两阶段优化"(特征 vs 阈值),回答"**优化什么**"
- Part 8 讲"Walk-Forward CV",回答"**怎么评估**"
- 两者结合:Part 7 的两个阶段都用 Part 8 的 Walk-Forward 方式做评估

---

## 八个 Part 的核心收获

| Part | 核心收获 |
|------|---------|
| 1 实验数 | 链式 baseline 不是全网格,3~4 个实验就够(模型先定,架构 + 标签后定) |
| 2 IC 指标 | SOP 门 2 必须用;ML 训练/最终报告推荐但非必须(AUC-PR / Sharpe 已覆盖) |
| 3 特征评估 + 双池 | 主观发现的指标走 SOP 5 门;两个池训练时不分级,管理上严格区分 |
| 4 SOP 性质 | SOP 是噪声过滤器,不是强度过滤器。9 现有规则直接进核心池,新指标走 SOP |
| 5 特征结构 | 9 布尔 + ~15 连续 + ~15 衍生 ≈ 40 特征(适配 1640 样本 √n)。布尔丢了程度信息,必须配连续 |
| 6 指标改造 | t-statistic 作主指标,前瞻收益作诊断列;成本优势降级或删除 |
| 7 两阶段优化 | 特征工程优化 AUC-PR(快),锁定后阈值优化 Sharpe(慢)。测试集只跑一次,不可再调 |
| 8 Walk-Forward CV | Train + Val 合并为建模池,内部 5 fold walk-forward;测试集只用一次。所有评估都用 mean ± std |

## 与其他文档的关系

| 文档 | 关系 |
|------|------|
| `ml-master-roadmap.md` | 总路线图;本文档是执行细节补充。Part 7、Part 8 直接对应阶段 3~5 |
| `ml-gt-labeling-plan.md` | 标签方法详解 |
| `meta-labeling-implementation-plan.md` | Meta-Labeling 架构详解 |
| `indicator-evaluation-sop.md` | 本文档 Part 3、Part 4 引用的 SOP 详解 |
