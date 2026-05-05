# 实施方案：VIX / Put-Call Ratio / Safe Haven Demand

## 整体思路

三个指标实现模式一致：**获取数据 → 存 CSV → 做成 Entry → 参数搜索 → 全量比较 → 副图展示**。复用 Breadth 的技术路径（`fetch_breadth.py` + `BreadthEntry` + 副图面板）和 NDay 的两轮比较模式（先参数搜索 → 人工审核 → 再全量比较）。

三个都做成独立 Entry 接入 `compare_signals.py`，让数据说话，而非靠理论假设判断信号价值。

## 变更范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/fetch_sentiment.py` | 新增 | 一次性拉取 VIX / P/C Ratio / TLT，存 CSV |
| `data/vix_daily.csv` | 生成 | VIX 日线数据（date, close） |
| `data/put_call_ratio.csv` | 生成 | P/C Ratio 日线数据（date, pc_ratio, pc_ratio_5d） |
| `data/safe_haven.csv` | 生成 | Safe Haven 数据（date, spy_ret_20d, tlt_ret_20d, safe_haven） |
| `src/modules/entry.py` | 修改 | 新增 `VIXEntry`、`PutCallEntry`、`SafeHavenEntry` 三个类 |
| `scripts/compare_signals.py` | 修改 | 新增三个参数搜索模式 + 全量比较更新 |
| `src/interactive_chart.py` | 修改 | 新增 VIX 副图面板 |
| `scripts/show_chart.py` | 修改 | 加载 VIX 数据并传给图表 |

---

## 第一步：数据获取脚本

新建 `scripts/fetch_sentiment.py`，一次性获取三项数据：

```python
# VIX：直接下载收盘价
yfinance.download('^VIX', start='1993-01-01')  → data/vix_daily.csv
# 列：date, close

# Put/Call Ratio：下载后计算 5 日均值平滑
yfinance.download('^CPCE', start='2003-01-01') → data/put_call_ratio.csv
# 列：date, pc_ratio（原始值）, pc_ratio_5d（5日均值）

# Safe Haven Demand：TLT vs SPY 滚动收益差
yfinance.download('TLT', start='2002-01-01')   → data/safe_haven.csv
# 计算：20 日滚动收益率差 = tlt_ret_20d - spy_ret_20d
# 列：date, spy_ret_20d, tlt_ret_20d, safe_haven
```

输出格式参考 `data/sp500_breadth.csv`（CSV + DictReader 可读）。

## 第二步：三个 Entry 入场策略

在 `src/modules/entry.py` 新增三个类，模式与 `BreadthEntry` 一致（构造时预计算日期集合，运行时只查集合）：

### VIXEntry

```python
class VIXEntry:
    """VIX 恐慌驱动入场：VIX > threshold 时买入"""

    def __init__(self, vix_csv, threshold=30):
        self.threshold = threshold
        self._buy_dates = self._load_buy_dates(vix_csv, threshold)

    @staticmethod
    def _load_buy_dates(csv_path, threshold):
        # 读取 CSV，筛选 close > threshold 的日期
        ...

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False
```

### PutCallEntry

```python
class PutCallEntry:
    """Put/Call Ratio 逆向入场：P/C Ratio（5日均值）> threshold 时买入"""

    def __init__(self, pc_csv, threshold=1.0):
        self.threshold = threshold
        self._buy_dates = self._load_buy_dates(pc_csv, threshold)

    @staticmethod
    def _load_buy_dates(csv_path, threshold):
        # 读取 CSV，筛选 pc_ratio_5d > threshold 的日期
        ...
```

使用 5 日均值平滑以减少单日噪音。

### SafeHavenEntry

```python
class SafeHavenEntry:
    """避险需求入场：Safe Haven > threshold 时买入（TLT 跑赢 SPY = risk-off）"""

    def __init__(self, sh_csv, threshold=0.05):
        self.threshold = threshold
        self._buy_dates = self._load_buy_dates(sh_csv, threshold)

    @staticmethod
    def _load_buy_dates(csv_path, threshold):
        # 读取 CSV，筛选 safe_haven > threshold 的日期
        ...
```

## 第三步：参数搜索（第一轮）

在 `compare_signals.py` 中新增三个参数搜索模式，和 `--mode nday` 同一套路。每个模式遍历候选阈值，按**成本优势比**选最优参数。

### 搜索参数

| 指标 | 模式 | 搜索范围 | 逻辑 |
|------|------|---------|------|
| VIX | `--mode vix` | 30, 35, 40, 45, 50 | 阈值越高 = 越恐慌才买 = 信号越少但可能更便宜 |
| P/C Ratio | `--mode pcr` | 0.8, 0.9, 1.0, 1.1, 1.2 | 阈值越高 = 对冲越多才买 |
| Safe Haven | `--mode safehaven` | 0.02, 0.05, 0.08, 0.10 | 阈值越高 = 避险越强才买 |

