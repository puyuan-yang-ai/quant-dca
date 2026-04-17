"""
组合策略
将 4 个模块（档口/入场/仓位/止盈）组合成完整策略
"""


class ComposableStrategy:
    """
    可组合策略：由 4 个独立模块组装而成

    每日决策流程：
    1. 档口模块 → 三档价格偏移
    2. 入场模块 → 是否市价买入？是否挂限价单？
    3. 仓位模块 → 各档买入股数
    4. 止盈模块 → 是否触发止盈信号？
    """

    def __init__(self, tiers, entry, position, take_profit):
        self.tiers = tiers
        self.entry = entry
        self.position = position
        self.take_profit = take_profit

    def on_day(self, context):
        """
        生成当日交易指令

        Args:
            context: Context 对象，包含当日数据、历史、指标、持仓等

        Returns:
            {
                'buy_orders': [(price_ratio, shares), ...],
                'tp_orders': [{'trigger_price', 'sell_pct', 'ttl', 'signal'}, ...] | None
            }
        """
        tier1, tier2, tier3 = self.tiers.get_tiers(context)

        do_market = self.entry.should_market_buy(context)
        do_limits = self.entry.should_place_limits(context)

        market_shares, limit_shares = self.position.get_shares(context)

        buy_orders = []
        if do_market and market_shares > 0:
            buy_orders.append((1.0, market_shares))
        if do_limits:
            if limit_shares[0] > 0:
                buy_orders.append((1.0 - tier1, limit_shares[0]))
            if limit_shares[1] > 0:
                buy_orders.append((1.0 - tier2, limit_shares[1]))
            if limit_shares[2] > 0:
                buy_orders.append((1.0 - tier3, limit_shares[2]))

        tp_result = self.take_profit.check(context)
        if tp_result is None:
            tp_orders = []
        elif isinstance(tp_result, list):
            tp_orders = tp_result
        else:
            tp_orders = [tp_result]

        return {
            'buy_orders': buy_orders,
            'tp_orders': tp_orders,
        }

    def __repr__(self):
        return (f"ComposableStrategy(\n"
                f"  tiers={self.tiers},\n"
                f"  entry={self.entry},\n"
                f"  position={self.position},\n"
                f"  take_profit={self.take_profit}\n"
                f")")
