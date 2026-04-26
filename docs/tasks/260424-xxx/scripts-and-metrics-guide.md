# 脚本体系与指标计算全解

---

## 1. 三个脚本的定位与关系

```
┌─────────────────────────────────────────────────────────┐
│                    日常使用                               │
│                                                         │
│  compare_signals.py          show_chart.sh              │
│  ┌───────────────┐           ┌───────────────┐          │
│  │ 快速筛选信号    │           │ 可视化验证     │          │
│  │ 多策略横向对比  │           │ 单策略深入查看  │          │
│  │ 输出：排名表格  │           │ 输出：交互式图表│          │
│  └───────────────┘           └───────────────┘          │
│         ↑                           ↑                    │
│         │ 找到最优信号后              │ 锁定最优组合后      │
│         ↓                           ↓                    │
│  ┌─────────────────────────────────────────┐            │
│  │         run_experiments.py               │            │
│  │         一次性参数空间遍历                  │            │
│  │         4 阶段逐步优化                     │            │
│  │         输出：各阶段最优组合                 │            │
│  └─────────────────────────────────────────┘            │
│                    偶尔使用                               │
└─────────────────────────────────────────────────────────┘
```

### 1.1 run_experiments.py — 一次性参数探索

**你的理解完全正确。** 这是一次性脚本，用于遍历参数空间，找到最优组合。

**工作方式**：4 阶段逐步锁定

```
第 1 阶段：遍历 3 种档口方案 × 5 个环境 → 锁定最优档口（1-A）
    ↓
第 2 阶段：遍历 5 种入场方案 × 5 个环境 → 锁定最优入场（2-C-5）
    ↓
第 3 阶段：遍历 3 种仓位方案 × 5 个环境 → 锁定最优仓位（3-B）
    ↓
第 4 阶段：遍历 4 种止盈方案 × 5 个环境 → 锁定最优止盈（4-0）
    ↓
最终组合：1-A + 2-C-5 + 3-B + 4-0
```

**什么时候需要重新跑**：
- 换了标的（SOXL → SPY）后，最优组合可能不同，需要重新跑
- 新增了模块（比如新的 Entry 类型），需要重新跑对应阶段
- 日常迭代**不需要**重新跑

**跑一次大约 85 次回测，耗时几十秒。**

### 1.2 compare_signals.py — 日常信号筛选

**日常使用频率最高的脚本。** 用于横向比较不同入场信号的择时质量。

**核心设计思想**：标准化执行层

```python
tiers     = FixedTiers(drops=())                        # 无限价单
position  = FixedPyramid(market_shares=1, limit_shares=(0,0,0))  # 固定买 1 股
take_profit = NoTakeProfit()                             # 不止盈
```

**为什么要标准化？** 因为如果执行层不同（比如 A 策略用限价单、B 策略不用），你分不清最终收益差异到底是"入场信号好"还是"执行参数好"。标准化执行层消除了这个变量，让对比纯粹聚焦在"信号质量"上。

**能比较多少个策略？** 没有限制。当前比较 7 个（5 个基础 + 2 个组合），想加几个加几个，只需在 `build_entries()` 里注册即可。

### 1.3 show_chart.sh — 可视化验证

**纯展示脚本。** 逻辑很简单：

```
1. 选一个策略（best 或 baseline）
2. 选一个环境（bear / bull / bear-bull / bull-bear / all）
3. 跑一次回测
4. 把结果传给 interactive_chart.py 生成 HTML
5. 启动 HTTP 服务，浏览器打开看图
```

**没有复杂逻辑**，不做策略比较、不做排名、不做参数搜索。它的价值在于让你**直观看到**买入/卖出发生在 K 线的什么位置，RSI 信号在什么时候触发。

---

## 2. compare_signals.py 详细流程

### 2.1 执行流程图

