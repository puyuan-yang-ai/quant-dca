"""
止盈策略模块
决定何时挂出止盈限价卖单
"""
from src.indicators import calc_max_abs_change


class NoTakeProfit:
    """不止盈"""

    def check(self, context):
        return None

    def __repr__(self):
        return "NoTakeProfit()"


class DeviationPeakTP:
    """
    偏离度峰值止盈

    当偏离度连续下降 2 天（动量衰竭信号）时：
    - 确认前日为偏离度峰值
    - 止盈价 = 峰值日收盘价 × (1 + 7日最大|涨跌幅|)
    - 卖出 50% 仓位
    """

    def __init__(self, sell_pct=0.50, lookback_change=7, tp_ttl=5):
        self.sell_pct = sell_pct
        self.lookback_change = lookback_change
        self.tp_ttl = tp_ttl

    def check(self, context):
        devs = context.deviation_history
        if len(devs) < 3:
            return None

        # 偏离度连续下降 2 天：dev[-1] < dev[-2] < dev[-3]
        if not (devs[-1] < devs[-2] < devs[-3]):
            return None

        # 峰值在 devs[-3] 对应的那天（即 2 天前）
        # 只在偏离度为正（价格在均线上方）时触发
        if devs[-3] <= 0:
            return None

        # 峰值日的收盘价：history[-3] 对应 devs[-3]
        if len(context.history) < 3:
            return None
        peak_close = context.history[-3]['close']

        max_change = calc_max_abs_change(context.history, self.lookback_change)
        trigger_price = peak_close * (1 + max_change)

        return {
            'trigger_price': trigger_price,
            'sell_pct': self.sell_pct,
            'ttl': self.tp_ttl,
            'signal': 'deviation_peak',
        }

    def __repr__(self):
        return f"DeviationPeakTP(sell={self.sell_pct})"


class TrendConfirmTP:
    """
    趋势确认止盈

    连续 N 天收盘价 > EMA 时：
    - 止盈价 = 第 N 天收盘价 × (1 + 7日最大|涨跌幅|)
    - 卖出 25% 仓位
    """

    def __init__(self, n_days=3, sell_pct=0.25, lookback_change=7, tp_ttl=5):
        self.n_days = n_days
        self.sell_pct = sell_pct
        self.lookback_change = lookback_change
        self.tp_ttl = tp_ttl

    def check(self, context):
        if context.consecutive_above_ema < self.n_days:
            return None

        # 恰好达到 N 天时才触发（避免每天重复触发）
        if context.consecutive_above_ema != self.n_days:
            return None

        if context.portfolio.soxl_shares <= 0:
            return None

        current_close = context.day['close']
        max_change = calc_max_abs_change(context.history, self.lookback_change)
        trigger_price = current_close * (1 + max_change)

        return {
            'trigger_price': trigger_price,
            'sell_pct': self.sell_pct,
            'ttl': self.tp_ttl,
            'signal': 'trend_confirm',
        }

    def __repr__(self):
        return f"TrendConfirmTP(n={self.n_days}, sell={self.sell_pct})"


class DualTakeProfit:
    """
    双层止盈（同时启用偏离度峰值 + 趋势确认）
    两个信号独立触发，各自挂各自的止盈单
    """

    def __init__(self, deviation_tp=None, trend_tp=None):
        self.deviation_tp = deviation_tp or DeviationPeakTP()
        self.trend_tp = trend_tp or TrendConfirmTP()

    def check(self, context):
        results = []
        dev_result = self.deviation_tp.check(context)
        if dev_result:
            results.append(dev_result)
        trend_result = self.trend_tp.check(context)
        if trend_result:
            results.append(trend_result)
        return results if results else None

    def __repr__(self):
        return f"DualTakeProfit({self.deviation_tp}, {self.trend_tp})"
