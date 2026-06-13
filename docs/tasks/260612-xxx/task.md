# ML Meta-Labeling MVP — 需求与目标

## 背景

项目已有一套成熟的规则信号系统（NDayConfirm、VIX、Breadth 等），通过 `ComposableStrategy` 在多种市场环境下回测验证。现需在规则信号之上加一层 ML 过滤器，验证机器学习是否能提升信号质量。

由于知识盲区和项目 scope 过大导致长期阻塞（~1个月），决定以最小可行产品（MVP）方式启动，先跑通再迭代。

## 核心需求

**一句话：** 用 XGBoost 判断"规则说买的时候，这次买入能不能赚钱"，过滤掉低质量信号。

## 确定的技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 交易标的 | SPY | 与现有回测系统一致 |
| 时间粒度 | 日线 | SPY_adjusted.csv，8000+ 行 |
| Primary Model | NDayConfirmEntry(n=5) | 实验中锁定的最优规则入场 |
| 标签方式 | Fixed Horizon (5天) | 最简单：信号后 5 天收益 > 0 → 正标签 |
| ML 模型 | XGBoost 二分类 | 直接上，不需要先做逻辑回归 baseline |
| Baseline 对比 | "不过滤"（即规则信号全部执行） | ML 过滤后 vs 不过滤，看是否有提升 |

## MVP 交付物

一个可运行的端到端 pipeline，输出可视化对比结果：

1. ML 过滤后的信号 vs 原始规则信号的胜率对比
2. ML 过滤后 vs 不过滤的收益指标对比（Sharpe、累计收益等）
3. XGBoost 模型的基础评估指标（AUC、准确率）

## 不在 MVP 范围内

以下内容明确推迟到后续迭代：

- Triple Barrier 标签
- 逻辑回归 baseline / 模型对比
- 凯利公式仓位管理
- 分箱验证 / 阈值优化
- IC 指标分析
- Walk-forward CV（MVP 先用简单 train/test split）
- 与现有 BacktestEngine 的集成（先独立脚本验证）

## 成功标准

MVP 不追求效果好坏，追求的是：

1. Pipeline 能跑通，不报错
2. 能看到一个对比结果（哪怕 ML 没有提升也是有效结论）
3. 为后续迭代建立了可复用的代码结构