```
run_comparison()
│
├── 1. 加载配置
│   ├── 从 configs.py 读取 DATA_FILE, SMH_FILE, MARKET_ENVS
│   └── 定义标准化执行层（固定 1 股、无限价单、不止盈）
│
├── 2. 外层循环：遍历 5 个市场环境
│   │
│   ├── 加载该环境的 SPY 数据和 SMH 数据
│   ├── 构建所有 Entry 候选（调用 build_entries(data)）
│   │   └── 返回 7 个 Entry 实例（Unconditional, EMA, NDay3, NDay5, RSI, AND, OR）
│   │
│   └── 3. 内层循环：遍历 7 个 Entry 策略
│       │
│       ├── 组装 ComposableStrategy（标准化执行层 + 当前 Entry）
│       ├── 创建 BacktestEngine，执行 engine.run()
│       ├── 获取 metrics 字典（包含所有指标）
│       ├── 打印该策略在该环境下的表现（年化、回撤、Sharpe、成本优势、买入次数）
│       └── 存储结果到 results[entry_id][env_id] = metrics
│
├── 4. 计算加权综合评分
│   ├── 对每个策略，计算：加权 Sharpe = Σ(Sharpe × 环境权重) / Σ(权重)
│   │   └── 权重：bear 0.15, bull 0.15, bear-bull 0.35, bull-bear 0.35, all 0.00
│   └── 按加权 Sharpe 降序排名
│
└── 5. 输出结论
    └── 最高分是否为 NDayConfirm-5？是则"Baseline 仍最优"，否则提示升级
```

### 2.2 关键代码段解读

#### build_entries(data) — 注册候选策略

```python
# scripts/compare_signals.py:34-44
def build_entries(data):
    return {
        'Unconditional':  {'label': '无条件每日买入',     'entry': UnconditionalEntry()},
        'EMAFilter':      {'label': 'EMA 均线过滤',       'entry': EMAFilterEntry()},
        'NDayConfirm-3':  {'label': '连续3天低于EMA',     'entry': NDayConfirmEntry(n_days=3)},
        'NDayConfirm-5':  {'label': '连续5天低于EMA(best)', 'entry': NDayConfirmEntry(n_days=5)},
        'RSISignal':      {'label': 'RSI v2 信号',        'entry': RSISignalEntry(data)},
        'AND-NDay5+RSI':  {'label': 'NDay5 AND RSI',     'entry': CombinedAndEntry(data, n_days=5)},
        'OR-NDay5+RSI':   {'label': 'NDay5 OR RSI',      'entry': CombinedOrEntry(data, n_days=5)},
    }
```

**为什么传 data？** RSISignalEntry / CombinedAndEntry / CombinedOrEntry 需要在构造时预计算 RSI 信号（遍历全量 K 线数据计算 RSI v2 三事件信号），得到一个买入日期集合。运行时只需 O(1) 查表。

**为什么每个环境要重新构建？** 因为不同环境的数据范围不同，RSI 信号也不同。

#### 加权评分逻辑

```python
# scripts/compare_signals.py:102-117
for entry_id, entry_data in results.items():
    weighted_sharpe = 0
    for env_id, env_config in envs_for_score.items():  # 排除 all（权重=0）
        w = env_config['weight']
        weighted_sharpe += entry_data[env_id]['sharpe_ratio'] * w
    weighted_sharpe /= total_weight  # 归一化
```

权重分配的设计意图：
- bear-bull (0.35) 和 bull-bear (0.35) 权重最高 → 最重视跨周期表现
- bear (0.15) 和 bull (0.15) 次之 → 纯单边行情参考价值有限
- all (0.00) 不参与评分 → 32 年全量数据只做观察用

### 2.3 新增策略只需两步

```python
# 第一步：在 src/modules/entry.py 写一个新类
class MyNewEntry:
    def should_market_buy(self, context):
        return <你的条件>
    def should_place_limits(self, context):
        return False

# 第二步：在 build_entries() 里注册
'MyNew': {'label': '我的新策略', 'entry': MyNewEntry()},
```

跑 `python scripts/compare_signals.py` 就自动包含新策略的对比。

---

## 3. 指标计算的完整链路

### 3.1 计算发生在哪？

