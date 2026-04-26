"""
入场条件模块
决定每日是否执行市价买入和/或挂限价单
"""
from src.rsi_signals import calc_rsi_v2_signals


def _extract_buy_dates(data):
    """从 K 线数据中预计算 RSI v2 买入信号日期集合"""
    result = calc_rsi_v2_signals(data)
    buy_dates = set()
    for i, sigs in enumerate(result['signals']):
        for sig in sigs:
            if sig['type'].startswith('B'):
                buy_dates.add(data[i]['date'])
    return buy_dates


class UnconditionalEntry:
    """无条件每日买入：市价单 + 限价单"""

    def should_market_buy(self, context):
        return True

    def should_place_limits(self, context):
        return True

    def __repr__(self):
        return "UnconditionalEntry()"


class EMAFilterEntry:
    """
    EMA 均线过滤

    - 昨收 < EMA → 下跌趋势 → 市价买入 + 限价单（全量买入）
    - 昨收 >= EMA → 上涨趋势 → 仅挂限价单（不追涨，但回调可接）
    """

    def should_market_buy(self, context):
        if context.ema is None:
            return True
        return context.prev_close < context.ema

    def should_place_limits(self, context):
        return True

    def __repr__(self):
        return "EMAFilterEntry()"


class NDayConfirmEntry:
    """
    连续 N 天确认

    连续 N 天收盘价 < EMA 才开始买入（市价 + 限价），否则不买。
    N 值越大，信号越可靠但可能错过机会。
    """

    def __init__(self, n_days=3):
        self.n_days = n_days

    def should_market_buy(self, context):
        return context.consecutive_below_ema >= self.n_days

    def should_place_limits(self, context):
        return context.consecutive_below_ema >= self.n_days

    def __repr__(self):
        return f"NDayConfirmEntry(n={self.n_days})"


class RSISignalEntry:
    """
    RSI v2 信号驱动入场

    当天有 B/B+/B++ 信号时市价买入，无信号不买。
    构造时需传入完整 K 线数据以预计算信号。
    """

    def __init__(self, data):
        self._buy_dates = _extract_buy_dates(data)

    def should_market_buy(self, context):
        return context.day['date'] in self._buy_dates

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"RSISignalEntry(signals={len(self._buy_dates)})"


class CombinedAndEntry:
    """
    NDayConfirm AND RSI：双重确认

    连续 N 天低于 EMA 且 RSI 触发买入信号时才买入。
    趋势确认 + 动量超卖同时满足，过滤最严格。
    """

    def __init__(self, data, n_days=5):
        self.n_days = n_days
        self._buy_dates = _extract_buy_dates(data)

    def should_market_buy(self, context):
        nday_ok = context.consecutive_below_ema >= self.n_days
        rsi_ok = context.day['date'] in self._buy_dates
        return nday_ok and rsi_ok

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"CombinedAndEntry(n={self.n_days}, rsi_signals={len(self._buy_dates)})"


class CombinedOrEntry:
    """
    NDayConfirm OR RSI：双通道

    连续 N 天低于 EMA 或 RSI 触发买入信号，任一条件满足即买入。
    覆盖面最广，互补两种信号的盲区。
    """

    def __init__(self, data, n_days=5):
        self.n_days = n_days
        self._buy_dates = _extract_buy_dates(data)

    def should_market_buy(self, context):
        nday_ok = context.consecutive_below_ema >= self.n_days
        rsi_ok = context.day['date'] in self._buy_dates
        return nday_ok or rsi_ok

    def should_place_limits(self, context):
        return False

    def __repr__(self):
        return f"CombinedOrEntry(n={self.n_days}, rsi_signals={len(self._buy_dates)})"
