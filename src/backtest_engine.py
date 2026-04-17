"""
有状态回测引擎
支持历史数据访问、EMA 指标、持仓管理、止盈挂单、SMH 分流
"""
from src.indicators import calc_ema, calc_deviation
from src.portfolio import Portfolio
from src.metrics import calc_all_metrics, calc_daily_returns


class Context:
    """策略每日收到的上下文信息"""

    __slots__ = [
        'day', 'day_index', 'history', 'prev_close',
        'ema', 'consecutive_below_ema', 'consecutive_above_ema',
        'deviation', 'deviation_history', 'portfolio',
    ]

    def __init__(self):
        self.day = None
        self.day_index = 0
        self.history = []
        self.prev_close = 0.0
        self.ema = None
        self.consecutive_below_ema = 0
        self.consecutive_above_ema = 0
        self.deviation = 0.0
        self.deviation_history = []
        self.portfolio = None


class BacktestEngine:
    """
    有状态回测引擎

    Args:
        data: SOXL K 线数据列表
        smh_data: SMH K 线数据列表（用于分流买入和基准对比）
        fee_rate: 手续费率
        strategy: ComposableStrategy 实例
        ema_period: EMA 周期
    """

    def __init__(self, data, smh_data, fee_rate, strategy, ema_period=20):
        self.data = data
        self.smh_data = smh_data
        self.fee_rate = fee_rate
        self.strategy = strategy
        self.ema_period = ema_period

        self._smh_by_date = {d['date']: d for d in smh_data} if smh_data else {}

    def run(self):
        """
        执行回测

        Returns:
            包含所有评估指标和每日数据的字典
        """
        portfolio = Portfolio()

        closes = [d['close'] for d in self.data]
        ema_series = calc_ema(closes, self.ema_period)

        consecutive_below = 0
        consecutive_above = 0
        deviation_history = []

        dates = []
        daily_values = []
        daily_soxl_values = []
        daily_smh_values = []
        daily_dca_returns = []
        daily_hold_returns = []
        daily_smh_returns = []

        order_stats = {}
        limit_orders_placed = 0
        limit_orders_filled = 0

        first_close = self.data[0]['close']
        smh_first = self._smh_by_date.get(self.data[0]['date'])
        smh_first_close = smh_first['close'] if smh_first else None

        for i, day in enumerate(self.data):
            ema_val = ema_series[i]

            prev_close = self.data[i - 1]['close'] if i > 0 else day['close']

            if ema_val is not None:
                dev = calc_deviation(day['close'], ema_val)
                if prev_close < ema_val:
                    consecutive_below += 1
                    consecutive_above = 0
                else:
                    consecutive_above += 1
                    consecutive_below = 0
            else:
                dev = 0.0
                consecutive_below = 0
                consecutive_above = 0

            deviation_history.append(dev)

            ctx = Context()
            ctx.day = day
            ctx.day_index = i
            ctx.history = self.data[:i + 1]
            ctx.prev_close = prev_close
            ctx.ema = ema_val
            ctx.consecutive_below_ema = consecutive_below
            ctx.consecutive_above_ema = consecutive_above
            ctx.deviation = dev
            ctx.deviation_history = deviation_history[:]
            ctx.portfolio = portfolio

            # 1) 检查止盈挂单是否触发
            smh_day = self._smh_by_date.get(day['date'])
            triggered_tps = portfolio.check_tp_orders(day['high'], i)
            for tp in triggered_tps:
                _, profit = portfolio.sell_soxl(
                    tp['sell_pct'], tp['trigger_price'], self.fee_rate
                )
                if profit > 0 and smh_day:
                    portfolio.divert_to_smh(
                        profit, smh_day['close'], self.fee_rate
                    )

            # 2) 获取策略指令
            actions = self.strategy.on_day(ctx)

            # 3) 执行买入订单
            for price_ratio, shares in actions['buy_orders']:
                if shares <= 0:
                    continue

                target_price = day['open'] * price_ratio

                is_market = (price_ratio == 1.0)
                if not is_market:
                    limit_orders_placed += 1

                if is_market or day['low'] <= target_price:
                    cost = portfolio.buy_soxl(shares, target_price, self.fee_rate)

                    if not is_market:
                        limit_orders_filled += 1

                    if price_ratio not in order_stats:
                        order_stats[price_ratio] = {
                            'shares': 0.0, 'cost': 0.0, 'count': 0
                        }
                    order_stats[price_ratio]['shares'] += shares
                    order_stats[price_ratio]['cost'] += cost
                    order_stats[price_ratio]['count'] += 1

            # 4) 添加新的止盈挂单
            for tp_order in actions.get('tp_orders', []):
                portfolio.add_tp_order(
                    trigger_price=tp_order['trigger_price'],
                    sell_pct=tp_order['sell_pct'],
                    created_day_index=i,
                    ttl=tp_order.get('ttl', 5),
                )

            # 5) 记录当日数据
            smh_close = smh_day['close'] if smh_day else 0
            soxl_val = portfolio.soxl_value(day['close'])
            smh_val = portfolio.smh_value(smh_close)
            total_val = soxl_val + smh_val

            dates.append(day['date'])
            daily_values.append(total_val)
            daily_soxl_values.append(soxl_val)
            daily_smh_values.append(smh_val)

            total_invested = portfolio.soxl_cost + portfolio.total_diverted
            dca_ret = (total_val - total_invested) / total_invested if total_invested > 0 else 0
            daily_dca_returns.append(dca_ret)

            hold_ret = (day['close'] - first_close) / first_close
            daily_hold_returns.append(hold_ret)

            if smh_first_close and smh_day:
                smh_ret = (smh_day['close'] - smh_first_close) / smh_first_close
            else:
                smh_ret = 0
            daily_smh_returns.append(smh_ret)

        # 6) 计算评估指标
        total_invested = portfolio.soxl_cost + portfolio.total_diverted
        soxl_close_prices = [d['close'] for d in self.data]

        metrics = calc_all_metrics(
            daily_values=daily_values,
            total_cost=total_invested,
            total_shares=portfolio.soxl_shares,
            dates=dates,
            close_prices=soxl_close_prices,
        )

        # 补充 SMH 和交易统计
        smh_last = self._smh_by_date.get(self.data[-1]['date'])
        metrics.update({
            'soxl_shares': portfolio.soxl_shares,
            'soxl_cost': portfolio.soxl_cost,
            'soxl_final_value': daily_soxl_values[-1] if daily_soxl_values else 0,
            'smh_shares': portfolio.smh_shares,
            'smh_cost': portfolio.smh_cost,
            'smh_final_value': daily_smh_values[-1] if daily_smh_values else 0,
            'total_diverted': portfolio.total_diverted,
            'realized_profit': portfolio.realized_profit,
            'order_stats': order_stats,
            'limit_orders_placed': limit_orders_placed,
            'limit_orders_filled': limit_orders_filled,
            'limit_fill_rate': (limit_orders_filled / limit_orders_placed
                                if limit_orders_placed > 0 else 0),
            'buy_count': portfolio.buy_count,
            'sell_count': portfolio.sell_count,
            'tp_trigger_count': portfolio.tp_trigger_count,
            'tp_expire_count': portfolio.tp_expire_count,
            # 图表数据
            'dates': dates,
            'daily_values': daily_values,
            'daily_soxl_values': daily_soxl_values,
            'daily_smh_values': daily_smh_values,
            'daily_dca_returns': daily_dca_returns,
            'daily_hold_returns': daily_hold_returns,
            'daily_smh_returns': daily_smh_returns,
        })

        return metrics
