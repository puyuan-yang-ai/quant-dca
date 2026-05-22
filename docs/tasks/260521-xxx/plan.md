# 实施方案：MMA CRD Event Study

## 整体思路

三阶段递进：**数据准备 → 全扫描基线 → MMA 规则对照**。每阶段都产出可独立审核的中间产物，避免最后一锅端无法复盘。

```
Stage 1: 数据准备           (4-6 h)
  ├─ 行情数据 (SPY + DJIA)
  └─ 行星历表 (1928-2026 每日行星黄经)
            ↓
Stage 2: 全相位扫描基线      (6-8 h)
  ├─ 枚举所有行星对×相位组合 (~150 个)
  ├─ 标记每个组合的 CRD 窗口
  ├─ 计算反转频率 + 前瞻收益
  └─ 多重比较校正 → 显著性排序表
            ↓
Stage 3: MMA 规则对照验证    (4-6 h)
  ├─ 从 MMA 文献提取明确点名的 CRD 组合 (~10-20 个)
  ├─ 与 Stage 2 全扫描结果交叉对比
  ├─ 验证 MMA 的 "82% 反转频率" claim
  └─ 输出最终 report.md + Go/No-Go 决策
```

## 变更范围

| 文件 / 目录 | 操作 | 说明 |
|------------|------|------|
| `requirements.txt` | 修改 | 新增 `skyfield`、`scipy`、`statsmodels` |
| `scripts/fetch_djia_history.py` | 新增 | 拉取 DJIA 1928-2026 日线（Stooq 优先，Yahoo 镜像兜底） |
| `scripts/fetch_spy_long.py` | 新增 | 拉取 SPY 1993-2026 完整日线（Tiingo） |
| `scripts/compute_planetary_aspects.py` | 新增 | 一次性算出 1928-2026 全部相位事件，存 CSV |
| `data/djia_daily.csv` | 生成 | DJIA 日线 (1928-2026) |
| `data/spy_daily_long.csv` | 生成 | SPY 日线 (1993-2026) |
| `data/planetary_aspects.csv` | 生成 | 全相位事件表（约 5000-8000 行） |
| `src/event_study/__init__.py` | 新增 | 模块初始化 |
| `src/event_study/aspects.py` | 新增 | 相位计算核心逻辑（基于 Skyfield） |
| `src/event_study/windows.py` | 新增 | CRD 窗口标记 + 对照组采样 |
| `src/event_study/metrics.py` | 新增 | 反转频率 + 前瞻收益统计指标 |
| `src/event_study/stats.py` | 新增 | 假设检验 + 多重比较校正 |
| `docs/tasks/260521-xxx/notebooks/explore.ipynb` | 新增 | 探索 + 可视化 |
| `docs/tasks/260521-xxx/report.md` | 新增 | 最终统计报告与决策建议 |
| `docs/tasks/260521-xxx/note.md` | 滚动更新 | 每次工作的进展笔记 |

---

## Stage 1：数据准备

### 1.1 行情数据

**SPY (1993-2026)**：复用 `fetch_spy_for_mma.py` 模式，用 Tiingo API。新脚本 `scripts/fetch_spy_long.py`：

- 拉取范围：1993-01-01 → 今日
- 字段：date, open, high, low, close, volume
- 输出：`data/spy_daily_long.csv`

**DJIA (1928-2026)**：Tiingo 不支持指数本身（只支持 DIA ETF，1998 起），需用 Stooq 或 Yahoo 镜像。新脚本 `scripts/fetch_djia_history.py`：

- 优先源：Stooq (`https://stooq.com/q/d/?s=^dji&i=d`，CSV 直下，无需 API key)
- 兜底源：Yahoo Finance 镜像 (`^DJI`)
- 字段：date, open, high, low, close
- 输出：`data/djia_daily.csv`
- 数据质量检查：打印 1928-1962 / 1962-1993 / 1993- 三段的缺失率，标记需要警惕的时期

