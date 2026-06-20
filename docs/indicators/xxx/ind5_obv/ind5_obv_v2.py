"""
指标⑤ OBV量能潮 — 精简版 v2（Python 验证版）

与 ind5_obv_v2.pine 严格对齐。相比 v1：
  1. 量能潮归一化到 0-100（v1 是上亿量纲、不可读）。
  2. 删除满屏“量价同步 QS”噪声。
  3. 只保留两类高价值信号：量价背离（看涨/看跌）+ 天量 ③④。

【信号语义】
  - bull_div（底背离）：价格创新低但量能未创新低 → 卖压衰竭，看涨。
  - bear_div（顶背离）：价格创新高但量能未创新高 → 买力不足，看跌。
  - hv3 / hv4：当天成交量是近 120 / 250 日最大量（天量，常对应底/顶转折）。

【与 Pine 的对齐点】
  - OBV 振荡器 = EMA(OBV,3) - SMA(OBV,9)；归一化用最近 normLen 根 min/max。
  - 枢轴 = 左右各 pivLen 根的严格局部高/低点（确认滞后 pivLen 根）。
  - 背离信号标在“确认根”（枢轴 + pivLen），与 Pine 去掉 offset 后一致。

【关于前视偏差（重要）】
  枢轴判定需要其右侧 pivLen 根数据，所以"某天是高/低点"这件事，要等它之后再走
  pivLen 根才能确认。旧版把信号画回高/低点当天（offset=-pivLen），会造成"价格已
  跌了几天、却在之前高点冒出顶背标签"的事后诸葛亮假象（repaint）。现版本把可用信号
  （bull_div/bear_div）标在确认根，诚实反映"此刻才知道几天前形成了背离"，代价是比
  高/低点晚 pivLen 根。回测/实盘只能用 bull_div/bear_div，不可用 *_at_pivot。

【已知差异点】
  - 归一化窗口暖机：序列最前 normLen 根内 min/max 样本不足，数值与 TradingView
    的 ta.lowest/highest（要求满 normLen）略有出入，稳定后吻合。
"""
from typing import List, Optional

Num = Optional[float]


# =============================================================================
# 基础辅助
# =============================================================================
def ema(values: List[float], period: int) -> List[Num]:
    n = len(values)
    if n < period:
        return [None] * n
    out: List[Num] = [None] * n
    alpha = 2.0 / (period + 1)
    out[period - 1] = sum(values[:period]) / period
    for i in range(period, n):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def sma(values: List[float], period: int) -> List[Num]:
    n = len(values)
    out: List[Num] = [None] * n
    for i in range(n):
        if i < period - 1:
            continue
        out[i] = sum(values[i - period + 1:i + 1]) / period
    return out


def highest(values: List[float], period: int) -> List[Num]:
    n = len(values)
    out: List[Num] = [None] * n
    for i in range(n):
        if i < period - 1:
            continue
        out[i] = max(values[i - period + 1:i + 1])
    return out


def calc_obv_osc(closes, volumes):
    """OBV 振荡器 = EMA(累计OBV,3) - SMA(累计OBV,9)。"""
    n = len(closes)
    va = [0.0] * n
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            va[i] = volumes[i]
        elif closes[i] < closes[i - 1]:
            va[i] = -volumes[i]
    obv = []
    acc = 0.0
    for i in range(n):
        acc += va[i]
        obv.append(acc)
    e3 = ema(obv, 3)
    m9 = sma(obv, 9)
    osc: List[Num] = [None] * n
    for i in range(n):
        if e3[i] is not None and m9[i] is not None:
            osc[i] = e3[i] - m9[i]
    return osc


def normalize_0_100(series, length):
    """用最近 length 根的 min/max 把序列拉伸到 0-100（对齐 Pine 的 lowest/highest）。"""
    n = len(series)
    out: List[Num] = [None] * n
    for i in range(n):
        if series[i] is None:
            continue
        window = [series[j] for j in range(max(0, i - length + 1), i + 1)
                  if series[j] is not None]
        if not window:
            continue
        lo, hi = min(window), max(window)
        out[i] = 50.0 if hi == lo else (series[i] - lo) / (hi - lo) * 100.0
    return out


