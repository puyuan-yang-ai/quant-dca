# SPY 回测方案

## 1. 目标

用现有 DCA 回测系统跑 SPY（标普 500 ETF）日线回测，验证策略在大盘指数上的表现。

---

## 2. 需要修改的文件

### 2.1 必须改（1 个文件）

**`experiments/configs.py`** — 核心配置文件

| 行号 | 当前值 | 改为 | 原因 |
|------|--------|------|------|
| 22 | `DATA_FILE = 'data/SOXL_adjusted.csv'` | `DATA_FILE = 'data/SPY_adjusted.csv'` | 切换主标的为 SPY |
| 19 | `'all': {'start': '2010-03-12', ...}` | `'all': {'start': '1993-01-29', ...}` | SPY 上市日为 1993-01-29，拉长全量数据范围 |

> **SMH_FILE 不需要改。** 引擎对 `smh_data` 的处理是安全的：即使 SPY 回测期间 SMH 数据存在，分流金额为 0（因为 BEST_TP = NoTakeProfit，不会触发止盈卖出），所以 SMH 相关指标全部为 0，不影响结果。

### 2.2 建议改（美观，非必须）

**`scripts/show_chart.py`** 第 78 行

```python
# 当前
title = f"SOXL DCA [{strat_config['label']}] — ..."
# 改为
title = f"SPY DCA [{strat_config['label']}] — ..."
```

### 2.3 不需要改的文件

| 文件 | 原因 |
|------|------|
| `src/data_loader.py` | 完全通用，读取中文列名 CSV，不绑定任何 ticker |
| `src/backtest_engine.py` | 变量名虽写着 soxl/smh，但逻辑完全通用 |
| `src/strategies/composable.py` | 纯抽象策略，无 ticker 依赖 |
| `src/portfolio.py` | 方法名 `buy_soxl` 等仅是命名，逻辑通用 |
| `experiments/runner.py` | 从 `configs.py` 导入路径，无硬编码 |
| `scripts/compare_signals.py` | 同上 |
| `show_chart.sh` | 纯壳脚本，无 ticker 逻辑 |

---

## 3. 市场环境日期说明

现有 5 个市场环境的日期范围是按 SOXL/半导体周期划分的（2022 熊、2022.10 牛启动等）。**这些日期对 SPY 同样有意义**，因为：

- 2022 年：美联储加息，标普同样经历熊市（SPY 从 ~480 跌到 ~350）
- 2022.10 ~ 2024.07：标普同样走牛（~350 回到 ~550+）
- 2024.07 ~ 2025.04：标普高位震荡/回调

所以不需要重新划分环境日期，直接复用即可。唯一改的是 `all` 环境的起始日，因为 SPY 数据从 1993 年开始。

---

## 4. 运行流程

### 方案 A：快速验证（推荐先跑这个）

```bash
# 第一步：信号策略比较（~10 秒）
python scripts/compare_signals.py
```

**执行流程：**
1. 从 `configs.py` 读取 `DATA_FILE`（此时已指向 SPY）和 `SMH_FILE`
2. 对 5 个市场环境 × 5 个 Entry 策略 = 25 次回测
3. 每次回测：用标准化执行层（市价买 1 股、无限价单、不止盈）
4. 输出：各策略在各环境下的年化收益/最大回撤/Sharpe + 加权排名
5. **预期**：因为 SPY 波动率远低于 SOXL（~18% vs ~60%+），所以：
   - 年化收益率会低很多（SPY 长期约 10%/年 vs SOXL 杠杆放大）
   - 最大回撤也会小很多（SPY 2022 熊市约 -25% vs SOXL -80%+）
   - Sharpe 比较才是重点——哪个 Entry 在 SPY 上择时最好

### 方案 B：交互式图表

```bash
# 查看熊转牛环境 + best 策略
bash show_chart.sh --env bear-bull

# 查看全量数据
bash show_chart.sh --env all
```

**执行流程：**
1. 加载 SPY 数据 + SMH 数据
2. 构建 ComposableStrategy（best 或 baseline）
3. `BacktestEngine.run()` 执行回测，每日循环：
   - 计算 EMA(20)、偏离度、连续低于/高于 EMA 天数
   - 检查止盈挂单（NoTakeProfit 下无挂单）
   - 策略 `on_day(ctx)` 返回买入指令
   - 执行买入（市价单 + 限价单看是否触及）
   - 记录组合价值、交易日志
4. 计算 Sharpe / Calmar / 最大回撤 / 年化收益
5. 启动 HTTP 服务，浏览器展示 K 线 + RSI 副图
6. **预期**：SPY 的 K 线比 SOXL 平滑很多，买入箭头更稀疏（NDayConfirm-5 在 SPY 上可能过滤掉更多交易日）

### 方案 C：完整 4 阶段实验（耗时较长）

```bash
python run_experiments.py
```

**执行流程：**
1. 第一阶段（档口）：3 个档口方案 × 5 个环境 = 15 次回测
2. 第二阶段（入场）：5 个 Entry × 5 个环境 = 25 次回测（锁定最优档口）
3. 第三阶段（仓位）：3 个 Position × 5 个环境 = 15 次回测
4. 第四阶段（止盈）：4 个 TP × 5 个环境 = 20 次回测
5. 回归验证：baseline vs optimized × 5 环境 = 10 次回测
6. 总计 ~85 次回测
7. **预期**：最优组合可能与 SOXL 不同——SPY 波动率低，限价单档位 2%/5%/10% 可能很少触及（SPY 单日跌 5%+ 极罕见），波动率动态档口可能反而更好

---

## 5. 预期结果对比

| 指标 | SOXL（预期） | SPY（预期） | 原因 |
|------|-------------|------------|------|
| 年化收益 | 高（杠杆放大） | ~8-12% | SPY 长期年化约 10% |
| 最大回撤 | 60-80%+ | 20-35% | SPY 2022 熊市约 -25% |
| Sharpe | 看策略 | 看策略 | 可直接比较策略质量 |
| 市价单买入次数 | 多 | 更多/更少取决于 Entry | NDayConfirm 在 SPY 上可能很不同 |
| 限价单成交率 | 中等 | 很低 | SPY 单日跌 5%/10% 极罕见 |
| 止盈触发 | 取决于 TP 模块 | 0 | BEST_TP = NoTakeProfit |

---

## 6. 注意事项

1. **限价单档位可能形同虚设**：SOXL 的固定档位是 2%/5%/10%，对 SOXL（日均波动 3-5%）合理。但 SPY 日均波动约 0.8%，单日跌 5% 以上极罕见（仅在 2020.03、2008 等极端日出现）。所以限价单基本不会成交。
2. **这不影响回测有效性**：如果用 BEST 策略（NDayConfirm-5 + AdaptivePyramid），市价单是主要买入渠道，限价单成交率低只是说明这个参数对 SPY 不敏感。
3. **后续优化方向**：如果想针对 SPY 优化，可以把档位缩小到 0.5%/1%/2%，但那是后续的事，先跑一遍看看。

---

## 7. 推荐执行顺序

```
1. 修改 experiments/configs.py（2 行代码）
2. 修改 scripts/show_chart.py 标题（1 行，可选）
3. python scripts/compare_signals.py        ← 先跑这个，10 秒出结果
4. bash show_chart.sh --env bear-bull       ← 看图
5. python run_experiments.py                ← 完整实验（可选）
```

改动最小化，2-3 行代码即可跑通。
