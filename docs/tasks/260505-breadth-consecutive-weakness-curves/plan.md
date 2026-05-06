# 计划：Breadth 连续弱势曲线计算与可视化

## Step 1：扩展 Breadth 数据计算

修改 `fetch_breadth.py`，在计算现有 Breadth 指标时，同步计算连续弱势曲线。

计算逻辑：

1. 对每个 S&P 500 成分股，判断当日是否 `close < SMA(20)`。
2. 维护每只股票"连续低于 MA20"的天数计数器：低于 → +1，不低于 → 归零。
3. 对 N=2,3,4,5，统计"计数器 >= N"的股票占比，取反（`100 - 占比`），使低值=恐慌。
4. 输出到 CSV。

输出字段：

```text
date,breadth,breadth_c2,breadth_c3,breadth_c4,breadth_c5
```

- `breadth`：保留现有含义（站上 MA20 的比例），向后兼容。
- `breadth_c2` ~ `breadth_c5`：连续弱势曲线，低值=恐慌。
- 不输出 `breadth_c1`，因为 `breadth_c1 ≡ breadth`（连续 ≥1 天低于 MA20 = 今天低于 MA20 = 100 - breadth），冗余。

## Step 2：数据校验

生成数据后做基础校验：

- 确认每个交易日满足 `breadth ≤ breadth_c2 ≤ breadth_c3 ≤ breadth_c4 ≤ breadth_c5`（N 越大 → 条件越严格 → 平时值越高）。
- 检查缺失值、日期对齐和成分股数据不足导致的异常点。

这一步只做数据质量验证，不引入策略判断。

## Step 3：交互式图表接入

修改交互式图表相关逻辑，将连续弱势数据传入前端图表渲染。

可视化要求：

- 在现有 Breadth 副图中叠加显示 5 条曲线（原始 breadth + breadth_c2 ~ c5）。
- 五条曲线使用不同颜色区分，并在图例中明确标注。
- Y 轴范围使用 0-100，便于和现有 Breadth 指标对照。

## Step 4：人工观察与记录

先不写交易规则，重点观察曲线形态是否有稳定信息量。

建议重点检查：

- 2022 熊市期间，是否出现 breadth ≈ breadth_c5 且整体低位的持续弱势形态。
- 2020 年 3 月 COVID 崩盘期间，是否出现 breadth 快速下跌但 breadth_c5 滞后的突发冲击形态。
- 关键底部附近，是否出现 breadth_c5 仍低但 breadth 开始回升的修复形态。
- `breadth - breadth_c5` 的 spread 是否能反映市场恶化或修复速度。

观察结论可以记录到 `note.md` 或后续 GT 文档中。

## Step 5：后续特征工程预留

如果可视化确认这组曲线有价值，再进入 ML 特征工程阶段。

可预留的特征包括：

- 原始曲线：`breadth` + `breadth_c2` ~ `breadth_c5`
- spread：例如 `breadth - breadth_c5`
- 变化率：例如 `delta_breadth_c5`
- 曲线面积或分层面积
- 与 VIX、Breadth、NDay5、RSI、SafeHaven、Breadth Divergence 的组合特征

模型方向先以 XGBoost / LightGBM 为主，并使用 walk-forward validation 和严格样本外验证控制过拟合风险。

## Step 6：前瞻收益与期权验证

在特征探索之外，可以补充更新 `validate_signal_returns.py`：

- 加入 VIX、Breadth 和第一梯队 AND 组合。
- 输出 5/10/20 日前瞻收益、胜率和最大回撤。
- 基于前瞻收益判断是否值得继续做期权回测。

如果前瞻收益支持，再考虑模拟 30 DTE 牛市价差，并结合实际 VIX 水平估算期权成本和期望收益。
