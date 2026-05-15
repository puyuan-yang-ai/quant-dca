"""
回测引擎模块
执行策略并计算各项评估指标
"""
from datetime import datetime
from src.utils import calc_max_drawdown, calc_annualized_return, calc_sharpe_ratio


def run_backtest(data, fee_rate=0.01, orders=None, execute_day=None):
    """
    执行回测
    
    Args:
        data: 历史数据列表（由 data_loader 加载）
        fee_rate: 手续费率，默认 1%
        orders: 订单配置列表 [(价格系数, 股数), ...]
    
    Returns:
        包含所有评估指标的字典
    """
    if not data:
        return None
    
    # 跟踪状态
    total_shares = 0.0
    total_cost = 0.0
    daily_values = []
    
    # 按 price_ratio 分类统计
    order_stats = {}
    
    # 用于图表的每日数据
    dates = []
    daily_dca_returns = []
    daily_hold_returns = []
    
    first_close = data[0]['close']
    max_drawdown_idx = 0
    max_drawdown_value = 0.0
    peak = 0.0
    
    # 遍历每个交易日
    for i, day in enumerate(data):
        # 执行当日策略
        day_orders = execute_day(day['open'], day['low'], fee_rate, orders)
        
        # 累计成交
        for order in day_orders:
            total_shares += order['shares']
            total_cost += order['cost']
            
            # 按 price_ratio 分类统计
            ratio = order['price_ratio']
            if ratio not in order_stats:
                order_stats[ratio] = {'shares': 0, 'cost': 0, 'count': 0}
            order_stats[ratio]['shares'] += order['shares']
            order_stats[ratio]['cost'] += order['cost']
            order_stats[ratio]['count'] += 1
        
        # 记录当日市值
        daily_value = day['close'] * total_shares
        daily_values.append(daily_value)
        
        # 记录日期
        dates.append(day['date'])
        
        # DCA 策略收益率
        dca_return = (daily_value - total_cost) / total_cost if total_cost > 0 else 0
        daily_dca_returns.append(dca_return)
        
        # SOXL 持有收益率
        hold_return = (day['close'] - first_close) / first_close
        daily_hold_returns.append(hold_return)
        
        # 跟踪最大回撤点
        if daily_value > peak:
            peak = daily_value
        drawdown = (peak - daily_value) / peak if peak > 0 else 0
        if drawdown > max_drawdown_value:
            max_drawdown_value = drawdown
            max_drawdown_idx = i
    
    # 计算评估指标
    final_value = daily_values[-1]
    total_profit = final_value - total_cost
    total_return = total_profit / total_cost if total_cost > 0 else 0
    
    start_date = data[0]['date']
    end_date = data[-1]['date']
    days = (datetime.strptime(end_date, '%Y-%m-%d') - 
            datetime.strptime(start_date, '%Y-%m-%d')).days + 1
    
    annualized_return = calc_annualized_return(total_return, days)
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'trading_days': len(data),
        'total_cost': total_cost,
        'total_shares': total_shares,
        'final_value': final_value,
        'total_profit': total_profit,
        'total_return': total_return,
        'annualized_return': annualized_return,
        'max_drawdown': max_drawdown_value,
        'sharpe_ratio': calc_sharpe_ratio(daily_values, annualized_return),
        'avg_cost': total_cost / total_shares if total_shares > 0 else 0,
        'order_stats': order_stats,
        # 图表数据
        'dates': dates,
        'daily_dca_returns': daily_dca_returns,
        'daily_hold_returns': daily_hold_returns,
        'max_drawdown_idx': max_drawdown_idx,
    }
