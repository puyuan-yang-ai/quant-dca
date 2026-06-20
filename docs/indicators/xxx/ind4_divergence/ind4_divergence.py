"""
指标④ 超买超卖 - 三重背离 + RSI 超卖买点（Python 验证版）

译自通达信原始公式（docs/indicators/xxx/指标.txt 第 191-244 行），
逻辑与同目录 ind4_divergence.pine 严格对齐，用于在 TradingView 验证通过后接入量化系统。

【设计约定】
- 纯函数、list 入 list 出，与 src/indicators/__init__.py 风格一致；本模块自带辅助函数，
  暂不依赖 src/，保持独立可移植。验证通过后再考虑合入 src。
- 数据不足处用 None 占位，保持与价格序列等长。

【与 Pine 版的对齐点】
- MACD(12,26,9)：DIF=EMA(C,12)-EMA(C,26)，DEA=EMA(DIF,9)。
- KDJ(9,3,3)：RSV 用 9 日随机值，K=RMA(RSV,3)，D=RMA(K,3)。等价通达信 SMA(x,3,1)。
- RSI 双线(6,12)：通达信 RSI = RMA(MAX(C-LC,0),N)/RMA(ABS(C-LC),N)*100。
- 背离判断：在“相邻两次金叉/死叉”之间比较价格与指标高低，完全照搬原公式。

【已知差异点】
- EMA/RMA 的初始化方式（首值用 SMA seed）与 TradingView 内置略有出入，
  前若干根 K 线数值会有暖机误差，稳定后吻合。验证时忽略序列最前段。
"""
from typing import List, Optional

Num = Optional[float]


# =============================================================================
# 基础辅助函数（自带，保持模块独立）
# =============================================================================
def ema(values: List[float], period: int) -> List[Num]:
    """EMA，首值用 period 个 SMA 初始化，前 period-1 个为 None。"""
    n = len(values)
    if n < period:
        return [None] * n
    out: List[Num] = [None] * n
    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    for i in range(period, n):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def rma(values: List[float], period: int) -> List[Num]:
    """
    Wilder 平滑（RMA），等价通达信 SMA(X, period, 1)。
    首值用 period 个 SMA 初始化，之后 prev*(period-1)/period + x/period。
    """
    n = len(values)
    if n < period:
        return [None] * n
    out: List[Num] = [None] * n
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return out


def stoch_rsv(closes, highs, lows, period: int) -> List[Num]:
    """随机值 RSV = (C - LLV(L,n)) / (HHV(H,n) - LLV(L,n)) * 100。"""
    n = len(closes)
    out: List[Num] = [None] * n
    for i in range(n):
        if i < period - 1:
            continue
        hh = max(highs[i - period + 1:i + 1])
        ll = min(lows[i - period + 1:i + 1])
        rng = hh - ll
        out[i] = 0.0 if rng == 0 else (closes[i] - ll) / rng * 100.0
    return out


# =============================================================================
# 指标线计算
# =============================================================================
def calc_macd(closes, fast=12, slow=26, signal=9):
    """返回 (dif, dea)，均与 closes 等长。"""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    dif_clean = [v for v in dif if v is not None]
    dea_clean = ema(dif_clean, signal)
    # 把 dea 对齐回原长度
    dea: List[Num] = [None] * len(closes)
    offset = len(closes) - len(dif_clean)
    for i, v in enumerate(dea_clean):
        dea[offset + i] = v
    return dif, dea


def calc_kdj(closes, highs, lows, n=9, m1=3, m2=3):
    """返回 (k, d)。"""
    rsv = stoch_rsv(closes, highs, lows, n)
    rsv_clean = [v for v in rsv if v is not None]
    k_clean = rma(rsv_clean, m1)
    # K 链上去掉 None 前缀后再递推算 D（K、D 都是 SMA 链，连续递推）
    k_valid = [v for v in k_clean if v is not None]
    d_valid = rma(k_valid, m2)
    k: List[Num] = [None] * len(closes)
    d: List[Num] = [None] * len(closes)
    rsv_offset = len(closes) - len(rsv_clean)
    for i, v in enumerate(k_clean):
        k[rsv_offset + i] = v
    k_offset = len(closes) - len(k_valid)
    for i, v in enumerate(d_valid):
        d[k_offset + i] = v
    return k, d


def calc_tdx_rsi(closes, period):
    """通达信 RSI = RMA(MAX(C-LC,0),N)/RMA(ABS(C-LC),N)*100。返回与 closes 等长。"""
    n = len(closes)
    up = [0.0]
    absc = [0.0]
    for i in range(1, n):
        ch = closes[i] - closes[i - 1]
        up.append(max(ch, 0.0))
        absc.append(abs(ch))
    rma_up = rma(up, period)
    rma_abs = rma(absc, period)
    out: List[Num] = [None] * n
    for i in range(n):
        if rma_up[i] is None or rma_abs[i] is None:
            continue
        out[i] = 100.0 if rma_abs[i] == 0 else rma_up[i] / rma_abs[i] * 100.0
    return out


