"""
持仓管理模块
管理 SOXL 主仓位 + SMH 分流仓位 + 跨日止盈挂单
"""


class Portfolio:
    """管理 SOXL 主仓位和 SMH 分流仓位"""

    def __init__(self):
        self.soxl_shares = 0.0
        self.soxl_cost = 0.0

        self.smh_shares = 0.0
        self.smh_cost = 0.0

        self.realized_profit = 0.0
        self.total_diverted = 0.0

        self.pending_tp_orders = []

        # 交易统计
        self.buy_count = 0
        self.sell_count = 0
        self.tp_trigger_count = 0
        self.tp_expire_count = 0

    def buy_soxl(self, shares, price, fee_rate):
        """
        买入 SOXL

        Args:
            shares: 买入股数
            price: 成交价格
            fee_rate: 手续费率

        Returns:
            实际支出（含手续费）
        """
        if shares <= 0:
            return 0.0

        amount = price * shares
        cost = amount * (1 + fee_rate)

        self.soxl_shares += shares
        self.soxl_cost += cost
        self.buy_count += 1

        return cost

    def sell_soxl(self, pct, price, fee_rate):
        """
        按比例卖出 SOXL

        Args:
            pct: 卖出仓位比例 (0-1)
            price: 成交价格
            fee_rate: 手续费率

        Returns:
            (卖出收入净额, 利润)
            利润 = 卖出收入 - 对应成本
        """
        if self.soxl_shares <= 0 or pct <= 0:
            return 0.0, 0.0

        sell_shares = self.soxl_shares * pct
        gross = price * sell_shares
        net = gross * (1 - fee_rate)

        cost_basis = self.soxl_cost * pct
        profit = net - cost_basis

        self.soxl_shares -= sell_shares
        self.soxl_cost -= cost_basis
        self.realized_profit += profit
        self.sell_count += 1

        return net, profit

    def divert_to_smh(self, profit, smh_close_price, fee_rate, divert_ratio=0.50):
        """
        将止盈利润分流到 SMH

        Args:
            profit: 止盈利润
            smh_close_price: 当日 SMH 收盘价
            fee_rate: 手续费率
            divert_ratio: 分流比例（默认 50%）

        Returns:
            实际买入的 SMH 股数
        """
        if profit <= 0 or smh_close_price <= 0:
            return 0.0

        divert_amount = profit * divert_ratio
        smh_cost = divert_amount  # 用这笔钱买 SMH
        smh_shares = smh_cost / (smh_close_price * (1 + fee_rate))

        self.smh_shares += smh_shares
        self.smh_cost += smh_cost
        self.total_diverted += divert_amount

        return smh_shares

    def add_tp_order(self, trigger_price, sell_pct, created_day_index, ttl=5):
        """
        添加止盈限价挂单

        Args:
            trigger_price: 触发价格（当日最高价 >= 此价格时成交）
            sell_pct: 卖出仓位比例
            created_day_index: 创建时的交易日索引
            ttl: 有效期（交易日）
        """
        self.pending_tp_orders.append({
            'trigger_price': trigger_price,
            'sell_pct': sell_pct,
            'created_day_index': created_day_index,
            'ttl': ttl,
        })

    def check_tp_orders(self, high_price, current_day_index):
        """
        检查并处理止盈挂单

        Args:
            high_price: 当日最高价
            current_day_index: 当前交易日索引

        Returns:
            触发的止盈订单列表 [{'trigger_price': ..., 'sell_pct': ...}, ...]
        """
        triggered = []
        remaining = []

        for order in self.pending_tp_orders:
            days_alive = current_day_index - order['created_day_index']

            if high_price >= order['trigger_price']:
                triggered.append(order)
                self.tp_trigger_count += 1
            elif days_alive >= order['ttl']:
                self.tp_expire_count += 1
            else:
                remaining.append(order)

        self.pending_tp_orders = remaining
        return triggered

    def soxl_value(self, close):
        """SOXL 当前市值"""
        return self.soxl_shares * close

    def smh_value(self, smh_close):
        """SMH 当前市值"""
        return self.smh_shares * smh_close

    def total_value(self, soxl_close, smh_close):
        """总资产 = SOXL 市值 + SMH 市值"""
        return self.soxl_value(soxl_close) + self.smh_value(smh_close)

    @property
    def soxl_avg_cost(self):
        """SOXL 平均持仓成本"""
        if self.soxl_shares <= 0:
            return 0.0
        return self.soxl_cost / self.soxl_shares