def find_pivot_lows(lows, pivlen):
    """严格局部低点索引：low[i] < 左右各 pivlen 根。确认滞后 pivlen 根。"""
    n = len(lows)
    out = []
    for i in range(pivlen, n - pivlen):
        v = lows[i]
        if all(v < lows[j] for j in range(i - pivlen, i)) and \
           all(v < lows[j] for j in range(i + 1, i + pivlen + 1)):
            out.append(i)
    return out


def find_pivot_highs(highs, pivlen):
    n = len(highs)
    out = []
    for i in range(pivlen, n - pivlen):
        v = highs[i]
        if all(v > highs[j] for j in range(i - pivlen, i)) and \
           all(v > highs[j] for j in range(i + 1, i + pivlen + 1)):
            out.append(i)
    return out


# =============================================================================
# 主入口
# =============================================================================
def compute(closes, highs, lows, volumes, norm_len=100, piv_len=5):
    """
    返回 dict（各为与输入等长的列表）：
      obv_norm : 归一化量能潮 0-100（float/None）
      bull_div : 底背离 bool（标在枢轴位置）
      bear_div : 顶背离 bool
      hv3 / hv4 : 天量 bool（近 120 / 250 日最大量）
    """
    n = len(closes)
    osc = calc_obv_osc(closes, volumes)
    obv_norm = normalize_0_100(osc, norm_len)

    bull_div = [False] * n
    bear_div = [False] * n
    # 枢轴(pivot)需左右各 piv_len 根确认，故信号在"枢轴 + piv_len"那根才可知。
    # 必须标注在确认根（confirm bar），否则就是前视偏差/事后诸葛亮（repaint）。
    bull_div_at_pivot = [False] * n   # 仅供画图参考：枢轴真实位置（含未来信息，勿用于回测）
    bear_div_at_pivot = [False] * n

    piv_lows = find_pivot_lows(lows, piv_len)
    for k in range(1, len(piv_lows)):
        ip, ic = piv_lows[k - 1], piv_lows[k]
        if obv_norm[ip] is None or obv_norm[ic] is None:
            continue
        # 价格新低 + 量能未新低 → 底背离
        if lows[ic] < lows[ip] and obv_norm[ic] > obv_norm[ip]:
            bull_div_at_pivot[ic] = True
            confirm = ic + piv_len
            if confirm < n:
                bull_div[confirm] = True

    piv_highs = find_pivot_highs(highs, piv_len)
    for k in range(1, len(piv_highs)):
        ip, ic = piv_highs[k - 1], piv_highs[k]
        if obv_norm[ip] is None or obv_norm[ic] is None:
            continue
        # 价格新高 + 量能未新高 → 顶背离
        if highs[ic] > highs[ip] and obv_norm[ic] < obv_norm[ip]:
            bear_div_at_pivot[ic] = True
            confirm = ic + piv_len
            if confirm < n:
                bear_div[confirm] = True

    h250 = highest(volumes, 250)
    h120 = highest(volumes, 120)
    hv4 = [False] * n
    hv3 = [False] * n
    for i in range(n):
        is250 = h250[i] is not None and volumes[i] == h250[i]
        is120 = h120[i] is not None and volumes[i] == h120[i]
        hv4[i] = is250
        hv3[i] = is120 and not is250

    return {
        "obv_norm": obv_norm,
        # 实盘/回测用这两个：标在确认根，无前视偏差，但比高/低点晚 piv_len 根
        "bull_div": bull_div, "bear_div": bear_div,
        # 仅供画图/研究参考：标在枢轴真实位置，含未来信息，禁止用于回测
        "bull_div_at_pivot": bull_div_at_pivot,
        "bear_div_at_pivot": bear_div_at_pivot,
        "hv3": hv3, "hv4": hv4,
    }
