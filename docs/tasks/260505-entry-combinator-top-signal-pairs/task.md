# 通用组合器重构 + 三强信号两两组合测试

## 背景

日线 GT 表中三个最强信号为 VIX>30（Sharpe 第一）、Breadth<20（成本优势第二）、NDay5（最稳健）。三者信号维度各不相同（期权隐含波动率 / 市场宽度 / 价格趋势），但目前只有 NDay+RSI 和 Breadth+RSI 的组合数据，缺少三强信号的两两组合。

同时，entry.py 中已有 4 个硬编码组合类（`CombinedAndEntry`、`CombinedOrEntry`、`BreadthAndRSIEntry`、`BreadthOrRSIEntry`），继续新增会导致类爆炸。

## 需求

### 1. 重构：通用组合器替换专用组合类

用通用的 `AndEntry(entry_a, entry_b)` 和 `OrEntry(entry_a, entry_b)` 替换掉现有 4 个专用组合类，支持任意两个 Entry 实例的 AND/OR 组合。

### 2. 测试：6 个新组合

| 组合 | 逻辑 |
|------|------|
| NDay5 AND Breadth<20 | 趋势 + 宽度 双重确认 |
| NDay5 OR Breadth<20 | 趋势 + 宽度 双通道 |
| VIX>30 AND Breadth<20 | 恐慌 + 宽度 双重确认 |
| VIX>30 OR Breadth<20 | 恐慌 + 宽度 双通道 |
| VIX>30 AND NDay5 | 恐慌 + 趋势 双重确认 |
| VIX>30 OR NDay5 | 恐慌 + 趋势 双通道 |

### 3. 日线 + 周线都跑

- 日线：标准化执行层，近三年全量（2022-01-01 ~ 2025-06-01），结果更新到 GT 指标总表
- 周线：同样标准化执行层，结果更新到 GT 周线指标总表

### 4. 注意事项

- 周线 VIX 数据需要处理日期对齐问题：VIX CSV 是日线日期，周线回测用的是周一日期，需重采样
- 周线 NDay5 语义变为"连续 5 周低于 EMA"，由引擎自然计算，无需额外处理
