"""
指标⑤ 成交量能 - OBV量能潮 + 量价确认 + 放量分级（Python 验证版）

译自通达信原始公式（docs/indicators/xxx/指标.txt 第 246-316 行）的可移植部分，
逻辑与同目录 ind5_obv.pine 严格对齐。

【翻译范围】
- OBV 量能潮 OBV3
- 量价同步确认 QS（量能与 3 日均价同时向上）
- 量均线 5/35/135
- 放量分级 FL1~FL4（突破 30/60/120/250 日量峰）

【已丢弃】原文“吸拉派落”依赖外部指标 XLPL，无法移植；STICKLINE 分色仅可视化。

【数据要求】需要成交量。项目 data/SPY_adjusted.csv 等含成交量列，可用。
"""
from typing import List, Optional

Num = Optional[float]


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
    """简单移动平均（通达信 MA）。"""
    n = len(values)
    out: List[Num] = [None] * n
    for i in range(n):
        if i < period - 1:
            continue
        out[i] = sum(values[i - period + 1:i + 1]) / period
    return out


def highest(values: List[float], period: int) -> List[Num]:
    """HHV：N 日最高。"""
    n = len(values)
    out: List[Num] = [None] * n
    for i in range(n):
        if i < period - 1:
            continue
        out[i] = max(values[i - period + 1:i + 1])
    return out


def calc_obv_tide(closes, volumes):
    """
    返回 (obv1, obv2, obv3)。
    VA = +VOL/-VOL/0 按涨跌；OBV1 = 累计和；OBV2 = EMA(OBV1,3)-MA(OBV1,9)；
    OBV3 = EMA(MAX(OBV2,0),3) 量能潮。
    """
    n = len(closes)
    va = [0.0] * n
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            va[i] = volumes[i]
        elif closes[i] < closes[i - 1]:
            va[i] = -volumes[i]
        else:
            va[i] = 0.0
    obv1 = []
    acc = 0.0
    for i in range(n):
        acc += va[i]
        obv1.append(acc)
    ema3 = ema(obv1, 3)
    ma9 = sma(obv1, 9)
    obv2: List[Num] = [None] * n
    for i in range(n):
        if ema3[i] is not None and ma9[i] is not None:
            obv2[i] = ema3[i] - ma9[i]
    obv2_pos = [(v if (v is not None and v > 0) else 0.0) for v in obv2]
    obv3 = ema(obv2_pos, 3)
    return obv1, obv2, obv3


def compute(closes, volumes):
    """
    输入 closes、volumes（等长正序），返回 dict：
      obv3 : 量能潮（float/None）
      qs   : 量价同步确认 bool（量能升 且 3日均价升）
      v5/v35/v135 : 量均线
      fl1/fl2/fl3/fl4 : 放量分级 bool（4 最强）
    """
    n = len(closes)
    _, _, obv3 = calc_obv_tide(closes, volumes)
    mac3 = sma(closes, 3)

    qs = [False] * n
    for i in range(1, n):
        if None in (obv3[i], obv3[i - 1], mac3[i], mac3[i - 1]):
            continue
        qs[i] = obv3[i] > obv3[i - 1] and mac3[i] > mac3[i - 1]

    v5 = sma(volumes, 5)
    v35 = sma(volumes, 35)
    v135 = sma(volumes, 135)

    h30 = highest(volumes, 30)
    h60 = highest(volumes, 60)
    h120 = highest(volumes, 120)
    h250 = highest(volumes, 250)
    fl1 = [False] * n
    fl2 = [False] * n
    fl3 = [False] * n
    fl4 = [False] * n
    for i in range(n):
        v = volumes[i]
        is250 = h250[i] is not None and v == h250[i]
        is120 = h120[i] is not None and v == h120[i]
        is60 = h60[i] is not None and v == h60[i]
        is30 = h30[i] is not None and v == h30[i]
        fl4[i] = is250
        fl3[i] = is120 and not is250
        fl2[i] = is60 and not is120 and not is250
        fl1[i] = is30 and not is60 and not is120 and not is250

    return {
        "obv3": obv3, "qs": qs,
        "v5": v5, "v35": v35, "v135": v135,
        "fl1": fl1, "fl2": fl2, "fl3": fl3, "fl4": fl4,
    }
