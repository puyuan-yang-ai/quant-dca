# czsc 缠论接入 · 进度总览与规划（审核用）

> 单一总览文档，供逐项核对"已完成的工作"与审核"未来规划是否合理"。
> 详细设计见同目录：`plan.md`（主方案）、`architecture.md`（架构图）、
> `phase0-findings.md`（阶段0结论）、`buy-sell-points-guide.md`（买卖点函数指导）。
> 分支：`feat/czsc-chan`。

## 一、总进度

| 阶段 | 内容 | 状态 | 完成度 |
| --- | --- | --- | --- |
| 阶段 0 | 取源码 vendored + 跑通 + 三类买卖点验证 | ✅ 完成 | 100% |
| 阶段 1 | 可视化（缠论画到交互式图表） | ⬜ 未开始 | 0% |
| 阶段 2 | 信号接入回测引擎（ChanEntry） | ⬜ 未开始 | 0% |
| 阶段 3 | 纳入 ML Meta-Labeling（可选） | ⬜ 未开始 | 0% |

**当前整体进度：约 30%（4 阶段完成 1）。**

---

## 二、已完成（阶段 0）— 请逐项核对

### 2.1 新增的代码文件（实际存在，可核对）

```
src/chan/czsc_vendor/
├── __init__.py          # 出口：CZSC/RawBar/Freq/Mark/Direction/...
├── analyze.py           # 缠论核心：分型/笔识别（魔改主战场）
├── objects.py           # FX/BI/ZS/RawBar 数据结构
├── enum.py              # Freq/Mark/Direction/Operate 枚举
├── envs.py              # 环境变量（max_bi_num 等默认值）
├── signals_cxt.py       # 43 个 cxt_* 买卖点信号函数（三类买卖点已可用）
└── utils/
    ├── __init__.py
    ├── corr.py          # single_linear（objects 依赖）
    ├── sig.py           # get_zs_seq（中枢）/ get_sub_elements / create_single_signal
    └── tas.py           # 纯 numpy SMA/EMA/MACD（替代 TA-Lib，供二买/三买）

scripts/spike_czsc.py    # 阶段0验证脚本（可丢弃）
```

### 2.2 完成的事项清单

- [x] clone czsc v0.9.69（纯 Python）到临时目录，勘察依赖
- [x] 只拷缠论核心文件到 `src/chan/czsc_vendor/`，裁掉连接器/交易器/画图
- [x] 全部内部 import 改相对导入；echarts/plotly 画图改惰性导入；绕开 rs_czsc
- [x] 补 3 个轻量依赖（loguru/deprecated/tqdm）写入 `requirements.txt`
- [x] 写 spike 脚本，读 SPY 8400 根日线跑通
- [x] **修复 max_bi_num 截断**：默认 50 笔（首笔2024）→ 大值 667 笔（首笔1993）
- [x] **三类买卖点全部验证**（买+卖，全历史真实命中）
- [x] **纯 numpy 重写 tas.py**，让二买/三买（依赖均线）能跑且不引入 TA-Lib
- [x] 写《三类买卖点函数指导》`buy-sell-points-guide.md`
- [x] 写《阶段0结论》`phase0-findings.md`

### 2.3 实测验证结果（核对依据）

缠论四要素（SPY 8400 根日线，`max_bi_num=8400`）：分型 2967 / 笔 667 / 中枢 116 / 买卖点全类命中。

| 信号 | 首次 | 命中次数 |
| --- | --- | --- |
| 一买 / 一卖 | 1998-10 / 1993-05 | 229 / 1329 |
| 二买 / 二卖 | 1993-06 / 1993-05 | 1903 / 973 |
| 三买(纯笔/中枢) / 三卖(中枢) | 1993 / 1994 | 1194+872 / 280 |

> 自查命令：`python scripts/spike_czsc.py`

---

## 三、未来规划（请审核合理性）

### 阶段 1：可视化（先看对不对）— 下一步

**目标**：把分型/笔/中枢/买卖点画到现有交互式图表主图上，肉眼确认缠论算得对。

- [ ] **1.1** 新建 `src/chan/__init__.py`（chan 子包出口，对外暴露适配层）
- [ ] **1.2** 新建 `src/chan/viz_adapter.py`：
  - [ ] `build_chan_viz(bars)` → 统一入口，内部构 `CZSC(bars, max_bi_num=大值)`
  - [ ] 笔 `bi_list` → line series 端点列表 `[{time, value}, ...]`
  - [ ] 中枢 `get_zs_seq` → **半透明矩形框**（zg/zd 上下沿 + sdt/edt 左右沿）
  - [ ] 分型 `fx_list` → markers（顶分型▲/底分型▼）
  - [ ] 买卖点 → **按六类分桶**，每类不同颜色+文字标签（一买/二买/三买/一卖/二卖/三卖）
  - [ ] 输出一个 `chan_data` dict，键：`bi` / `zs` / `fx` / `bs_points`（bs_points 内按类别分组）
