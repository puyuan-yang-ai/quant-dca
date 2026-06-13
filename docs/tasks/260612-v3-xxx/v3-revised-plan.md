# V3 修正方案 — GT 回退 SL7 + 特征窗口化 + 指标升级

## 背景

V3 初版使用 SL5+SL7 并集作为 GT，但在图表上验证后发现 SL5 噪声太大（日内小波动就触发），引入了大量不必要的"假底部"。决定回退 GT 到 SL7-only。

## 需求

1. GT 回退到 SL7 (K=3)，与 V1/V2 保持一致
2. 特征保持 V3 的窗口化 + confluence 升级（21 个特征）
3. 评估指标加入 Precision/Recall/F1 + 收益 T-test

## 目标

验证：在相同 GT 下，V3 的窗口化特征是否比 V2 表现更好。

## 实施步骤

### 1. 修改 versions.py

v3 的 labeling 从 `sl_multi` 改回 `sl_proximity`：
```python
"v3": {
    "labeling": {
        "method": "sl_proximity",
        "sl_n": 7,
        "k": 3,
    },
    ...
}
```

### 2. 修改 show_chart.py 图表 GT 显示

图表只显示 SL7 作为 GT 标记（移除 SL5-only 显示）。

### 3. 升级 evaluate.py 指标

在现有输出基础上新增：
```
Precision: 模型说买时，多少真在底部
Recall: 底部出现时，模型抓住了多少
F1: 两者调和均值
T-test: ML过滤后收益 vs baseline 收益，p值判断是否显著
```

### 4. 重新跑 pipeline

对比 V2 vs V3（相同 GT，不同特征）：
- V2: 15 特征 + SL7 GT
- V3: 21 特征(窗口化+confluence) + SL7 GT

### 5. 启动图表验证

生成新图表，确认 GT 标记正确（只有 SL7 橙色点）。

## 成功标准

- F1 > V2 的 F1
- 收益 T-test p < 0.05（ML 过滤后收益显著优于不过滤）
- Precision 和 Recall 之间取得合理平衡

## 评估指标说明

| 指标 | 含义 | DCA 场景意义 |
|------|------|-------------|
| Precision | 模型说买，真的是底部 | 信号可信度 |
| Recall | 底部出现，模型抓住了 | 底部覆盖率 |
| F1 | 精确率和召回率的平衡 | 综合评分 |
| T-test | 收益差异是否统计显著 | 排除运气成分 |
