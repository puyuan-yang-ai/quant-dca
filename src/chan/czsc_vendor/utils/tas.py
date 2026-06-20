# -*- coding: utf-8 -*-
"""
均线/MACD 缓存（vendored 轻量版）

原 czsc.signals.tas 的 update_ma_cache / update_macd_cache 依赖 TA-Lib。
这里用纯 numpy 重写 SMA/EMA/MACD，避免引入 TA-Lib 重依赖，行为对齐：
把指标值写入每根 RawBar.cache[cache_key]，供二类买卖点等信号函数读取。

仅实现缠论二类买卖点会用到的 SMA / EMA，以及 MACD。如需 WMA/KAMA 等其它
均线类型，在 _ma() 里按需补充。
"""
import numpy as np


def _sma(close: np.ndarray, timeperiod: int) -> np.ndarray:
    """简单移动平均（前 timeperiod-1 个用累计均值回填，避免 NaN）"""
    out = np.full(len(close), np.nan)
    if len(close) == 0:
        return out
    csum = np.cumsum(close)
    for i in range(len(close)):
        if i + 1 >= timeperiod:
            out[i] = (csum[i] - (csum[i - timeperiod] if i - timeperiod >= 0 else 0)) / timeperiod
        else:
            out[i] = csum[i] / (i + 1)
    return out


def _ema(close: np.ndarray, timeperiod: int) -> np.ndarray:
    """指数移动平均"""
    out = np.full(len(close), np.nan)
    if len(close) == 0:
        return out
    alpha = 2.0 / (timeperiod + 1)
    out[0] = close[0]
    for i in range(1, len(close)):
        out[i] = alpha * close[i] + (1 - alpha) * out[i - 1]
    return out


def _ma(close: np.ndarray, timeperiod: int, ma_type: str) -> np.ndarray:
    ma_type = ma_type.upper()
    if ma_type == "EMA":
        return _ema(close, timeperiod)
    # 默认 SMA（czsc 二买默认即 SMA）
    return _sma(close, timeperiod)


def update_ma_cache(c, **kwargs):
    """更新均线缓存，把均线值写入每根 K 线 cache[cache_key]，返回 cache_key。

    :param c: CZSC 对象
    :param kwargs: ma_type（SMA/EMA），timeperiod
    """
    timeperiod = int(kwargs["timeperiod"])
    ma_type = kwargs.get("ma_type", "SMA").upper()
    cache_key = f"{ma_type}#{timeperiod}"

    if c.bars_raw[-1].cache and c.bars_raw[-1].cache.get(cache_key, None):
        return cache_key

    close = np.array([x.close for x in c.bars_raw], dtype=float)
    ma = _ma(close, timeperiod, ma_type)
    for i in range(len(close)):
        _c = dict(c.bars_raw[i].cache) if c.bars_raw[i].cache else dict()
        val = ma[i]
        _c.update({cache_key: float(val) if not np.isnan(val) else float(close[i])})
        c.bars_raw[i].cache = _c
    return cache_key


def update_macd_cache(c, **kwargs):
    """更新 MACD 缓存，把 {dif,dea,macd} 写入每根 K 线 cache[cache_key]，返回 cache_key。"""
    fastperiod = int(kwargs.get("fastperiod", 12))
    slowperiod = int(kwargs.get("slowperiod", 26))
    signalperiod = int(kwargs.get("signalperiod", 9))
    cache_key = f"MACD{fastperiod}#{slowperiod}#{signalperiod}"

    if c.bars_raw[-1].cache and c.bars_raw[-1].cache.get(cache_key, None):
        return cache_key

    close = np.array([x.close for x in c.bars_raw], dtype=float)
    dif = _ema(close, fastperiod) - _ema(close, slowperiod)
    dea = _ema(dif, signalperiod)
    macd = (dif - dea) * 2
    for i in range(len(close)):
        _c = dict(c.bars_raw[i].cache) if c.bars_raw[i].cache else dict()
        _c.update({cache_key: {
            "dif": float(dif[i]) if not np.isnan(dif[i]) else 0.0,
            "dea": float(dea[i]) if not np.isnan(dea[i]) else 0.0,
            "macd": float(macd[i]) if not np.isnan(macd[i]) else 0.0,
        }})
        c.bars_raw[i].cache = _c
    return cache_key
