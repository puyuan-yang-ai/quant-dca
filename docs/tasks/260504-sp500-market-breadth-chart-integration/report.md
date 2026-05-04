# 实施报告：S&P 500 Market Breadth 指标接入

## 一、工作概述

将 TradingView PineScript 的 S&P 500 Market Breadth 指标移植为 Python 实现，并集成到项目的交互式图表系统中，作为第三个副图面板展示。

工作在 git worktree 中完成，分支 `feature/market-breadth`，产出 1 个 commit：

```
77649bc feat: add S&P 500 Market Breadth indicator
```

## 二、变更文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/fetch_breadth.py` | 新增 | 预计算脚本，拉取 S&P 500 成分股数据并计算 Breadth |
| `data/sp500_breadth.csv` | 新增 | 预计算结果（8370 个交易日，1993-02-01 ~ 2026-05-01） |
| `src/interactive_chart.py` | 修改 | 新增 Breadth 副图面板，重构多图同步逻辑 |
| `scripts/show_chart.py` | 修改 | 新增 `load_breadth()` 函数，加载 CSV 并传入图表 |
| `requirements.txt` | 修改 | 新增 `yfinance>=0.2.0`、`pandas>=1.5.0` |

变更量：5 files, +8658, -39

## 三、各模块实现细节

### 3.1 预计算脚本 `scripts/fetch_breadth.py`

**用法：**
```bash
python scripts/fetch_breadth.py
```

**流程：**
1. 从 Wikipedia 获取当前 S&P 500 成分股列表（约 503 只）
2. 通过 yfinance 批量拉取所有股票从 1993-01-01 至今的日频收盘价
3. 计算每只股票的 20 日 SMA
4. 逐日统计"收盘价 > 20 日 SMA"的比例（0-100%）
5. 输出到 `data/sp500_breadth.csv`（date, breadth 两列）

**幸存者偏差处理：**
- 分母使用当天实际有数据的股票数（而非固定 500）
- 1993 年约 260 只有效，逐年递增至 2026 年约 492 只
- 脚本运行时打印各年份有效股票数，便于评估数据质量

**运行耗时：** 约 5-8 分钟（主要是 yfinance 下载 500 只股票的历史数据）

**遇到的问题及解决：**
1. Wikipedia 返回 HTTP 403 → 添加 User-Agent 请求头
2. `print_yearly_stats()` 中 `close_df` 与 `breadth` 索引长度不一致（因为 breadth 去掉了前 20 天 SMA 预热期）→ 用 `close_df.loc[breadth.index]` 对齐

### 3.2 图表集成 `src/interactive_chart.py`

**主要改动：**

1. **函数签名扩展**：`show_interactive_chart()` 和 `_build_html()` 新增 `breadth_data` 参数

2. **高度分配**：根据面板数量动态调整
   - 三面板（主图 + RSI + Breadth）：50% / 25% / 25%
   - 两面板（主图 + RSI 或 Breadth）：70% / 30%
   - 单面板：100%

3. **Breadth 副图样式**：
   - 曲线颜色：`#2196F3`（蓝色），lineWidth: 2
   - 参考线：20（红色虚线）、50（灰色点线）、80（绿色虚线）
   - 背景填充：使用 Lightweight Charts 的 `addBaselineSeries`，以 50 为基准线，上方绿色渐变、下方红色渐变

4. **多图同步机制重构**：
   - 原实现：主图和 RSI 之间硬编码的双向同步
   - 新实现：集中式 `allCharts` 数组 + `syncTimeRange()` / `syncCrosshair()` 函数，任意数量的图表自动两两同步
   - 当只有 Breadth 无 RSI 时，退回到简单的双向同步

5. **主题适配**：`applyTheme()` 中新增 `breadthChart.applyOptions()`

### 3.3 数据接入 `scripts/show_chart.py`

新增 `load_breadth(filepath, start_date, end_date)` 函数：
- 读取 CSV，按环境日期范围过滤
- 转换为 Lightweight Charts 需要的 `[{time, value}]` 格式
- CSV 不存在时打印提示并返回 None（图表正常显示，只是没有 Breadth 面板）

