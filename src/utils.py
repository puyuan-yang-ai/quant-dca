"""
工具函数模块
"""


def calc_max_drawdown(values):
    """
    计算最大回撤
    
    Args:
        values: 每日市值列表
    
    Returns:
        最大回撤比例（0-1 之间的小数）
    """
    if not values:
        return 0.0
    
    max_drawdown = 0.0
    peak = values[0]
    
    for value in values:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)
    
    return max_drawdown


def calc_annualized_return(total_return, days):
    """
    计算年化收益率
    
    Args:
        total_return: 总收益率（小数形式，如 0.5 表示 50%）
        days: 投资天数
    
    Returns:
        年化收益率（小数形式）
    """
    if days <= 0:
        return 0.0
    
    # 公式：(1 + 总收益率) ^ (365 / 天数) - 1
    return (1 + total_return) ** (365 / days) - 1


def calc_sharpe_ratio(daily_values, annualized_return, risk_free_rate=0.0):
    """
    计算夏普比率
    
    Args:
        daily_values: 每日市值列表
        annualized_return: 年化收益率
        risk_free_rate: 无风险利率，默认 0
    
    Returns:
        夏普比率
    """
    if len(daily_values) < 2:
        return 0.0
    
    # 计算日收益率
    daily_returns = []
    for i in range(1, len(daily_values)):
        if daily_values[i - 1] > 0:
            daily_return = (daily_values[i] - daily_values[i - 1]) / daily_values[i - 1]
            daily_returns.append(daily_return)
    
    if not daily_returns:
        return 0.0
    
    # 计算标准差
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / len(daily_returns)
    std = variance ** 0.5
    
    # 年化波动率 = 日波动率 * sqrt(252)
    annualized_volatility = std * (252 ** 0.5)
    
    if annualized_volatility == 0:
        return 0.0
    
    return (annualized_return - risk_free_rate) / annualized_volatility

