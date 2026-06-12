# V3 实施方案

## 三大改进

### 1. 特征窗口化（布尔3天 + 连续min3天）

保留 V2 全部 15 个原始特征，新增 5 个窗口版本：

| 新增特征 | 计算方式 | 窗口 |
|----------|----------|------|
| `sig_rsi_recent_3d` | 最近3天内是否有 RSI B 信号 | 3天 |
| `sig_breadth_recent_3d` | 最近3天内 breadth 是否 < 20 | 3天 |
| `sig_breadth_div_recent_5d` | 最近5天内是否有 breadth 背离 | 5天 |
| `rsi_min_3d` | 最近3天 RSI(14) 的最低值 | 3天 |
| `breadth_min_3d` | 最近3天 breadth 的最低值 | 3天 |

### 2. 信号共振计数（Confluence Score）

新增 1 个综合特征 `confluence_5d`：

```python
confluence_5d = sum([
    rsi_min_5d < 30,            # 最近5天RSI到过超卖
    breadth_min_5d < 20,        # 最近5天breadth到过低位
    vix_regime >= 2,            # VIX在Elevated+
    consecutive_below_ema >= 7, # 连续跌够久
    sig_rsi_recent_5d == 1,     # 最近5天有RSI B信号
])
# 值域 0~5，越大越像底部
```

### 3. 多尺度 SL 标注

GT 从 SL7-only 改为 SL5+SL7 联合：

```python
label = 1 if (nearest_SL5 <= 3) or (nearest_SL7 <= 3) else 0
```

- SL5 每年约 15 个（vs SL7 的 11 个），覆盖更多温和底部
- 预期正标签比例从 40% 升到 ~50-55%

## 特征总数

V2(15) + 窗口化(5) + confluence(1) = **21 个特征**

样本/特征比 ≈ 1376/21 ≈ 65:1，仍在合理范围。

## 实施步骤

1. `ml/labeling.py`：新增 `create_labels_sl_multi(sl_ns=[5,7], k=3)`
2. `ml/features_v3.py`：复制 V2，添加 5 个窗口特征 + confluence_5d
3. `ml/versions.py`：注册 v3 配置
4. 运行 pipeline，对比 V2
5. 验证被误杀信号（2022-12-28, 2023-03-13）概率是否提升
6. 如果通过 → 激活 v3；不通过 → 保持 v2

## 窗口大小选择理由

- 布尔信号 + min/max 用 **3天**：对应"信号错位1-2天"的现实情况
- Confluence 用 **5天**：共振需要多个信号陆续到位，5天给足时间
- breadth_div 用 **5天**：背离信号本身稀疏，需要更宽窗口

## 成功标准

- Recall >= 50%（核心目标：减少误杀）
- AUC-ROC >= 0.618（不退步）
- 被误杀的黄金坑（2022-12-28, 2023-03-13）概率 >= 0.5