## 四、数据验证

### 4.1 各年份 Breadth 统计

```
  年份   有效股票数  Breadth均值    最低    最高
--------------------------------------------------
  1993       260        56.1    27.4    81.8
  1994       274        50.3     5.5    82.8
  ...
  2000       343        54.4    25.1    82.9   ← 互联网泡沫
  ...
  2008       406        43.2     0.0    89.1   ← 金融危机
  2009       409        61.1     3.7    96.6   ← 危机后反弹
  ...
  2020       477        59.0     0.2    98.5   ← COVID 闪崩 + V型反弹
  2021       483        60.0    10.1    90.9
  2022       485        48.3     1.6    94.0   ← 熊市
  2023       487        55.9     6.0    91.8
  2024       490        57.4     8.0    91.6
  2025       491        54.5     2.2    89.6
```

### 4.2 极端值交叉验证

| 市场事件 | 年份 | Breadth 最低值 | 是否符合预期 |
|---------|------|--------------|------------|
| 金融危机 | 2008 | 0.0% | 符合：几乎所有股票跌破 20MA |
| COVID 闪崩 | 2020 | 0.2% | 符合：极端恐慌 |
| 2022 熊市 | 2022 | 1.6% | 符合：深度恐慌 |
| 2009 反弹 | 2009 | 最高 96.6% | 符合：全面反弹 |
| 2020 V 型反弹 | 2020 | 最高 98.5% | 符合：几乎所有股票反弹 |
| 2013 牛市 | 2013 | 均值 65.5% | 符合：持续强势 |
| 2017 牛市 | 2017 | 最低 27.0% | 符合：回调温和 |

结论：指标在所有已知重大市场事件中表现符合预期，极端值（<5% 和 >95%）与历史恐慌/狂热时段高度吻合。

### 4.3 端到端运行验证

```bash
# bear-bull 环境
$ python scripts/show_chart.py --env bear-bull
策略：最优组合（1-A+2-C-5+3-B+4-0）
环境：熊转牛（2022-01-01 ~ 2024-07-08）
Breadth 数据：630 个交易日          ← 成功加载
执行回测...
总收益率：+38.71%  夏普：0.14  最大回撤：10.4%
交易记录：137 笔
图表已更新，刷新浏览器即可查看最新结果
```

- 三图面板正确生成（主图 + RSI + Breadth）
- HTML 中包含 `breadth-chart` div、`breadthChart` 实例、`allCharts` 同步数组
- `all` 环境下 Breadth 数据覆盖 8248 个交易日

## 五、最终图表结构

```
┌──────────────────────────────────────┐
│  主图（50vh）：SPY K线 + EMA 均线    │
│  + 买入/止盈交易标记                  │
├──────────────────────────────────────┤
│  副图1（25vh）：RSI(14) + EMA(5)     │
│  + B/B+/B++/S/S+/S++ 信号标记        │
├──────────────────────────────────────┤
│  副图2（25vh）：Market Breadth       │
│  蓝色曲线，20/50/80 参考线           │
│  上方绿色填充，下方红色填充           │
└──────────────────────────────────────┘
三图时间轴同步 + 十字光标联动
深色/浅色主题切换
```

## 六、当前状态

- 分支 `feature/market-breadth` 已提交，尚未合并到 master
- Worktree 位于 `.worktrees/market-breadth`
- 功能完整可用，等待用户确认合并方式

## 七、后续扩展方向（本次未实施）

1. **行业板块拆分**：按 GICS 行业分组计算 12 条独立的 Breadth 曲线
2. **策略接入**：将 Breadth 作为 Entry 模块的增强信号（如 Breadth < 20 时加大买入力度）
3. **自动环境分类**：用 Breadth 阈值替代手动划分 bear/bull 市场环境
4. **数据自动更新**：定期运行 `fetch_breadth.py` 追加增量数据