### 1.2 行星历表

新脚本 `scripts/compute_planetary_aspects.py`，一次性计算全部相位事件：

```python
from skyfield.api import load
from skyfield.framelib import ecliptic_frame

ts = load.timescale()
eph = load('de440.bsp')  # JPL 历表，首次运行自动下载 ~120MB

planets = ['Sun', 'Mercury', 'Venus', 'Mars', 'Jupiter',
           'Saturn', 'Uranus', 'Neptune', 'Pluto']
aspects = {0: 'conjunction', 60: 'sextile', 90: 'square',
           120: 'trine', 180: 'opposition'}
orb_days = 3  # MMA 标准 ±3 days orb
```

对每日 1928-2026：
1. 计算每颗行星的黄经
2. 对每对行星算角度差
3. 找出角度差等于上述 5 种相位（容差 ±1°）的精确时刻
4. 输出 `data/planetary_aspects.csv`：`date, planet1, planet2, aspect_type, exact_angle, orb_start, orb_end`

**预估事件量**：9 颗行星 × C(9,2)=36 对 × 5 种相位 ≈ 180 种事件，1928-2026 共 98 年，每种事件平均每年 1-30 次（视行星速度而定），总计约 5000-8000 个事件。

### 1.3 验收

- 抽样 5 个已知事件（如 2020-12-21 Jupiter-Saturn 合相）人工对照天文软件验证精度
- 检查 SPY / DJIA 数据无明显缺口、无异常值

---

## Stage 2：全相位扫描基线

### 2.1 CRD 窗口标记

`src/event_study/windows.py` 提供：

```python
def mark_crd_windows(aspect_events, orb_days=3):
    """对每个相位事件标记 [event_date - orb, event_date + orb] 窗口"""

def sample_control_windows(price_dates, crd_dates, n_samples, window_size):
    """随机采样不与任何 CRD 窗口重叠的对照窗口（block bootstrap）"""
```

### 2.2 反转频率统计（复现 MMA claim）

`src/event_study/metrics.py`：

```python
def reversal_rate(price_df, windows, lookback_days=10):
    """
    定义 "reversal": 窗口内出现 N-day 局部高点/低点，
    且后续 5 日内反向回撤 ≥ X%
    """
```

参数（先用 MMA 自己的定义，再做敏感性分析）：
- N-day 高低点：10 天（≈两周）
- 反转幅度：2%（先松后紧）

### 2.3 前瞻收益统计

```python
def forward_returns(price_df, event_dates, horizons=[1, 3, 5, 10, 20]):
    """计算每个 event_date 之后 N 天的累计收益"""
```

输出每个相位组合在每个 horizon 下的：mean, std, Sharpe, hit rate (正收益占比)。

### 2.4 假设检验 + 多重比较校正

`src/event_study/stats.py`：

- **两样本检验**：CRD 组 vs 对照组，对 (1) 反转频率用 Fisher's exact test；(2) 前瞻收益用 t-test（或更稳健的 Mann-Whitney U）
- **多重比较校正**：~180 个相位组合 × 5 个 horizon = 900 次比较，Bonferroni α=0.05/900 ≈ 5.6e-5；并行报告 Benjamini-Hochberg FDR 控制（更宽松但更有效）
- **时间稳定性检验**：把样本切成 1928-1970 / 1970-2000 / 2000-2026 三段，分别报告。如果只有某一段显著则提示警告。

### 2.5 产出

`docs/tasks/260521-xxx/notebooks/explore.ipynb` 中：

- **主表 1**：所有相位组合按 p-value 排序，标注是否通过 Bonferroni / FDR 校正
- **主表 2**：前 20 名最显著组合在 SPY / DJIA 上的反转频率、前瞻收益分布
- **可视化**：CRD 窗口前后 ±20 天的平均累计收益曲线，分相位类型叠加

---

## Stage 3：MMA 规则对照验证

