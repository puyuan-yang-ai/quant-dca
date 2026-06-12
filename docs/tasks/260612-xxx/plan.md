# ML Meta-Labeling MVP — 实施方案

## 架构概览

```
SPY_adjusted.csv (日线 OHLC)
    ↓
[1] NDayConfirmEntry(n=5) 生成买入信号日期列表
    ↓
[2] Fixed Horizon Labeling: 每个信号日 → 看未来5天收益 → 二分类标签
    ↓
[3] 特征构造: 信号触发当天的市场状态指标
    ↓
[4] Train/Test Split (按时间前后切分，避免未来信息泄漏)
    ↓
[5] XGBoost 训练 → predict_proba 输出置信度
    ↓
[6] 评估 + 可视化对比
```

## 实施步骤

### Step 1: 信号生成

- 复用现有 `src/modules/entry.py` 中 `NDayConfirmEntry` 的逻辑
- 输入: SPY 日线数据
- 输出: 所有触发买入信号的日期列表

### Step 2: 标签构造

- 对每个信号日 t，计算 `close[t+5] / close[t] - 1`
- 收益 > 0 → label = 1（信号正确）
- 收益 ≤ 0 → label = 0（信号错误）

### Step 3: 特征构造

使用信号触发当天可获取的市场数据（无未来信息）：

| 特征 | 来源 | 说明 |
|------|------|------|
| RSI(14) | SPY close | 超买超卖 |
| EMA20 距离 | SPY close | 当前价相对均线位置 (%) |
| EMA50 距离 | SPY close | 中期趋势 |
| 5日收益率 | SPY close | 近期动量 |
| 20日收益率 | SPY close | 中期动量 |
| 5日波动率 | SPY close | 近期波动 |
| VIX | vix_daily.csv | 恐慌指数 |
| Breadth | sp500_breadth.csv | 市场宽度 |

### Step 4: 数据切分

- 时间序列切分，不能随机 shuffle
- 方案: 前 80% 训练，后 20% 测试
- 后续迭代可升级为 walk-forward CV

### Step 5: 模型训练

- XGBoost 二分类，默认参数先跑
- 输出: `predict_proba` 概率值
- 阈值暂定 0.5

### Step 6: 评估与可视化

输出内容：

1. **模型指标**: AUC-ROC, 准确率, 精确率, 召回率
2. **对比表格**: 
   - 原始信号（NDay5 全部执行）: 胜率、平均收益、信号数量
   - ML 过滤后（只执行 prob > 0.5 的）: 胜率、平均收益、信号数量
3. **可视化图表**:
   - 测试集上信号分布图（正确/错误信号的概率分布）
   - 累计收益对比曲线

## 文件结构

```
ml/
├── run_mvp.py          # 入口脚本，一键跑通全流程
├── labeling.py         # Step 1-2: 信号生成 + 标签
├── features.py         # Step 3: 特征构造
└── evaluate.py         # Step 5-6: 训练 + 评估 + 可视化
```

## 依赖

需新增:
- `xgboost`
- `scikit-learn`（train_test_split, metrics）

## 运行方式

```bash
cd /home/puyuyang/Projects/quant-dca
python -m ml.run_mvp
```

预期输出:
- 终端打印对比表格
- 保存图表到 `output/ml_mvp_comparison.png`
