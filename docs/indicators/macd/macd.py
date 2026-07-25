# -*- coding: utf-8 -*-
"""
MACD 指标（与 TradingView / Pine 的口径对齐）

口径基准：docs/indicators/macd/macd.pine
    DIF (MACD line) = EMA(close, 12) - EMA(close, 26)
    DEA (signal)    = EMA(DIF, 9)
    hist            = DIF - DEA          # 单倍，**不是** ×2

EMA 采用 TradingView ta.ema 的口径：alpha = 2/(period+1)，**首值用第一个数据点初始化**
（递归从第 0 根开始，等价于 pandas ewm(adjust=False)）。

注意：本模块的 _ema 与 src/indicators.calc_ema 不同——后者用 SMA 初始化、前 period-1 个值为 None，
两者仅在预热段有差异，收敛后一致。回抽判定要求逐根对齐 TradingView，故此处单独实现首值初始化版本。

切勿套用 src/chan/czsc_vendor/utils/tas.py 的 MACD：它的 hist = (DIF-DEA)×2，口径不符。
"""
from typing import List, Sequence, Tuple


def _ema(values: Sequence[float], period: int) -> List[float]:
    """首值初始化的递归 EMA（对齐 TradingView ta.ema / pandas ewm(adjust=False)）。

    :param values: 数值序列（按时间正序）
    :param period: EMA 周期
    :return: 与 values 等长的 EMA 列表
    """
    n = len(values)
    if n == 0:
        return []
    alpha = 2.0 / (period + 1)
    out = [0.0] * n
    out[0] = float(values[0])
    for i in range(1, n):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def calc_macd(
    closes: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[List[float], List[float], List[float]]:
    """计算 MACD，返回 (dif, dea, hist) 三个与 closes 等长的列表。

    - dif  = EMA(close, fast) - EMA(close, slow)   # 快线（TradingView 的 MACD line）
    - dea  = EMA(dif, signal)                       # 慢线（TradingView 的 Signal line）
    - hist = dif - dea                              # 柱状图（单倍口径）

    :param closes: 收盘价序列（按时间正序）
    :param fast: 快线周期，默认 12
    :param slow: 慢线周期，默认 26
    :param signal: 信号线周期，默认 9
    :return: (dif, dea, hist)
    """
    n = len(closes)
    if n == 0:
        return [], [], []

    closes = [float(x) for x in closes]
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    dif = [ema_fast[i] - ema_slow[i] for i in range(n)]
    dea = _ema(dif, signal)
    hist = [dif[i] - dea[i] for i in range(n)]
    return dif, dea, hist