```
BacktestEngine.run()                    ← src/backtest_engine.py
│
├── 回测循环（逐日执行策略）
│   └── 统计交易数据：buy_count, sell_count, limit_orders_placed, ...
│
├── 调用 calc_all_metrics()             ← src/metrics.py:230
│   ├── 年化收益率     calc_annualized_return()
│   ├── 最大回撤       calc_max_drawdown()
│   ├── 回撤持续天数   calc_max_drawdown_duration()
│   ├── Sharpe        calc_sharpe_ratio()
│   ├── Sortino       calc_sortino_ratio()
│   ├── Calmar        calc_calmar_ratio()
│   ├── 成本优势比     calc_cost_advantage()
│   ├── 总收益率       (直接算)
│   └── 其他基础数据   (总投入、总股数、期间均价等)
│
└── 补充交易统计（engine 自己加）
    ├── soxl_shares, soxl_cost, soxl_final_value
    ├── smh_shares, smh_cost, smh_final_value
    ├── buy_count, sell_count
    ├── limit_orders_placed, limit_orders_filled, limit_fill_rate
    ├── tp_trigger_count, tp_expire_count
    ├── trade_log（用于图表标注）
    ├── ema_series（用于图表均线）
    └── rsi_v2（用于 RSI 副图）
```

### 3.2 计算了多少 vs 展示了多少

**calc_all_metrics() 计算了 15 个字段：**

| 字段 | 含义 | compare_signals 展示 | show_chart 展示 | run_experiments 展示 |
|------|------|:---:|:---:|:---:|
| `annualized_return` | 年化收益率 | 展示 | 展示 | 展示 |
| `max_drawdown` | 最大回撤 | 展示 | 展示 | 展示 |
| `sharpe_ratio` | Sharpe 比率 | 展示 | 展示 | 展示 |
| `cost_advantage` | 成本优势比 | 展示 | - | - |
| `calmar_ratio` | Calmar 比率 | - | - | 展示 |
| `sortino_ratio` | Sortino 比率 | - | - | - |
| `max_dd_duration` | 回撤持续天数 | - | - | - |
| `total_return` | 总收益率 | - | 展示 | 展示 |
| `total_cost` | 总投入 | - | - | - |
| `total_shares` | 总股数 | - | - | - |
| `final_value` | 最终市值 | - | - | - |
| `total_profit` | 总利润 | - | - | - |
| `avg_cost` | 平均成本 | - | - | - |
| `period_avg_price` | 期间均价 | - | - | - |
| `calendar_days` | 自然日天数 | - | - | - |

**BacktestEngine 额外补充了 ~15 个交易统计字段（buy_count、trade_log 等）。**

**结论：系统计算了约 30 个字段，但每个脚本只展示其中 4-5 个。** 大部分数据都算了，只是没打印出来。如果需要，随时可以在打印语句中加上。

### 3.3 各脚本的指标使用差异

| 脚本 | 展示的指标 | 排名依据 | 原因 |
|------|----------|---------|------|
| compare_signals.py | 年化、回撤、Sharpe、成本优势、买入次数 | 加权 Sharpe | 纯信号比较，关注择时质量 |
| run_experiments.py | 总收益率、Sharpe、回撤、Calmar | 加权 Sharpe（辅助 Calmar） | 完整策略比较，需兼顾风险 |
| show_chart.py | 总收益率、Sharpe、回撤、交易笔数 | 不排名 | 只展示一个策略，无需比较 |

---

## 4. 总结：日常工作流

```
场景 1：想试一个新的入场信号
  → 在 entry.py 写新类
  → 在 compare_signals.py 注册
  → python scripts/compare_signals.py        （10 秒出结果）

场景 2：想看某个策略在具体行情中的表现
  → bash show_chart.sh --env bear-bull       （浏览器看图）

场景 3：锁定了新的最优信号，想优化完整执行层参数
  → 更新 configs.py 中的 BEST_ENTRY
  → python run_experiments.py                （偶尔跑一次）

场景 4：换了标的（如 SOXL → SPY）
  → 改 configs.py 的 DATA_FILE
  → 先跑 compare_signals.py 看信号排名
  → 可选跑 run_experiments.py 重新优化执行层
```
