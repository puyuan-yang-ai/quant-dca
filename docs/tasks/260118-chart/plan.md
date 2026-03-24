# DCA 策略收益对比图表实施方案

## 整体思路

在现有回测框架基础上，新增图表绑制模块。核心改动是让 `backtest.py` 返回每日收益率序列，然后由新模块 `chart.py` 绘图并保存。

## 改动范围

| 文件 | 操作 | 说明 |
|-----|------|------|
| `src/backtest.py` | 修改 | 返回每日收益率数据 |
| `src/chart.py` | 新建 | 图表绘制模块 |
| `main.py` | 修改 | 调用绘图函数 |
| `requirements.txt` | 修改 | 添加 matplotlib |

## 实施步骤

### Step 1: 修改 backtest.py

在 `run_backtest()` 中新增两个返回字段：

```
daily_dca_returns: List[float]   # DCA 策略每日收益率
daily_hold_returns: List[float]  # SOXL 持有每日收益率
dates: List[str]                 # 日期序列
max_drawdown_date: str           # 最大回撤发生日期
```

计算逻辑：
- DCA 收益率 = (当日市值 - 累计成本) / 累计成本
- 持有收益率 = (当日收盘价 - 首日收盘价) / 首日收盘价

### Step 2: 新建 src/chart.py

核心函数：`save_chart(result, output_dir)`

功能：
1. 绑制两条收益率曲线（DCA 浅蓝 / SOXL 淡红）
2. 添加标题、图例、回测区间
3. 标注最终收益率和最大回撤点
4. X 轴日期自动间隔
5. 保存为 PNG（文件名：时间戳格式）

技术要点：
- 使用 `matplotlib.dates.AutoDateLocator` 自动间隔 X 轴
- 中文显示：设置 `plt.rcParams['font.sans-serif']`

### Step 3: 修改 main.py

在回测完成后调用：
```python
from src.chart import save_chart
save_chart(result, 'output/')
```

### Step 4: 更新 requirements.txt

添加：`matplotlib>=3.5.0`

## 文件结构

```
quant-dca/
├── src/
│   ├── backtest.py   # [修改] 增加每日收益率返回
│   └── chart.py      # [新建] 图表绘制
├── main.py           # [修改] 调用绘图
├── output/           # [自动创建] 图片输出目录
└── requirements.txt  # [修改] 添加 matplotlib
```

## 验收清单

- [ ] backtest.py 返回每日收益率数据
- [ ] chart.py 正确绘制双曲线
- [ ] 颜色：DCA 浅蓝 / SOXL 淡红
- [ ] 显示标题、图例、回测区间
- [ ] 标注最终收益率和最大回撤点
- [ ] X 轴日期无重叠
- [ ] 图片保存到 output/，文件名为时间戳

