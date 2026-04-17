"""
评估指标模块
计算 Sharpe、Sortino、Calmar、Max DD Duration 等专业量化指标
"""
from datetime import datetime
import math


def calc_daily_returns(daily_values):
    """
    从每日市值序列计算日收益率序列

    Args:
        daily_values: 每日市值列表

    Returns:
        日收益率列表（长度 = len(daily_values) - 1）
    """
    returns = []
    for i in range(1, len(daily_values)):
        if daily_values[i - 1] > 0:
            returns.append((daily_values[i] - daily_values[i - 1]) / daily_values[i - 1])
        else:
            returns.append(0.0)
    return returns


def calc_annualized_return(total_return, days):
    """
    计算年化收益率

    Args:
        total_return: 总收益率（小数形式）
        days: 自然日天数

    Returns:
        年化收益率
    """
    if days <= 0:
        return 0.0
    return (1 + total_return) ** (365.0 / days) - 1


def calc_max_drawdown(daily_values):
    """
    计算最大回撤

    Args:
        daily_values: 每日市值列表

    Returns:
        (max_drawdown, peak_idx, valley_idx)
        max_drawdown 为 0-1 之间的小数
    """
    if not daily_values:
        return 0.0, 0, 0

    max_dd = 0.0
    peak = daily_values[0]
    peak_idx = 0
    dd_peak_idx = 0
    dd_valley_idx = 0

    for i, value in enumerate(daily_values):
        if value > peak:
            peak = value
            peak_idx = i
        dd = (peak - value) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            dd_peak_idx = peak_idx
            dd_valley_idx = i

    return max_dd, dd_peak_idx, dd_valley_idx


def calc_max_drawdown_duration(daily_values):
    """
    计算最大回撤恢复天数（交易日）

    从任一峰值跌落后，到重新达到该峰值的最长天数。
    如果到回测结束仍未恢复，记录从峰值到回测结束的天数。

    Args:
        daily_values: 每日市值列表

    Returns:
        最大回撤持续天数（交易日）
    """
    if len(daily_values) < 2:
        return 0

    peak = daily_values[0]
    peak_idx = 0
    max_duration = 0

    for i, value in enumerate(daily_values):
        if value >= peak:
            duration = i - peak_idx
            max_duration = max(max_duration, duration)
            peak = value
            peak_idx = i

    # 如果到结束仍未恢复
    if daily_values[-1] < peak:
        duration = len(daily_values) - 1 - peak_idx
        max_duration = max(max_duration, duration)

    return max_duration


def calc_sharpe_ratio(daily_values, annualized_return, risk_free_rate=0.0):
    """
    计算夏普比率（适配 DCA 策略）

    DCA 策略每日有新资金注入，不能直接用日市值变化算收益率。
    采用业界通用做法：
    - 分子：用总投入/总回报计算的复合年化收益率
    - 分母：用日市值变化率的年化波动率

    Args:
        daily_values: 每日市值列表
        annualized_return: 复合年化收益率（从总投入回报计算）
        risk_free_rate: 年化无风险利率

    Returns:
        夏普比率
    """
    if len(daily_values) < 2:
        return 0.0

    daily_returns = []
    for i in range(1, len(daily_values)):
        if daily_values[i - 1] > 0:
            daily_returns.append(
                (daily_values[i] - daily_values[i - 1]) / daily_values[i - 1]
            )

    if not daily_returns:
        return 0.0

    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / len(daily_returns)
    std = math.sqrt(variance)
    annualized_vol = std * math.sqrt(252)

    if annualized_vol == 0:
        return 0.0

    return (annualized_return - risk_free_rate) / annualized_vol


