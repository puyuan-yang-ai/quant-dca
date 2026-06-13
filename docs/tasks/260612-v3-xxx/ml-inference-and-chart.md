# ML 推理模式 + 交互式图表集成

## 背景

ML pipeline 当前只能对**有标签的**测试集做预测。标签计算（SL7 Proximity）需要未来 20 天的价格数据，导致最近 ~20 个交易日的 NDay5 信号被丢弃。

在实盘场景中，当天触发 NDay5 信号时必须立即给出买入/跳过建议——不可能等 20 天后才知道答案。模型推理只需要当天的特征值（RSI、VIX、breadth 等），不需要标签。

## 目标

1. 给 `generate_ml_markers()` 加推理模式：对最近无标签的 NDay5 信号日也构造特征并输出预测概率
2. 在交互式 K 线图（`show_chart.py --ml`）上展示这些推理信号，与有标签的回测信号区分显示
3. 更新环境日期配置，覆盖到 2026-06-12

## 涉及文件

| 文件 | 改动 |
|------|------|
| `scripts/show_chart.py` | `generate_ml_markers()` 增加推理分支 |
| `experiments/configs.py` | `ml-test` / `all` 环境 end 日期更新 |
| `src/interactive_chart.py` | ML 标记渲染适配 `PRED` 类型 |

## 实施方案

### Step 1: 更新 configs.py

将 `ml-test` 的 `end` 改为 `2026-06-12`，`all` 同步更新。

### Step 2: 改造 generate_ml_markers()

当前流程：
```
SPY 全量 → NDay5 信号 → SL7 打标签 → build_features → 80/20 切分 → 训练 → 预测测试集
```

改造后：
```
SPY 全量 → NDay5 信号 → SL7 打标签（能标的标）→ build_features
                                  ↓
                    有标签的信号 → 80/20 切分 → 训练模型
                                  ↓
                    用训练好的模型对两部分做预测:
                      1. 测试集（有标签）→ action=buy/skip, 标注 WIN/LOSS
                      2. 最近无标签的信号 → action=buy/skip, 标注 PRED
```

关键改动：
- 在 labeling 阶段保留无标签的信号日（不 dropna）
- 对无标签信号单独构造特征
- 用已训练模型预测，输出类型标记为 `PRED`（蓝色箭头），与回测的 `WIN`（绿）/ `LOSS`（红）区分

### Step 3: interactive_chart.py 适配

在 ML 标记渲染逻辑中识别 `PRED` 类型，用蓝色（#2196F3）箭头标注，tooltip 显示概率值。

### Step 4: 验证

```bash
python scripts/show_chart.py --env ml-test --ml --port 9870
```

预期：K 线图上能看到：
- 2019~2026-04 区间：绿色（WIN）/红色（LOSS）/灰色（SKIP）标记
- 2026-04~2026-06-12 区间：蓝色（PRED BUY）/灰色（PRED SKIP）标记