def calc_tdx_rsi_ref(closes, period, ref):
    """与 calc_tdx_rsi 同，但用 REF(C, ref) 作为基准（隔 ref 日比较）。"""
    n = len(closes)
    up = [0.0] * n
    absc = [0.0] * n
    for i in range(n):
        if i < ref:
            continue
        ch = closes[i] - closes[i - ref]
        up[i] = max(ch, 0.0)
        absc[i] = abs(ch)
    rma_up = rma(up, period)
    rma_abs = rma(absc, period)
    out: List[Num] = [None] * n
    for i in range(n):
        if rma_up[i] is None or rma_abs[i] is None:
            continue
        out[i] = 100.0 if rma_abs[i] == 0 else rma_up[i] / rma_abs[i] * 100.0
    return out


# =============================================================================
# 背离检测
# =============================================================================
def _crossover(fast, slow):
    """fast 上穿 slow：今天 fast>slow 且 昨天 fast<=slow。返回 bool 列表。"""
    n = len(fast)
    out = [False] * n
    for i in range(1, n):
        if None in (fast[i], slow[i], fast[i - 1], slow[i - 1]):
            continue
        if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            out[i] = True
    return out


def _crossunder(fast, slow):
    n = len(fast)
    out = [False] * n
    for i in range(1, n):
        if None in (fast[i], slow[i], fast[i - 1], slow[i - 1]):
            continue
        if fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
            out[i] = True
    return out


def _bars_since_prev(cond, i):
    """BARSLAST(REF(cond,1))：从 i 往前（不含 i）最近一次 cond 为真的距离。"""
    for d in range(1, i + 1):
        if cond[i - d]:
            return d
    return None


def detect_bottom_divergence(closes, fast, slow):
    """
    底背离：fast 金叉 slow 时，价格创新低(REF(C,a+1)>C) 但指标未创新低(fast[a+1]<fast)。
    a = 上一次金叉距今天数。返回 bool 列表。
    """
    cross = _crossover(fast, slow)
    n = len(closes)
    out = [False] * n
    for i in range(n):
        if not cross[i]:
            continue
        a = _bars_since_prev(cross, i)
        if a is None:
            continue
        idx = i - (a + 1)
        if idx < 0 or fast[idx] is None or fast[i] is None:
            continue
        if closes[idx] > closes[i] and fast[idx] < fast[i]:
            out[i] = True
    return out


def detect_top_divergence(closes, fast, slow):
    """顶背离：fast 死叉 slow 时，价格创新高 但指标未创新高。"""
    cross = _crossunder(fast, slow)
    n = len(closes)
    out = [False] * n
    for i in range(n):
        if not cross[i]:
            continue
        a = _bars_since_prev(cross, i)
        if a is None:
            continue
        idx = i - (a + 1)
        if idx < 0 or fast[idx] is None or fast[i] is None:
            continue
        if closes[idx] < closes[i] and fast[idx] > fast[i]:
            out[i] = True
    return out


# =============================================================================
# 主入口：一次算出全部信号
# =============================================================================
def compute(closes, highs, lows):
    """
    输入三条等长序列（按时间正序），返回 dict，每个值都是与输入等长的列表：
      macd_bottom / macd_top / kdj_bottom / kdj_top / rsi_bottom / rsi_top : bool
      buy / sell : bool（超卖买点 / 超买卖点）
      triple_bottom : bool（三重底背离共振）
    """
    dif, dea = calc_macd(closes)
    k, d = calc_kdj(closes, highs, lows)
    rsi1 = calc_tdx_rsi(closes, 6)
    rsi2 = calc_tdx_rsi(closes, 12)

    macd_bottom = detect_bottom_divergence(closes, dif, dea)
    macd_top    = detect_top_divergence(closes, dif, dea)
    kdj_bottom  = detect_bottom_divergence(closes, k, d)
    kdj_top     = detect_top_divergence(closes, k, d)
    rsi_bottom  = detect_bottom_divergence(closes, rsi1, rsi2)
    rsi_top     = detect_top_divergence(closes, rsi1, rsi2)

    a02   = calc_tdx_rsi_ref(closes, 7, ref=2)
    var03 = calc_tdx_rsi_ref(closes, 7, ref=1)
    n = len(closes)
    buy = [False] * n
    sell = [False] * n
    for i in range(n):
        if a02[i] is not None and var03[i] is not None:
            buy[i] = a02[i] < 12 or var03[i] < 12
        if a02[i] is not None:
            sell[i] = a02[i] > 79

    triple_bottom = [
        macd_bottom[i] and kdj_bottom[i] and rsi_bottom[i] for i in range(n)
    ]

    return {
        "macd_bottom": macd_bottom, "macd_top": macd_top,
        "kdj_bottom": kdj_bottom, "kdj_top": kdj_top,
        "rsi_bottom": rsi_bottom, "rsi_top": rsi_top,
        "buy": buy, "sell": sell,
        "triple_bottom": triple_bottom,
        # 附带指标线，便于对数
        "dif": dif, "dea": dea, "k": k, "d": d,
        "rsi1": rsi1, "rsi2": rsi2, "a02": a02, "var03": var03,
    }