def calc_sortino_ratio(daily_values, annualized_return, risk_free_rate=0.0):
    """
    计算 Sortino 比率（适配 DCA 策略）

    与 Sharpe 类似，但分母只用下行波动率。

    Args:
        daily_values: 每日市值列表
        annualized_return: 复合年化收益率
        risk_free_rate: 年化无风险利率

    Returns:
        Sortino 比率
    """
    if len(daily_values) < 2:
        return 0.0

    daily_returns = []
    for i in range(1, len(daily_values)):
        if daily_values[i - 1] > 0:
            daily_returns.append(
                (daily_values[i] - daily_values[i - 1]) / daily_values[i - 1]
            )

    if not daily_returns:
        return 0.0

    downside_returns = [r for r in daily_returns if r < 0]
    if not downside_returns:
        return float('inf') if annualized_return > risk_free_rate else 0.0

    downside_variance = sum(r ** 2 for r in downside_returns) / len(daily_returns)
    downside_std = math.sqrt(downside_variance)
    annualized_downside_vol = downside_std * math.sqrt(252)

    if annualized_downside_vol == 0:
        return 0.0

    return (annualized_return - risk_free_rate) / annualized_downside_vol


def calc_calmar_ratio(annualized_return, max_drawdown):
    """
    计算 Calmar 比率

    Calmar = 年化收益率 / 最大回撤

    Args:
        annualized_return: 年化收益率（小数形式）
        max_drawdown: 最大回撤（0-1 之间的小数）

    Returns:
        Calmar 比率，回撤为 0 时返回 0
    """
    if max_drawdown == 0:
        return 0.0
    return annualized_return / max_drawdown


def calc_cost_advantage(avg_cost, period_avg_price):
    """
    成本优势比

    正值表示平均成本低于市场均价（买得好）

    Args:
        avg_cost: 平均买入成本
        period_avg_price: 回测期间收盘价简单平均

    Returns:
        成本优势比 = (期间均价 - 平均成本) / 期间均价
    """
    if period_avg_price <= 0:
        return 0.0
    return (period_avg_price - avg_cost) / period_avg_price


def calc_all_metrics(daily_values, total_cost, total_shares, dates, close_prices):
    """
    一次性计算所有评估指标

    Args:
        daily_values: 每日总资产市值列表
        total_cost: 总投入成本
        total_shares: 总持股数
        dates: 日期列表 (YYYY-MM-DD 字符串)
        close_prices: 每日收盘价列表

    Returns:
        包含所有指标的字典
    """
    final_value = daily_values[-1] if daily_values else 0
    total_profit = final_value - total_cost
    total_return = total_profit / total_cost if total_cost > 0 else 0

    start_date = dates[0]
    end_date = dates[-1]
    calendar_days = (datetime.strptime(end_date, '%Y-%m-%d') -
                     datetime.strptime(start_date, '%Y-%m-%d')).days + 1

    ann_return = calc_annualized_return(total_return, calendar_days)
    max_dd, dd_peak_idx, dd_valley_idx = calc_max_drawdown(daily_values)
    max_dd_duration = calc_max_drawdown_duration(daily_values)
    sharpe = calc_sharpe_ratio(daily_values, ann_return)
    sortino = calc_sortino_ratio(daily_values, ann_return)
    calmar = calc_calmar_ratio(ann_return, max_dd)

    avg_cost = total_cost / total_shares if total_shares > 0 else 0
    period_avg_price = sum(close_prices) / len(close_prices) if close_prices else 0
    cost_adv = calc_cost_advantage(avg_cost, period_avg_price)

    return {
        'start_date': start_date,
        'end_date': end_date,
        'trading_days': len(dates),
        'calendar_days': calendar_days,
        'total_cost': total_cost,
        'total_shares': total_shares,
        'final_value': final_value,
        'total_profit': total_profit,
        'total_return': total_return,
        'annualized_return': ann_return,
        'max_drawdown': max_dd,
        'max_drawdown_peak_idx': dd_peak_idx,
        'max_drawdown_valley_idx': dd_valley_idx,
        'max_dd_duration': max_dd_duration,
        'sharpe_ratio': sharpe,
        'sortino_ratio': sortino,
        'calmar_ratio': calmar,
        'avg_cost': avg_cost,
        'period_avg_price': period_avg_price,
        'cost_advantage': cost_adv,
    }
