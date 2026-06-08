# ML Entry 模块建设方案

## 第 1 步：特征工程

把现有信号模块的输出 + 原始指标都做成特征矩阵：

- RSI 当前值、RSI 5 日均、是否触发 B/B+/B++ 信号
- Breadth 当前值、Breadth 5/20 日变化、是否在背离
- VIX 当前值、VIX 5 日变化、是否 > 30
- 价格距 EMA20/50/200 偏离度
- 近 N 日收益率 / 波动率
- ……

特征数控制在 30~50 个，800 样本撑得住。

## 第 2 步：严格的 Walk-Forward CV

绝对不能用 sklearn 默认的 K-Fold，会泄漏未来信息！必须用 `TimeSeriesSplit` 或自己写 walk-forward：

| 训练集 | 验证集 |
|---|---|
| 2022 全年 | 2023 Q1 |
| 2022 + 2023 Q1 | 2023 Q2 |
| 2022 + 2023 H1 | 2023 Q3 |
| … | … |

## 第 3 步：Baseline（逻辑回归）→ XGBoost → 对比

记录每一步的 AUC / Precision@TopK / 在回测引擎里跑出来的 Sharpe。

> 最终评判标准是 **Sharpe**，不是 AUC——AUC 高但回测 Sharpe 低是常事（因为信号集中度、交易成本等）。

## 第 4 步：接入回测引擎

把 ML 模型包装成一个新的 Entry 模块 `MLEntry`，和现有的 `BreadthEntry` 等并列。

`predict_proba` 输出 → 映射到仓位。这样能直接复用已有的整个回测框架。