### 3.1 MMA 文献规则提取

从手头的 MMA 资料中提取**明确点名**的 CRD 组合：

- `docs/tasks/260510-mma-free-docs/samples/` 下的样本周报与月报
- `docs/tasks/260510-mma-2026-annual-forecast/` 下的年度展望
- 本周周报 `5-Weekly-Stocks-260518-2yiil2.txt`
- `docs/tasks/260510-mma-free-docs/merriman-resources.md` 提到的资源链接（仅在前面三类不足时再补）

预期提取的关键规则（基于已读文献）：

- Venus-Saturn hard aspects（"buy a market falling into a hard aspect between Venus and Saturn"）
- Sun-Uranus conjunction（"sudden shock event"）
- Mars-Saturn 系列硬相位
- Jupiter-Saturn 合相（20 年大周期）
- Saturn-Neptune 合相

每条规则记录到 `docs/tasks/260521-xxx/mma_rules.md`，包含：规则描述、来源出处、预期市场反应方向。

### 3.2 交叉对比

把 Stage 2 的全扫描结果与 Stage 3.1 的 MMA 规则集做交叉：

- MMA 点名的组合在全扫描中**排名靠前**（前 20%）→ MMA 经验有效
- MMA 点名的组合**排名居中**（20%-80%）→ MMA 经验部分有效，但有 cherry-picking 嫌疑
- MMA 点名的组合**排名靠后**（后 20%）→ MMA 经验可能是后视偏差

### 3.3 复现 MMA 的 "82% 反转频率"

用 MMA 周报 CRDs 部分的精确定义（"midpoint date with ±3 days orb, expanding to ±6 days"）回测历史：

- 历史 CRD 列表来自 MMA 公开过的旧周报（如能找到）或自动生成
- 计算"两周新高/低 + 反转"的频率
- 与 MMA 自己 claim 的 82% / 90% 对比

### 3.4 最终决策

`docs/tasks/260521-xxx/report.md` 输出：

1. **核心结论**：基于 Stage 2 + Stage 3 数据，MMA 是否通过 Kill 检验（p ≤ 0.05 且年化超额 ≥ 3%）
2. **效应量量化**：通过的相位组合的具体 effect size 与置信区间
3. **时间稳健性**：在 3 个时段中是否一致
4. **Go/No-Go 建议**：明确给出后续是否进入 Step 2（规则化回测）
5. **如 Go**：列出哪些相位组合是真正应该纳入交易决策的，哪些可以忽略

---

## 执行顺序与人工审核点

| 步骤 | 内容 | 产出 | 人工审核 |
|------|------|------|---------|
| 1 | 写 `fetch_spy_long.py` + `fetch_djia_history.py` | 两个 CSV | 检查数据缺口、量纲 |
| 2 | 写 `compute_planetary_aspects.py`，运行生成相位表 | `planetary_aspects.csv` | 抽样验证天文精度 |
| 3 | 实现 `src/event_study/` 四个核心模块 | 单元测试通过 | code review |
| 4 | Notebook 跑 Stage 2 全扫描 | 显著性排序表 | **关键审核点**：是否有明显异常 |
| 5 | 提取 MMA 规则到 `mma_rules.md` | 规则文档 | **关键审核点**：规则提取是否准确 |
| 6 | Notebook 跑 Stage 3 交叉对比 | 对比图表 | — |
| 7 | 写 `report.md` 并做 Go/No-Go 决策 | 最终报告 | **关键审核点**：决策是否中肯 |

## 不在本 task 范围（后续可能扩展）

- 月相 / 太阳-月亮 reversal dates（短周期，单独研究）
- Heliocentric 视角的行星相位（MMA 主要用 geocentric）
- 单星座（如 Mars in Aries）的影响（属于"位置"而非"几何关系"）
- 个股层面的事件研究（先看大盘）
- 自动化的实时 CRD 报警系统（属于工程化阶段）