### 运行命令

```bash
# 分三次运行，每次搜一个指标的最优阈值
python scripts/compare_signals.py --mode vix
python scripts/compare_signals.py --mode pcr
python scripts/compare_signals.py --mode safehaven
```

每次输出该指标各阈值在 5 个市场环境下的成本优势比，人工审核后确定最优参数。

### 搜索构建函数

```python
def build_entries_vix():
    """VIX 阈值参数搜索"""
    entries = {}
    for t in [30, 35, 40, 45, 50]:
        entries[f'VIX>{t}'] = {
            'label': f'VIX>{t}',
            'entry': VIXEntry(VIX_CSV, threshold=t),
        }
    return entries

def build_entries_pcr():
    """Put/Call Ratio 阈值参数搜索"""
    entries = {}
    for t in [0.8, 0.9, 1.0, 1.1, 1.2]:
        entries[f'PCR>{t}'] = {
            'label': f'P/C>{t}(5d)',
            'entry': PutCallEntry(PC_CSV, threshold=t),
        }
    return entries

def build_entries_safehaven():
    """Safe Haven 阈值参数搜索"""
    entries = {}
    for t in [0.02, 0.05, 0.08, 0.10]:
        entries[f'SH>{t}'] = {
            'label': f'SafeHaven>{t}',
            'entry': SafeHavenEntry(SH_CSV, threshold=t),
        }
    return entries
```

## 第四步：全量比较（第二轮）

人工审核三个指标的最优阈值后，用最优参数组成完整策略列表做全量比较：

```bash
python scripts/compare_signals.py --mode full \
    --best-nday 5 --best-vix V --best-pcr P --best-sh S
```

10 个策略全量对比：

| # | 策略 | 说明 |
|---|------|------|
| 1 | Unconditional | 无条件每天买 |
| 2 | EMAFilter | EMA 过滤 |
| 3 | NDayConfirm-5 | 连续 5 天低于 EMA |
| 4 | RSISignal | RSI v2 信号 |
| 5 | AND-NDay5+RSI | NDay5 且 RSI |
| 6 | OR-NDay5+RSI | NDay5 或 RSI |
| 7 | Breadth<20 | Breadth 恐慌买入 |
| 8 | VIX>**V** | VIX 恐慌买入（最优阈值） |
| 9 | PutCall>**P** | P/C Ratio 逆向买入（最优阈值） |
| 10 | SafeHaven>**S** | 避险需求买入（最优阈值） |

重点验证：
- VIX vs Breadth 的买入日期重叠度和成本优势差异
- P/C Ratio 是否提供了 Breadth/VIX 之外的独立信号
- Safe Haven 在 2022-2025 区间是否有效

## 第五步：VIX 副图指标

在 `interactive_chart.py` 中新增 VIX 面板（仅 VIX，P/C 和 Safe Haven 暂不加副图）：

- 蓝色折线（VIX 收盘价）
- 水平参考线：20（黄色虚线）、30（红色虚线）
- 区域填充：> 30 红色半透明（恐慌区）
- 加入 `allCharts` 数组实现时间轴和十字光标同步

在 `show_chart.py` 中加载 VIX 数据并传入图表。

## 第六步：文档更新

- 更新 CLAUDE.md（新增指标描述、脚本说明、数据文件列表）
- 撰写 report.md（参数搜索结果 + 全量比较分析）

## 执行顺序

| 步骤 | 内容 | 产出 | 人工审核 |
|------|------|------|---------|
| 1 | 编写 `fetch_sentiment.py`，获取三项数据 | 3 个 CSV 文件 | — |
| 2 | 新增三个 Entry 类 | entry.py 更新 | — |
| 3 | 修改 `compare_signals.py`，新增参数搜索模式 | 脚本更新 | — |
| 4 | 运行 VIX 参数搜索 `--mode vix` | VIX 各阈值成本优势对比 | 确定最优 VIX 阈值 |
| 5 | 运行 P/C Ratio 参数搜索 `--mode pcr` | PCR 各阈值成本优势对比 | 确定最优 PCR 阈值 |
| 6 | 运行 Safe Haven 参数搜索 `--mode safehaven` | SH 各阈值成本优势对比 | 确定最优 SH 阈值 |
| 7 | 运行全量比较 `--mode full` | 10 策略全量对比 + 排名 | — |
| 8 | 新增 VIX 副图面板 | interactive_chart.py 更新 | — |
| 9 | 更新文档 | CLAUDE.md + report.md | — |
