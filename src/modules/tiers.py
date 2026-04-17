"""
档口设置模块
决定限价挂单的价格层级（距开盘价的跌幅百分比）
"""
from src.indicators import calc_volatility_tiers

FALLBACK_DROPS = (0.02, 0.05, 0.10)


class FixedTiers:
    """固定比例档口"""

    def __init__(self, drops=(0.02, 0.05, 0.10)):
        self.drops = drops

    def get_tiers(self, context):
        return self.drops

    def __repr__(self):
        pcts = tuple(round(d * 100, 1) for d in self.drops)
        return f"FixedTiers({pcts}%)"


class VolatilityTiers:
    """
    波动率动态档口

    基于最近 N 个交易日的日跌幅分布，自适应调整三档位置：
    - 一档：30th 分位数（常规波动，高频成交）
    - 二档：60th 分位数（中等波动，中频成交）
    - 三档：最大跌幅 × 90%（极端波动，低频成交）
    """

    def __init__(self, lookback=14, percentiles=(30, 60), max_scale=0.90):
        self.lookback = lookback
        self.percentiles = percentiles
        self.max_scale = max_scale

    def get_tiers(self, context):
        result = calc_volatility_tiers(
            context.history,
            lookback=self.lookback,
            percentiles=self.percentiles,
            max_scale=self.max_scale,
        )
        if result is None:
            return FALLBACK_DROPS
        return result

    def __repr__(self):
        return (f"VolatilityTiers(lookback={self.lookback}, "
                f"pct={self.percentiles}, scale={self.max_scale})")
