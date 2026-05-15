"""
DCA 多层次定投策略
实现每日交易逻辑：市价单 + 三层限价挂单
"""

# 默认订单配置：(价格系数, 买入股数)
DEFAULT_ORDERS = [
    (1.00, 0.70),   # 市价单：开盘价买入 0.7 股
    (0.98, 0.40),   # 限价单 A：跌 2% 买入 0.4 股
    (0.95, 0.25),   # 限价单 B：跌 5% 买入 0.25 股
    (0.90, 0.15),   # 限价单 C：跌 10% 买入 0.15 股
]


def execute_day(open_price, low_price, fee_rate=0.01, orders=None):
    """
    执行单日交易逻辑
    
    Args:
        open_price: 当日开盘价（作为挂单基准价格）
        low_price: 当日最低价（用于判断限价单是否成交）
        fee_rate: 手续费率，默认 1%
        orders: 订单配置列表 [(价格系数, 股数), ...]，默认使用 DEFAULT_ORDERS
    
    Returns:
        成交订单列表，每项包含 shares（股数）、price（成交价）、cost（实际支出含手续费）、price_ratio（价格系数）
    """
    if orders is None:
        orders = DEFAULT_ORDERS
    
    executed = []
    
    for price_ratio, shares in orders:
        # 跳过股数为 0 的订单
        if shares <= 0:
            continue
            
        target_price = open_price * price_ratio
        
        # 市价单（price_ratio=1.0）直接成交
        # 限价单需要最低价 <= 挂单价才成交
        if price_ratio == 1.0 or low_price <= target_price:
            amount = target_price * shares
            cost = amount * (1 + fee_rate)  # 手续费额外收取
            executed.append({
                'shares': shares,
                'price': target_price,
                'cost': cost,
                'price_ratio': price_ratio
            })
    
    return executed
