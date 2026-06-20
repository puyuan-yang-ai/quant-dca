"""
指标① 主力指标 - 买点雷达 + 卖点雷达（Python 验证版）

译自通达信原始公式（docs/indicators/xxx/指标.txt 第 24-36 行），
逻辑与同目录 ind1_radar.pine 严格对齐。

【翻译范围】
- 卖点雷达：6日RSI 从超买区下穿 85 → 顶部预警
- 买点雷达：7日RSI<20 且 13日RSI<25 且 上市足够久 且 AR人气<70

【已丢弃】“主力吸货 VAR7”为可视化分色、信号价值低，未翻译。

【已知差异点】
- VARD=BARSCOUNT(C) 用 bar 序号近似（i>50）；SPY/SMH 数据长，基本恒真。
- 阈值针对 A 股个股调过，用于 ETF 可能需重调。
"""
from typing import List, Optional

Num = Optional[float]


def rma(values: List[float], period: int) -> List[Num]:
    n = len(values)
    if n < period:
        return [None] * n
    out: List[Num] = [None] * n
    out[period - 1] = sum(values[:period]) / period
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return out


def calc_tdx_rsi(src, period):
    """通达信 RSI = RMA(MAX(src-prev,0),N)/RMA(ABS(src-prev),N)*100。"""
    n = len(src)
    up = [0.0] * n
    ab = [0.0] * n
    for i in range(1, n):
        ch = src[i] - src[i - 1]
        up[i] = max(ch, 0.0)
        ab[i] = abs(ch)
    ru = rma(up, period)
    ra = rma(ab, period)
    out: List[Num] = [None] * n
    for i in range(n):
        if ru[i] is None or ra[i] is None:
            continue
        out[i] = 100.0 if ra[i] == 0 else ru[i] / ra[i] * 100.0
    return out


def calc_ar(highs, opens, lows, period=26):
    """AR 人气指标 = SUM(H-O,N)/SUM(O-L,N)*100。"""
    n = len(highs)
    out: List[Num] = [None] * n
    for i in range(n):
        if i < period - 1:
            continue
        num = sum(highs[j] - opens[j] for j in range(i - period + 1, i + 1))
        den = sum(opens[j] - lows[j] for j in range(i - period + 1, i + 1))
        out[i] = None if den == 0 else num / den * 100.0
    return out


def compute(opens, highs, lows, closes):
    """
    输入四条等长序列（正序），返回 dict：
      sell_radar : 卖点雷达 bool（6日RSI 下穿 85）
      buy_radar  : 买点雷达 bool
      rsi6 / rsi13 / ar : 附带指标线，便于对数
    """
    n = len(closes)
    rsi6 = calc_tdx_rsi(closes, 6)
    rsi7 = calc_tdx_rsi(closes, 7)
    rsi13 = calc_tdx_rsi(closes, 13)
    ar = calc_ar(highs, opens, lows, 26)

    sell_radar = [False] * n
    for i in range(1, n):
        if rsi6[i] is None or rsi6[i - 1] is None:
            continue
        # CROSS(85, RSI1)：RSI1 下穿 85（昨>=85，今<85）
        if rsi6[i - 1] >= 85 and rsi6[i] < 85:
            sell_radar[i] = True

    buy_radar = [False] * n
    for i in range(n):
        if None in (rsi7[i], rsi13[i], ar[i]):
            continue
        if rsi7[i] < 20 and rsi13[i] < 25 and i > 50 and ar[i] < 70:
            buy_radar[i] = True

    return {
        "sell_radar": sell_radar, "buy_radar": buy_radar,
        "rsi6": rsi6, "rsi7": rsi7, "rsi13": rsi13, "ar": ar,
    }
