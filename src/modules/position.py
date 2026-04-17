"""
仓位分布模块
决定市价单和各档限价单的买入股数
"""


class FixedPyramid:
    """
    固定金字塔分布
    默认倒金字塔：市价单最多，越远档位越少
    """

    def __init__(self, market_shares=0.70, limit_shares=(0.40, 0.25, 0.15)):
        self.market_shares = market_shares
        self.limit_shares = limit_shares

    def get_shares(self, context):
        return self.market_shares, self.limit_shares

    def __repr__(self):
        return (f"FixedPyramid(market={self.market_shares}, "
                f"limits={self.limit_shares})")


class AdaptivePyramid:
    """
    自适应金字塔

    - 上涨趋势（昨收 >= EMA）：倒金字塔（近处多、远处少，尽早买入）
    - 下跌趋势（昨收 < EMA）：正金字塔（近处少、远处多，等更低价）
    """

    def __init__(self):
        self.up_market = 0.70
        self.up_limits = (0.40, 0.25, 0.15)
        self.down_market = 0.15
        self.down_limits = (0.25, 0.40, 0.70)

    def get_shares(self, context):
        if context.ema is None or context.prev_close >= context.ema:
            return self.up_market, self.up_limits
        else:
            return self.down_market, self.down_limits

    def __repr__(self):
        return "AdaptivePyramid()"


class DowntrendOnly:
    """
    仅下跌买入

    - 上涨趋势（昨收 >= EMA）：不买入
    - 下跌趋势（昨收 < EMA）：正金字塔
    """

    def __init__(self):
        self.market_shares = 0.15
        self.limit_shares = (0.25, 0.40, 0.70)

    def get_shares(self, context):
        if context.ema is not None and context.prev_close < context.ema:
            return self.market_shares, self.limit_shares
        else:
            return 0.0, (0.0, 0.0, 0.0)

    def __repr__(self):
        return "DowntrendOnly()"