- [ ] **1.3** 改 `src/interactive_chart.py`：
  - [ ] `show_interactive_chart(...)` 加可选参数 `chan_data=None`（默认 None = 原行为不变）
  - [ ] `_build_html` 主图加缠论绘制：笔用 addLineSeries、中枢用矩形/baseline、分型与买卖点用 setMarkers（参照现有 breadth 背离连线写法）
- [ ] **1.4** 改 `scripts/show_chart.py`：加 `--chan` 开关，开启时调用 viz_adapter 并把 `chan_data` 传入
- [ ] **1.5** 跑通：`bash show_chart.sh --chan`，浏览器肉眼核对缠论位置
- **门槛**：肉眼对照 K 线确认分型/笔/中枢合理 → 才进阶段 2

### 阶段 2：信号接入回测引擎

**目标**：把缠论买卖点做成标准 Entry，参与买卖决策，并与现有信号公平比较。

- [ ] **2.1** 新建 `src/chan/signal_adapter.py`：买卖点 → **按类别分桶**的日期集合
  - [ ] 输出 `dates_buy1/buy2/buy3` 与 `dates_sell1/sell2/sell3`（六桶，不糊成一个），便于单独统计各类准确率/召回率
  - [ ] 解决"命中数百上千次"问题：同一段只取笔结束日 / 信号首次出现日
  - [ ] 防未来函数：只用已完成的笔
  - [ ] 选定买卖点口径（三买用纯笔 V230228 还是中枢 V230319，需定一套）
- [ ] **2.2** `src/modules/entry.py` 新增 `ChanEntry`（独立 Entry，遵循现有协议）
  - [ ] 支持指定使用哪些类别（如 `ChanEntry(kinds=['buy1','buy2'])`），默认全用
  - [ ] 各类别可单独评估准确率/召回率
- [ ] **2.3** 可选与 `AndEntry`/`OrEntry` 组合（如 ChanEntry + VIXEntry），但默认独立使用
- [ ] **2.4** 走标准化执行层（`FixedTiers(drops=())` + `FixedPyramid(market_shares=1)` + `NoTakeProfit()`）做信号质量比较
- [ ] **2.5** 用 `scripts/compare_signals.py` 比较缠论买点 vs RSI/Breadth/VIX
- **门槛**：缠论信号在回测里有合理、可解释的表现

### 阶段 3：纳入 ML Meta-Labeling（可选）

- [ ] **3.1** 把缠论买卖点作为 ML 候选信号源
- [ ] **3.2** 用 XGBoost meta-labeling 筛选缠论信号质量

---

## 四、关键决策记录

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 用 czsc 还是解密 .tn6 | czsc | .tn6 无公开算法、Linux 不可行、来路指标可能过拟合 |
| 版本 | 0.9.69 纯 Python | 要魔改核心算法，纯 Python 改完即生效，无需 Rust 编译 |
| 集成方式 | Vendored（复制源码进项目） | pip 装的改动会被覆盖、不进 git；vendored 可自由魔改 |
| 拷贝范围 | 只拷核心 + 按需补 | 裁掉连接器/交易器，二买/三买依赖按需补了 tas |
| 买卖点来源 | czsc 自带 cxt_* 信号函数 | 官方实现，非自推导 |
| 标的/级别 | 仅 SPY 日线 | 当前只有日线数据，不做多级别联立 |

## 五、风险与待定事项（审核重点）

| 项 | 说明 | 处理时机 |
| --- | --- | --- |
| **买卖点去重** | 信号每日重复命中数百上千次，不能当独立买点 | 阶段 2 必做 |
| **买卖点口径选择** | 同一类点有多个版本函数，结论不完全一致，需选一套 | 阶段 2 决策 |
| **未来函数风险** | 缠论笔会重画，回测须只用已完成的笔 | 阶段 2 必做 |
| **过拟合** | 缠论当候选信号之一，不神化（呼应 backtest-overfitting-fable） | 阶段 2 比较时 |
| **max_bi_num** | 必须传大值，否则历史笔截断 | 已知，适配层固定处理 |
| **高级信号未启用** | 多级别共振/盘中信号依赖 CzscSignals/pandas/sklearn 未 vendored | 暂不需要 |
| **魔改与上游脱节** | vendored 即放弃上游同步 | 已接受 |

## 六、已拍板的关键设计决策（2026-06-20 对齐）

1. **缠论买卖点单独做一个 Entry**（`ChanEntry`），不强制与别的信号 AND 组合；可选地用 `AndEntry`/`OrEntry` 组合，但默认独立。
2. **三类买卖点全用，且必须按类别区分**——代码层面与可视化层面都要能分清是一/二/三类买点还是卖点：
   - 代码：`_buy_dates` 不能糊成一个集合，要**按类别分桶**（如 `dates_buy1` / `dates_buy2` / `dates_buy3` 及对应卖点），便于后续**单独统计每类的准确率/召回率**。
   - 可视化：六类点用**不同颜色 + 不同文字标签**区分。
3. **中枢画法：半透明矩形框**（zg/zd 为上下沿，sdt/edt 为左右沿）。
