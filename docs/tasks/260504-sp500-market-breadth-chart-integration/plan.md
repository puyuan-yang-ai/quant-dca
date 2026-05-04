# 实施方案：S&P 500 Market Breadth 指标

## 整体分两步

1. **数据层**：编写预计算脚本，生成 Breadth CSV
2. **展示层**：在交互式图表中新增 Breadth 副图面板

---

## 第一步：预计算脚本

### 新增文件

`scripts/fetch_breadth.py` — 独立脚本，运行一次生成数据文件。

### 计算流程

```
获取成分股列表 → 批量拉取收盘价 → 计算 20 日 SMA → 逐日统计百分比 → 存 CSV
```

### 关键实现

1. **成分股列表**：从 Wikipedia 的 S&P 500 成分股页面获取（`pd.read_html`），提取 ticker 列表（约 503 只）
2. **批量拉取**：`yf.download(tickers, start='1993-01-01')`，取 `Close` 列。yfinance 支持批量请求，预计几分钟完成
3. **计算逻辑**：
   ```python
   sma20 = close_data.rolling(window=20).mean()
   above = (close_data > sma20).sum(axis=1)
   total = close_data.notna().sum(axis=1)
   breadth = (above / total * 100).round(2)
   ```
4. **输出文件**：`data/sp500_breadth.csv`，格式为 `date,breadth`（日期 + 百分比值 0-100）

### 幸存者偏差处理

- 分母使用当天实际有数据的股票数，而非固定 500
- 早期年份（1993-2000）有效股票数可能只有 300-350，但百分比仍然有意义
- 脚本运行时打印各年份的有效股票数，便于用户了解数据质量

### 依赖

- 新增 `yfinance` 和 `pandas` 依赖（需更新 `requirements.txt`）

---

## 第二步：图表集成

### 修改文件

- `src/interactive_chart.py` — 新增 Breadth 副图面板
- `scripts/show_chart.py` — 加载 Breadth CSV 并传入图表函数

### 图表结构

```
┌──────────────────────────┐
│  主图：SPY K线 + EMA      │  （现有，不变）
├──────────────────────────┤
│  副图1：RSI + 信号标记    │  （现有，不变）
├──────────────────────────┤
│  副图2：Market Breadth   │  ← 新增
│  (0-100 范围)            │
└──────────────────────────┘
```

### Breadth 副图样式（与原版 PineScript 对齐）

- Y 轴范围：0-120（留出标签空间）
- 水平线：0（红色虚线）、20（红色虚线）、50（灰色虚线）、80（绿色虚线）、100（绿色虚线）
- 填充区域：0-20 红色半透明、80-100 绿色半透明
- Breadth 曲线：白色或黑色实线（根据深浅色主题切换）

### 联动方式

参考现有主图与 RSI 副图的联动实现：
- 使用 Lightweight Charts 的 `createChart` 创建第三个图表实例
- 通过 `subscribeVisibleTimeRangeChange` 和 `subscribeCrosshairMove` 实现三图时间轴同步和十字光标联动

---

## 执行顺序

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | 编写 `scripts/fetch_breadth.py` | `data/sp500_breadth.csv` |
| 2 | 运行脚本，验证数据（检查极端值是否对应已知市场事件） | 数据验证通过 |
| 3 | 修改 `src/interactive_chart.py`，新增 Breadth 面板 | 图表代码 |
| 4 | 修改 `scripts/show_chart.py`，加载 Breadth 数据 | 数据接入 |
| 5 | `bash show_chart.sh` 验证效果 | 三图联动可视化 |

---

## 后续可能的扩展（本次不做）

- 按 GICS 行业拆分 12 条线
- 将 Breadth 作为信号接入 Entry 模块（如 Breadth < 20 时加大买入力度）
- 将 Breadth 用于自动市场环境分类（替代手动划分 bear/bull）
