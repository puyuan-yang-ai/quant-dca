# V2 特征升级 — 实施方案

## 特征变更总览

| 操作 | 特征名 | 计算方式 | 加入理由 |
|------|--------|----------|----------|
| 新增 | `rsi_minus_ma` | RSI(14) - EMA(RSI, 5) | "位置+方向"双维度：RSI 在回升还是恶化 |
| 新增 | `breadth_spread` | breadth_c5 - breadth_c1 | 收敛=恐慌消退，发散=恐慌扩散 |
| 新增 | `breadth_delta_3d` | breadth[t] - breadth[t-3] | breadth 短期方向（3日变化） |
| 新增 | `drawdown_from_high` | close / max(close, 60日) - 1 | 区分"刚开始跌"vs"已跌够" |
| 替换 | `breadth_c2` → `breadth_c3` | 直接用 c3 连续值 | c2 与 c1 共线性高，c3 信息量更大 |

## 各特征设计逻辑

### 1. rsi_minus_ma（RSI 动量方向）

```python
rsi = RSI(close, 14)
rsi_fast_ma = EMA(rsi, 5)
rsi_minus_ma = rsi - rsi_fast_ma
```

- 正值 = RSI 在回升（底部可能正在形成）
- 负值 = RSI 还在下行（还没到底）
- 解决问题：v1 只知道"RSI=28"，不知道 28 是往下跌到 28 还是从 20 回升到 28

### 2. breadth_spread（c5 - c1）

```python
breadth_spread = breadth_c5 - breadth_c1
```

- 大值 = c5 远高于 c1，深套股票多，恐慌仍在扩散
- 小值且在缩小 = 股票在摆脱均线压制，底部信号
- 来源：SpreadConvergence 的布尔版无效(p=0.14)，但连续值保留完整信息

### 3. breadth_delta_3d（breadth 3日变化）

```python
breadth_delta_3d = breadth[t] - breadth[t-3]
```

- 正值 = breadth 在好转（底部确认中）
- 负值 = breadth 在恶化（下跌未结束）
- 用 3 天而非 1 天：减少单日噪声，捕捉短期趋势

### 4. drawdown_from_high（从近期高点的回撤幅度）

```python
rolling_high = close.rolling(60).max()
drawdown_from_high = close / rolling_high - 1
```

- -2% = 刚开始回调（大概率假底）
- -10% = 已经跌了很多（更可能是真底）
- 直接解决 v1 弱点：模型可以学到"只跌了 2% 的信号大概率不是底"

### 5. breadth_c2 → breadth_c3

- c1 和 c2 只差一个平滑步骤（c2 = 最近2天有1天低于MA），相关系数高
- c3 = 连续3天低于MA，与 c1 有更大差异
- 且 sig_breadth_consec 已验证 c3<20 有效（重要度 Top 3）

## 实施步骤

1. 复制 `ml/features_v1.py` → `ml/features_v2.py`
2. 在 v2 中实现 5 个变更
3. 在 `ml/versions.py` 新增 v2 配置
4. 设 `ACTIVE_VERSION = "v2"`，运行 pipeline
5. 对比 v1 和 v2 指标
6. 更好则保留 v2，不好则切回 v1

## 风险控制

- 特征数 14，样本数 ~1376，比例约 98:1，无过拟合风险
- v1 代码不动（`features_v1.py` 锁定）
- 一行切回：`ACTIVE_VERSION = "v1"`
